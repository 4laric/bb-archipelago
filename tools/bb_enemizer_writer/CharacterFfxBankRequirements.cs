using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using SoulsFormats;

// Delivers explicitly witnessed character TAE roots through a pinned whole-bank merge.
// This does not resolve recursive FXR references or establish runtime bank precedence.
internal static class CharacterFfxBankRequirements
{
    static readonly JsonSerializerOptions Json = new() {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
        WriteIndented = true,
    };

    internal sealed record Root(int SourceTaeEntryId, CharacterFfxRequirements.Witness Witness);
    internal sealed record Requirement(string Format, string SourceMap, string SourcePart,
        int SourceEntityId, string SourceCharacter, string DestinationMap,
        string DestinationPart, int DestinationEntityId, string SourceFfxFile,
        string DestinationFfxFile, List<Root> Roots);
    internal sealed record Validated(Requirement Requirement, string SourceBank, string DestinationBank,
        CharacterFfxRequirements.Verified SourceProof, List<Root> Roots);
    internal sealed record Delivered(string SourceMap, string SourcePart, int SourceEntityId,
        string SourceCharacter, string DestinationMap, string DestinationPart, int DestinationEntityId,
        string SourceAnibndFile, string SourceAnibndSha256,
        int SourceTaeEntryId, string SourceTaeEntry, string SourceTaeSha256,
        CharacterFfxRequirements.Witness Witness, string SourceBank, string SourceBankSha256,
        string DestinationBank, string DestinationBankSha256, string RootFxrSha256,
        string DeliveryScope, string RecursiveFxrDependencies, bool RuntimeValidated);

    static void Need(bool value, string why) { if (!value) throw new InvalidDataException(why); }
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static string Bank(string map, string file) {
        Need(map is not null && Regex.IsMatch(map, @"^m\d{2}_\d{2}_\d{2}_\d{2}$"),
            "invalid character FFX bank map");
        var match = Regex.Match(file ?? "", @"^frpg_sfxbnd_(m\d{2})(?:_(\d{2}))?\.ffxbnd\.dcx$");
        Need(match.Success && match.Groups[1].Value == map![..3]
            && (!match.Groups[2].Success || match.Groups[2].Value == map.Substring(4, 2)),
            "character FFX bank filename does not match map area/subarea");
        return file!;
    }
    static string RootKey(int effectId) => $"effect/f{effectId:D9}.fxr";
    static string Key(string path) {
        string normalized = "/" + path.Replace('\\', '/');
        int marker = normalized.IndexOf("/sfx/", StringComparison.OrdinalIgnoreCase);
        Need(marker >= 0, "character FFX entry is outside sfx namespace");
        return normalized[(marker + 5)..];
    }
    static BinderFile OneRoot(BND4 binder, int effectId, string role) {
        string key = RootKey(effectId);
        var entries = binder.Files.Where(file => Key(file.Name).Equals(key, StringComparison.OrdinalIgnoreCase)).ToList();
        Need(entries.Count == 1, $"missing or ambiguous {role} character FFX root {effectId}");
        return entries[0];
    }

