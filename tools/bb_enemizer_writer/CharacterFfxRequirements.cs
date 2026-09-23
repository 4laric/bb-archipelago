using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;
using SoulsFormats;

// Verifies one explicitly declared, supported set of Bloodborne typed TAE effect roots.
// This is deliberately a partial typed witness set, not all TAE behavior or
// combat closure. It does not deliver FXR resources: a separate, reviewed
// closure manifest is required before character effects can enter boss plans.
internal static class CharacterFfxRequirements
{
    static readonly JsonSerializerOptions Json = new() {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
        WriteIndented = true,
    };

    internal sealed record Witness(long AnimationId, int EventIndex, ulong EventType,
        long ParameterOffset, int EffectId);
    sealed record RawTaeEntry(
        int SourceTaeEntryId,
        string SourceTaeEntry,
        string SourceTaeSha256,
        int SourceAnimationCount,
        List<Witness> TypedEventWitnesses,
        List<int> DirectEffectIds,
        List<ulong>? DecodedEventTypes);
    internal sealed record TaeEntry(
        int SourceTaeEntryId,
        string SourceTaeEntry,
        string SourceTaeSha256,
        int SourceAnimationCount,
        List<ulong> DecodedEventTypes,
        List<Witness> TypedEventWitnesses,
        List<int> DirectEffectIds);
    sealed record RawRequirement(
        string Format,
        string SourceMap,
        string SourcePart,
        int SourceEntityId,
        string SourceCharacter,
        string SourceAnibndFile,
        string SourceAnibndSha256,
        int? SourceTaeEntryId,
        string? SourceTaeEntry,
        string? SourceTaeSha256,
        int? SourceAnimationCount,
        List<ulong>? DecodedEventTypes,
        List<Witness>? TypedEventWitnesses,
        List<RawTaeEntry>? SourceTaeEntries,
        List<int>? DirectEffectIds);
    internal sealed record Requirement(
        string Format,
        string SourceMap,
        string SourcePart,
        int SourceEntityId,
        string SourceCharacter,
        string SourceAnibndFile,
        string SourceAnibndSha256,
        List<TaeEntry> SourceTaeEntries,
        List<int> DirectEffectIds);
    internal sealed record VerifiedTaeEntry(
        int SourceTaeEntryId,
        string SourceTaeEntry,
        string SourceTaeSha256,
        int SourceAnimationCount,
        List<ulong> DecodedEventTypes,
        List<Witness> TypedEventWitnesses,
        List<int> DirectEffectIds);
    internal sealed record Verified(
        string SourceMap,
        string SourcePart,
        int SourceEntityId,
        string SourceCharacter,
        string SourceAnibndFile,
        string SourceAnibndSha256,
        List<VerifiedTaeEntry> SourceTaeEntries,
        List<int> DirectEffectIds,
        string CoverageScope,
        string FxrDeliveryStatus);
    sealed record ActorBinding(string SourceMap, string SourcePart, int SourceEntityId,
        string SourceCharacter);
    internal sealed record ParsedTae(int AnimationCount, List<Witness> Witnesses);

    static readonly List<ulong> LegacyDecodedEventTypes = [96, 100, 118];
    static readonly List<ulong> ExpandedDecodedEventTypes = [96, 99, 100, 108, 109, 112, 118];

    static void Need(bool value, string why) { if (!value) throw new InvalidDataException(why); }
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static void RequireHash(string value, string role) => Need(value is { Length: 64 }
        && value.All(c => char.IsAsciiHexDigit(c) && !char.IsUpper(c)), $"invalid {role} SHA256");
    static string Normalize(string value) => value.Replace('\\', '/').TrimStart('/');

    static List<ulong> NormalizeDecodedEventTypes(List<ulong>? declared)
    {
        var result = declared is null ? [.. LegacyDecodedEventTypes] : declared;
        Need(result.SequenceEqual(LegacyDecodedEventTypes)
            || result.SequenceEqual(ExpandedDecodedEventTypes),
            "unsupported character FFX decoded event type profile");
        return [.. result];
    }

    static TaeEntry NormalizeEntry(RawTaeEntry entry) => new(entry.SourceTaeEntryId,
        entry.SourceTaeEntry, entry.SourceTaeSha256, entry.SourceAnimationCount,
        NormalizeDecodedEventTypes(entry.DecodedEventTypes), entry.TypedEventWitnesses,
        entry.DirectEffectIds);

