using System.Numerics;
using System.Text.Json;
using SoulsFormats;

if (args.Length != 4 || args[3] != "--apply")
{
    Console.Error.WriteLine(
        "usage: BBEnemizerWriter <manifest.json> <MapStudio-input> <output-root> --apply");
    Console.Error.WriteLine("Refuses to write without the explicit --apply argument.");
    return 2;
}

string manifestPath = Path.GetFullPath(args[0]);
string inputRoot = Path.GetFullPath(args[1]);
string outputRoot = Path.GetFullPath(args[2]);
if (StringComparer.OrdinalIgnoreCase.Equals(inputRoot.TrimEnd(Path.DirectorySeparatorChar),
        outputRoot.TrimEnd(Path.DirectorySeparatorChar)))
{
    Console.Error.WriteLine("input and output roots must differ");
    return 2;
}

var jsonOptions = new JsonSerializerOptions {
    PropertyNameCaseInsensitive = true,
    PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
};
Manifest manifest = JsonSerializer.Deserialize<Manifest>(File.ReadAllText(manifestPath), jsonOptions)
    ?? throw new InvalidDataException("manifest is empty");
if (manifest.Format != "bb-enemizer-plan-v2" || !manifest.DryRun)
    throw new InvalidDataException("expected a dry-run bb-enemizer-plan-v2 manifest");

var changesByMap = new Dictionary<string, List<Change>>(StringComparer.Ordinal);
foreach (Swap swap in manifest.Swaps)
{
    foreach (string destination in swap.DestinationKeys)
    {
        int split = destination.IndexOf(':');
        if (split <= 0 || split == destination.Length - 1)
            throw new InvalidDataException($"invalid destination key {destination}");
        string map = destination[..split];
        string part = destination[(split + 1)..];
        if (!swap.DestinationSources.TryGetValue(destination, out Archetype? physicalSource))
            throw new InvalidDataException($"{destination}: missing physical source provenance");
        changesByMap.GetOrAdd(map).Add(new Change(part, physicalSource, swap.Target));
    }
}

// Transactional preflight: resolve, parse, and source-check every requested
// map before creating the output root or writing the first file.
var loadedMaps = new Dictionary<string, (
    string Input,
    MSBB Msb,
    Dictionary<string, PartState> OriginalStates,
    HashSet<string> OriginalModels)>(StringComparer.Ordinal);
foreach ((string map, List<Change> changes) in changesByMap.OrderBy(entry => entry.Key))
{
    string input = ResolveMap(inputRoot, map);
    MSBB msb = MSBB.Read(input);
    var parts = PartsByName(msb);
    var originalStates = parts.ToDictionary(
        entry => entry.Key, entry => PartState.Capture(entry.Value), StringComparer.Ordinal);
    var originalModels = msb.Models.Enemies.Select(model => model.Name).ToHashSet(StringComparer.Ordinal);
    foreach (Change change in changes)
    {
        if (!parts.TryGetValue(change.PartName, out MSBB.Part.EnemyBase? part))
            throw new InvalidDataException($"{map}: missing Part {change.PartName}");
        RequireSource(map, part, change.Source);
    }
    loadedMaps.Add(map, (input, msb, originalStates, originalModels));
}

Directory.CreateDirectory(outputRoot);
int mapsWritten = 0, partsWritten = 0, modelsAdded = 0;
foreach ((string map, List<Change> changes) in changesByMap.OrderBy(entry => entry.Key))
{
    (string input, MSBB msb, Dictionary<string, PartState> originalStates,
        HashSet<string> originalModels) = loadedMaps[map];
    string output = Path.Combine(outputRoot, Path.GetFileName(input));
    var parts = PartsByName(msb);

    foreach (Change change in changes)
    {
        MSBB.Part.EnemyBase part = parts[change.PartName];
        PartInvariant before = PartInvariant.Capture(part);
        if (!msb.Models.Enemies.Any(model => model.Name == change.Target.ModelName))
        {
            msb.Models.Enemies.Add(new MSBB.Model.Enemy {
                Name = change.Target.ModelName,
                SibPath = ""
            });
            modelsAdded++;
        }
        part.ModelName = change.Target.ModelName;
        part.NPCParamID = change.Target.NpcParamId;
        part.ThinkParamID = change.Target.ThinkParamId;
        part.CharaInitID = change.Target.CharaInitId;
        before.RequireUnchanged(map, part);
        partsWritten++;
    }

    msb.Write(output);
    VerifyRoundTrip(output, changes, originalStates, originalModels);
    mapsWritten++;
}

Console.WriteLine(
    $"maps={mapsWritten} parts={partsWritten} models_added={modelsAdded} output={outputRoot}");
return 0;

static string ResolveMap(string root, string map)
{
    // Miner-derived plan keys retain the ".msb" extension because
    // Path.GetFileNameWithoutExtension strips only ".dcx"; accept bare map
    // ids and the miner-suffixed form alike.
    string bare = map;
    if (bare.EndsWith(".msb.dcx", StringComparison.OrdinalIgnoreCase))
        bare = bare[..^".msb.dcx".Length];
    else if (bare.EndsWith(".msb", StringComparison.OrdinalIgnoreCase))
        bare = bare[..^".msb".Length];
    string compressed = Path.Combine(root, bare + ".msb.dcx");
    if (File.Exists(compressed)) return compressed;
    string plain = Path.Combine(root, bare + ".msb");
    if (File.Exists(plain)) return plain;
    throw new FileNotFoundException($"no MSBB for {map} under {root} (tried {compressed}, {plain})");
}

