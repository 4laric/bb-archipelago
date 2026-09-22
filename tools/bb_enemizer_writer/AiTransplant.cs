using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using SoulsFormats;

internal static class AiTransplant
{
    static readonly JsonSerializerOptions Json = new() {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true, WriteIndented = true,
    };
    static string Leaf(string name) => name.Replace('\\', '/').Split('/')[^1];
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static string GoalKey(LUAINFO.Goal goal) => $"{goal.ID}:{goal.Name}";
    static string GoalState(LUAINFO.Goal goal) => JsonSerializer.Serialize(goal, Json);
    static bool Exports(Script script, LUAINFO.Goal goal) =>
        script.Symbols.Writes.Contains(goal.Name) || script.Symbols.Writes.Contains(goal.Name + "_Activate");

    sealed record Script(string Archive, BinderFile File, LuaSymbols Symbols)
    {
        public string Name => Leaf(File.Name);
    }

    sealed class Archive
    {
        public string Name { get; }
        public BND4 Binder { get; }
        public BinderFile InfoFile { get; }
        public BinderFile GlobalsFile { get; }
        public LUAINFO Info { get; }
        public LUAGNL Globals { get; }
        public List<Script> Scripts { get; }

        public Archive(string path)
        {
            Name = Path.GetFileName(path);
            Binder = BND4.Read(path);
            InfoFile = Binder.Files.Single(f => f.Name.EndsWith(".luainfo", StringComparison.Ordinal));
            GlobalsFile = Binder.Files.Single(f => f.Name.EndsWith(".luagnl", StringComparison.Ordinal));
            Info = LUAINFO.Read(InfoFile.Bytes);
            Globals = LUAGNL.Read(GlobalsFile.Bytes);
            if (Binder.Files.Select(f => Leaf(f.Name)).Distinct().Count() != Binder.Files.Count
                || Binder.Files.Select(f => f.ID).Distinct().Count() != Binder.Files.Count)
                throw new InvalidDataException($"{Name}: duplicate binder names or IDs");
            Scripts = Binder.Files.Where(f => f.Name.EndsWith(".lua", StringComparison.Ordinal))
                .Select(f => new Script(Name, f, Lua50.Read(f.Bytes))).ToList();
        }
    }

    sealed record Requirement(int Id, bool Logic);
    sealed record NoAiExemption(string Role, string SourceMap, string SourcePart, int SourceEntityId,
        string DestinationMap, string DestinationPart, int DestinationEntityId,
        int ThinkParamId, string PartSha256, string? AnchorSha256);
    sealed record Prepared(Archive Archive, Dictionary<string, byte[]> Originals, List<Script> Added,
        List<Requirement> Required, int MissingBefore, int GlobalsAdded, int GoalsAdded);

    static void Need(bool value, string message)
    {
        if (!value) throw new InvalidDataException(message);
    }

    static string BareMap(string value)
    {
        string map = value;
        if (map.EndsWith(".msb.dcx", StringComparison.OrdinalIgnoreCase)) map = map[..^8];
        else if (map.EndsWith(".msb", StringComparison.OrdinalIgnoreCase)) map = map[..^4];
        return map;
    }

    static string Text(JsonElement value, string property, string context)
    {
        if (value.ValueKind != JsonValueKind.Object || !value.TryGetProperty(property, out var item)
            || item.ValueKind != JsonValueKind.String || string.IsNullOrWhiteSpace(item.GetString()))
            throw new InvalidDataException($"{context} requires {property}");
        return item.GetString()!;
    }

    static int Integer(JsonElement value, string property, string context)
    {
        if (value.ValueKind != JsonValueKind.Object || !value.TryGetProperty(property, out var item)
            || item.ValueKind != JsonValueKind.Number || !item.TryGetInt32(out int result))
            throw new InvalidDataException($"{context} requires integer {property}");
        return result;
    }

    static JsonElement Object(JsonElement value, string property, string context)
    {
        if (value.ValueKind != JsonValueKind.Object || !value.TryGetProperty(property, out var item)
            || item.ValueKind != JsonValueKind.Object)
            throw new InvalidDataException($"{context} requires {property}");
        return item;
    }

    static string Pin(JsonElement provenance, string property, string context)
    {
        string hash = Text(provenance, property, context);
        Need(hash.Length == 64 && hash.All(c => c is >= '0' and <= '9' or >= 'a' and <= 'f'),
            $"{context} requires lowercase SHA256 {property}");
        return hash;
    }

