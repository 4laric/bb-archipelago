using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using SoulsFormats;

// Adds only source-pinned MSBB Event.SFX records for reviewed encounters.
// An MSBB EffectID is only an event reference: this class deliberately does
// not claim that the destination FFXBND contains the referenced FXR files.
internal static class BossSfxTransplant
{
    static readonly JsonSerializerOptions Json = new() {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
        WriteIndented = true,
    };

    internal sealed record SfxProvenance(string Format, string EventSha256);
    internal sealed record AnchorProvenance(string Format, string PartSha256);
    internal sealed record Addition(
        string SourceMap, string SourceEvent, int SourceEventId, int SourceEntityId,
        SfxProvenance SourceProvenance, string SourceAnchorPart, AnchorProvenance SourceAnchorProvenance,
        string DestinationMap, string DestinationEvent, int DestinationEventId, int DestinationEntityId,
        string DestinationPartName, string DestinationRegionName,
        string DestinationAnchorPart, AnchorProvenance DestinationAnchorProvenance);
    internal sealed record Applied(string SourceMap, string DestinationMap, string DestinationEvent, int DestinationEventId,
        int DestinationEntityId, int EffectId, string OutputEventSha256);

    static void Need(bool value, string why) { if (!value) throw new InvalidDataException(why); }
    static string Bare(string map) => map.EndsWith(".msb.dcx", StringComparison.OrdinalIgnoreCase) ? map[..^8]
        : map.EndsWith(".msb", StringComparison.OrdinalIgnoreCase) ? map[..^4] : map;
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static void RequireHash(string? hash, string what) => Need(hash is { Length: 64 }
        && hash.All(c => char.IsAsciiHexDigit(c) && !char.IsUpper(c)), $"invalid {what} SHA256");
    static string Resolve(string root, string map) {
        Need(Path.GetFileName(map) == map && Bare(map).StartsWith("m", StringComparison.Ordinal), "invalid SFX map name");
        foreach (string ext in new[] { ".msb.dcx", ".msb" }) {
            string path = Path.Combine(root, Bare(map) + ext);
            if (File.Exists(path)) return path;
        }
        throw new FileNotFoundException("no MSBB for SFX addition " + map);
    }
    static object CanonicalSfx(string map, MSBB.Event.SFX item) => new {
        format = "bb-boss-sfx-pin-v1", map = Bare(map), name = item.Name, event_id = item.EventID,
        entity_id = item.EntityID, part_name = item.PartName, region_name = item.RegionName,
        unk_e0c = item.UnkE0C, unk_e0d = item.UnkE0D, unk_e0e = item.UnkE0E, unk_e0f = item.UnkE0F,
        effect_id = item.EffectID, start_disabled = item.StartDisabled,
    };
    internal static string Fingerprint(string map, MSBB.Event.SFX item) =>
        Hash(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(CanonicalSfx(map, item), Json)));
    static MSBB.Event.SFX Sfx(MSBB map, string name, int eventId, int entityId, string role) {
        var rows = map.Events.SFX.Where(item => item.Name == name && item.EventID == eventId && item.EntityID == entityId).ToList();
        Need(rows.Count == 1, $"missing or ambiguous {role} SFX event {name}/{eventId}/{entityId}"); return rows[0];
    }
    static MSBB.Part Anchor(MSBB map, string name, string role) {
        var rows = map.Parts.GetEntries().Where(part => part.Name == name).ToList();
        Need(rows.Count == 1, $"missing or ambiguous {role} anchor Part {name}"); return rows[0];
    }
    static void RequireAnchor(string map, MSBB.Part anchor, AnchorProvenance provenance, string role) {
        Need(provenance is not null && provenance.Format == "bb-boss-actor-pin-v1", $"unsupported {role} anchor provenance format");
        var expected = provenance ?? throw new InvalidDataException($"missing {role} anchor provenance");
        RequireHash(expected.PartSha256, role + " anchor provenance");
        Need(expected.PartSha256 == BossActorTransplant.Fingerprint(map, anchor),
            $"{map}:{anchor.Name}: {role} anchor provenance pin drift");
    }
    static IEnumerable<int> BoundEntityIds(MSBB map) => map.Parts.GetEntries().Select(item => item.EntityID)
        .Concat(map.Regions.Regions.Select(item => item.EntityID)).Concat(map.Events.GetEntries().Select(item => item.EntityID))
        .Where(item => item >= 0);
    static void RequireUnique(IReadOnlyList<Addition> additions) {
        Need(additions.Select(item => (Bare(item.DestinationMap), item.DestinationEvent)).Distinct().Count() == additions.Count,
            "duplicate SFX destination event name");
        Need(additions.Select(item => (Bare(item.DestinationMap), item.DestinationEventId)).Distinct().Count() == additions.Count,
            "duplicate SFX destination event ID");
        Need(additions.Select(item => (Bare(item.DestinationMap), item.DestinationEntityId)).Distinct().Count() == additions.Count,
            "duplicate SFX destination entity ID");
    }

    internal static List<Addition> Read(string planPath, bool required) {
        using var doc = JsonDocument.Parse(File.ReadAllText(planPath));
        if (!doc.RootElement.TryGetProperty("boss_sfx_additions", out var node)) {
            Need(!required, "missing boss_sfx_additions"); return [];
        }
        var additions = node.Deserialize<List<Addition>>(Json) ?? throw new InvalidDataException("invalid boss_sfx_additions");
        Need(additions.Count > 0, "boss_sfx_additions must not be empty"); RequireUnique(additions); return additions;
    }
    internal static void ValidatePlan(string planPath, bool required) { _ = Read(planPath, required); }

    static void RequireCurrentOriginalSfx(MSBB original, MSBB current, string map) {
        Need(current.Events.SFX.Count == original.Events.SFX.Count, "SFX output contains undeclared pre-existing additions");
        for (int index = 0; index < original.Events.SFX.Count; index++)
            Need(Fingerprint(map, original.Events.SFX[index]) == Fingerprint(map, current.Events.SFX[index]),
                "SFX output changed an original SFX event before reviewed additions");
    }
    static void VerifyFinalMap(string originalPath, string outputPath, string map, IReadOnlyList<Applied> expected) {
        var original = MSBB.Read(originalPath); var check = MSBB.Read(outputPath);
        Need(check.Events.SFX.Count == original.Events.SFX.Count + expected.Count, "SFX round-trip count differs");
        for (int index = 0; index < original.Events.SFX.Count; index++)
            Need(Fingerprint(map, original.Events.SFX[index]) == Fingerprint(map, check.Events.SFX[index]),
                "SFX round-trip changed an original SFX event or order");
        for (int index = 0; index < expected.Count; index++) {
            var item = expected[index];
            var output = Sfx(check, item.DestinationEvent, item.DestinationEventId, item.DestinationEntityId, "persisted destination");
            Need(Fingerprint(map, output) == item.OutputEventSha256, "SFX round-trip changed a reviewed addition");
            Need(Fingerprint(map, check.Events.SFX[original.Events.SFX.Count + index]) == item.OutputEventSha256,
                "SFX round-trip changed reviewed addition order");
        }
    }

    // Source and destination anchors are evidence that named map references
    // were reviewed against original maps. SFX records have no geometry to
    // transform; PartName and RegionName are rewritten only by the manifest.
    internal static List<Applied> Apply(string planPath, string sourceMaps, string destinationMaps,
        string outputMaps, bool required) {
        var additions = Read(planPath, required); if (additions.Count == 0) return [];
        var sources = new Dictionary<string, MSBB>(StringComparer.Ordinal);
        var targets = new Dictionary<string, (MSBB Original, MSBB Current, string OriginalPath, string OutputPath, List<Applied> Expected)>(StringComparer.Ordinal);
        MSBB Source(string map) { string key = Bare(map); if (!sources.TryGetValue(key, out var value)) sources[key] = value = MSBB.Read(Resolve(sourceMaps, key)); return value; }
        (MSBB Original, MSBB Current, string OriginalPath, string OutputPath, List<Applied> Expected) Target(string map) {
            string key = Bare(map); if (targets.TryGetValue(key, out var value)) return value;
            string originalPath = Resolve(destinationMaps, key), outputPath = Path.Combine(outputMaps, Path.GetFileName(originalPath));
            var original = MSBB.Read(originalPath); var current = File.Exists(outputPath) ? MSBB.Read(outputPath) : MSBB.Read(originalPath);
            RequireCurrentOriginalSfx(original, current, key); value = (original, current, originalPath, outputPath, []); targets[key] = value; return value;
        }
        foreach (var add in additions) {
            Need(add.SourceEventId > 0 && add.SourceEntityId > 0 && add.DestinationEventId > 0 && add.DestinationEntityId > 0
                && !string.IsNullOrWhiteSpace(add.SourceEvent) && !string.IsNullOrWhiteSpace(add.DestinationEvent), "invalid SFX identity");
            var sourceMap = Source(add.SourceMap); var source = Sfx(sourceMap, add.SourceEvent, add.SourceEventId, add.SourceEntityId, "source");
            Need(add.SourceProvenance is not null && add.SourceProvenance.Format == "bb-boss-sfx-pin-v1", "unsupported SFX provenance format");
            var provenance = add.SourceProvenance ?? throw new InvalidDataException("missing SFX provenance");
            RequireHash(provenance.EventSha256, "SFX provenance");
            Need(provenance.EventSha256 == Fingerprint(add.SourceMap, source),
                $"{add.SourceMap}:{add.SourceEvent}: SFX provenance pin drift");
            var sourceAnchor = Anchor(sourceMap, add.SourceAnchorPart, "source SFX"); RequireAnchor(add.SourceMap, sourceAnchor, add.SourceAnchorProvenance, "source SFX");
            var target = Target(add.DestinationMap); var destinationAnchor = Anchor(target.Original, add.DestinationAnchorPart, "destination SFX");
            RequireAnchor(add.DestinationMap, destinationAnchor, add.DestinationAnchorProvenance, "destination SFX");
            Need(!string.IsNullOrWhiteSpace(source.PartName) && !string.IsNullOrWhiteSpace(source.RegionName)
                && !string.IsNullOrWhiteSpace(add.DestinationPartName) && !string.IsNullOrWhiteSpace(add.DestinationRegionName),
                "SFX requires explicit source and destination Part/Region mappings");
            Need(sourceMap.Parts.GetEntries().Count(item => item.Name == source.PartName) == 1,
                "SFX source Part mapping is missing or ambiguous");
            Need(sourceMap.Regions.Regions.Count(item => item.Name == source.RegionName) == 1,
                "SFX source Region mapping is missing or ambiguous");
            Need(target.Current.Parts.GetEntries().Count(item => item.Name == add.DestinationPartName) == 1,
                "SFX destination Part mapping is missing or ambiguous");
            Need(target.Current.Regions.Regions.Count(item => item.Name == add.DestinationRegionName) == 1,
                "SFX destination Region mapping is missing or ambiguous");
            Need(!target.Current.Events.GetEntries().Any(item => item.Name == add.DestinationEvent), "SFX destination event name already exists");
            Need(!target.Current.Events.GetEntries().Any(item => item.EventID == add.DestinationEventId), "SFX destination event ID already exists");
            Need(!BoundEntityIds(target.Current).Contains(add.DestinationEntityId), "SFX destination entity ID already exists");
            var clone = (MSBB.Event.SFX)source.DeepCopy();
            clone.Name = add.DestinationEvent; clone.EventID = add.DestinationEventId; clone.EntityID = add.DestinationEntityId;
            clone.PartName = add.DestinationPartName; clone.RegionName = add.DestinationRegionName;
            target.Current.Events.SFX.Add(clone);
            target.Expected.Add(new Applied(Bare(add.SourceMap), Bare(add.DestinationMap), clone.Name, clone.EventID,
                clone.EntityID, clone.EffectID, Fingerprint(Bare(add.DestinationMap), clone)));
        }
        foreach (var (map, target) in targets) {
            Directory.CreateDirectory(Path.GetDirectoryName(target.OutputPath)!); target.Current.Write(target.OutputPath);
            VerifyFinalMap(target.OriginalPath, target.OutputPath, map, target.Expected);
        }
        // The manifest order is the reviewed order within each map. Preserve
        // it here too, so VerifyFinal can prove the on-disk appended suffix.
        return additions.Select(add => targets[Bare(add.DestinationMap)].Expected.Single(item =>
            item.DestinationEvent == add.DestinationEvent && item.DestinationEventId == add.DestinationEventId
            && item.DestinationEntityId == add.DestinationEntityId)).ToList();
    }
    internal static void VerifyFinal(IEnumerable<Applied> additions, string destinationMaps, string outputMaps) {
        foreach (var group in additions.GroupBy(item => Bare(item.DestinationMap), StringComparer.Ordinal)) {
            string original = Resolve(destinationMaps, group.Key), output = Path.Combine(outputMaps, Path.GetFileName(original));
            Need(File.Exists(output), "SFX final output map missing"); VerifyFinalMap(original, output, group.Key, group.ToList());
        }
    }
    internal static int Inspect(string path) {
        var map = MSBB.Read(path); string name = Bare(Path.GetFileName(path));
        Console.WriteLine(JsonSerializer.Serialize(new {
            format = "bb-boss-sfx-pins-v1", map = name, map_sha256 = Hash(File.ReadAllBytes(path)),
            sfx = map.Events.SFX.OrderBy(item => item.Name, StringComparer.Ordinal).ThenBy(item => item.EventID).Select(item => new {
                name = item.Name, event_id = item.EventID, entity_id = item.EntityID, fingerprint = Fingerprint(name, item),
                part_name = item.PartName, region_name = item.RegionName, unk_e0c = item.UnkE0C, unk_e0d = item.UnkE0D,
                unk_e0e = item.UnkE0E, unk_e0f = item.UnkE0F, effect_id = item.EffectID, start_disabled = item.StartDisabled,
            }),
        }, Json));
        return 0;
    }
}
