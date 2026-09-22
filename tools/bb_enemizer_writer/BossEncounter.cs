using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using SoulsFormats;

// Native application of reviewed, compiler-produced encounter edits.  The
// manifest is evidence for one or more exact event replacements; it is never
// an event recipe and it cannot add, remove, or reorder original events.
internal static class BossEncounter
{
    static readonly JsonSerializerOptions Json = new() {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true, WriteIndented = true,
    };

    internal sealed record Manifest(string Format, List<Encounter> Encounters);
    internal sealed record TerminalPredicate(long EventId, int OriginalActor, long BridgeEventId);
    internal sealed record Encounter(
        string DestinationEventFile,
        string OriginalEventSha256,
        List<long> ChangedEventIds,
        Dictionary<long, string> CompiledEventFingerprints,
        List<long> ProtectedCompletionEventIds,
        List<long>? AddedEventIds = null,
        List<TerminalPredicate>? TerminalPredicates = null);

    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static void Need(bool condition, string reason) { if (!condition) throw new InvalidDataException(reason); }
    static EMEVD.Event Event(EMEVD file, long id) {
        var matches = file.Events.Where(e => e.ID == id).ToList();
        Need(matches.Count == 1, $"missing or ambiguous encounter event {id}");
        return matches[0];
    }
    static void RequireUniqueIds(EMEVD file, string role) =>
        Need(file.Events.Select(e => e.ID).Distinct().Count() == file.Events.Count,
            $"duplicate {role} event IDs");
    static void RequireHash(string hash, string what) =>
        Need(hash.Length == 64 && hash.All(c => char.IsAsciiHexDigit(c) && !char.IsUpper(c)),
            $"invalid {what} SHA256");

    internal static string Fingerprint(EMEVD.Event e) {
        using var digest = SHA256.Create();
        using var data = new MemoryStream();
        using var writer = new BinaryWriter(data);
        writer.Write(e.ID);
        writer.Write((int)e.RestBehavior);
        foreach (var instruction in e.Instructions) {
            writer.Write(instruction.Bank); writer.Write(instruction.ID); writer.Write(instruction.ArgData.Length);
            writer.Write(instruction.ArgData); writer.Write(instruction.Layer.GetValueOrDefault(uint.MaxValue));
        }
        foreach (var parameter in e.Parameters) {
            writer.Write(parameter.InstructionIndex); writer.Write(parameter.TargetStartByte);
            writer.Write(parameter.SourceStartByte); writer.Write(parameter.ByteCount); writer.Write(parameter.UnkID);
        }
        writer.Flush();
        return Convert.ToHexString(digest.ComputeHash(data.ToArray())).ToLowerInvariant();
    }

    internal static void Validate(Encounter encounter) {
        string destination = encounter.DestinationEventFile ?? throw new InvalidDataException("missing destination event filename");
        string originalHash = encounter.OriginalEventSha256 ?? throw new InvalidDataException("missing original event SHA256");
        var changed = encounter.ChangedEventIds ?? throw new InvalidDataException("missing changed-event set");
        var protectedEvents = encounter.ProtectedCompletionEventIds
            ?? throw new InvalidDataException("missing protected completion events");
        var added = encounter.AddedEventIds ?? [];
        var fingerprints = encounter.CompiledEventFingerprints
            ?? throw new InvalidDataException("missing compiled event fingerprints");
        Need(Path.GetFileName(destination) == destination
             && destination.EndsWith(".emevd.dcx", StringComparison.OrdinalIgnoreCase),
             "invalid destination event filename");
        RequireHash(originalHash, "original event");
        Need(changed.Count > 0 && changed.Distinct().Count() == changed.Count,
             "encounter requires a non-empty unique changed-event set");
        Need(added.Distinct().Count() == added.Count && !changed.Intersect(added).Any(),
             "added event IDs must be unique and disjoint from changed events");
        Need(protectedEvents.Count > 0 && protectedEvents.Distinct().Count() == protectedEvents.Count,
             "encounter requires unique protected completion events");
        var terminals = encounter.TerminalPredicates ?? [];
        Need(terminals.Select(t => t.EventId).Distinct().Count() == terminals.Count,
            "duplicate terminal predicate event");
        Need(terminals.All(t => t.OriginalActor > 0 && t.BridgeEventId > 0 && t.BridgeEventId <= uint.MaxValue
             && protectedEvents.Contains(t.EventId) && changed.Contains(t.EventId) && added.Contains(t.BridgeEventId)),
            "terminal predicate requires protected changed event and added bridge");
        Need(!added.Intersect(protectedEvents).Any()
             && changed.Intersect(protectedEvents).ToHashSet().SetEquals(terminals.Select(t => t.EventId)),
            "encounter changes a protected completion event");
        Need(fingerprints.Count == changed.Count + added.Count && fingerprints.Keys.ToHashSet().SetEquals(changed.Concat(added)),
             "compiled fingerprints must cover exactly the declared changed and added events");
        foreach (var (id, fingerprint) in fingerprints) {
            Need(id >= 0, "invalid changed event ID");
            RequireHash(fingerprint, $"compiled event {id}");
        }
    }

