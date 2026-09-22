using System.Numerics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using SoulsFormats;

// Adds source-pinned MSBB Objects used by reviewed encounter controllers.
// Objects retain their donor model/type data. Their loading groups are copied
// from the destination anchor, because group masks describe destination map
// streaming/visibility rather than an object model's model-point geometry.
internal static class BossObjectTransplant
{
    static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower, PropertyNameCaseInsensitive = true, WriteIndented = true };
    internal sealed record ObjectProvenance(string Format, string PartSha256);
    internal sealed record AnchorProvenance(string Format, string PartSha256);
    internal sealed record Addition(string SourceMap, string SourcePart, int SourceEntityId, ObjectProvenance SourceProvenance,
        string SourceAnchorPart, AnchorProvenance SourceAnchorProvenance, string DestinationMap, string DestinationPart,
        int DestinationEntityId, string DestinationAnchorPart, AnchorProvenance DestinationAnchorProvenance);
    internal sealed record Applied(string DestinationMap, string DestinationPart, int DestinationEntityId, string OutputPartSha256);

    static void Need(bool value, string why) { if (!value) throw new InvalidDataException(why); }
    static string Bare(string map) => map.EndsWith(".msb.dcx", StringComparison.OrdinalIgnoreCase) ? map[..^8] : map.EndsWith(".msb", StringComparison.OrdinalIgnoreCase) ? map[..^4] : map;
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static void RequireHash(string? hash, string what) => Need(hash is { Length: 64 } && hash.All(c => char.IsAsciiHexDigit(c) && !char.IsUpper(c)), $"invalid {what} SHA256");
    static string Resolve(string root, string map) {
        Need(Path.GetFileName(map) == map && Bare(map).StartsWith("m", StringComparison.Ordinal), "invalid object map name");
        foreach (var ext in new[] { ".msb.dcx", ".msb" }) { var path = Path.Combine(root, Bare(map) + ext); if (File.Exists(path)) return path; }
        throw new FileNotFoundException("no MSBB for object addition " + map);
    }
    static float[] Values(Vector3 value) => [value.X, value.Y, value.Z];
    static object CanonicalModel(MSBB.Model.Object model) => new { name = model.Name, sib_path = model.SibPath };
    static object CanonicalObject(string map, MSBB msb, MSBB.Part.Object item) {
        var models = msb.Models.Objects.Where(model => model.Name == item.ModelName).ToList();
        Need(models.Count == 1, $"{Bare(map)}:{item.Name}: missing or ambiguous object model {item.ModelName}");
        return new {
            format = "bb-boss-object-pin-v1", map = Bare(map), name = item.Name, entity_id = item.EntityID,
            description = item.Description, instance_id = item.InstanceID, model_name = item.ModelName, model = CanonicalModel(models[0]), sib_path = item.SibPath,
            position = Values(item.Position), rotation = Values(item.Rotation), scale = Values(item.Scale),
            draw_groups = item.DrawGroups, disp_groups = item.DispGroups, backread_groups = item.BackreadGroups,
            unk_e04 = item.UnkE04, unk_e05 = item.UnkE05, unk_e06 = item.UnkE06, unk_e07 = item.UnkE07,
            lantern_id = item.LanternID, lod_param_id = item.LodParamID, unk_e0e = item.UnkE0E, unk_e0f = item.UnkE0F,
            collision_name = item.CollisionName, break_term = item.BreakTerm, net_sync_type = item.NetSyncType,
            collision_filter = item.CollisionFilter, set_main_obj_structure_booleans = item.SetMainObjStructureBooleans,
            anim_ids = item.AnimIDs, model_sfx_param_relative_ids = item.ModelSfxParamRelativeIDs,
            gparam = new { light_set_id = item.Gparam.LightSetID, fog_param_id = item.Gparam.FogParamID,
                light_scattering_id = item.Gparam.LightScatteringID, env_map_id = item.Gparam.EnvMapID },
        };
    }
    internal static string Fingerprint(string map, MSBB msb, MSBB.Part.Object item) => Hash(Encoding.UTF8.GetBytes(JsonSerializer.Serialize(CanonicalObject(map, msb, item), Json)));
    static MSBB.Part.Object Object(MSBB map, string name, string role) { var rows = map.Parts.Objects.Where(item => item.Name == name).ToList(); Need(rows.Count == 1, $"missing or ambiguous {role} object {name}"); return rows[0]; }
    static MSBB.Part Anchor(MSBB map, string name, string role) { var rows = map.Parts.GetEntries().Where(item => item.Name == name).ToList(); Need(rows.Count == 1, $"missing or ambiguous {role} anchor Part {name}"); return rows[0]; }
    static IEnumerable<int> BoundEntityIds(MSBB map) => map.Parts.GetEntries().Select(item => item.EntityID).Concat(map.Regions.Regions.Select(item => item.EntityID)).Concat(map.Events.GetEntries().Select(item => item.EntityID)).Where(item => item >= 0);
    static void RequireAnchor(string map, MSBB.Part anchor, AnchorProvenance provenance, string role) {
        Need(provenance is not null && provenance.Format == "bb-boss-actor-pin-v1", $"unsupported {role} anchor provenance format");
        var expected = provenance ?? throw new InvalidDataException($"missing {role} anchor provenance");
        RequireHash(expected.PartSha256, role + " anchor provenance");
        Need(expected.PartSha256 == BossActorTransplant.Fingerprint(map, anchor), $"{map}:{anchor.Name}: {role} anchor provenance pin drift");
    }
    static void RequireUnique(List<Addition> additions) {
        Need(additions.Select(item => (Bare(item.DestinationMap), item.DestinationPart)).Distinct().Count() == additions.Count, "duplicate object destination Part");
        Need(additions.Select(item => (Bare(item.DestinationMap), item.DestinationEntityId)).Distinct().Count() == additions.Count, "duplicate object destination entity ID");
    }
    internal static List<Addition> Read(string planPath, bool required) {
        using var doc = JsonDocument.Parse(File.ReadAllText(planPath));
        if (!doc.RootElement.TryGetProperty("boss_object_additions", out var node)) { Need(!required, "missing boss_object_additions"); return []; }
        var additions = node.Deserialize<List<Addition>>(Json) ?? throw new InvalidDataException("invalid boss_object_additions");
        Need(additions.Count > 0, "boss_object_additions must not be empty"); RequireUnique(additions); return additions;
    }
    internal static void ValidatePlan(string planPath, bool required) { _ = Read(planPath, required); }
    static void RequireOriginalObjects(MSBB original, MSBB current, string map) {
        Need(original.Parts.Objects.Count == current.Parts.Objects.Count, "object output contains undeclared pre-existing additions");
        Need(original.Models.Objects.Count == current.Models.Objects.Count, "object output contains undeclared pre-existing models");
        for (var i = 0; i < original.Parts.Objects.Count; i++) Need(Fingerprint(map, original, original.Parts.Objects[i]) == Fingerprint(map, current, current.Parts.Objects[i]), "object output changed an original object before reviewed additions");
        for (var i = 0; i < original.Models.Objects.Count; i++) Need(JsonSerializer.Serialize(CanonicalModel(original.Models.Objects[i]), Json) == JsonSerializer.Serialize(CanonicalModel(current.Models.Objects[i]), Json), "object output changed an original object model before reviewed additions");
    }
    static void VerifyFinalMap(string originalPath, string outputPath, string map, IReadOnlyList<Applied> expected) {
        var original = MSBB.Read(originalPath); var check = MSBB.Read(outputPath);
        Need(check.Parts.Objects.Count == original.Parts.Objects.Count + expected.Count, "object round-trip count differs");
        for (var i = 0; i < original.Parts.Objects.Count; i++) Need(Fingerprint(map, original, original.Parts.Objects[i]) == Fingerprint(map, check, check.Parts.Objects[i]), "object round-trip changed an original object or order");
        Need(check.Models.Objects.Count >= original.Models.Objects.Count, "object round-trip lost an original model");
        for (var i = 0; i < original.Models.Objects.Count; i++)
            Need(JsonSerializer.Serialize(CanonicalModel(original.Models.Objects[i]), Json) == JsonSerializer.Serialize(CanonicalModel(check.Models.Objects[i]), Json), "object round-trip changed an original object model or order");
        foreach (var item in expected) { var output = Object(check, item.DestinationPart, "persisted destination"); Need(output.EntityID == item.DestinationEntityId && Fingerprint(map, check, output) == item.OutputPartSha256, "object round-trip changed a reviewed addition"); }
    }
    internal static List<Applied> Apply(string planPath, string sourceMaps, string destinationMaps, string outputMaps, bool required) {
        var additions = Read(planPath, required); if (additions.Count == 0) return [];
        var sources = new Dictionary<string, MSBB>(StringComparer.Ordinal);
        var targets = new Dictionary<string, (MSBB Original, MSBB Current, string OriginalPath, string OutputPath, List<Applied> Expected)>(StringComparer.Ordinal);
        MSBB Source(string map) { var key = Bare(map); if (!sources.TryGetValue(key, out var result)) sources[key] = result = MSBB.Read(Resolve(sourceMaps, key)); return result; }
        (MSBB Original, MSBB Current, string OriginalPath, string OutputPath, List<Applied> Expected) Target(string map) { var key = Bare(map); if (targets.TryGetValue(key, out var result)) return result; var originalPath = Resolve(destinationMaps, key); var outputPath = Path.Combine(outputMaps, Path.GetFileName(originalPath)); var original = MSBB.Read(originalPath); var current = File.Exists(outputPath) ? MSBB.Read(outputPath) : MSBB.Read(originalPath); RequireOriginalObjects(original, current, key); return targets[key] = (original, current, originalPath, outputPath, []); }
        foreach (var add in additions) {
            Need(add.SourceEntityId > 0 && add.DestinationEntityId > 0 && !string.IsNullOrWhiteSpace(add.SourcePart) && !string.IsNullOrWhiteSpace(add.DestinationPart), "invalid object identity");
            var sourceMap = Source(add.SourceMap); var source = Object(sourceMap, add.SourcePart, "source");
            Need(source.EntityID == add.SourceEntityId, $"{add.SourceMap}:{add.SourcePart}: object entity provenance drift");
            Need(add.SourceProvenance is not null && add.SourceProvenance.Format == "bb-boss-object-pin-v1", "unsupported object provenance format");
            var provenance = add.SourceProvenance ?? throw new InvalidDataException("missing object provenance");
            RequireHash(provenance.PartSha256, "object provenance"); Need(provenance.PartSha256 == Fingerprint(add.SourceMap, sourceMap, source), $"{add.SourceMap}:{add.SourcePart}: object provenance pin drift");
            Need(string.IsNullOrEmpty(source.CollisionName), "object source collision mapping unsupported");
            var sourceAnchor = Anchor(sourceMap, add.SourceAnchorPart, "source object"); RequireAnchor(add.SourceMap, sourceAnchor, add.SourceAnchorProvenance, "source object");
            var target = Target(add.DestinationMap); var destinationAnchor = Anchor(target.Original, add.DestinationAnchorPart, "destination object"); RequireAnchor(add.DestinationMap, destinationAnchor, add.DestinationAnchorProvenance, "destination object");
            Need(!target.Current.Parts.GetEntries().Any(item => item.Name == add.DestinationPart), "object destination Part already exists"); Need(!BoundEntityIds(target.Current).Contains(add.DestinationEntityId), "object destination entity ID already exists");
            var model = sourceMap.Models.Objects.SingleOrDefault(item => item.Name == source.ModelName) ?? throw new InvalidDataException("source object model missing");
            var matchingModels = target.Current.Models.Objects.Where(item => item.Name == source.ModelName).ToList(); Need(matchingModels.Count <= 1, "ambiguous destination object model");
            if (matchingModels.Count == 0) target.Current.Models.Objects.Add((MSBB.Model.Object)model.DeepCopy()); else Need(JsonSerializer.Serialize(CanonicalModel(model), Json) == JsonSerializer.Serialize(CanonicalModel(matchingModels[0]), Json), "destination object model provenance drift");
            var clone = (MSBB.Part.Object)source.DeepCopy(); var yaw = destinationAnchor.Rotation.Y - sourceAnchor.Rotation.Y;
            clone.Name = add.DestinationPart; clone.EntityID = add.DestinationEntityId; clone.Position = destinationAnchor.Position + BossActorTransplant.RotateOffset(source.Position - sourceAnchor.Position, yaw); clone.Rotation = source.Rotation + new Vector3(0, yaw, 0);
            // Preserve destination streaming/visibility semantics, never donor map group masks.
            Array.Copy(destinationAnchor.DrawGroups, clone.DrawGroups, clone.DrawGroups.Length); Array.Copy(destinationAnchor.DispGroups, clone.DispGroups, clone.DispGroups.Length); Array.Copy(destinationAnchor.BackreadGroups, clone.BackreadGroups, clone.BackreadGroups.Length);
            target.Current.Parts.Objects.Add(clone); target.Expected.Add(new Applied(Bare(add.DestinationMap), clone.Name, clone.EntityID, Fingerprint(Bare(add.DestinationMap), target.Current, clone)));
        }
        foreach (var (map, target) in targets) { Directory.CreateDirectory(Path.GetDirectoryName(target.OutputPath)!); target.Current.Write(target.OutputPath); VerifyFinalMap(target.OriginalPath, target.OutputPath, map, target.Expected); }
        return targets.Values.SelectMany(item => item.Expected).OrderBy(item => item.DestinationMap, StringComparer.Ordinal).ThenBy(item => item.DestinationPart, StringComparer.Ordinal).ToList();
    }
    internal static void VerifyFinal(IEnumerable<Applied> additions, string destinationMaps, string outputMaps) { foreach (var group in additions.GroupBy(item => Bare(item.DestinationMap), StringComparer.Ordinal)) { var original = Resolve(destinationMaps, group.Key); var output = Path.Combine(outputMaps, Path.GetFileName(original)); Need(File.Exists(output), "object final output map missing"); VerifyFinalMap(original, output, group.Key, group.ToList()); } }
    internal static int Inspect(string path) { var map = MSBB.Read(path); var name = Bare(Path.GetFileName(path)); Console.WriteLine(JsonSerializer.Serialize(new { format = "bb-boss-object-pins-v1", map = name, map_sha256 = Hash(File.ReadAllBytes(path)), objects = map.Parts.Objects.OrderBy(item => item.Name, StringComparer.Ordinal).Select(item => new { name = item.Name, entity_id = item.EntityID, fingerprint = Fingerprint(name, map, item), description = item.Description, instance_id = item.InstanceID, model_name = item.ModelName, model_sib_path = map.Models.Objects.Single(model => model.Name == item.ModelName).SibPath, position = Values(item.Position), rotation = Values(item.Rotation), scale = Values(item.Scale), draw_groups = item.DrawGroups, disp_groups = item.DispGroups, backread_groups = item.BackreadGroups, unk_e04 = item.UnkE04, unk_e05 = item.UnkE05, unk_e06 = item.UnkE06, unk_e07 = item.UnkE07, lantern_id = item.LanternID, lod_param_id = item.LodParamID, unk_e0e = item.UnkE0E, unk_e0f = item.UnkE0F, collision_name = item.CollisionName, break_term = item.BreakTerm, net_sync_type = item.NetSyncType, collision_filter = item.CollisionFilter, set_main_obj_structure_booleans = item.SetMainObjStructureBooleans, anim_ids = item.AnimIDs, model_sfx_param_relative_ids = item.ModelSfxParamRelativeIDs, gparam = new { light_set_id = item.Gparam.LightSetID, fog_param_id = item.Gparam.FogParamID, light_scattering_id = item.Gparam.LightScatteringID, env_map_id = item.Gparam.EnvMapID } }) }, Json)); return 0; }
}
