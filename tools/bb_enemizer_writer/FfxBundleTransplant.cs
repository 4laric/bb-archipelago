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
    internal sealed record Imported(string Name, int Id, string Sha256, int Size);
    internal sealed record Applied(string SourceFile, string DestinationFile, int SourceEntryCount,
        int RetainedEntryCount, List<Imported> ImportedEntries, string OutputSha256);
    static void Need(bool value, string why) { if (!value) throw new InvalidDataException(why); }
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static string Resolve(string root, string name) {
        Need(Regex.IsMatch(name, @"^frpg_sfxbnd_m\d{2}\.ffxbnd\.dcx$"), "invalid FFX binder filename");
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
    internal static void VerifyCoverage(string planPath, IEnumerable<BossSfxTransplant.Applied> effects) {
        var merges = Read(planPath);
        static string Binder(string map) {
            Need(Regex.IsMatch(map, @"^m\d{2}_\d{2}_\d{2}_\d{2}$"), "invalid SFX map for FFX coverage");
            return "frpg_sfxbnd_" + map[..3] + ".ffxbnd.dcx";
        }
        var expected = effects.GroupBy(effect => (SourceFile: Binder(effect.SourceMap), DestinationFile: Binder(effect.DestinationMap)))
            .ToDictionary(group => group.Key, group => group.Select(effect => effect.EffectId).ToHashSet());
        Need(merges.Count == expected.Count, "FFX merge manifest does not exactly cover added map SFX");
        foreach (var row in merges) {
            Need(expected.TryGetValue((row.SourceFile, row.DestinationFile), out var required)
                && required.SetEquals(row.RequiredEffectIds), "FFX merge required effects do not exactly cover added map SFX");
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