    static void ValidateEntry(TaeEntry entry, string character, bool legacy)
    {
        RequireHash(entry.SourceTaeSha256, "character TAE provenance");
        string path = Normalize(entry.SourceTaeEntry);
        string directory = $"chr/{character}/tae/";
        string file = path.StartsWith(directory, StringComparison.OrdinalIgnoreCase)
            ? path[directory.Length..] : "";
        Need(entry.SourceTaeEntry == path
            && path.Equals(directory + file, StringComparison.OrdinalIgnoreCase)
            && !file.Contains('/') && !file.Contains('\\')
            && (file.Equals(character + ".tae", StringComparison.OrdinalIgnoreCase)
                || Regex.IsMatch(file, @"^a\d+\.tae$", RegexOptions.IgnoreCase))
            && (!legacy || file.Equals(character + ".tae", StringComparison.OrdinalIgnoreCase)),
            "invalid character FFX TAE entry path");
        Need(entry.SourceTaeEntryId >= 0 && entry.SourceAnimationCount > 0,
            "invalid character FFX TAE identity");
        var witnesses = entry.TypedEventWitnesses
            ?? throw new InvalidDataException("missing character FFX typed witness data");
        var effects = entry.DirectEffectIds
            ?? throw new InvalidDataException("missing character FFX typed witness data");
        Need(witnesses.All(witness => witness.EventIndex >= 0
            && entry.DecodedEventTypes.Contains(witness.EventType)
            && witness.ParameterOffset >= 0 && witness.EffectId > 0),
            "invalid character FFX typed witness");
        Need(witnesses.Distinct().Count() == witnesses.Count,
            "duplicate character FFX typed witness");
        Need(effects.All(effect => effect > 0) && effects.SequenceEqual(effects.Order()),
            "character FFX direct effects must be sorted");
        Need(effects.Distinct().Count() == effects.Count,
            "duplicate character FFX direct effect");
        Need(witnesses.Select(witness => witness.EffectId).Distinct().Order().SequenceEqual(effects),
            "character FFX direct effects do not summarize typed witnesses");
    }

    static bool SameEntry(TaeEntry left, TaeEntry right) =>
        left.SourceTaeEntryId == right.SourceTaeEntryId
        && Normalize(left.SourceTaeEntry).Equals(Normalize(right.SourceTaeEntry), StringComparison.OrdinalIgnoreCase)
        && left.SourceTaeSha256 == right.SourceTaeSha256
        && left.SourceAnimationCount == right.SourceAnimationCount
        && left.DecodedEventTypes.SequenceEqual(right.DecodedEventTypes)
        && left.TypedEventWitnesses.SequenceEqual(right.TypedEventWitnesses)
        && left.DirectEffectIds.SequenceEqual(right.DirectEffectIds);

    static bool SameProof(Requirement left, Requirement right) =>
        left.SourceCharacter == right.SourceCharacter
        && left.SourceAnibndSha256 == right.SourceAnibndSha256
        && left.SourceTaeEntries.Count == right.SourceTaeEntries.Count
        && left.SourceTaeEntries.Zip(right.SourceTaeEntries).All(pair => SameEntry(pair.First, pair.Second))
        && left.DirectEffectIds.SequenceEqual(right.DirectEffectIds);