    // BB EMEDF 4[0] (CharacterDead) and 3[0] (EventFlag), MAIN condition.
    // Replace only the combat predicate. Every reward/progression instruction,
    // condition index, branch offset, parameter and event property stays exact.
    internal static void ValidateTerminal(EMEVD.Event original, EMEVD.Event replacement, TerminalPredicate terminal) {
        Need(original.ID == terminal.EventId && replacement.ID == terminal.EventId,
            "terminal event identity mismatch");
        byte[] death = new byte[12];
        BitConverter.GetBytes(terminal.OriginalActor).CopyTo(death, 4); death[8] = 1;
        byte[] flag = new byte[8]; flag[1] = 1;
        BitConverter.GetBytes((uint)terminal.BridgeEventId).CopyTo(flag, 4);
        var matches = original.Instructions.Select((instruction, index) => (instruction, index))
            .Where(pair => pair.instruction.Bank == 4 && pair.instruction.ID == 0
                   && pair.instruction.ArgData.SequenceEqual(death)).ToList();
        Need(matches.Count == 1 && original.Instructions.Count == replacement.Instructions.Count,
            "terminal requires one exact MAIN character-death predicate");
        int at = matches[0].index;
        var changed = replacement.Instructions[at];
        Need(changed.Bank == 3 && changed.ID == 0 && changed.ArgData.SequenceEqual(flag)
             && changed.Layer == matches[0].instruction.Layer,
            "terminal replacement must wait for its declared bridge flag");
        var isolated = new EMEVD(EMEVD.Game.Bloodborne); isolated.Events.Add(replacement);
        var restored = EMEVD.Read(isolated.Write()).Events.Single();
        restored.Instructions[at] = matches[0].instruction;
        Need(Fingerprint(restored) == Fingerprint(original), "terminal changed non-predicate progression");
    }

