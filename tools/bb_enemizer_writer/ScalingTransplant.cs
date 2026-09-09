using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using SoulsFormats;

// Experimental static normalization. The original 7401..7413 area ladder is
// measured data; application at character construction still needs a live canary.
internal static class ScalingTransplant
{
    static readonly JsonSerializerOptions Json = new() {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true, WriteIndented = true,
    };
    static readonly Dictionary<string, int> MapLevels = new() {
        ["m21_00"] = 13, ["m22_00"] = 5, ["m23_00"] = 2, ["m24_00"] = 4,
        ["m24_01"] = 1, ["m25_00"] = 9, ["m26_00"] = 12, ["m27_00"] = 6,
        ["m28_00"] = 10, ["m32_00"] = 8, ["m33_00"] = 12,
        ["m34_00"] = 11, ["m35_00"] = 12, ["m36_00"] = 13,
    };
    static readonly string[] Attack = ["physicsAttackPowerRate", "magicAttackPowerRate", "fireAttackPowerRate", "thunderAttackPowerRate"];
    static readonly string[] Defense = ["physicsDiffenceRate", "magicDiffenceRate", "fireDiffenceRate", "thunderDiffenceRate"];
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static string HashFile(string path) => Hash(File.ReadAllBytes(path));
    static string Leaf(string path) => path.Replace('\\', '/').Split('/')[^1];
    static void Need(bool condition, string reason) { if (!condition) throw new InvalidDataException(reason); }
    static PARAM.Cell Cell(PARAM.Row row, string field) => row[field]
        ?? throw new InvalidDataException($"row {row.ID}: missing {field}");
    static double Number(PARAM.Row row, string field) => Convert.ToDouble(Cell(row, field).Value);
    static void Set(PARAM.Row row, string field, double value) {
        var cell = Cell(row, field);
        cell.Value = Convert.ChangeType(value, cell.Value.GetType());
    }
    static PARAM.Row Unique(PARAM table, int id) {
        var rows = table.Rows.Where(r => r.ID == id).ToList();
        Need(rows.Count == 1, $"{table.ParamType}: missing or ambiguous row {id}");
        return rows[0];
    }
    static string RowState(PARAM.Row row) => JsonSerializer.Serialize(new {
        row.ID, row.Name, cells = row.Cells.Select(c => new {c.Def.InternalName, c.Value})
    }, Json);
    static void InsertRow(PARAM table, PARAM.Row row) {
        // Keep ordered tables ordered without rearranging any original rows
        // (some original SpEffect tables contain out-of-order entries).
        int index = table.Rows.FindIndex(existing => existing.ID > row.ID);
        if (index < 0) table.Rows.Add(row); else table.Rows.Insert(index, row);
    }
    static int NativeLevel(PARAM.Row row) {
        int id = (int)Number(row, "GameClearSpEffectID");
        if (id is >= 7401 and <= 7413) return id - 7400;
        return id switch {7490 or 7491 => 11, 7492 or 7493 or 7494 or 7497 => 12, 7495 or 7496 => 13, _ => 0};
    }

    internal sealed record Scaling(bool Enabled, string Mechanism, int ChangeCount, List<Scale> Changes);
    internal sealed record Scale(string LogicalKey, int SourceNpcParamId, int ClonedNpcParamId,
        string SpEffectSlot, int MintedSpEffectId, double HaveSoulRate, int SourceLevel,
        int DestinationLevel, double HpMultiplier, double AttackMultiplier, double DefenseMultiplier);

    public static int Run(string planPath, string gamePath, string defsPath,
        string mapsPath, string scriptsPath, string outputPath)
    {
        string output = Path.GetFullPath(outputPath);
        Need(!Directory.Exists(output) && !File.Exists(output), "scaled output must not exist");
        foreach (string input in new[] {mapsPath, scriptsPath, Path.GetDirectoryName(Path.GetFullPath(gamePath))!,
            Path.GetDirectoryName(Path.GetFullPath(defsPath))!, Path.GetDirectoryName(Path.GetFullPath(planPath))!}) {
            string relative = Path.GetRelativePath(Path.GetFullPath(input), output);
            Need(relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal) || Path.IsPathRooted(relative),
                "scaled output must be outside every input directory");
        }
        var plan = JsonNode.Parse(File.ReadAllText(planPath))!.AsObject();
        var manifest = plan.Deserialize<Manifest>(Json)!;
        Need(manifest.Format == "bb-enemizer-plan-v2" && manifest.DryRun && manifest.Swaps.Count > 0, "expected non-empty dry-run enemizer plan");
        var scaling = plan["scaling"]?.Deserialize<Scaling>(Json)
            ?? throw new InvalidDataException("missing scaling section");
        Need(scaling.Enabled && scaling.Mechanism == "inferred_static_npc_clone_sp_effect", "expected enabled static normalization");
        Need(scaling.Changes.Count > 0 && scaling.ChangeCount == scaling.Changes.Count, "invalid scaling change count");
        Need(manifest.Swaps.Select(s => s.LogicalKey).Distinct().Count() == manifest.Swaps.Count, "duplicate logical swap");
        Need(scaling.Changes.Select(s => s.LogicalKey).Distinct().Count() == scaling.Changes.Count, "duplicate scaling placement");
        Need(scaling.Changes.Select(s => s.ClonedNpcParamId).Distinct().Count() == scaling.Changes.Count, "duplicate clone ID");

