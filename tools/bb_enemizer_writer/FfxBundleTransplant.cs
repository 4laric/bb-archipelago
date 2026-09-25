using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using SoulsFormats;

// Conservative donor-bank closure: retain every donor FXR/model/texture entry.
// This does not pretend to infer transitive references from unparsed BB FXR data.
internal static class FfxBundleTransplant
{
    static readonly JsonSerializerOptions Json = new() {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower, PropertyNameCaseInsensitive = true, WriteIndented = true,
    };
    internal sealed record Merge(string SourceFile, string SourceSha256, string DestinationFile,
        string DestinationSha256, List<int> RequiredEffectIds, string Policy);
    internal sealed record EmevdRequirement(string Format, string SourceMap, string DestinationMap,
        string SourceEventFile, string SourceEventSha256, long SourceEventId,
        string DestinationEventFile, long DestinationEventId, int EffectId, int OccurrenceCount = 1);
    internal sealed record Imported(string Name, int Id, string Sha256, int Size);
    internal sealed record Applied(string SourceFile, string DestinationFile, int SourceEntryCount,
        int RetainedEntryCount, List<Imported> ImportedEntries, string OutputSha256);
    internal sealed record Conflict(string DestinationFile, string LeftFile, string RightFile, string Entry);
    static void Need(bool value, string why) { if (!value) throw new InvalidDataException(why); }
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static string Resolve(string root, string name) {
        Need(Regex.IsMatch(name, @"^frpg_sfxbnd_(?:m\d{2}(?:_\d{2})?|m29[a-d])\.ffxbnd\.dcx$"), "invalid FFX binder filename");
        return Path.Combine(root, name);
    }
    static void RequireHash(string path, string expected) {
        Need(expected is { Length: 64 } && expected.All(c => char.IsAsciiHexDigit(c) && !char.IsUpper(c)), "invalid FFX provenance hash");
        Need(File.Exists(path) && Hash(File.ReadAllBytes(path)) == expected, "FFX binder provenance drift: " + Path.GetFileName(path));
    }
    static string Key(string name) {
        string path = "/" + name.Replace('\\', '/');
        int index = path.IndexOf("/sfx/", StringComparison.OrdinalIgnoreCase);
        Need(index >= 0, "FFX entry is outside the sfx namespace");
        string key = path[(index + 5)..];
        Need(!key.Split('/').Any(part => part is "" or "." or ".."), "invalid FFX entry name");
        return key;
    }
    static Dictionary<string, BinderFile> Index(BND4 binder) {
        var result = new Dictionary<string, BinderFile>(StringComparer.OrdinalIgnoreCase);
        var ids = new HashSet<int>();
        foreach (var file in binder.Files) {
            Need(result.TryAdd(Key(file.Name), file), "ambiguous FFX entry name");
            Need(file.ID >= 0 && ids.Add(file.ID), "ambiguous FFX entry ID");
        }
        return result;
    }
    internal static List<Merge> Read(string planPath) {
        using var doc = JsonDocument.Parse(File.ReadAllText(planPath));
        if (!doc.RootElement.TryGetProperty("boss_ffx_merges", out var node)) return [];
        var merges = node.Deserialize<List<Merge>>(Json) ?? throw new InvalidDataException("invalid boss_ffx_merges");
        Need(merges.Count > 0, "boss_ffx_merges must not be empty");
        Need(merges.Select(row => (row.SourceFile, row.DestinationFile)).Distinct().Count() == merges.Count, "duplicate FFX merge");
        foreach (var row in merges) {
            Need(row.Policy == "preserve_destination_union_source_v1", "unsupported FFX merge policy");
            _ = Resolve("", row.SourceFile); _ = Resolve("", row.DestinationFile);
            Need(row.SourceFile != row.DestinationFile || row.SourceSha256 == row.DestinationSha256,
                "same-bank FFX reuse requires identical source and destination pins");
            Need(row.RequiredEffectIds is { Count: > 0 } && row.RequiredEffectIds.All(id => id > 0)
                && row.RequiredEffectIds.Distinct().Count() == row.RequiredEffectIds.Count, "invalid required FFX effects");
        }
        return merges;
    }
    static string EventFile(string map) {
        Need(Regex.IsMatch(map, @"^m\d{2}_\d{2}_\d{2}_\d{2}$"), "invalid EMEVD FFX map");
        return map + ".emevd.dcx";
    }
    static string Binder(string map) {
        _ = EventFile(map);
        return "frpg_sfxbnd_" + map[..3] + ".ffxbnd.dcx";
    }
    internal static List<EmevdRequirement> ReadEmevdRequirements(string planPath) {
        using var doc = JsonDocument.Parse(File.ReadAllText(planPath));
        if (!doc.RootElement.TryGetProperty("boss_emevd_ffx_requirements", out var node)) return [];
        var rows = node.Deserialize<List<EmevdRequirement>>(Json)
            ?? throw new InvalidDataException("invalid boss_emevd_ffx_requirements");
        Need(rows.Count > 0, "boss_emevd_ffx_requirements must not be empty");
        Need(rows.Select(row => (row.SourceEventFile, row.SourceEventId, row.DestinationEventFile,
                    row.DestinationEventId, row.EffectId)).Distinct().Count() == rows.Count,
            "duplicate EMEVD FFX requirement");
        foreach (var row in rows) {
            Need(row.Format == "bb-boss-emevd-ffx-requirement-v1", "unsupported EMEVD FFX requirement format");
            Need(row.SourceEventFile == EventFile(row.SourceMap)
                 && row.DestinationEventFile == EventFile(row.DestinationMap),
                "EMEVD FFX event filename does not match map");
            Need(row.SourceEventSha256 is { Length: 64 }
                 && row.SourceEventSha256.All(c => char.IsAsciiHexDigit(c) && !char.IsUpper(c)),
                "invalid EMEVD FFX source provenance hash");
            Need(row.SourceEventId >= 0 && row.DestinationEventId >= 0 && row.EffectId > 0 && row.OccurrenceCount > 0,
                "invalid EMEVD FFX event, effect ID or occurrence count");
        }
        return rows;
    }
    static EMEVD.Event OneEvent(EMEVD file, long id, string role) {
        var events = file.Events.Where(item => item.ID == id).ToList();
        Need(events.Count == 1, $"missing or ambiguous {role} event {id}");
        return events[0];
    }
    static int SpawnEffect(EMEVD.Instruction instruction) {
        Need(instruction.ArgData.Length == 16, "malformed SpawnOneshotSFX instruction");
        return BitConverter.ToInt32(instruction.ArgData, 12);
    }
    static void RequireEffects(EMEVD.Event item, int effectId, int occurrenceCount, string role) {
        var matches = item.Instructions.Select((instruction, index) => (instruction, index))
            .Where(pair => pair.instruction.Bank == 2006 && pair.instruction.ID == 3)
            .Where(pair => SpawnEffect(pair.instruction) == effectId).ToList();
        Need(matches.Count == occurrenceCount, $"{role} event must contain exactly {(occurrenceCount == 1 ? "one" : occurrenceCount.ToString())} declared SpawnOneshotSFX effect occurrences");
        var instructionIndices = matches.Select(pair => (long)pair.index).ToHashSet();
        Need(!item.Parameters.Any(parameter => instructionIndices.Contains(parameter.InstructionIndex)
                 && parameter.TargetStartByte < 16
                 && parameter.TargetStartByte + parameter.ByteCount > 12),
            $"{role} event parameterizes the declared SpawnOneshotSFX effect operand");
    }
    internal static List<EmevdRequirement> ValidateEmevdInputs(string planPath, string eventDirectory,
        IEnumerable<BossEncounter.Encounter> encounters) {
        var rows = ReadEmevdRequirements(planPath);
        var encounterList = encounters.ToList();
        foreach (var row in rows) {
            string sourcePath = Path.Combine(eventDirectory, row.SourceEventFile);
            Need(File.Exists(sourcePath) && Hash(File.ReadAllBytes(sourcePath)) == row.SourceEventSha256,
                "EMEVD FFX source provenance drift: " + row.SourceEventFile);
            var source = EMEVD.Read(sourcePath);
            Need(source.Format == EMEVD.Game.Bloodborne, "EMEVD FFX source is not Bloodborne");
            RequireEffects(OneEvent(source, row.SourceEventId, "EMEVD FFX source"), row.EffectId, row.OccurrenceCount,
                "EMEVD FFX source");
            var bound = encounterList.Where(encounter =>
                encounter.DestinationEventFile.Equals(row.DestinationEventFile, StringComparison.OrdinalIgnoreCase)
                && encounter.ChangedEventIds.Concat(encounter.AddedEventIds ?? []).Contains(row.DestinationEventId)).ToList();
            Need(bound.Count == 1, "EMEVD FFX destination event is not one reviewed encounter edit");
        }
        return rows;
    }
    internal static void ValidateEmevdFinal(IEnumerable<EmevdRequirement> requirements, string outputEventDirectory) {
        foreach (var group in requirements.GroupBy(row => row.DestinationEventFile, StringComparer.OrdinalIgnoreCase)) {
            string path = Path.Combine(outputEventDirectory, group.Key);
            Need(File.Exists(path), "missing final EMEVD FFX destination event file");
            var file = EMEVD.Read(path);
            Need(file.Format == EMEVD.Game.Bloodborne, "EMEVD FFX destination is not Bloodborne");
            foreach (var row in group)
                RequireEffects(OneEvent(file, row.DestinationEventId, "EMEVD FFX destination"), row.EffectId, row.OccurrenceCount,
                    "EMEVD FFX destination");
        }
    }
    internal static void VerifyCoverage(string planPath, IEnumerable<BossSfxTransplant.Applied> effects,
        IEnumerable<CharacterFfxBankRequirements.Validated>? characterRoots = null) {
        var merges = Read(planPath);
        var expected = new Dictionary<(string SourceFile, string DestinationFile), HashSet<int>>();
        foreach (var effect in effects) {
            var key = (Binder(effect.SourceMap), Binder(effect.DestinationMap));
            if (!expected.TryGetValue(key, out var ids)) expected[key] = ids = [];
            ids.Add(effect.EffectId);
        }
        foreach (var requirement in ReadEmevdRequirements(planPath)) {
            var key = (Binder(requirement.SourceMap), Binder(requirement.DestinationMap));
            if (!expected.TryGetValue(key, out var ids)) expected[key] = ids = [];
            ids.Add(requirement.EffectId);
        }
        foreach (var requirement in characterRoots ?? []) {
            var key = (requirement.SourceBank, requirement.DestinationBank);
            if (!expected.TryGetValue(key, out var ids)) expected[key] = ids = [];
            foreach (var root in requirement.Roots) ids.Add(root.Witness.EffectId);
        }
        Need(merges.Count == expected.Count, "FFX merge manifest does not exactly cover declared SFX dependencies");
        foreach (var row in merges) {
            Need(expected.TryGetValue((row.SourceFile, row.DestinationFile), out var required)
                && required.SetEquals(row.RequiredEffectIds),
                "FFX merge required effects do not exactly cover declared SFX dependencies");
        }
    }
    static object Header(BND4 bnd) => new { bnd.Version, bnd.Format, bnd.Unk04, bnd.Unk05,
        bnd.BigEndian, bnd.BitBigEndian, bnd.Unicode, bnd.Extended, bnd.Compression };
    static void Verify(BND4 expected, BND4 actual) {
        Need(JsonSerializer.Serialize(Header(expected), Json) == JsonSerializer.Serialize(Header(actual), Json), "FFX binder header changed");
        Need(expected.Files.Count == actual.Files.Count, "FFX round-trip entry count changed");
        for (int i = 0; i < expected.Files.Count; i++) {
            var left = expected.Files[i]; var right = actual.Files[i];
            Need(left.ID == right.ID && left.Name == right.Name && left.Flags == right.Flags
                && left.CompressionType == right.CompressionType
                && left.Bytes.SequenceEqual(right.Bytes), "FFX round-trip entry or order changed");
        }
        _ = Index(actual);
    }
    internal static List<Conflict> FindConflicts(string planPath, string originals) {
        var merges = Read(planPath);
        if (merges.Count == 0) return [];
        Need(Directory.Exists(originals), "boss FFX preflight requires original --sfx inputs");
        var cache = new Dictionary<string, (string Sha256, Dictionary<string, BinderFile> Entries)>(StringComparer.Ordinal);
        Dictionary<string, BinderFile> Load(string name, string expected) {
            if (!cache.TryGetValue(name, out var bank)) {
                string path = Resolve(originals, name);
                RequireHash(path, expected);
                bank = (Hash(File.ReadAllBytes(path)), Index(BND4.Read(path)));
                cache.Add(name, bank);
            }
            Need(bank.Sha256 == expected, "FFX binder provenance drift: " + name);
            return bank.Entries;
        }
        var conflicts = new List<Conflict>();
        foreach (var group in merges.GroupBy(row => row.DestinationFile, StringComparer.Ordinal)
                     .OrderBy(group => group.Key, StringComparer.Ordinal)) {
            var sources = new SortedDictionary<string, Dictionary<string, BinderFile>>(StringComparer.Ordinal);
            Dictionary<string, BinderFile>? destination = null;
            foreach (var row in group.OrderBy(row => row.SourceFile, StringComparer.Ordinal)) {
                var source = Load(row.SourceFile, row.SourceSha256);
                destination ??= Load(row.DestinationFile, row.DestinationSha256);
                // A later row with the same destination must still prove its
                // own pin, even when that binder was already cached.
                _ = Load(row.DestinationFile, row.DestinationSha256);
                foreach (var id in row.RequiredEffectIds)
                    Need(source.ContainsKey($"effect/f{id:D9}.fxr"), "declared FFX effect missing from donor binder");
                if (row.SourceFile != row.DestinationFile) sources.Add(row.SourceFile, source);
            }
            Need(destination is not null, "FFX preflight has no destination bank");
            var banks = new List<(string Name, Dictionary<string, BinderFile> Entries)> {
                (group.Key, destination!),
            };
            banks.AddRange(sources.Select(source => (source.Key, source.Value)));
            for (int left = 0; left < banks.Count; left++) {
                for (int right = left + 1; right < banks.Count; right++) {
                    string? entry = banks[left].Entries.Keys
                        .Where(key => banks[right].Entries.TryGetValue(key, out var other)
                                      && !banks[left].Entries[key].Bytes.SequenceEqual(other.Bytes))
                        .OrderBy(key => key, StringComparer.OrdinalIgnoreCase)
                        .ThenBy(key => key, StringComparer.Ordinal)
                        .FirstOrDefault();
                    if (entry is not null)
                        conflicts.Add(new Conflict(group.Key, banks[left].Name, banks[right].Name, entry));
                }
            }
        }
        return conflicts;
    }
    internal static int Preflight(string planPath, string originals, string reportPath) {
        string fullReport = Path.GetFullPath(reportPath), fullOriginals = Path.GetFullPath(originals);
        string relative = Path.GetRelativePath(fullOriginals, fullReport);
        Need(Path.GetFullPath(planPath) != fullReport, "FFX preflight report would replace its plan");
        Need(relative == ".." || relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal)
             || Path.IsPathRooted(relative), "FFX preflight report must be outside original SFX inputs");
        Need(Directory.Exists(Path.GetDirectoryName(fullReport)), "FFX preflight report parent is missing");
        var conflicts = FindConflicts(planPath, originals);
        File.WriteAllText(fullReport, JsonSerializer.Serialize(new {
            format = "bb-boss-ffx-preflight-v1", conflicts,
        }, Json));
        Console.WriteLine($"ffx_conflicts={conflicts.Count} report={fullReport}");
        return 0;
    }
    internal static List<Applied> Apply(string planPath, string? originals, string outputSfx) {
        var merges = Read(planPath);
        if (merges.Count == 0) return [];
        Need(originals is not null && Directory.Exists(originals), "boss FFX merges require original --sfx inputs");
        var outputs = new Dictionary<string, BND4>(StringComparer.Ordinal);
        var reports = new List<(Merge Spec, int SourceCount, int RetainedCount, List<Imported> Imports)>();
        foreach (var row in merges.OrderBy(item => item.DestinationFile, StringComparer.Ordinal).ThenBy(item => item.SourceFile, StringComparer.Ordinal)) {
            string sourcePath = Resolve(originals!, row.SourceFile), destinationPath = Resolve(originals!, row.DestinationFile);
            RequireHash(sourcePath, row.SourceSha256); RequireHash(destinationPath, row.DestinationSha256);
            var source = BND4.Read(sourcePath); var sourceIndex = Index(source);
            foreach (var id in row.RequiredEffectIds)
                Need(sourceIndex.ContainsKey($"effect/f{id:D9}.fxr"), "declared FFX effect missing from donor binder");
            if (!outputs.TryGetValue(row.DestinationFile, out var destination)) {
                Need(!File.Exists(Resolve(outputSfx, row.DestinationFile)), "refusing to replace staged FFX output");
                outputs[row.DestinationFile] = destination = BND4.Read(destinationPath);
            }
            var existing = Index(destination); int retained = destination.Files.Count;
            int nextId = destination.Files.Count == 0 ? 0 : checked(destination.Files.Max(file => file.ID) + 1);
            var imported = new List<Imported>();
            foreach (var file in source.Files) {
                string key = Key(file.Name);
                if (existing.TryGetValue(key, out var retainedFile)) {
                    Need(retainedFile.Bytes.SequenceEqual(file.Bytes), "conflicting FFX entry: " + key);
                    continue;
                }
                var clone = new BinderFile(file.Flags, nextId, file.Name, (byte[])file.Bytes.Clone()) {
                    CompressionType = file.CompressionType,
                };
                nextId = checked(nextId + 1);
                destination.Files.Add(clone); existing.Add(key, clone);
                imported.Add(new Imported(key, clone.ID, Hash(clone.Bytes), clone.Bytes.Length));
            }
            Need(sourceIndex.All(item => existing.TryGetValue(item.Key, out var found)
                && found.Bytes.SequenceEqual(item.Value.Bytes)), "FFX donor-bank closure incomplete");
            reports.Add((row, source.Files.Count, retained, imported));
        }
        Directory.CreateDirectory(outputSfx);
        var hashes = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var (name, destination) in outputs) {
            string path = Resolve(outputSfx, name); destination.Write(path);
            Verify(destination, BND4.Read(path)); hashes[name] = Hash(File.ReadAllBytes(path));
        }
        return reports.Select(row => new Applied(row.Spec.SourceFile, row.Spec.DestinationFile,
            row.SourceCount, row.RetainedCount, row.Imports, hashes[row.Spec.DestinationFile])).ToList();
    }
}
