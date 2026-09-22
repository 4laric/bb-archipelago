using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text.Json;
using SoulsFormats;

// Preserves an opaque, source-witnessed event operand.  This is deliberately
// not a materializer: the referenced ID remains absent from every MSB table.
internal static class BossExternalReference
{
    static readonly JsonSerializerOptions Json = new() {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
    };
    // DarkScript3 3.6.3 Resources/bb-common.emedf.json: BB EMEDF 2004[11].
    const int SetCharacterEventTargetBank = 2004;
    const int SetCharacterEventTargetId = 11;

    internal sealed record Reference(string Format, int EntityId, string SourceMap,
        List<string> DestinationMaps, string SourceMapSha256, Dictionary<string, string> DestinationMapSha256,
        string SourceEventFile, string SourceEventSha256, long SourceEventId, int SourceActor,
        string DestinationEventFile, long DestinationEventId, int DestinationActor,
        string EvidenceStatus, string RuntimeStatus);

    static void Need(bool value, string reason) { if (!value) throw new InvalidDataException(reason); }
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static string HashFile(string path) => Hash(File.ReadAllBytes(path));
    static string Bare(string name) => name.EndsWith(".msb.dcx", StringComparison.OrdinalIgnoreCase) ? name[..^8]
        : name.EndsWith(".msb", StringComparison.OrdinalIgnoreCase) ? name[..^4] : name;
    static void RequireHash(string? hash, string what) => Need(hash is { Length: 64 }
        && hash.All(c => char.IsAsciiHexDigit(c) && !char.IsUpper(c)), $"invalid {what} SHA256");
    static bool ValidMap(string? map) => map is not null && Path.GetFileName(map) == map
        && Bare(map) == map && map.StartsWith("m", StringComparison.Ordinal);
    static string ResolveMap(string root, string map) {
        foreach (string extension in new[] { ".msb.dcx", ".msb" }) {
            string path = Path.Combine(root, map + extension);
            if (File.Exists(path)) return path;
        }
        throw new FileNotFoundException("no MSBB for external reference " + map);
    }
    static IEnumerable<int> EntityIds(MSBB map) => map.Parts.GetEntries().Select(item => item.EntityID)
        .Concat(map.Regions.Regions.Select(item => item.EntityID))
        .Concat(map.Events.GetEntries().Select(item => item.EntityID));
    static void RequireAbsent(string mapPath, int entityId, string role) {
        var map = MSBB.Read(mapPath);
        Need(!EntityIds(map).Contains(entityId), $"external reference {entityId} is materialized in {role} map {Path.GetFileName(mapPath)}");
    }
    static EMEVD.Event Event(EMEVD file, long id, string role) {
        var rows = file.Events.Where(item => item.ID == id).ToList();
        Need(rows.Count == 1, $"missing or ambiguous external reference {role} event {id}");
        return rows[0];
    }
    static bool IsSetCharacterEventTarget(EMEVD.Instruction instruction, int actor, int target) =>
        instruction.Bank == SetCharacterEventTargetBank && instruction.ID == SetCharacterEventTargetId
        && instruction.ArgData.Length == 8
        && BinaryPrimitives.ReadInt32LittleEndian(instruction.ArgData.AsSpan(0, 4)) == actor
        && BinaryPrimitives.ReadInt32LittleEndian(instruction.ArgData.AsSpan(4, 4)) == target;
    static void RequireTarget(EMEVD file, long eventId, int actor, int target, string role) =>
        Need(Event(file, eventId, role).Instructions.Count(instruction => IsSetCharacterEventTarget(instruction, actor, target)) == 1,
            $"external reference requires exactly one {role} SetCharacterEventTarget witness");
    static readonly HashSet<string> Fields = new(StringComparer.Ordinal) {
        "format", "entity_id", "source_map", "destination_maps", "source_map_sha256", "destination_map_sha256",
        "source_event_file", "source_event_sha256", "source_event_id", "source_actor",
        "destination_event_file", "destination_event_id", "destination_actor", "evidence_status", "runtime_status",
    };
    static void ValidateShape(JsonElement element) {
        Need(element.ValueKind == JsonValueKind.Object && element.EnumerateObject().All(property => Fields.Contains(property.Name)),
            "external reference cannot declare materialization or mapping fields");
    }
    internal static List<Reference> Read(string planPath, bool required) {
        using var document = JsonDocument.Parse(File.ReadAllText(planPath));
        Need(!document.RootElement.TryGetProperty("boss_external_materializations", out _)
            && !document.RootElement.TryGetProperty("boss_external_reference_mappings", out _),
            "external reference cannot materialize or remap an entity");
        if (!document.RootElement.TryGetProperty("boss_external_references", out var node)) {
            Need(!required, "missing boss_external_references"); return [];
        }
        Need(node.ValueKind == JsonValueKind.Array && node.GetArrayLength() > 0, "boss_external_references must be non-empty array");
        foreach (var item in node.EnumerateArray()) ValidateShape(item);
        var records = node.Deserialize<List<Reference>>(Json) ?? throw new InvalidDataException("invalid boss_external_references");
        Need(records.Select(record => (record.SourceEventFile, record.SourceEventId, record.DestinationEventFile, record.DestinationEventId, record.EntityId))
            .Distinct().Count() == records.Count, "duplicate boss external reference");
        foreach (var record in records) Validate(record);
        return records;
    }
    static void Validate(Reference record) {
        Need(record.Format == "bb-boss-external-reference-v1" && record.EntityId > 0
            && record.SourceActor > 0 && record.DestinationActor > 0 && record.SourceEventId >= 0 && record.DestinationEventId >= 0,
            "invalid external reference identity");
        Need(ValidMap(record.SourceMap) && record.DestinationMaps is { Count: > 0 }
            && record.DestinationMaps.All(ValidMap) && record.DestinationMaps.Distinct(StringComparer.Ordinal).Count() == record.DestinationMaps.Count,
            "invalid external reference map identity");
        RequireHash(record.SourceMapSha256, "external source map");
        Need(record.DestinationMapSha256 is not null
            && record.DestinationMapSha256.Keys.ToHashSet(StringComparer.Ordinal).SetEquals(record.DestinationMaps),
            "external reference destination map hashes must cover exactly destination maps");
        var destinationHashes = record.DestinationMapSha256!;
        foreach (var (map, hash) in destinationHashes) {
            Need(ValidMap(map), "invalid external destination map hash key"); RequireHash(hash, "external destination map");
        }
        Need(!string.IsNullOrWhiteSpace(record.SourceEventFile) && !string.IsNullOrWhiteSpace(record.DestinationEventFile)
            && Path.GetFileName(record.SourceEventFile) == record.SourceEventFile
            && Path.GetFileName(record.DestinationEventFile) == record.DestinationEventFile
            && record.SourceEventFile.EndsWith(".emevd.dcx", StringComparison.OrdinalIgnoreCase)
            && record.DestinationEventFile.EndsWith(".emevd.dcx", StringComparison.OrdinalIgnoreCase),
            "invalid external reference event filename");
        RequireHash(record.SourceEventSha256, "external source event");
        Need(record.EvidenceStatus == "inferred" && record.RuntimeStatus == "unobserved",
            "external reference must remain inferred and runtime-unobserved");
    }
    internal static void ValidateInputs(IEnumerable<Reference> records, string mapsPath, string eventDirectory) {
        foreach (var record in records) {
            string sourceMap = ResolveMap(mapsPath, record.SourceMap);
            Need(HashFile(sourceMap) == record.SourceMapSha256, "unsupported external source map " + record.SourceMap);
            RequireAbsent(sourceMap, record.EntityId, "source");
            foreach (string destination in record.DestinationMaps) {
                string path = ResolveMap(mapsPath, destination);
                Need(HashFile(path) == record.DestinationMapSha256[destination], "unsupported external destination map " + destination);
                RequireAbsent(path, record.EntityId, "destination");
            }
            string sourceEvent = Path.Combine(eventDirectory, record.SourceEventFile);
            Need(File.Exists(sourceEvent) && HashFile(sourceEvent) == record.SourceEventSha256,
                "unsupported external source event " + record.SourceEventFile);
            var source = EMEVD.Read(sourceEvent);
            Need(source.Format == EMEVD.Game.Bloodborne, "external source event must be Bloodborne EMEVD");
            RequireTarget(source, record.SourceEventId, record.SourceActor, record.EntityId, "source");
        }
    }
    internal static void ValidateEncounterBindings(IEnumerable<Reference> records, IEnumerable<BossEncounter.Encounter> encounters) {
        foreach (var record in records) {
            var matches = encounters.Where(encounter => encounter.DestinationEventFile == record.DestinationEventFile).ToList();
            Need(matches.Count == 1 && matches[0].ChangedEventIds.Contains(record.DestinationEventId),
                "external reference destination event is not a declared reviewed edit");
        }
    }
    internal static void ValidateFinal(IEnumerable<Reference> records, string outputMaps, string outputEvents) {
        foreach (var record in records) {
            foreach (string map in record.DestinationMaps) RequireAbsent(ResolveMap(outputMaps, map), record.EntityId, "output");
            string eventPath = Path.Combine(outputEvents, record.DestinationEventFile);
            Need(File.Exists(eventPath), "missing external reference output event " + record.DestinationEventFile);
            var output = EMEVD.Read(eventPath);
            Need(output.Format == EMEVD.Game.Bloodborne, "external output event must be Bloodborne EMEVD");
            RequireTarget(output, record.DestinationEventId, record.DestinationActor, record.EntityId, "output");
        }
    }
    internal static void ValidateRetainedPlan(string planPath, string retainedPlanPath) {
        using var source = JsonDocument.Parse(File.ReadAllText(planPath));
        using var retained = JsonDocument.Parse(File.ReadAllText(retainedPlanPath));
        Need(source.RootElement.TryGetProperty("boss_external_references", out var sourceNode)
            && retained.RootElement.TryGetProperty("boss_external_references", out var retainedNode)
            && JsonElement.DeepEquals(sourceNode, retainedNode),
            "external reference metadata was not retained in output plan");
    }
}