    internal static List<Requirement> Read(string planPath) {
        using var document = JsonDocument.Parse(File.ReadAllText(planPath));
        if (!document.RootElement.TryGetProperty("boss_character_ffx_bank_requirements", out var node)) return [];
        var rows = node.Deserialize<List<Requirement>>(Json)
            ?? throw new InvalidDataException("invalid boss_character_ffx_bank_requirements");
        Need(rows.Count > 0, "boss_character_ffx_bank_requirements must not be empty");
        Need(rows.Select(row => (row.DestinationMap, row.DestinationPart, row.DestinationEntityId))
            .Distinct().Count() == rows.Count, "duplicate character FFX destination actor requirement");
        foreach (var row in rows) {
            Need(row.Format == "bb-boss-character-ffx-bank-requirement-v1",
                "unsupported character FFX bank requirement format");
            _ = Bank(row.SourceMap, row.SourceFfxFile);
            _ = Bank(row.DestinationMap, row.DestinationFfxFile);
            Need(!string.IsNullOrWhiteSpace(row.SourcePart) && !string.IsNullOrWhiteSpace(row.DestinationPart)
                && Regex.IsMatch(row.SourceCharacter ?? "", @"^c\d{4}$")
                && row.SourceEntityId > 0 && row.DestinationEntityId > 0,
                "invalid character FFX actor identity");
            Need(row.Roots is { Count: > 0 } && row.Roots.All(root => root is not null
                && root.SourceTaeEntryId >= 0 && root.Witness is not null && root.Witness.EffectId > 0)
                && row.Roots.Select(root => root.Witness.EffectId).Distinct().Count() == row.Roots.Count,
                "duplicate or invalid character FFX bank root");
        }
        return rows;
    }

    internal static List<Validated> Validate(string planPath,
        IEnumerable<CharacterFfxRequirements.Verified> verifiedRequirements) {
        var rows = Read(planPath);
        if (rows.Count == 0) return [];
        var merges = FfxBundleTransplant.Read(planPath);
        var verified = verifiedRequirements.ToList();
        var actors = BossActorTransplant.Read(planPath, required: false)
            .Select(item => (item.SourceMap, item.SourcePart, item.SourceEntityId,
                SourceCharacter: item.SourceArchetype.ModelName, item.DestinationMap,
                item.DestinationPart, item.DestinationEntityId))
            .Concat(BossActorTransplant.ReadPrimaryInitializations(planPath, required: false)
                .Select(item => (item.SourceMap, item.SourcePart, item.SourceEntityId,
                    SourceCharacter: item.SourceArchetype.ModelName, item.DestinationMap,
                    item.DestinationPart, item.DestinationEntityId))).ToList();
        var result = new List<Validated>();
        foreach (var row in rows) {
            var actorKey = (row.SourceMap, row.SourcePart, row.SourceEntityId,
                row.SourceCharacter, row.DestinationMap, row.DestinationPart, row.DestinationEntityId);
            Need(actors.Count(actor => actor == actorKey) == 1,
                "character FFX bank requirement is not bound to one transplanted actor destination");
            var proofs = verified.Where(item => item.SourceMap == row.SourceMap
                && item.SourcePart == row.SourcePart && item.SourceEntityId == row.SourceEntityId
                && item.SourceCharacter == row.SourceCharacter).ToList();
            Need(proofs.Count == 1, "character FFX bank requirement lacks one verified source actor TAE");
            var proof = proofs[0];
            foreach (var root in row.Roots) {
                var entries = proof.SourceTaeEntries.Where(item => item.SourceTaeEntryId == root.SourceTaeEntryId
                    && item.TypedEventWitnesses.Contains(root.Witness)).ToList();
                Need(entries.Count == 1 && proof.DirectEffectIds.Contains(root.Witness.EffectId),
                    "character FFX bank root lacks exact verified typed TAE witness");
            }
            string sourceBank = Bank(row.SourceMap, row.SourceFfxFile);
            string destinationBank = Bank(row.DestinationMap, row.DestinationFfxFile);
            var merge = merges.Where(item => item.SourceFile == sourceBank
                && item.DestinationFile == destinationBank).ToList();
            Need(merge.Count == 1 && row.Roots.All(root =>
                    merge[0].RequiredEffectIds.Contains(root.Witness.EffectId)),
                "character FFX bank root lacks pinned declared merge");
            result.Add(new Validated(row, sourceBank, destinationBank, proof, row.Roots));
        }
        return result;
    }

