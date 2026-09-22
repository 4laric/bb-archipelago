using System.Numerics;
using System.Text.Json;
using SoulsFormats;

// Adds only explicitly witnessed actors.  There is deliberately no native ID
// allocator: every output name and entity ID is reviewed in the plan.
internal static class BossActorTransplant
{
    static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower, PropertyNameCaseInsensitive = true };
    internal sealed record Addition(string SourceMap, string SourcePart, string SourceAnchorPart, int SourceEntityId,
        Archetype SourceArchetype, string DestinationMap, string DestinationAnchorPart, string DestinationPart, int DestinationEntityId);
    static void Need(bool value, string why) { if (!value) throw new InvalidDataException(why); }
    static string Bare(string map) => map.EndsWith(".msb.dcx", StringComparison.OrdinalIgnoreCase) ? map[..^8]
        : map.EndsWith(".msb", StringComparison.OrdinalIgnoreCase) ? map[..^4] : map;
    static string Resolve(string root, string map) {
        Need(Path.GetFileName(map) == map && Bare(map).StartsWith("m", StringComparison.Ordinal), "invalid actor map name");
        string bare = Bare(map);
        foreach (string ext in new[] { ".msb.dcx", ".msb" }) { string path = Path.Combine(root, bare + ext); if (File.Exists(path)) return path; }
        throw new FileNotFoundException("no MSBB for actor addition " + map);
    }
    static IEnumerable<MSBB.Part> Parts(MSBB map) => map.Parts.GetEntries();
    static MSBB.Part Part(MSBB map, string name, string role) {
        var rows = Parts(map).Where(p => p.Name == name).ToList();
        Need(rows.Count == 1, $"missing or ambiguous {role} Part {name}"); return rows[0];
    }
    static void RequireArchetype(MSBB.Part.Enemy part, Addition add) => Need(part.EntityID == add.SourceEntityId
        && part.ModelName == add.SourceArchetype.ModelName && part.NPCParamID == add.SourceArchetype.NpcParamId
        && part.ThinkParamID == add.SourceArchetype.ThinkParamId && part.CharaInitID == add.SourceArchetype.CharaInitId,
        $"{add.SourceMap}:{add.SourcePart}: donor provenance drift");
    static void RequireUnique(IEnumerable<Addition> additions) {
        Need(additions.Select(a => (Bare(a.DestinationMap), a.DestinationPart)).Distinct().Count() == additions.Count(), "duplicate actor destination Part");
        Need(additions.Select(a => (Bare(a.DestinationMap), a.DestinationEntityId)).Distinct().Count() == additions.Count(), "duplicate actor destination entity ID");
    }
    static Vector3 Rotate(Vector3 offset, float yaw) => Vector3.TransformNormal(offset, Matrix4x4.CreateRotationY(yaw));

    internal static List<Addition> Read(string planPath, bool required) {
        using var doc = JsonDocument.Parse(File.ReadAllText(planPath));
        if (!doc.RootElement.TryGetProperty("boss_actor_additions", out var node)) {
            Need(!required, "missing boss_actor_additions"); return [];
        }
        var additions = node.Deserialize<List<Addition>>(Json) ?? throw new InvalidDataException("invalid boss_actor_additions");
        Need(additions.Count > 0, "boss_actor_additions must not be empty"); RequireUnique(additions); return additions;
    }

    // sourceMaps always remains original. destinationMaps is the original map
    // corpus, while outputMaps can already contain MapTransplant's primary edits.
    internal static int Apply(string planPath, string sourceMaps, string destinationMaps, string outputMaps, bool required) {
        var additions = Read(planPath, required);
        if (additions.Count == 0) return 0;
        var sources = new Dictionary<string, MSBB>(StringComparer.Ordinal);
        var targets = new Dictionary<string, (MSBB Map, string Output, HashSet<string> OriginalNames, HashSet<int> OriginalIds, Dictionary<string, PartState> OriginalEnemies)>(StringComparer.Ordinal);
        MSBB Source(string map) { string key = Bare(map); if (!sources.TryGetValue(key, out var value)) sources[key] = value = MSBB.Read(Resolve(sourceMaps, key)); return value; }
        (MSBB Map, string Output, HashSet<string> OriginalNames, HashSet<int> OriginalIds, Dictionary<string, PartState> OriginalEnemies) Target(string map) {
            string key = Bare(map); if (targets.TryGetValue(key, out var value)) return value;
            string original = Resolve(destinationMaps, key), output = Path.Combine(outputMaps, Path.GetFileName(original));
            var loaded = File.Exists(output) ? MSBB.Read(output) : MSBB.Read(original);
            value = (loaded, output, Parts(loaded).Select(p => p.Name).ToHashSet(), Parts(loaded).Select(p => p.EntityID).ToHashSet(),
                Parts(loaded).OfType<MSBB.Part.EnemyBase>().ToDictionary(p => p.Name, PartState.Capture)); targets[key] = value; return value;
        }
        foreach (var add in additions) {
            Need(add.SourceEntityId > 0 && add.DestinationEntityId > 0 && !string.IsNullOrWhiteSpace(add.DestinationPart), "invalid actor identity");
            var donorMap = Source(add.SourceMap);
            var donor = Part(donorMap, add.SourcePart, "donor") as MSBB.Part.Enemy;
            Need(donor != null, "actor donor must be an ordinary Enemy, not a dummy or another Part type"); RequireArchetype(donor!, add);
            var donorAnchor = Part(donorMap, add.SourceAnchorPart, "donor anchor");
            var target = Target(add.DestinationMap);
            var destinationAnchor = Part(target.Map, add.DestinationAnchorPart, "destination anchor") as MSBB.Part.Enemy;
            Need(destinationAnchor != null, "destination actor anchor must be an ordinary Enemy");
            Need(!Parts(target.Map).Any(p => p.Name == add.DestinationPart), "actor destination Part already exists");
            Need(!Parts(target.Map).Any(p => p.EntityID == add.DestinationEntityId), "actor destination entity ID already exists");
            // Clone the destination anchor to preserve its collision, groups,
            // move points and all map-local loading state; only combat identity
            // is imported from the independently verified donor.
            var spawned = (MSBB.Part.Enemy)destinationAnchor!.DeepCopy();
            float yaw = destinationAnchor!.Rotation.Y - donorAnchor.Rotation.Y;
            spawned.Name = add.DestinationPart; spawned.EntityID = add.DestinationEntityId;
            spawned.Position = destinationAnchor.Position + Rotate(donor!.Position - donorAnchor.Position, yaw);
            spawned.Rotation = donor.Rotation + new Vector3(0, yaw, 0);
            spawned.ModelName = donor.ModelName; spawned.NPCParamID = donor.NPCParamID;
            spawned.ThinkParamID = donor.ThinkParamID; spawned.CharaInitID = donor.CharaInitID;
            if (!target.Map.Models.Enemies.Any(model => model.Name == donor.ModelName)) target.Map.Models.Enemies.Add(new MSBB.Model.Enemy { Name = donor.ModelName, SibPath = "" });
            target.Map.Parts.Enemies.Add(spawned);
        }
        foreach (var (map, output, names, ids, originals) in targets.Values) {
            Directory.CreateDirectory(Path.GetDirectoryName(output)!); map.Write(output);
            var check = MSBB.Read(output);
            Need(names.All(name => Parts(check).Any(p => p.Name == name)) && ids.All(id => Parts(check).Any(p => p.EntityID == id)), "actor round-trip lost an original Part");
            foreach (var (name, state) in originals) {
                var part = Parts(check).OfType<MSBB.Part.EnemyBase>().SingleOrDefault(p => p.Name == name);
                Need(part != null, "actor round-trip lost an original Enemy");
                Need(state.Archetype == new Archetype(part!.ModelName, part.NPCParamID, part.ThinkParamID, part.CharaInitID), "actor round-trip changed an original Enemy archetype");
                state.Invariant.RequireSame(Path.GetFileName(output), part);
            }
        }
        return additions.Count;
    }
}