    static void RequireInitialization(JsonElement row, string context)
    {
        var initialization = Object(row, "source_initialization", context);
        foreach (string field in new[] { "talk_id", "unk_t18", "init_anim_id", "damage_anim_id" })
            _ = Integer(initialization, field, context + " source initialization");
    }

    static void RequireArchetype(JsonElement archetype, Archetype expected, string context)
    {
        Need(Text(archetype, "model_name", context) == expected.ModelName
            && Integer(archetype, "npc_param_id", context) == expected.NpcParamId
            && Integer(archetype, "think_param_id", context) == expected.ThinkParamId
            && Integer(archetype, "chara_init_id", context) == expected.CharaInitId,
            $"{context} source archetype does not match logical swap");
    }

    static Archetype ArchetypeFrom(JsonElement value, string context) => new(
        Text(value, "model_name", context), Integer(value, "npc_param_id", context),
        Integer(value, "think_param_id", context), Integer(value, "chara_init_id", context));

    static (string Map, string Part) PhysicalDestination(string key)
    {
        int split = key.IndexOf(':');
        Need(split > 0 && split < key.Length - 1, $"invalid destination key {key}");
        string map = BareMap(key[..split]), part = key[(split + 1)..];
        Need(Regex.IsMatch(map, @"^m\d{2}_\d{2}_\d{2}_\d{2}$") && !string.IsNullOrWhiteSpace(part),
            $"invalid destination key {key}");
        return (map, part);
    }

    static List<NoAiExemption> RequirePrimaryNoAiEvidence(
        JsonElement root, Swap swap, JsonElement swapJson)
    {
        Need(root.TryGetProperty("boss_actor_initializations", out var node)
            && node.ValueKind == JsonValueKind.Array,
            "boss ThinkParam 0 primary requires source-pinned boss_actor_initializations");
        JsonElement sourceArchetype = swapJson.TryGetProperty("unscaled_target", out var unscaled)
            && unscaled.ValueKind == JsonValueKind.Object ? unscaled : swapJson.GetProperty("target");
        Archetype expected = ArchetypeFrom(sourceArchetype, "boss ThinkParam 0 logical source");
        Need(expected.ThinkParamId == 0, "boss ThinkParam 0 logical source changed during preparation");
        var result = new List<NoAiExemption>();
        foreach (string destinationKey in swap.DestinationKeys)
        {
            var destination = PhysicalDestination(destinationKey);
            var matches = node.EnumerateArray().Where(row =>
                BareMap(Text(row, "destination_map", "boss primary initialization")) == destination.Map
                && Text(row, "destination_part", "boss primary initialization") == destination.Part).ToList();
            Need(matches.Count == 1,
                "boss ThinkParam 0 primary requires one source-pinned boss_actor_initialization for every physical destination");
            JsonElement row = matches[0];
            string context = $"boss ThinkParam 0 primary {destination.Map}:{destination.Part}";
            RequireArchetype(Object(row, "source_archetype", context), expected, context);
            RequireInitialization(row, context);
            var provenance = Object(row, "source_provenance", context);
            Need(Text(provenance, "format", context) == "bb-boss-actor-pin-v1",
                $"{context} has unsupported provenance format");
            string partPin = Pin(provenance, "part_sha256", context);
            string sourceMap = BareMap(Text(row, "source_map", context));
            Need(Regex.IsMatch(sourceMap, @"^m\d{2}_\d{2}_\d{2}_\d{2}$"), $"{context} has invalid source map");
            int sourceEntity = Integer(row, "source_entity_id", context);
            int destinationEntity = Integer(row, "destination_entity_id", context);
            Need(sourceEntity > 0 && destinationEntity > 0, $"{context} has invalid actor identity");
            result.Add(new("primary", sourceMap, Text(row, "source_part", context), sourceEntity,
                destination.Map, destination.Part, destinationEntity, 0, partPin, null));
        }
        return result;
    }