    internal static byte[] Merge(EMEVD original, EMEVD compiled, Encounter encounter) {
        Validate(encounter);
        Need(original.Format == EMEVD.Game.Bloodborne && compiled.Format == EMEVD.Game.Bloodborne,
            "boss encounter requires Bloodborne events");
        RequireUniqueIds(original, "original");
        RequireUniqueIds(compiled, "compiled");
        var originalIds = original.Events.Select(e => e.ID).ToList();
        var added = encounter.AddedEventIds ?? [];
        Need(added.All(id => !originalIds.Contains(id)), "added event already exists in original");
        Need(compiled.Events.Select(e => e.ID).ToHashSet().SetEquals(originalIds.Concat(added)),
            "compiled event set differs from original plus declared additions");
        Need(compiled.Events.Where(e => originalIds.Contains(e.ID)).Select(e => e.ID).SequenceEqual(originalIds),
            "compiled original event order differs");
        var before = original.Events.ToDictionary(e => e.ID, Fingerprint);
        foreach (long id in encounter.ProtectedCompletionEventIds) Event(original, id);
        foreach (long id in encounter.ChangedEventIds) {
            var replacement = Event(compiled, id);
            Need(Fingerprint(replacement) == encounter.CompiledEventFingerprints[id],
                $"compiled event {id} does not match reviewed fingerprint");
        }
        foreach (var terminal in encounter.TerminalPredicates ?? [])
            ValidateTerminal(Event(original, terminal.EventId), Event(compiled, terminal.EventId), terminal);
        // DarkScript can normalize unrelated compiled event bodies.  They are
        // never copied: the merge starts from original and substitutes only
        // reviewed, fingerprint-pinned IDs, then proves every other output
        // event stayed byte-equivalent at the EMEVD event level.

        // Reading the original serialization creates an isolated mutable copy;
        // a validation failure cannot alter the caller's loaded source event.
        var merged = EMEVD.Read(original.Write());
        foreach (long id in encounter.ChangedEventIds)
            merged.Events[merged.Events.FindIndex(e => e.ID == id)] = Event(compiled, id);
        foreach (long id in added.OrderBy(id => id)) merged.Events.Add(Event(compiled, id));
        byte[] bytes = merged.Write();
        var check = EMEVD.Read(bytes);
        Need(check.Events.Select(e => e.ID).SequenceEqual(originalIds.Concat(added.OrderBy(id => id))),
            "persisted event identity or order differs from reviewed output");
        Need(check.LinkedFileOffsets.SequenceEqual(original.LinkedFileOffsets)
             && check.StringData.SequenceEqual(original.StringData), "event link/string data changed");
        foreach (var e in check.Events) {
            string expected = encounter.CompiledEventFingerprints.TryGetValue(e.ID, out var replacement)
                ? replacement : before[e.ID];
            Need(Fingerprint(e) == expected, $"persisted encounter event verification failed: {e.ID}");
        }
        foreach (long id in encounter.ProtectedCompletionEventIds.Except((encounter.TerminalPredicates ?? []).Select(t => t.EventId)))
            Need(Fingerprint(Event(check, id)) == before[id], $"protected completion event changed: {id}");
        foreach (var terminal in encounter.TerminalPredicates ?? [])
            ValidateTerminal(Event(original, terminal.EventId), Event(check, terminal.EventId), terminal);
        return bytes;
    }

    internal static int Inspect(string path) {
        var file = EMEVD.Read(path);
        RequireUniqueIds(file, "compiled");
        Console.WriteLine(JsonSerializer.Serialize(file.Events.ToDictionary(e => e.ID, Fingerprint), Json));
        return 0;
    }

    static int Integer(JsonNode? value, string field) {
        try { return value!.GetValue<int>(); }
        catch (Exception) { throw new InvalidDataException("invalid " + field); }
    }