        var binder = BND4.Read(gamePath);
        var defs = BND4.Read(defsPath).Files.Select(f => PARAMDEF.Read(f.Bytes)).ToList();
        var originalFiles = binder.Files.Select(f => Hash(f.Bytes)).ToArray();
        var npcFile = binder.Files.Single(f => Leaf(f.Name) == "NpcParam.param");
        var effectFile = binder.Files.Single(f => Leaf(f.Name) == "SpEffectParam.param");
        PARAM Read(BinderFile file) {
            var table = PARAM.Read(file.Bytes);
            table.ApplyParamdef(defs.Single(d => d.ParamType == table.ParamType));
            return table;
        }
        var npcs = Read(npcFile);
        var effects = Read(effectFile);
        Need(!npcs.Rows.Any(r => r.ID is >= 6000000 and <= 6099999), "NpcParam clone range collision");
        Need(!effects.Rows.Any(r => r.ID is >= 60000 and <= 60168), "SpEffect clone range collision");
        var npcStates = npcs.Rows.Select(RowState).ToArray();
        var effectStates = effects.Rows.Select(RowState).ToArray();
        var template = Unique(effects, 7401);
        // Observed persistent category-0, iconless NG+ template, CUSA03173 01.09.
        foreach (var (field, expected) in new Dictionary<string, double> {
            ["spCategory"] = 0, ["effectEndurance"] = -1, ["iconId"] = -1,
            ["useSpEffectEffect"] = 0, ["behaviorId"] = -1, ["animIdOffset"] = -1,
            ["replaceSpEffectId"] = -1, ["cycleOccurrenceSpEffectId"] = -1,
            ["atkOccurrenceSpEffectId"] = -1, ["bGameClearBonus"] = 1,
            ["soulRate"] = 1, ["soul"] = 0, ["clearSoul"] = 0,
            ["soulStealRate"] = 1, ["itemDropRate"] = 0,
        }) Need(Number(template, field) == expected, $"unsafe scaling template field {field}");
        var swaps = manifest.Swaps.ToDictionary(s => s.LogicalKey);
        var minted = new Dictionary<int, string>();
        foreach (var change in scaling.Changes.OrderBy(c => c.LogicalKey, StringComparer.Ordinal)) {
            Need(swaps.TryGetValue(change.LogicalKey, out var swap), "scaling placement is not a swap");
            Need(swap!.Target.NpcParamId == change.SourceNpcParamId, "scaling donor does not match swap target");
            Need(change.ClonedNpcParamId is >= 6000000 and <= 6099999, "clone ID outside claimed range");
            Need(change.SourceLevel is >= 1 and <= 13 && change.DestinationLevel is >= 1 and <= 13, "invalid scaling tier");
            Need(change.MintedSpEffectId == 60000 + (change.SourceLevel - 1) * 13 + change.DestinationLevel - 1, "effect ID does not match tier pair");
            Need(change.HaveSoulRate == 1, "scaling must be echo-neutral");
            var donor = Unique(npcs, change.SourceNpcParamId);
            Need(NativeLevel(donor) == change.SourceLevel, "source tier drift");
            string map = change.LogicalKey.Split(':')[0];
            Need(map.Length >= 6 && MapLevels.GetValueOrDefault(map[..6]) == change.DestinationLevel, "destination tier drift");
            Need(Enumerable.Range(0, 8).Select(i => $"spEffectID{i}").Contains(change.SpEffectSlot), "invalid effect slot");
            Need(Number(donor, change.SpEffectSlot) < 0, "scaling effect slot is occupied");
            var source = Unique(effects, 7400 + change.SourceLevel);
            var dest = Unique(effects, 7400 + change.DestinationLevel);
            foreach (var rung in new[] {source, dest}) {
                Need(Number(rung, "spCategory") == 0 && Number(rung, "effectEndurance") == -1, "unsafe native ladder category or duration");
                foreach (var fields in new[] {Attack, Defense})
                    Need(fields.All(f => Number(rung, f) == Number(rung, fields[0])), "inconsistent elemental native ladder");
            }
            foreach (var (field, multiplier) in new[] {("maxHpRate", change.HpMultiplier),
                (Attack[0], change.AttackMultiplier), (Defense[0], change.DefenseMultiplier)}) {
                double a = Number(source, field), b = Number(dest, field);
                Need(double.IsFinite(a) && double.IsFinite(b) && a > 0 && b > 0, "invalid native ladder rate");
                double expected = Math.Round(Math.Clamp(a / b, 0.25, 4.0), 6);
                Need(double.IsFinite(multiplier) && multiplier is >= 0.25 and <= 4.0 && Math.Abs(expected - multiplier) < 0.000002,
                    $"scaling multiplier does not match native ladder: {field}");
            }
            var effect = new PARAM.Row(template) {ID = change.MintedSpEffectId, Name = $"AP normalization {change.SourceLevel} to {change.DestinationLevel}"};
            Set(effect, "maxHpRate", change.HpMultiplier);
            foreach (string field in Attack) Set(effect, field, change.AttackMultiplier);
            foreach (string field in Defense) Set(effect, field, change.DefenseMultiplier);
            Set(effect, "haveSoulRate", 1);
            Set(effect, "staminaAttackRate", 1);
            Set(effect, "bGameClearBonus", 0);
            Need(Number(effect, "haveSoulRate") == 1, "minted effect changes echoes");
            string state = RowState(effect);
            if (minted.TryGetValue(effect.ID, out string? existing)) Need(existing == state, "conflicting effect ID");
            else { minted.Add(effect.ID, state); InsertRow(effects, effect); }
            var clone = new PARAM.Row(donor) {ID = change.ClonedNpcParamId, Name = $"AP normalized {donor.ID}"};
            Set(clone, change.SpEffectSlot, effect.ID);
            InsertRow(npcs, clone);
            var node = plan["swaps"]!.AsArray().Single(n => n!["logical_key"]!.GetValue<string>() == change.LogicalKey)!;
            node["unscaled_target"] = node["target"]!.DeepClone();
            node["target"]!["npc_param_id"] = clone.ID;
        }
        plan["scaling"]!["applied"] = true;
        npcFile.Bytes = npcs.Write();
        effectFile.Bytes = effects.Write();
        string parent = Path.GetDirectoryName(output)!;
        Directory.CreateDirectory(parent);
        string staging = Path.Combine(parent, ".bb-scaled-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(staging);
        try {
            string paramPath = Path.Combine(staging, "dvdroot_ps4", "param", "gameparam", "gameparam.parambnd.dcx");
            Directory.CreateDirectory(Path.GetDirectoryName(paramPath)!);
            binder.Write(paramPath);
            var check = BND4.Read(paramPath);
            Need(check.Files.Count == binder.Files.Count, "binder file count changed");
            for (int i = 0; i < check.Files.Count; i++) {
                var before = binder.Files[i]; var after = check.Files[i];
                Need(before.Name == after.Name && before.ID == after.ID && before.Flags == after.Flags
                    && before.CompressionType == after.CompressionType, "binder metadata changed");
                if (before != npcFile && before != effectFile) Need(Hash(after.Bytes) == originalFiles[i], "unrelated parameter changed");
            }
            void Verify(PARAM expected, PARAM actual, string[] originals, int firstNewId, int lastNewId) {
                Need(actual.Rows.Count == expected.Rows.Count, "parameter row count changed");
                Need(actual.Rows.Where(r => r.ID < firstNewId || r.ID > lastNewId).Select(RowState).SequenceEqual(originals),
                    "original parameter rows or relative order changed");
                Need(actual.Rows.Select(RowState).SequenceEqual(expected.Rows.Select(RowState)), "parameter round-trip differs");
            }
            Verify(npcs, Read(check.Files.Single(f => Leaf(f.Name) == "NpcParam.param")), npcStates, 6000000, 6099999);
            Verify(effects, Read(check.Files.Single(f => Leaf(f.Name) == "SpEffectParam.param")), effectStates, 60000, 60168);
            string adjustedPlan = Path.Combine(staging, "bb-enemizer-plan.json");
            File.Copy(planPath, Path.Combine(staging, "source-enemizer-plan.json"));
            File.WriteAllText(adjustedPlan, plan.ToJsonString(Json));
            MapTransplant.Run(adjustedPlan, mapsPath, Path.Combine(staging, "dvdroot_ps4", "map", "MapStudio"), scalingPrepared: true);
            AiTransplant.Run(adjustedPlan, gamePath, defsPath, scriptsPath, Path.Combine(staging, "dvdroot_ps4", "script"), true);
            var report = new {
                format = "bb-enemizer-scaling-v1", applied = true, live_validated = false,
                source_plan_sha256 = HashFile(planPath), source_gameparam_sha256 = HashFile(gamePath),
                paramdef_sha256 = HashFile(defsPath), output_gameparam_sha256 = HashFile(paramPath),
                output_plan_sha256 = HashFile(adjustedPlan), npc_clones = scaling.Changes.Count,
                minted_effects = minted.Count, changes = scaling.Changes,
            };
            File.WriteAllText(Path.Combine(staging, "scaling-report.json"), JsonSerializer.Serialize(report, Json));
            Directory.Move(staging, output);
            Console.WriteLine($"scaled_npcs={scaling.Changes.Count} effects={minted.Count} output={output}");
            return 0;
        }
        finally {
            // Only the fresh sibling staging directory may be removed.
            if (Directory.Exists(staging) && Path.GetDirectoryName(staging) == parent
                && Path.GetFileName(staging).StartsWith(".bb-scaled-", StringComparison.Ordinal)) Directory.Delete(staging, true);
        }
    }
}