    internal static void VerifyFinalActors(IEnumerable<Validated> requirements, string outputMaps) {
        foreach (var group in requirements.GroupBy(item => item.Requirement.DestinationMap,
                     StringComparer.Ordinal)) {
            string path = Path.Combine(outputMaps, group.Key + ".msb.dcx");
            if (!File.Exists(path)) path = Path.Combine(outputMaps, group.Key + ".msb");
            Need(File.Exists(path), "missing staged character FFX destination actor map");
            var map = MSBB.Read(path);
            foreach (var item in group) {
                var row = item.Requirement;
                var parts = map.Parts.GetEntries().Where(part => part.Name == row.DestinationPart).ToList();
                Need(parts.Count == 1 && parts[0] is MSBB.Part.EnemyBase
                    && parts[0].EntityID == row.DestinationEntityId
                    && parts[0].ModelName == row.SourceCharacter
                    && map.Parts.GetEntries().Count(part => part.EntityID == row.DestinationEntityId) == 1,
                    "staged character FFX destination actor identity drift");
            }
        }
    }

    internal static List<Delivered> VerifyDelivered(IEnumerable<Validated> requirements,
        IEnumerable<FfxBundleTransplant.Applied> applied, string originalSfx, string outputSfx,
        string planPath) {
        var rows = requirements.ToList();
        if (rows.Count == 0) return [];
        var merges = FfxBundleTransplant.Read(planPath);
        var reports = applied.ToList();
        var receipts = new List<Delivered>();
        foreach (var group in rows.GroupBy(item => (item.SourceBank, item.DestinationBank))) {
            var merge = merges.Where(item => item.SourceFile == group.Key.SourceBank
                && item.DestinationFile == group.Key.DestinationBank).ToList();
            var report = reports.Where(item => item.SourceFile == group.Key.SourceBank
                && item.DestinationFile == group.Key.DestinationBank).ToList();
            Need(merge.Count == 1 && report.Count == 1,
                "character FFX root lacks one applied pinned whole-bank merge");
            string sourcePath = Path.Combine(originalSfx, group.Key.SourceBank);
            string outputPath = Path.Combine(outputSfx, group.Key.DestinationBank);
            Need(File.Exists(sourcePath) && Hash(File.ReadAllBytes(sourcePath)) == merge[0].SourceSha256,
                "character FFX source bank provenance drift");
            Need(File.Exists(outputPath) && Hash(File.ReadAllBytes(outputPath)) == report[0].OutputSha256,
                "character FFX output bank provenance drift");
            var source = BND4.Read(sourcePath); var output = BND4.Read(outputPath);
            foreach (var item in group) {
                var row = item.Requirement;
                foreach (var root in item.Roots) {
                    Need(merge[0].RequiredEffectIds.Contains(root.Witness.EffectId),
                        "character FFX root is undeclared in pinned bank merge");
                    var originalFxr = OneRoot(source, root.Witness.EffectId, "original");
                    var outputFxr = OneRoot(output, root.Witness.EffectId, "output");
                    Need(originalFxr.Bytes.SequenceEqual(outputFxr.Bytes),
                        "character FFX delivered root bytes differ from original source");
                    var tae = item.SourceProof.SourceTaeEntries.Single(entry =>
                        entry.SourceTaeEntryId == root.SourceTaeEntryId
                        && entry.TypedEventWitnesses.Contains(root.Witness));
                    receipts.Add(new Delivered(row.SourceMap, row.SourcePart, row.SourceEntityId,
                        row.SourceCharacter, row.DestinationMap, row.DestinationPart,
                        row.DestinationEntityId, item.SourceProof.SourceAnibndFile,
                        item.SourceProof.SourceAnibndSha256, root.SourceTaeEntryId, tae.SourceTaeEntry,
                        tae.SourceTaeSha256, root.Witness,
                        item.SourceBank, merge[0].SourceSha256, item.DestinationBank,
                        report[0].OutputSha256, Hash(originalFxr.Bytes),
                        "explicit-typed-tae-direct-root-bank-delivery", "not-validated", false));
                }
            }
        }
        return receipts;
    }
}