    static NoAiExemption RequireHelperNoAiEvidence(JsonElement addition)
    {
        string context = "boss ThinkParam 0 helper";
        var archetype = Object(addition, "source_archetype", context);
        Need(Integer(archetype, "think_param_id", context) == 0
            && !string.IsNullOrWhiteSpace(Text(archetype, "model_name", context))
            && Integer(archetype, "npc_param_id", context) > 0
            && Integer(archetype, "chara_init_id", context) >= 0,
            $"{context} requires a complete source archetype pin");
        RequireInitialization(addition, context);
        var provenance = Object(addition, "source_provenance", context);
        Need(Text(provenance, "format", context) == "bb-boss-actor-pin-v1",
            $"{context} has unsupported provenance format");
        string partPin = Pin(provenance, "part_sha256", context);
        string anchorPin = Pin(provenance, "anchor_sha256", context);
        string sourceMap = BareMap(Text(addition, "source_map", context));
        string destinationMap = BareMap(Text(addition, "destination_map", context));
        Need(Regex.IsMatch(sourceMap, @"^m\d{2}_\d{2}_\d{2}_\d{2}$")
            && Regex.IsMatch(destinationMap, @"^m\d{2}_\d{2}_\d{2}_\d{2}$"),
            $"{context} has invalid map identity");
        int sourceEntity = Integer(addition, "source_entity_id", context);
        int destinationEntity = Integer(addition, "destination_entity_id", context);
        Need(sourceEntity > 0 && destinationEntity > 0, $"{context} has invalid actor identity");
        _ = Text(addition, "source_anchor_part", context);
        _ = Text(addition, "destination_anchor_part", context);
        return new("helper", sourceMap, Text(addition, "source_part", context), sourceEntity,
            destinationMap, Text(addition, "destination_part", context), destinationEntity,
            0, partPin, anchorPin);
    }

    public static int Run(string planPath, string gamePath, string defsPath,
        string scriptRoot, string output, bool apply, bool bossPrepared = false)
    {
        var manifest = JsonSerializer.Deserialize<Manifest>(File.ReadAllText(planPath), Json)
            ?? throw new InvalidDataException("empty enemizer plan");
        if (manifest.Format != "bb-enemizer-plan-v2" || !manifest.DryRun || manifest.Swaps.Count == 0)
            throw new InvalidDataException("expected a non-empty bb-enemizer-plan-v2 manifest");
        using var planDocument = JsonDocument.Parse(File.ReadAllText(planPath));
        JsonElement planRoot = planDocument.RootElement;
        if (!bossPrepared && planRoot.TryGetProperty("boss_actor_scaling", out _))
            throw new InvalidDataException("boss actor scaling requires --boss-encounters and reviewed map evidence");
        string inputRoot = Path.GetFullPath(scriptRoot);
        string outputPath = Path.GetFullPath(output);
        // Outputs are a new standalone directory, never any part of the input tree.
        string relativeOutput = Path.GetRelativePath(inputRoot, outputPath);
        if (!relativeOutput.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal)
            && !Path.IsPathRooted(relativeOutput))
            throw new InvalidDataException("AI output must be outside the script input directory");
        if (File.Exists(outputPath) || Directory.Exists(outputPath))
            throw new IOException($"AI output already exists: {outputPath}");
        if (apply && File.Exists(outputPath + ".json"))
            throw new IOException($"AI report already exists: {outputPath}.json");