    // A donor without a measured native level cannot receive an invented
    // normalization clone.  The plan must say so explicitly, with no hidden
    // parameter writes, before this route may retain the original binder.
    internal static bool ScalingEnabled(JsonObject plan) {
        var scaling = plan["scaling"] as JsonObject ?? throw new InvalidDataException("missing scaling section");
        var swaps = plan["swaps"] as JsonArray ?? throw new InvalidDataException("missing swaps for scaling");
        var swapKeys = new HashSet<string>(StringComparer.Ordinal);
        foreach (var swap in swaps) {
            string key = (swap as JsonObject)?["logical_key"]?.GetValue<string>()
                ?? throw new InvalidDataException("scaling swap lacks logical key");
            Need(swapKeys.Add(key), "duplicate scaling swap logical key");
        }
        Need(swapKeys.Count > 0, "scaling requires at least one swap");
        bool enabled;
        try { enabled = scaling["enabled"]!.GetValue<bool>(); }
        catch (Exception) { throw new InvalidDataException("invalid scaling enabled flag"); }
        var changes = scaling["changes"] as JsonArray ?? throw new InvalidDataException("missing scaling changes");
        var skips = scaling["skips"] as JsonArray ?? throw new InvalidDataException("missing scaling skips");
        Need(Integer(scaling["change_count"], "scaling change_count") == changes.Count,
            "scaling change_count differs from changes");
        Need(Integer(scaling["skip_count"], "scaling skip_count") == skips.Count,
            "scaling skip_count differs from skips");
        var accounted = new HashSet<string>(StringComparer.Ordinal);
        foreach (var change in changes) {
            string key = (change as JsonObject)?["logical_key"]?.GetValue<string>()
                ?? throw new InvalidDataException("scaling change lacks logical key");
            Need(swapKeys.Contains(key) && accounted.Add(key), "scaling change does not uniquely match a swap");
        }
        foreach (var skip in skips) {
            var item = skip as JsonObject;
            string? key = item?["logical_key"]?.GetValue<string>();
            string? reason = item?["reason"]?.GetValue<string>();
            Need(key != null && swapKeys.Contains(key) && accounted.Add(key), "scaling skip does not uniquely match a swap");
            Need(reason is "unknown source or destination tier" or "no free spEffectID slot",
                "unsupported scaling skip reason");
        }
        Need(accounted.SetEquals(swapKeys), "scaling changes and skips do not account for every swap");
        if (enabled) return true;
        Need(scaling["mechanism"]?.GetValue<string>() == "inferred_static_npc_clone_sp_effect",
            "unsupported disabled scaling mechanism");
        Need(changes.Count == 0 && skips.Count > 0, "disabled scaling must declare zero changes and explicit skips");
        return false;
    }

    static void RunUnscaled(string planPath, JsonObject plan, string gamePath, string defsPath,
        string mapsPath, string scriptsPath, string overlay)
    {
        var scaling = (JsonObject)plan["scaling"]!;
        var changes = (JsonArray)scaling["changes"]!;
        var skips = (JsonArray)scaling["skips"]!;
        string root = Path.Combine(overlay, "dvdroot_ps4");
        string parameter = Path.Combine(root, "param", "gameparam", "gameparam.parambnd.dcx");
        string sourcePlan = Path.Combine(overlay, "source-enemizer-plan.json");
        string outputPlan = Path.Combine(overlay, "bb-enemizer-plan.json");
        Directory.CreateDirectory(Path.GetDirectoryName(parameter)!);
        Directory.CreateDirectory(overlay);
        File.Copy(gamePath, parameter);
        Need(Hash(File.ReadAllBytes(gamePath)) == Hash(File.ReadAllBytes(parameter)),
            "unscaled gameparam copy verification failed");
        File.Copy(planPath, sourcePlan);
        File.Copy(planPath, outputPlan);
        Need(Hash(File.ReadAllBytes(sourcePlan)) == Hash(File.ReadAllBytes(outputPlan)),
            "unscaled plan copy verification failed");
        MapTransplant.Run(outputPlan, mapsPath, Path.Combine(root, "map", "MapStudio"), bossPrepared: true);
        AiTransplant.Run(outputPlan, gamePath, defsPath, scriptsPath, Path.Combine(root, "script"), true, bossPrepared: true);
        File.WriteAllText(Path.Combine(overlay, "scaling-report.json"), JsonSerializer.Serialize(new {
            format = "bb-enemizer-scaling-v1", applied = false, live_validated = false,
            source_plan_sha256 = Hash(File.ReadAllBytes(planPath)), source_gameparam_sha256 = Hash(File.ReadAllBytes(gamePath)),
            paramdef_sha256 = Hash(File.ReadAllBytes(defsPath)), output_gameparam_sha256 = Hash(File.ReadAllBytes(parameter)),
            output_plan_sha256 = Hash(File.ReadAllBytes(outputPlan)), npc_clones = 0, minted_effects = 0,
            changes, skips,
        }, Json));
    }