    internal static List<Requirement> Read(string planPath, bool required)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(planPath));
        if (!document.RootElement.TryGetProperty("boss_character_ffx_requirements", out var node)) {
            Need(!required, "missing boss_character_ffx_requirements");
            return [];
        }
        var rawRows = node.Deserialize<List<RawRequirement>>(Json)
            ?? throw new InvalidDataException("invalid boss_character_ffx_requirements");
        Need(rawRows.Count > 0, "boss_character_ffx_requirements must not be empty");
        var rows = new List<Requirement>();
        foreach (var raw in rawRows) {
            bool legacy = raw.Format == "bb-boss-character-ffx-requirement-v1";
            bool multi = raw.Format == "bb-boss-character-ffx-requirement-v2";
            Need(legacy || multi, "unsupported character FFX requirement format");
            Need(Regex.IsMatch(raw.SourceMap, @"^m\d{2}_\d{2}_\d{2}_\d{2}$"),
                "invalid character FFX source map");
            Need(Regex.IsMatch(raw.SourceCharacter, @"^c\d{4}$"),
                "invalid character FFX source character");
            Need(Regex.IsMatch(raw.SourceAnibndFile, @"^c\d{4}\.anibnd\.dcx$")
                && Path.GetFileName(raw.SourceAnibndFile) == raw.SourceAnibndFile
                && raw.SourceAnibndFile.StartsWith(raw.SourceCharacter, StringComparison.Ordinal),
                "invalid character FFX animation binder filename");
            RequireHash(raw.SourceAnibndSha256, "character animation binder provenance");
            List<TaeEntry> entries;
            if (legacy) {
                Need(raw.SourceTaeEntries is null && raw.SourceTaeEntryId is not null
                    && raw.SourceTaeEntry is not null && raw.SourceTaeSha256 is not null
                    && raw.SourceAnimationCount is not null && raw.TypedEventWitnesses is not null,
                    "invalid v1 character FFX TAE proof shape");
                entries = [new TaeEntry(raw.SourceTaeEntryId!.Value, raw.SourceTaeEntry!,
                    raw.SourceTaeSha256!, raw.SourceAnimationCount!.Value,
                    NormalizeDecodedEventTypes(raw.DecodedEventTypes),
                    raw.TypedEventWitnesses!, raw.DirectEffectIds
                        ?? throw new InvalidDataException("missing character FFX typed witness data"))];
            } else {
                Need(raw.SourceTaeEntryId is null && raw.SourceTaeEntry is null
                    && raw.SourceTaeSha256 is null && raw.SourceAnimationCount is null
                    && raw.DecodedEventTypes is null && raw.TypedEventWitnesses is null
                    && raw.SourceTaeEntries is { Count: > 0 },
                    "invalid v2 character FFX TAE proof shape");
                entries = raw.SourceTaeEntries!.Select(NormalizeEntry).ToList();
            }
            foreach (var entry in entries) ValidateEntry(entry, raw.SourceCharacter, legacy);
            Need(entries.Select(entry => entry.SourceTaeEntryId).Distinct().Count() == entries.Count
                && entries.Select(entry => Normalize(entry.SourceTaeEntry))
                    .Distinct(StringComparer.OrdinalIgnoreCase).Count() == entries.Count,
                "duplicate character FFX TAE entry identity");
            Need(entries.SequenceEqual(entries.OrderBy(entry => entry.SourceTaeEntryId)
                    .ThenBy(entry => Normalize(entry.SourceTaeEntry), StringComparer.OrdinalIgnoreCase)),
                "character FFX TAE entries must be sorted");
            var effects = raw.DirectEffectIds
                ?? throw new InvalidDataException("missing character FFX aggregate direct effects");
            Need(effects.All(effect => effect > 0) && effects.SequenceEqual(effects.Order())
                && effects.Distinct().Count() == effects.Count,
                "character FFX aggregate direct effects must be sorted and unique");
            Need(entries.SelectMany(entry => entry.DirectEffectIds).Distinct().Order().SequenceEqual(effects),
                "character FFX aggregate direct effects do not summarize TAE entries");
            rows.Add(new Requirement(raw.Format, raw.SourceMap, raw.SourcePart, raw.SourceEntityId,
                raw.SourceCharacter, raw.SourceAnibndFile, raw.SourceAnibndSha256, entries, effects));
        }
        Need(rows.Select(row => (row.SourceMap, row.SourcePart, row.SourceEntityId))
            .Distinct().Count() == rows.Count, "duplicate character FFX actor binding");
        foreach (var group in rows.GroupBy(row => row.SourceAnibndFile, StringComparer.OrdinalIgnoreCase)) {
            var expected = group.First();
            Need(group.All(row => SameProof(row, expected)),
                "conflicting character FFX animation binder declarations");
        }
        return rows;
    }

    static long Int64(byte[] bytes, long offset, string role)
    {
        int index = Range(bytes, offset, 8, role);
        return BinaryPrimitives.ReadInt64LittleEndian(bytes.AsSpan(index, 8));
    }

    static ulong UInt64(byte[] bytes, long offset, string role)
    {
        int index = Range(bytes, offset, 8, role);
        return BinaryPrimitives.ReadUInt64LittleEndian(bytes.AsSpan(index, 8));
    }

    static int Int32(byte[] bytes, long offset, string role)
    {
        int index = Range(bytes, offset, 4, role);
        return BinaryPrimitives.ReadInt32LittleEndian(bytes.AsSpan(index, 4));
    }

    static uint UInt32(byte[] bytes, long offset, string role)
    {
        int index = Range(bytes, offset, 4, role);
        return BinaryPrimitives.ReadUInt32LittleEndian(bytes.AsSpan(index, 4));
    }

    static int Range(byte[] bytes, long offset, long size, string role)
    {
        Need(offset >= 0 && size >= 0 && offset <= bytes.LongLength
            && size <= bytes.LongLength - offset && offset <= int.MaxValue,
            $"character TAE {role} is outside the file");
        return (int)offset;
    }

    internal static ParsedTae ParseTae(byte[] bytes) => ParseTae(bytes, LegacyDecodedEventTypes);

    internal static ParsedTae ParseTae(byte[] bytes, IReadOnlyCollection<ulong> decodedEventTypes)
    {
        Need(decodedEventTypes.SequenceEqual(LegacyDecodedEventTypes)
            || decodedEventTypes.SequenceEqual(ExpandedDecodedEventTypes),
            "unsupported character FFX decoded event type profile");
        ReadOnlySpan<byte> magic = [0x54, 0x41, 0x45, 0x20, 0x00, 0x00, 0x00, 0xff];
        Need(bytes.Length >= 0x60 && bytes.AsSpan(0, 8).SequenceEqual(magic),
            "unsupported Bloodborne character TAE header");
        Need(UInt32(bytes, 8, "version") == 0x1000c,
            "unsupported Bloodborne character TAE version");
        int animationCount = Int32(bytes, 0x54, "animation count");
        long animationTable = Int64(bytes, 0x58, "animation table");
        Need(animationCount > 0 && animationCount < 10000,
            "invalid Bloodborne character TAE animation count");
        Range(bytes, animationTable, checked((long)animationCount * 16), "animation table");
        var witnesses = new List<Witness>();
        var animationIds = new HashSet<long>();
        for (int animationIndex = 0; animationIndex < animationCount; animationIndex++) {
            long animationRow = checked(animationTable + (long)animationIndex * 16);
            long animationId = Int64(bytes, animationRow, "animation ID");
            Need(animationIds.Add(animationId), "duplicate Bloodborne character TAE animation ID");
            long body = Int64(bytes, animationRow + 8, "animation body");
            Range(bytes, body, 36, "animation body");
            long eventTable = Int64(bytes, body, "event table");
            int eventCount = Int32(bytes, body + 32, "event count");
            Need(eventCount >= 0 && eventCount < 10000,
                "invalid Bloodborne character TAE event count");
            Range(bytes, eventTable, checked((long)eventCount * 24), "event table");
            for (int eventIndex = 0; eventIndex < eventCount; eventIndex++) {
                long eventRow = checked(eventTable + (long)eventIndex * 24);
                long data = Int64(bytes, eventRow + 16, "event data");
                ulong type = UInt64(bytes, data, "event type");
                long parameters = Int64(bytes, data + 8, "event parameters");
                Need(parameters == checked(data + 16),
                    "unsupported Bloodborne character TAE parameter layout");
                if (!decodedEventTypes.Contains(type)) continue;
                int effect = Int32(bytes, parameters, "FFX effect operand");
                Need(effect > 0, "invalid Bloodborne character TAE FFX effect operand");
                witnesses.Add(new Witness(animationId, eventIndex, type, parameters, effect));
            }
        }
        return new ParsedTae(animationCount, witnesses);
    }

    static List<ActorBinding> ActorBindings(JsonElement root)
    {
        var result = new List<ActorBinding>();
        foreach (string property in new[] { "boss_actor_initializations", "boss_actor_additions" }) {
            if (!root.TryGetProperty(property, out var rows)) continue;
            Need(rows.ValueKind == JsonValueKind.Array, $"invalid {property} for character FFX binding");
            foreach (var row in rows.EnumerateArray()) {
                Need(row.TryGetProperty("source_archetype", out var archetype),
                    $"missing {property} source archetype for character FFX binding");
                Need(archetype.TryGetProperty("model_name", out var model),
                    $"missing {property} source archetype for character FFX binding");
                result.Add(new ActorBinding(
                    row.GetProperty("source_map").GetString()
                        ?? throw new InvalidDataException("missing character FFX actor source map"),
                    row.GetProperty("source_part").GetString()
                        ?? throw new InvalidDataException("missing character FFX actor source part"),
                    row.GetProperty("source_entity_id").GetInt32(),
                    model.GetString()
                        ?? throw new InvalidDataException("missing character FFX actor model")));
            }
        }
        return result.Distinct().ToList();
    }

    static string? CanonicalTaeEntry(string binderEntry, string character)
    {
        string normalized = Normalize(binderEntry);
        string prefix = $"chr/{character}/tae/";
        if (normalized.StartsWith(prefix, StringComparison.OrdinalIgnoreCase)) return normalized;
        string marker = "/" + prefix;
        int index = normalized.LastIndexOf(marker, StringComparison.OrdinalIgnoreCase);
        return index < 0 ? null : normalized[(index + 1)..];
    }

    internal static List<Verified> Validate(string planPath, string? characterDirectory)
    {
        var requirements = Read(planPath, required: false);
        if (requirements.Count == 0) return [];
        Need(characterDirectory is not null && Directory.Exists(characterDirectory),
            "character FFX requirements require original --characters inputs");
        using var document = JsonDocument.Parse(File.ReadAllText(planPath));
        var actors = ActorBindings(document.RootElement);
        var declaredBindings = requirements.Select(row => new ActorBinding(row.SourceMap,
            row.SourcePart, row.SourceEntityId, row.SourceCharacter)).ToHashSet();
        Need(declaredBindings.All(actors.Contains),
            "character FFX requirement is not bound to a materialized source actor");
        var declaredModels = requirements.Select(row => row.SourceCharacter).ToHashSet(StringComparer.Ordinal);
        Need(actors.Where(actor => declaredModels.Contains(actor.SourceCharacter)).All(declaredBindings.Contains),
            "materialized source character lacks a character FFX requirement");

        var verified = new List<Verified>();
        foreach (var row in requirements) {
            string path = Path.Combine(characterDirectory!, row.SourceAnibndFile);
            Need(File.Exists(path), "missing original character animation binder: " + row.SourceAnibndFile);
            byte[] binderBytes = File.ReadAllBytes(path);
            Need(Hash(binderBytes) == row.SourceAnibndSha256,
                "character animation binder provenance drift: " + row.SourceAnibndFile);
            var binder = BND4.Read(binderBytes);
            var verifiedEntries = new List<VerifiedTaeEntry>();
            foreach (var proof in row.SourceTaeEntries) {
                string taeKey = Normalize(proof.SourceTaeEntry);
                var entries = binder.Files.Where(file => file.ID == proof.SourceTaeEntryId
                    && CanonicalTaeEntry(file.Name, row.SourceCharacter)?.Equals(
                        taeKey, StringComparison.OrdinalIgnoreCase) == true).ToList();
                Need(entries.Count == 1, "missing or ambiguous character TAE entry: " + proof.SourceTaeEntry);
                byte[] taeBytes = entries[0].Bytes;
                Need(Hash(taeBytes) == proof.SourceTaeSha256,
                    "character TAE provenance drift: " + proof.SourceTaeEntry);
                var parsed = ParseTae(taeBytes, proof.DecodedEventTypes);
                Need(parsed.AnimationCount == proof.SourceAnimationCount,
                    "character TAE animation count drift: " + proof.SourceTaeEntry);
                Need(parsed.Witnesses.SequenceEqual(proof.TypedEventWitnesses),
                    "character TAE typed FFX witness drift: " + proof.SourceTaeEntry);
                var effects = parsed.Witnesses.Select(witness => witness.EffectId).Distinct().Order().ToList();
                Need(effects.SequenceEqual(proof.DirectEffectIds),
                    "character TAE direct FFX effect drift: " + proof.SourceTaeEntry);
                verifiedEntries.Add(new VerifiedTaeEntry(proof.SourceTaeEntryId, taeKey,
                    proof.SourceTaeSha256, parsed.AnimationCount, [.. proof.DecodedEventTypes],
                    parsed.Witnesses, effects));
            }
            verified.Add(new Verified(row.SourceMap, row.SourcePart, row.SourceEntityId,
                row.SourceCharacter, row.SourceAnibndFile,
                row.SourceAnibndSha256, verifiedEntries, row.DirectEffectIds,
                "partial-typed-witness", "not-validated"));
        }
        return verified;
    }
}