        var archives = Directory.GetFiles(inputRoot, "*.luabnd.dcx")
            .Where(p => Path.GetFileName(p) == "aicommon.luabnd.dcx"
                || Regex.IsMatch(Path.GetFileName(p), @"^m\d{2}_\d{2}_\d{2}_\d{2}\.luabnd\.dcx$"))
            .Order(StringComparer.Ordinal).Select(p => new Archive(p)).ToDictionary(a => a.Name);
        if (!archives.TryGetValue("aicommon.luabnd.dcx", out Archive? common))
            throw new InvalidDataException("missing aicommon.luabnd.dcx");
        var allScripts = archives.Values.SelectMany(a => a.Scripts).ToList();
        var providers = allScripts.SelectMany(s => s.Symbols.Definitions.Select(g => (g, s)))
            .GroupBy(p => p.g).ToDictionary(g => g.Key, g => g.Select(p => p.s).ToList());
        var goalProviders = archives.Values.SelectMany(a => a.Info.Goals.Select(g => (a, g)))
            .GroupBy(p => "GOAL_" + p.g.Name).ToDictionary(g => g.Key, g => g.ToList());
        var game = BND4.Read(gamePath);
        var think = PARAM.Read(game.Files.Single(f => Leaf(f.Name) == "NpcThinkParam.param").Bytes);
        var definitions = BND4.Read(defsPath).Files.Select(f => PARAMDEF.Read(f.Bytes));
        think.ApplyParamdef(definitions.Single(d => d.ParamType == think.ParamType));
        var thinkRows = think.Rows.GroupBy(r => r.ID).ToDictionary(g => g.Key, g => g.ToList());
        var requirements = new SortedDictionary<string, HashSet<Requirement>>(StringComparer.Ordinal);
        var thinkRequirements = new SortedDictionary<int, List<Requirement>>();
        var noAiExemptions = new List<NoAiExemption>();
        var swapJsonByKey = planRoot.GetProperty("swaps").EnumerateArray()
            .ToDictionary(row => Text(row, "logical_key", "logical swap"), StringComparer.Ordinal);
        foreach (var swap in manifest.Swaps)
        {
            if (swap.Target.ThinkParamId == 0)
            {
                if (!bossPrepared) throw new InvalidDataException("missing NpcThinkParam 0");
                Need(swapJsonByKey.TryGetValue(swap.LogicalKey, out var swapJson),
                    $"missing logical swap evidence {swap.LogicalKey}");
                noAiExemptions.AddRange(RequirePrimaryNoAiEvidence(planRoot, swap, swapJson));
                continue;
            }
            if (!thinkRows.TryGetValue(swap.Target.ThinkParamId, out var rows))
                throw new InvalidDataException($"missing NpcThinkParam {swap.Target.ThinkParamId}");
            var row = rows[0];
            var goals = new List<Requirement>();
            foreach (string field in new[] { "logicId", "battleGoalID", "goalID_ToCaution", "goalID_ToFind", "goalID_ToInterest" })
            {
                var ids = rows.Select(r => Convert.ToInt32(r.Cells.Single(c => c.Def.InternalName == field).Value))
                    .Distinct().ToList();
                if (ids.Count != 1)
                    throw new InvalidDataException($"ambiguous NpcThinkParam {row.ID} field {field}");
                int id = ids[0];
                if (id > 0) goals.Add(new Requirement(id, field == "logicId"));
            }
            if (goals.Count == 0) throw new InvalidDataException($"NpcThinkParam {row.ID} has no AI goals");
            thinkRequirements[row.ID] = goals.Distinct().OrderBy(g => g.Id).ThenBy(g => g.Logic).ToList();
            foreach (string destination in swap.DestinationKeys)
            {
                string map = destination.Split(':')[0].Split('.')[0];
                if (!Regex.IsMatch(map, @"^m\d{2}_\d{2}_\d{2}_\d{2}$"))
                    throw new InvalidDataException($"invalid destination map {destination}");
                // Alternate MSB world states load the area's canonical Lua binder.
                string name = map[..^2] + "00.luabnd.dcx";
                if (!requirements.TryGetValue(name, out var set)) requirements[name] = set = [];
                set.UnionWith(goals);
            }
        }
        // Multi-actor encounter additions are not logical swaps. They still
        // need their donor ThinkParam goals in the destination area's binder.
        if (planRoot.TryGetProperty("boss_actor_additions", out var additions))
        {
            if (additions.ValueKind != JsonValueKind.Array) throw new InvalidDataException("invalid boss_actor_additions");
            foreach (var addition in additions.EnumerateArray())
            {
                int thinkId = addition.GetProperty("source_archetype").GetProperty("think_param_id").GetInt32();
                string map = addition.GetProperty("destination_map").GetString() ?? throw new InvalidDataException("actor addition has no destination map");
                if (thinkId == 0)
                {
                    if (!bossPrepared) throw new InvalidDataException("missing NpcThinkParam 0");
                    noAiExemptions.Add(RequireHelperNoAiEvidence(addition));
                    continue;
                }
                if (!thinkRows.TryGetValue(thinkId, out var rows)) throw new InvalidDataException($"missing NpcThinkParam {thinkId}");
                var goals = new List<Requirement>();
                foreach (string field in new[] { "logicId", "battleGoalID", "goalID_ToCaution", "goalID_ToFind", "goalID_ToInterest" })
                {
                    var ids = rows.Select(r => Convert.ToInt32(r.Cells.Single(c => c.Def.InternalName == field).Value)).Distinct().ToList();
                    if (ids.Count != 1) throw new InvalidDataException($"ambiguous NpcThinkParam {thinkId} field {field}");
                    if (ids[0] > 0) goals.Add(new Requirement(ids[0], field == "logicId"));
                }
                if (goals.Count == 0) throw new InvalidDataException($"NpcThinkParam {thinkId} has no AI goals");
                thinkRequirements[thinkId] = goals.Distinct().OrderBy(g => g.Id).ThenBy(g => g.Logic).ToList();
                string bare = map.Split('.')[0];
                if (!Regex.IsMatch(bare, @"^m\d{2}_\d{2}_\d{2}_\d{2}$")) throw new InvalidDataException($"invalid actor destination map {map}");
                string binder = bare[..^2] + "00.luabnd.dcx";
                if (!requirements.TryGetValue(binder, out var set)) requirements[binder] = set = [];
                set.UnionWith(goals);
            }
        }
        var prepared = new List<Prepared>();
        foreach (var (name, needed) in requirements)
        {
            if (!archives.TryGetValue(name, out Archive? destination))
                throw new InvalidDataException($"missing destination AI binder {name}");
            // Re-read to keep the global donor index immutable across destinations.
            destination = new Archive(Path.Combine(inputRoot, name));
            var originals = destination.Binder.Files.ToDictionary(f => Leaf(f.Name), f => (byte[])f.Bytes.Clone());
            var existing = destination.Scripts.Concat(common.Scripts).ToList();
            var available = existing.SelectMany(s => s.Symbols.Definitions).ToHashSet(StringComparer.Ordinal);
            var selected = new Dictionary<string, Script>(StringComparer.Ordinal);
            var pending = new Queue<Script>();
            var inspected = new HashSet<(string Archive, string Name)>();
            var registrations = destination.Info.Goals.ToDictionary(GoalKey, GoalState);
            int globalsBefore = destination.Globals.Globals.Count, goalsBefore = destination.Info.Goals.Count;

            void Add(Script script)
            {
                var current = existing.Concat(selected.Values).FirstOrDefault(s => s.Name == script.Name);
                if (current != null)
                {
                    if (!current.File.Bytes.SequenceEqual(script.File.Bytes))
                        throw new InvalidDataException($"{name}: conflicting AI script {script.Name}");
                }
                else
                {
                    selected.Add(script.Name, script);
                    available.UnionWith(script.Symbols.Definitions);
                }
                // Identical chunks can already exist without their metadata or
                // helper closure. Reuse bytes, but still repair registrations
                // and inspect the original donor context exactly once.
                if (inspected.Add((script.Archive, script.Name))) pending.Enqueue(script);
                var donor = archives[script.Archive];
                foreach (var goal in donor.Info.Goals.Where(g => Exports(script, g)))
                {
                    string key = GoalKey(goal), state = GoalState(goal);
                    if (registrations.TryGetValue(key, out string? old))
                    {
                        if (old != state) throw new InvalidDataException($"{name}: conflicting goal {key}");
                    }
                    else { destination.Info.Goals.Add(goal); registrations.Add(key, state); }
                }
                // Preserve authored registration order, and only register symbols
                // exported by the actual imported chunks (not an entire donor map).
                var globals = destination.Globals.Globals.ToHashSet(StringComparer.Ordinal);
                foreach (string global in donor.Globals.Globals)
                    if (script.Symbols.Writes.Contains(global) && globals.Add(global))
                        destination.Globals.Globals.Add(global);
            }

            Script Choose(IEnumerable<Script> candidates, string label)
            {
                var choices = candidates.OrderBy(s => s.Archive, StringComparer.Ordinal)
                    .ThenBy(s => s.Name, StringComparer.Ordinal).ToList();
                if (choices.Count == 0) throw new InvalidDataException($"{name}: no script for {label}");
                if (choices.Select(s => Hash(s.File.Bytes)).Distinct().Count() != 1)
                    throw new InvalidDataException($"{name}: ambiguous script versions for {label}");
                return choices[0];
            }

            bool Satisfied(Requirement requirement) => HasGoal(destination, common, requirement);
            int missing = needed.Count(r => !Satisfied(r));
            foreach (var requirement in needed.OrderBy(r => r.Id).ThenBy(r => r.Logic))
            {
                string file = $"{requirement.Id:D6}_{(requirement.Logic ? "logic" : "battle")}.lua";
                if (Satisfied(requirement))
                {
                    // Audit retained map goals too. Byte-identical original
                    // copies supply donor context for a missing helper.
                    var retained = destination.Scripts.FirstOrDefault(s => s.Name == file);
                    if (retained != null)
                        foreach (var context in allScripts.Where(s => s.Name == file
                            && s.File.Bytes.SequenceEqual(retained.File.Bytes))) Add(context);
                    continue;
                }
                // Require the matching registration as well as the filename. A
                // Think row ID is NOT a Lua goal ID; both are read from the param.
                Add(Choose(allScripts.Where(s => s.Name == file
                    && archives[s.Archive].Info.Goals.Any(g => g.ID == requirement.Id && Exports(s, g))), file));
            }
            while (pending.TryDequeue(out Script? script))
            {
                foreach (string global in script.Symbols.Reads.Order(StringComparer.Ordinal))
                {
                    if (goalProviders.TryGetValue(global, out var goalChoices))
                    {
                        // Shared engine goals can be registration-only. A map
                        // subgoal needs its chunk, even if metadata is present.
                        if (!common.Info.Goals.Any(g => "GOAL_" + g.Name == global))
                        {
                            var candidates = goalChoices.SelectMany(p => p.a.Scripts.Where(s => Exports(s, p.g))).ToList();
                            var registered = destination.Info.Goals.Where(g => "GOAL_" + g.Name == global).ToList();
                            var retained = existing.Concat(selected.Values)
                                .Where(s => registered.Any(g => Exports(s, g))).ToList();
                            if (retained.Count == 0) Add(Choose(candidates, global));
                            else foreach (var context in candidates.Where(p => retained.Any(s => s.Name == p.Name
                                && s.File.Bytes.SequenceEqual(p.File.Bytes)))) Add(context);
                        }
                    }
                    if (!providers.TryGetValue(global, out var choices)) continue;
                    var local = choices.Where(s => s.Archive == script.Archive).ToList();
                    // Runtime scratch globals can be read before assignment in
                    // vanilla scripts. Only import a provider from the donor's
                    // actual load context; similarly named variables elsewhere
                    // are not evidence of a dependency.
                    if (local.Count > 0)
                    {
                        var active = existing.Concat(selected.Values)
                            .Where(s => s.Symbols.Definitions.Contains(global)).ToList();
                        // A matching name alone does not prove the donor's
                        // helper is installed. Refuse a same-file version
                        // conflict; other chunks may legitimately share globals.
                        if (local.Any(provider => active.Any(s => s.Name == provider.Name
                            && !s.File.Bytes.SequenceEqual(provider.File.Bytes))))
                            throw new InvalidDataException($"{name}: conflicting AI helper {global}");
                        if (!available.Contains(global)) Add(Choose(local, global));
                        else foreach (var provider in local.Where(p => active.Any(s => s.File.Bytes.SequenceEqual(p.File.Bytes))))
                            Add(provider);
                    }
                }
            }
            var usedIds = destination.Binder.Files.Select(f => f.ID).ToHashSet();
            // Observed in original CUSA03173 01.09 common/map AI binders:
            // Lua chunks occupy IDs >= 1000, metadata starts at 1000000.
            // Do not allocate in the unrelated event-script range below 1000.
            // Continue after authored scripts, preserving their ordering/IDs.
            int nextId = Math.Max(1000, checked(destination.Scripts
                .Select(s => s.File.ID).DefaultIfEmpty(999).Max() + 1));
            foreach (var script in selected.Values)
            {
                while (usedIds.Contains(nextId)) nextId++;
                if (nextId >= 1000000)
                    throw new InvalidDataException($"{name}: no free AI script ID below metadata range");
                var file = new BinderFile(script.File.Flags, nextId, script.File.Name, script.File.Bytes) {
                    CompressionType = script.File.CompressionType,
                };
                usedIds.Add(nextId++);
                // Keep metadata last, as in the authored binders.
                int index = destination.Binder.Files.FindIndex(f => f == destination.GlobalsFile || f == destination.InfoFile);
                destination.Binder.Files.Insert(index, file);
                destination.Scripts.Add(new Script(name, file, script.Symbols));
            }
            foreach (var requirement in needed)
                if (!Satisfied(requirement))
                    throw new InvalidDataException($"{name}: unsatisfied {(requirement.Logic ? "logic" : "battle")} goal {requirement.Id}");
            destination.InfoFile.Bytes = destination.Info.Write();
            destination.GlobalsFile.Bytes = destination.Globals.Write();
            prepared.Add(new Prepared(destination, originals, selected.Values.ToList(), needed.ToList(), missing,
                destination.Globals.Globals.Count - globalsBefore, destination.Info.Goals.Count - goalsBefore));
        }