    public static int Run(string planPath, string gamePath, string defsPath, string mapsPath, string scriptsPath,
        string eventInputDirectory, string compiledEventDirectory, string outputPath, string? sfxPath = null)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(planPath));
        var root = document.RootElement;
        var plan = root.Deserialize<Manifest>(Json);
        Need(plan != null && plan.Format == "bb-enemizer-plan-v2", "expected bb-enemizer-plan-v2 manifest");
        Need(!root.TryGetProperty("boss_adapter", out _),
            "legacy boss canary plans cannot apply generalized boss encounters");
        Need(root.TryGetProperty("boss_contract", out var contract) && contract.ValueKind == JsonValueKind.Object,
            "generalized boss encounters require a boss_contract identity");
        Need(root.TryGetProperty("boss_encounters", out var encounterNode), "missing boss_encounters manifest");
        var planNode = JsonNode.Parse(File.ReadAllText(planPath))!.AsObject();
        bool scalingEnabled = ScalingEnabled(planNode);
        var encounters = encounterNode.Deserialize<Manifest>(Json);
        var encounterList = encounters?.Encounters;
        Need(encounters?.Format == "bb-boss-encounters-v1" && encounterList is { Count: > 0 },
            "invalid boss_encounters manifest");
        foreach (var encounter in encounterList!) Validate(encounter);
        Need(encounterList.Select(e => e.DestinationEventFile).Distinct(StringComparer.OrdinalIgnoreCase).Count()
             == encounterList.Count, "duplicate boss encounter destination event file");
        BossActorTransplant.ValidatePlan(planPath, required: false);
        BossRegionTransplant.ValidatePlan(planPath, required: false);
        BossSfxTransplant.ValidatePlan(planPath, required: false);
        var ffxMerges = FfxBundleTransplant.Read(planPath);
        Need(ffxMerges.Count == 0 || sfxPath is not null, "boss FFX merges require original --sfx inputs");
        var externalReferences = BossExternalReference.Read(planPath, required: false);
        BossExternalReference.ValidateEncounterBindings(externalReferences, encounterList);

        string output = Path.GetFullPath(outputPath), parent = Path.GetDirectoryName(output)!;
        Need(!Directory.Exists(output) && !File.Exists(output), "boss encounter output must not exist");
        foreach (string input in new[] {planPath, gamePath, defsPath, mapsPath, scriptsPath, eventInputDirectory, compiledEventDirectory}
            .Concat(sfxPath is null ? Array.Empty<string>() : new[] {sfxPath})) {
            string directory = Directory.Exists(input) ? Path.GetFullPath(input) : Path.GetDirectoryName(Path.GetFullPath(input))!;
            string relative = Path.GetRelativePath(directory, output);
            Need(relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal) || Path.IsPathRooted(relative),
                "boss encounter output must be outside input directories");
        }
        BossExternalReference.ValidateInputs(externalReferences, mapsPath, eventInputDirectory);
        // Load and validate every binary before ScalingTransplant creates output.
        var prepared = new List<(Encounter Encounter, byte[] Events)>();
        foreach (var encounter in encounterList.OrderBy(e => e.DestinationEventFile, StringComparer.Ordinal)) {
            string originalPath = Path.Combine(eventInputDirectory, encounter.DestinationEventFile);
            string compiledPath = Path.Combine(compiledEventDirectory, encounter.DestinationEventFile);
            Need(File.Exists(originalPath) && File.Exists(compiledPath),
                "missing reviewed original or compiled event for " + encounter.DestinationEventFile);
            byte[] originalBytes = File.ReadAllBytes(originalPath);
            Need(Hash(originalBytes) == encounter.OriginalEventSha256,
                "unsupported original event binary " + encounter.DestinationEventFile);
            prepared.Add((encounter, Merge(EMEVD.Read(originalBytes), EMEVD.Read(compiledPath), encounter)));
        }

        Directory.CreateDirectory(parent);
        string stage = Path.Combine(parent, ".bb-boss-encounters-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(stage);
        try {
            string overlay = Path.Combine(stage, "overlay");
            if (scalingEnabled)
                ScalingTransplant.Run(planPath, gamePath, defsPath, mapsPath, scriptsPath, overlay, bossPrepared: true);
            else
                RunUnscaled(planPath, planNode, gamePath, defsPath, mapsPath, scriptsPath, overlay);
            string overlayMaps = Path.Combine(overlay, "dvdroot_ps4", "map", "MapStudio");
            BossActorTransplant.ApplyActorsAndPrimary(planPath, mapsPath, mapsPath, overlayMaps, required: false);
            var regionAdditions = BossRegionTransplant.Apply(planPath, mapsPath, mapsPath, overlayMaps, required: false);
            var objectAdditions = BossObjectTransplant.Apply(planPath, mapsPath, mapsPath, overlayMaps, required: false);
            var sfxAdditions = BossSfxTransplant.Apply(planPath, mapsPath, mapsPath, overlayMaps, required: false);
            BossActorTransplant.ApplyGeneratorsOnly(planPath, mapsPath, mapsPath, overlayMaps);
            BossRegionTransplant.VerifyFinal(regionAdditions, mapsPath, overlayMaps);
            BossObjectTransplant.VerifyFinal(objectAdditions, mapsPath, overlayMaps);
            BossSfxTransplant.VerifyFinal(sfxAdditions, mapsPath, overlayMaps);
            FfxBundleTransplant.VerifyCoverage(planPath, sfxAdditions);
            var ffxAdditions = FfxBundleTransplant.Apply(planPath, sfxPath, Path.Combine(overlay, "dvdroot_ps4", "sfx"));
            foreach (var (encounter, events) in prepared) {
                string eventPath = Path.Combine(overlay, "dvdroot_ps4", "event", encounter.DestinationEventFile);
                Directory.CreateDirectory(Path.GetDirectoryName(eventPath)!);
                File.WriteAllBytes(eventPath, events);
                Need(Hash(File.ReadAllBytes(eventPath)) == Hash(events), "boss encounter event copy verification failed");
            }
            BossExternalReference.ValidateFinal(externalReferences,
                Path.Combine(overlay, "dvdroot_ps4", "map", "MapStudio"), Path.Combine(overlay, "dvdroot_ps4", "event"));
            if (externalReferences.Count > 0)
                BossExternalReference.ValidateRetainedPlan(planPath, Path.Combine(overlay, "bb-enemizer-plan.json"));
            var files = Directory.GetFiles(overlay, "*", SearchOption.AllDirectories)
                .OrderBy(path => Path.GetRelativePath(overlay, path), StringComparer.Ordinal)
                .Select(path => new { path = Path.GetRelativePath(overlay, path).Replace('\\', '/'),
                    sha256 = Hash(File.ReadAllBytes(path)), size = new FileInfo(path).Length }).ToArray();
            File.WriteAllText(Path.Combine(overlay, "boss-encounters-report.json"), JsonSerializer.Serialize(new {
                format = "bb-boss-encounters-v1", applied = true, runtime_validated = false,
                encounters = prepared.Select(item => new {
                    destination_event_file = item.Encounter.DestinationEventFile,
                    original_event_sha256 = item.Encounter.OriginalEventSha256,
                    output_event_sha256 = Hash(item.Events),
                    changed_event_ids = item.Encounter.ChangedEventIds,
                    added_event_ids = item.Encounter.AddedEventIds ?? [],
                    protected_completion_event_ids = item.Encounter.ProtectedCompletionEventIds,
                    terminal_predicates = item.Encounter.TerminalPredicates ?? [],
                    compiled_event_fingerprints = item.Encounter.CompiledEventFingerprints,
                }), external_references = externalReferences, region_additions = regionAdditions, object_additions = objectAdditions, sfx_additions = sfxAdditions, ffx_merges = ffxAdditions, files,
                warning = "Experimental encounter edits require live validation of entrance, combat, arena fit and AP completion.",
            }, Json));
            Directory.Move(overlay, output);
            Console.WriteLine($"boss_encounters={prepared.Count} output={output}");
            return 0;
        }
        finally {
            if (Directory.Exists(stage) && Path.GetDirectoryName(stage) == parent
                && Path.GetFileName(stage).StartsWith(".bb-boss-encounters-", StringComparison.Ordinal)) Directory.Delete(stage, true);
        }
    }
}
