using System.Numerics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using SoulsFormats;

// Adds only reviewed source regions. Region geometry is copied exactly; only
// the explicitly named destination identity and anchor-relative transform vary.
internal static class BossRegionTransplant
{
    static readonly JsonSerializerOptions Json = new() {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
        WriteIndented = true,
    };

    internal sealed record RegionProvenance(string Format, string RegionSha256);
    internal sealed record AnchorProvenance(string Format, string PartSha256);
    internal sealed record Addition(
        string SourceMap, string SourceRegion, int SourceEntityId, RegionProvenance SourceProvenance,
        string SourceAnchorPart, AnchorProvenance SourceAnchorProvenance,
        string DestinationMap, string DestinationRegion, int DestinationEntityId,
        string DestinationAnchorPart, AnchorProvenance DestinationAnchorProvenance);
    internal sealed record Applied(string DestinationMap, string DestinationRegion, int DestinationEntityId,
        string OutputRegionSha256);

    static void Need(bool value, string why) { if (!value) throw new InvalidDataException(why); }
    static string Bare(string map) => map.EndsWith(".msb.dcx", StringComparison.OrdinalIgnoreCase) ? map[..^8]
        : map.EndsWith(".msb", StringComparison.OrdinalIgnoreCase) ? map[..^4] : map;
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static void RequireHash(string? hash, string what) => Need(hash is { Length: 64 }
        && hash.All(c => char.IsAsciiHexDigit(c) && !char.IsUpper(c)), $"invalid {what} SHA256");
    static string Resolve(string root, string map) {
        Need(Path.GetFileName(map) == map && Bare(map).StartsWith("m", StringComparison.Ordinal), "invalid region map name");
        string bare = Bare(map);
        foreach (string ext in new[] { ".msb.dcx", ".msb" }) {
            string path = Path.Combine(root, bare + ext);
            if (File.Exists(path)) return path;
        }
        throw new FileNotFoundException("no MSBB for region addition " + map);
    }
    static float[] Values(Vector3 value) => [value.X, value.Y, value.Z];
    static object CanonicalShape(MSB.Shape shape) => shape switch {
        MSB.Shape.Point => new { type = "point" },
        MSB.Shape.Circle item => new { type = "circle", radius = item.Radius },
        MSB.Shape.Sphere item => new { type = "sphere", radius = item.Radius },
        MSB.Shape.Cylinder item => new { type = "cylinder", radius = item.Radius, height = item.Height },
        MSB.Shape.Rectangle item => new { type = "rectangle", width = item.Width, depth = item.Depth },
        MSB.Shape.Box item => new { type = "box", width = item.Width, depth = item.Depth, height = item.Height },
        _ => throw new InvalidDataException("unsupported MSBB region shape"),
    };
    static object CanonicalRegion(string map, MSBB.Region region) => new {
        format = "bb-boss-region-pin-v1", map = Bare(map), name = region.Name, entity_id = region.EntityID,
        shape = CanonicalShape(region.Shape), position = Values(region.Position), rotation = Values(region.Rotation),
    };
    internal static string Fingerprint(string map, MSBB.Region region) =>
        Hash(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(CanonicalRegion(map, region), Json)));
    static MSBB.Region Region(MSBB map, string name, string role) {
        var rows = map.Regions.Regions.Where(region => region.Name == name).ToList();
        Need(rows.Count == 1, $"missing or ambiguous {role} region {name}"); return rows[0];
    }
    static MSBB.Part Anchor(MSBB map, string name, string role) {
        var rows = map.Parts.GetEntries().Where(part => part.Name == name).ToList();
        Need(rows.Count == 1, $"missing or ambiguous {role} anchor Part {name}"); return rows[0];
    }
    static IEnumerable<int> BoundEntityIds(MSBB map) => map.Parts.GetEntries().Select(item => item.EntityID)
        .Concat(map.Regions.Regions.Select(item => item.EntityID))
        .Concat(map.Events.GetEntries().Select(item => item.EntityID)).Where(item => item >= 0);
    static void RequireAnchor(string map, MSBB.Part anchor, AnchorProvenance provenance, string role) {
        Need(provenance is not null && provenance.Format == "bb-boss-actor-pin-v1", $"unsupported {role} anchor provenance format");
        var expected = provenance ?? throw new InvalidDataException($"missing {role} anchor provenance");
        RequireHash(expected.PartSha256, role + " anchor provenance");
        Need(expected.PartSha256 == BossActorTransplant.Fingerprint(map, anchor),
            $"{map}:{anchor.Name}: {role} anchor provenance pin drift");
    }
    static void RequireUnique(IEnumerable<Addition> additions) {
        Need(additions.Select(item => (Bare(item.DestinationMap), item.DestinationRegion)).Distinct().Count() == additions.Count(),
            "duplicate region destination name");
        var bound = additions.Where(item => item.DestinationEntityId >= 0).ToList();
        Need(bound.Select(item => (Bare(item.DestinationMap), item.DestinationEntityId)).Distinct().Count() == bound.Count,
            "duplicate region destination entity ID");
    }

    internal static List<Addition> Read(string planPath, bool required) {
        using var doc = JsonDocument.Parse(File.ReadAllText(planPath));
        if (!doc.RootElement.TryGetProperty("boss_region_additions", out var node)) {
            Need(!required, "missing boss_region_additions"); return [];
        }
        var additions = node.Deserialize<List<Addition>>(Json) ?? throw new InvalidDataException("invalid boss_region_additions");
        Need(additions.Count > 0, "boss_region_additions must not be empty"); RequireUnique(additions); return additions;
    }
    internal static void ValidatePlan(string planPath, bool required) { _ = Read(planPath, required); }

    static void RequireCurrentOriginalRegions(MSBB original, MSBB current, string map) {
        Need(current.Regions.Regions.Count == original.Regions.Regions.Count,
            "region output contains undeclared pre-existing additions");
        for (int index = 0; index < original.Regions.Regions.Count; index++)
            Need(Fingerprint(map, current.Regions.Regions[index]) == Fingerprint(map, original.Regions.Regions[index]),
                "region output changed an original region before reviewed additions");
    }
    static void VerifyFinalMap(string originalPath, string outputPath, string map, IReadOnlyList<Applied> expected) {
        var original = MSBB.Read(originalPath); var check = MSBB.Read(outputPath);
        Need(check.Regions.Regions.Count == original.Regions.Regions.Count + expected.Count,
            "region round-trip count differs");
        for (int index = 0; index < original.Regions.Regions.Count; index++)
            Need(Fingerprint(map, check.Regions.Regions[index]) == Fingerprint(map, original.Regions.Regions[index]),
                "region round-trip changed an original region or order");
        foreach (var item in expected) {
            var region = Region(check, item.DestinationRegion, "persisted destination");
            Need(region.EntityID == item.DestinationEntityId && Fingerprint(map, region) == item.OutputRegionSha256,
                "region round-trip changed a reviewed addition");
        }
    }

    // sourceMaps and destinationMaps remain original inputs. outputMaps may
    // contain primary/actor writes, but destination anchor evidence is always
    // read from destinationMaps before those writes.
    internal static List<Applied> Apply(string planPath, string sourceMaps, string destinationMaps,
        string outputMaps, bool required) {
        var additions = Read(planPath, required);
        if (additions.Count == 0) return [];
        var sources = new Dictionary<string, MSBB>(StringComparer.Ordinal);
        var targets = new Dictionary<string, (MSBB Original, MSBB Current, string OriginalPath, string OutputPath,
            List<Applied> Expected)>(StringComparer.Ordinal);
        MSBB Source(string map) {
            string key = Bare(map); if (!sources.TryGetValue(key, out var value))
                sources[key] = value = MSBB.Read(Resolve(sourceMaps, key)); return value;
        }
        (MSBB Original, MSBB Current, string OriginalPath, string OutputPath, List<Applied> Expected) Target(string map) {
            string key = Bare(map); if (targets.TryGetValue(key, out var value)) return value;
            string originalPath = Resolve(destinationMaps, key), outputPath = Path.Combine(outputMaps, Path.GetFileName(originalPath));
            var original = MSBB.Read(originalPath);
            var current = File.Exists(outputPath) ? MSBB.Read(outputPath) : MSBB.Read(originalPath);
            RequireCurrentOriginalRegions(original, current, key);
            value = (original, current, originalPath, outputPath, []); targets[key] = value; return value;
        }
        foreach (var add in additions) {
            Need(!string.IsNullOrWhiteSpace(add.SourceRegion) && !string.IsNullOrWhiteSpace(add.DestinationRegion),
                "invalid region identity");
            var sourceMap = Source(add.SourceMap);
            var source = Region(sourceMap, add.SourceRegion, "source");
            Need(source.EntityID == add.SourceEntityId, $"{add.SourceMap}:{add.SourceRegion}: region entity provenance drift");
            Need(add.SourceProvenance is not null && add.SourceProvenance.Format == "bb-boss-region-pin-v1",
                "unsupported region provenance format");
            var regionProvenance = add.SourceProvenance ?? throw new InvalidDataException("missing region provenance");
            RequireHash(regionProvenance.RegionSha256, "region provenance");
            Need(regionProvenance.RegionSha256 == Fingerprint(add.SourceMap, source),
                $"{add.SourceMap}:{add.SourceRegion}: region provenance pin drift");
            var sourceAnchor = Anchor(sourceMap, add.SourceAnchorPart, "source region");
            RequireAnchor(add.SourceMap, sourceAnchor, add.SourceAnchorProvenance, "source region");
            var target = Target(add.DestinationMap);
            // Use this original anchor only for evidence and geometry. The staged
            // map may already carry an NPC/init transplant, but it may not pick a
            // different location or a replacement anchor to satisfy this region.
            var destinationAnchor = Anchor(target.Original, add.DestinationAnchorPart, "destination region");
            RequireAnchor(add.DestinationMap, destinationAnchor, add.DestinationAnchorProvenance, "destination region");
            Need(!target.Current.Regions.Regions.Any(region => region.Name == add.DestinationRegion),
                "region destination name already exists");
            if (add.DestinationEntityId >= 0)
                Need(!BoundEntityIds(target.Current).Contains(add.DestinationEntityId),
                    "region destination entity ID already exists");
            var clone = source.DeepCopy();
            float yaw = destinationAnchor.Rotation.Y - sourceAnchor.Rotation.Y;
            clone.Name = add.DestinationRegion; clone.EntityID = add.DestinationEntityId;
            clone.Position = destinationAnchor.Position + BossActorTransplant.RotateOffset(source.Position - sourceAnchor.Position, yaw);
            clone.Rotation = source.Rotation + new Vector3(0, yaw, 0);
            target.Current.Regions.Regions.Add(clone);
            target.Expected.Add(new Applied(Bare(add.DestinationMap), clone.Name, clone.EntityID,
                Fingerprint(Bare(add.DestinationMap), clone)));
        }
        foreach (var (map, target) in targets) {
            Directory.CreateDirectory(Path.GetDirectoryName(target.OutputPath)!);
            target.Current.Write(target.OutputPath);
            VerifyFinalMap(target.OriginalPath, target.OutputPath, map, target.Expected);
        }
        return targets.Values.SelectMany(item => item.Expected).OrderBy(item => item.DestinationMap, StringComparer.Ordinal)
            .ThenBy(item => item.DestinationRegion, StringComparer.Ordinal).ToList();
    }

    internal static void VerifyFinal(IEnumerable<Applied> additions, string destinationMaps, string outputMaps) {
        foreach (var group in additions.GroupBy(item => Bare(item.DestinationMap), StringComparer.Ordinal)) {
            string original = Resolve(destinationMaps, group.Key);
            string output = Path.Combine(outputMaps, Path.GetFileName(original));
            Need(File.Exists(output), "region final output map missing");
            VerifyFinalMap(original, output, group.Key, group.ToList());
        }
    }

    internal static int Inspect(string path) {
        var map = MSBB.Read(path); string name = Bare(Path.GetFileName(path));
        Console.WriteLine(JsonSerializer.Serialize(new {
            format = "bb-boss-region-pins-v1", map = name, map_sha256 = Hash(File.ReadAllBytes(path)),
            regions = map.Regions.Regions.OrderBy(region => region.Name, StringComparer.Ordinal).Select(region => new {
                name = region.Name, entity_id = region.EntityID, fingerprint = Fingerprint(name, region),
                shape = CanonicalShape(region.Shape), position = Values(region.Position), rotation = Values(region.Rotation),
            }),
        }, Json));
        return 0;
    }
}