        // All maps, goals, bytecode headers and conflicts pass before any output.
        if (apply)
        {
            Directory.CreateDirectory(outputPath);
            foreach (var item in prepared)
            {
                string path = Path.Combine(outputPath, item.Archive.Name);
                item.Archive.Binder.Write(path);
                Verify(item, new Archive(path), common);
            }
        }
        var report = new {
            format = "bb-enemizer-ai-v1", applied = apply,
            plan_sha256 = Hash(File.ReadAllBytes(planPath)),
            gameparam_sha256 = Hash(File.ReadAllBytes(gamePath)),
            paramdef_sha256 = Hash(File.ReadAllBytes(defsPath)),
            think_parameters = thinkRequirements.Select(pair => new {think_param_id = pair.Key, goals = pair.Value}),
            no_ai_exemptions = noAiExemptions.OrderBy(row => row.Role, StringComparer.Ordinal)
                .ThenBy(row => row.DestinationMap, StringComparer.Ordinal)
                .ThenBy(row => row.DestinationPart, StringComparer.Ordinal),
            sources = archives.Keys.Order().ToDictionary(n => n, n => Hash(File.ReadAllBytes(Path.Combine(inputRoot, n)))),
            maps = prepared.Select(p => new {
                map = p.Archive.Name, missing_goals_before = p.MissingBefore, missing_goals_after = 0,
                goals_added = p.GoalsAdded, globals_added = p.GlobalsAdded,
                required_goals = p.Required.OrderBy(g => g.Id).ThenBy(g => g.Logic),
                scripts_added = p.Added.Select(s => new {file = s.Name, source = s.Archive, sha256 = Hash(s.File.Bytes)}),
                output_sha256 = apply ? Hash(File.ReadAllBytes(Path.Combine(outputPath, p.Archive.Name))) : null,
            }),
        };
        string reportPath = apply ? outputPath + ".json" : outputPath;
        Directory.CreateDirectory(Path.GetDirectoryName(reportPath)!);
        File.WriteAllText(reportPath, JsonSerializer.Serialize(report, Json) + "\n");
        Console.WriteLine($"AI maps={prepared.Count} missing_goals_before={prepared.Sum(p => p.MissingBefore)} "
            + $"scripts_added={prepared.Sum(p => p.Added.Count)} missing_goals_after=0 applied={apply} report={reportPath}");
        return 0;
    }

    static bool HasGoal(Archive destination, Archive common, Requirement requirement)
    {
        string file = $"{requirement.Id:D6}_{(requirement.Logic ? "logic" : "battle")}.lua";
        // Common engine goals have descriptive filenames. Shared registrations
        // are the authority for those; map-specific goals need their actual chunk.
        if (common.Info.Goals.Any(g => g.ID == requirement.Id
            && (requirement.Logic ? g.Name.EndsWith("_Logic") : !g.Name.EndsWith("_Logic")))) return true;
        return destination.Scripts.Any(s => s.Name == file && destination.Info.Goals.Any(g =>
            g.ID == requirement.Id && Exports(s, g)));
    }

    static void Verify(Prepared expected, Archive actual, Archive common)
    {
        var wanted = expected.Archive.Binder;
        if (actual.Binder.Files.Count != wanted.Files.Count)
            throw new InvalidDataException($"{actual.Name}: AI binder file count changed");
        for (int i = 0; i < wanted.Files.Count; i++)
        {
            var a = actual.Binder.Files[i]; var b = wanted.Files[i];
            if (a.ID != b.ID || a.Name != b.Name || a.Flags != b.Flags || !a.Bytes.SequenceEqual(b.Bytes))
                throw new InvalidDataException($"{actual.Name}: persisted AI file differs: {b.Name}");
        }
        foreach (var (name, bytes) in expected.Originals)
            if (!name.EndsWith(".luainfo") && !name.EndsWith(".luagnl")
                && !actual.Binder.Files.Single(f => Leaf(f.Name) == name).Bytes.SequenceEqual(bytes))
                throw new InvalidDataException($"{actual.Name}: changed original AI script {name}");
        if (!actual.Info.Goals.Select(GoalState).SequenceEqual(expected.Archive.Info.Goals.Select(GoalState))
            || !actual.Globals.Globals.SequenceEqual(expected.Archive.Globals.Globals)
            || expected.Required.Any(r => !HasGoal(actual, common, r)))
            throw new InvalidDataException($"{actual.Name}: persisted AI registration verification failed");
    }
}