static Dictionary<string, MSBB.Part.EnemyBase> PartsByName(MSBB msb) =>
    msb.Parts.Enemies.Cast<MSBB.Part.EnemyBase>()
        .Concat(msb.Parts.DummyEnemies)
        .ToDictionary(part => part.Name, StringComparer.Ordinal);

static void RequireSource(string map, MSBB.Part.EnemyBase part, Archetype expected)
{
    if (part.ModelName != expected.ModelName || part.NPCParamID != expected.NpcParamId
        || part.ThinkParamID != expected.ThinkParamId || part.CharaInitID != expected.CharaInitId)
    {
        throw new InvalidDataException(
            $"{map}:{part.Name}: source drift; manifest expects "
            + $"{expected.ModelName}/{expected.NpcParamId}/{expected.ThinkParamId}/{expected.CharaInitId}, "
            + $"file has {part.ModelName}/{part.NPCParamID}/{part.ThinkParamID}/{part.CharaInitID}");
    }
}

static void VerifyRoundTrip(
    string path,
    List<Change> changes,
    Dictionary<string, PartState> originals,
    HashSet<string> originalModels)
{
    MSBB check = MSBB.Read(path);
    var parts = check.Parts.Enemies.Cast<MSBB.Part.EnemyBase>()
        .Concat(check.Parts.DummyEnemies)
        .ToDictionary(part => part.Name, StringComparer.Ordinal);
    if (!parts.Keys.ToHashSet(StringComparer.Ordinal).SetEquals(originals.Keys))
        throw new InvalidDataException($"round-trip Part set changed: {path}");
    var changesByPart = changes.ToDictionary(change => change.PartName, StringComparer.Ordinal);
    foreach ((string name, MSBB.Part.EnemyBase part) in parts)
    {
        PartState before = originals[name];
        before.Invariant.RequireSame(path, part);
        Archetype target = changesByPart.TryGetValue(name, out Change? change)
            ? change.Target : before.Archetype;
        if (part.ModelName != target.ModelName || part.NPCParamID != target.NpcParamId
            || part.ThinkParamID != target.ThinkParamId || part.CharaInitID != target.CharaInitId)
            throw new InvalidDataException($"round-trip verification failed: {path}:{part.Name}");
    }
    var outputModels = check.Models.Enemies.Select(model => model.Name).ToHashSet(StringComparer.Ordinal);
    if (!originalModels.IsSubsetOf(outputModels))
        throw new InvalidDataException($"round-trip removed an original enemy model: {path}");
}

sealed record Manifest(string Format, bool DryRun, List<Swap> Swaps);
sealed record Swap(
    string LogicalKey,
    List<string> DestinationKeys,
    Dictionary<string, Archetype> DestinationSources,
    Archetype Source,
    Archetype Target);
sealed record Archetype(string ModelName, int NpcParamId, int ThinkParamId, int CharaInitId);
sealed record Change(string PartName, Archetype Source, Archetype Target);
sealed record PartState(Archetype Archetype, PartInvariant Invariant)
{
    public static PartState Capture(MSBB.Part.EnemyBase part) => new(
        new Archetype(part.ModelName, part.NPCParamID, part.ThinkParamID, part.CharaInitID),
        PartInvariant.Capture(part));
}

sealed record PartInvariant(
    string Name, string Description, int InstanceId, string SibPath,
    Vector3 Position, Vector3 Rotation, Vector3 Scale,
    uint[] DrawGroups, uint[] DispGroups, uint[] BackreadGroups,
    int EntityId, byte UnkE04, byte UnkE05, byte UnkE06, byte UnkE07,
    byte LanternId, byte LodParamId, byte UnkE0E, byte UnkE0F,
    int TalkId, int UnkT18, string CollisionName, short UnkT20,
    string[] MovePointNames, int InitAnimId, int DamageAnimId)
{
    public static PartInvariant Capture(MSBB.Part.EnemyBase part) => new(
        part.Name, part.Description, part.InstanceID, part.SibPath,
        part.Position, part.Rotation, part.Scale,
        (uint[])part.DrawGroups.Clone(), (uint[])part.DispGroups.Clone(),
        (uint[])part.BackreadGroups.Clone(), part.EntityID,
        part.UnkE04, part.UnkE05, part.UnkE06, part.UnkE07,
        part.LanternID, part.LodParamID, part.UnkE0E, part.UnkE0F,
        part.TalkID, part.UnkT18, part.CollisionName, part.UnkT20,
        (string[])part.MovePointNames.Clone(), part.InitAnimID, part.DamageAnimID);

    public void RequireUnchanged(string map, MSBB.Part.EnemyBase part)
    {
        PartInvariant after = Capture(part);
        bool same = this with { DrawGroups = [], DispGroups = [], BackreadGroups = [], MovePointNames = [] }
            == after with { DrawGroups = [], DispGroups = [], BackreadGroups = [], MovePointNames = [] };
        same &= DrawGroups.SequenceEqual(after.DrawGroups)
            && DispGroups.SequenceEqual(after.DispGroups)
            && BackreadGroups.SequenceEqual(after.BackreadGroups)
            && MovePointNames.SequenceEqual(after.MovePointNames);
        if (!same)
            throw new InvalidDataException($"{map}:{part.Name}: writer changed a protected Part field");
    }

    public void RequireSame(string map, MSBB.Part.EnemyBase part) => RequireUnchanged(map, part);
}

static class DictionaryExtensions
{
    public static List<TValue> GetOrAdd<TKey, TValue>(
        this Dictionary<TKey, List<TValue>> dictionary, TKey key) where TKey : notnull
    {
        if (!dictionary.TryGetValue(key, out List<TValue>? values))
        {
            values = [];
            dictionary.Add(key, values);
        }
        return values;
    }
}
