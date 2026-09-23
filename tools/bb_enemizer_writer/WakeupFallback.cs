using System.Buffers.Binary;
using System.Security.Cryptography;
using System.Text.Json;
using SoulsFormats;

internal static class WakeupFallback
{
    const string BodyFingerprint = "09c87b885de52154056dd891cd1331edc5c07b124660756d6600ed6d9b1dc86b";
    const string Format = "bb-enemizer-wakeup-fallback-v1";
    const long EventId = 12415130;
    static readonly JsonSerializerOptions Json = new() { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower, PropertyNameCaseInsensitive = true, WriteIndented = true };
    internal sealed record Row(string logical_key, int entity_id, string map, long event_id);
    static readonly IReadOnlyDictionary<string, (int Entity, int Slot, int Flag)> Allowed = new Dictionary<string, (int, int, int)>(StringComparer.Ordinal) {
        ["m24_01_00_00:c1120_0009"] = (2410148, 8, 1), ["m24_01_00_00:c1120_0010"] = (2410149, 9, 1),
        ["m24_01_00_00:c1120_0011"] = (2410150, 10, 0), ["m24_01_00_00:c1120_0015"] = (2410154, 14, 1),
        ["m24_01_00_00:c1120_0016"] = (2410140, 0, 1), ["m24_01_00_00:c1120_0017"] = (2410141, 1, 0),
        ["m24_01_00_00:c1120_0019"] = (2410143, 3, 0), ["m24_01_00_00:c1120_0020"] = (2410144, 4, 1),
        ["m24_01_00_00:c1120_0022"] = (2410146, 6, 0), ["m24_01_00_00:c1120_0023"] = (2410147, 7, 0),
    };
    static void Need(bool ok, string message) { if (!ok) throw new InvalidDataException(message); }
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static EMEVD.Event GetEvent(EMEVD file, long id) {
        var found = file.Events.Where(e => e.ID == id).ToArray();
        Need(found.Length == 1, $"expected one EMEVD event {id}");
        return found[0];
    }
    static int Arg(byte[] data, int index) => BinaryPrimitives.ReadInt32LittleEndian(data.AsSpan(index * 4, 4));

    internal static List<Row> ValidatePlan(string planJson)
    {
        using var doc = JsonDocument.Parse(planJson);
        var root = doc.RootElement;
        Need(root.TryGetProperty("wakeup_fallbacks", out var array) && array.ValueKind == JsonValueKind.Array, "plan lacks wakeup_fallbacks array");
        var rows = JsonSerializer.Deserialize<List<Row>>(array.GetRawText(), Json) ?? throw new InvalidDataException("invalid wakeup fallback rows");
        Need(rows.Count > 0 && rows.Count <= Allowed.Count, "wakeup fallback row count is invalid");
        Need(root.TryGetProperty("swaps", out var swaps) && swaps.ValueKind == JsonValueKind.Array, "plan lacks swaps array");
        var swapKeys = swaps.EnumerateArray().Select(s => s.GetProperty("logical_key").GetString() ?? "").ToHashSet(StringComparer.Ordinal);
        Need(rows.Select(r => r.logical_key).Distinct(StringComparer.Ordinal).Count() == rows.Count, "duplicate wakeup fallback key");
        foreach (var row in rows) {
            Need(Allowed.TryGetValue(row.logical_key, out var expected), $"unsupported wakeup fallback key {row.logical_key}");
            Need(row.map == "m24_01_00_00" && row.event_id == EventId && row.entity_id == expected.Entity, $"wakeup fallback witness differs for {row.logical_key}");
            Need(swapKeys.Contains(row.logical_key), $"wakeup fallback has no actual swap witness: {row.logical_key}");
        }
        return rows;
    }

    internal static void Apply(EMEVD original, IReadOnlyList<Row> rows, string expectedBody = BodyFingerprint)
    {
        Need(original.Format == EMEVD.Game.Bloodborne, "wakeup fallback requires Bloodborne EMEVD");
        var callee = GetEvent(original, EventId);
        Need(BossCanary.Fingerprint(callee) == expectedBody, "unsupported wakeup initializer body");
        Need(callee.Instructions.Count > 9, "wakeup initializer wait template is missing");
        var wait = callee.Instructions[9];
        Need(wait.Bank == 1001 && wait.ID == 3 && wait.ArgData.SequenceEqual(new byte[] { 0,0,0,0,60,0,0,0 }), "wakeup initializer wait template differs");
        var zeroWait = new EMEVD.Instruction(wait.Bank, wait.ID, [0,0,0,0,0,0,0,0]) { Layer = wait.Layer };

        var constructor = GetEvent(original, 0);
        var planned = rows.ToDictionary(r => r.entity_id, r => r);
        var matched = new Dictionary<int, int>();
        for (int i = 0; i < constructor.Instructions.Count; i++) {
            var ins = constructor.Instructions[i];
            if (ins.Bank != 2000 || ins.ID != 0 || ins.ArgData.Length != 36) continue;
            int entity = Arg(ins.ArgData, 2);
            if (!planned.ContainsKey(entity)) continue;
            Need(Arg(ins.ArgData, 1) == EventId, $"initializer event differs for planned entity {entity}");
            var row = planned[entity];
            var expected = Allowed[row.logical_key];
            Need(Arg(ins.ArgData, 0) == expected.Slot && Arg(ins.ArgData, 3) == 9000 && Arg(ins.ArgData, 4) == 9061
                && Arg(ins.ArgData, 5) == 52410270 && Arg(ins.ArgData, 6) == 112499 && Arg(ins.ArgData, 7) == 112400
                && Arg(ins.ArgData, 8) == expected.Flag, $"initializer witness differs for {row.logical_key}");
            Need(!constructor.Parameters.Any(p => p.InstructionIndex == i), $"initializer has event-parameter bindings: {row.logical_key}");
            matched[entity] = matched.GetValueOrDefault(entity) + 1;
            constructor.Instructions[i] = new EMEVD.Instruction(zeroWait.Bank, zeroWait.ID, zeroWait.ArgData.ToArray()) { Layer = ins.Layer };
        }
        Need(planned.Keys.All(entity => matched.GetValueOrDefault(entity) == 1), "each planned entity must have exactly one native initializer witness");
    }

    internal static int Run(string planPath, string sourcePath, string outputPath, string reportPath)
    {
        string planFull = Path.GetFullPath(planPath), sourceFull = Path.GetFullPath(sourcePath);
        string outputFull = Path.GetFullPath(outputPath), reportFull = Path.GetFullPath(reportPath);
        Need(planFull != sourceFull && planFull != outputFull && planFull != reportFull && sourceFull != outputFull && sourceFull != reportFull && outputFull != reportFull,
            "plan, source, output, and report paths must be distinct");
        Need(File.Exists(planFull) && File.Exists(sourceFull), "plan and source event file must exist");
        Need(!File.Exists(outputFull) && !Directory.Exists(outputFull) && !File.Exists(reportFull) && !Directory.Exists(reportFull), "output and report paths must not exist");

        byte[] planBytes = File.ReadAllBytes(planFull), sourceBytes = File.ReadAllBytes(sourceFull);
        var rows = ValidatePlan(System.Text.Encoding.UTF8.GetString(planBytes));

        var original = EMEVD.Read(sourceBytes);
        var eventIdsBefore = original.Events.Select(e => e.ID).ToArray();
        var fingerprintsBefore = original.Events.ToDictionary(e => e.ID, BossCanary.Fingerprint);
        var constructorParametersBefore = GetEvent(original, 0).Parameters.Select(p => (p.InstructionIndex, p.TargetStartByte, p.SourceStartByte, p.ByteCount, p.UnkID)).ToArray();
        var beforeConstructor = GetEvent(original, 0).Instructions.Select(i => (Bank: i.Bank, ID: i.ID, ArgData: i.ArgData.ToArray(), Layer: i.Layer)).ToArray();
        Apply(original, rows);
        byte[] outputBytes = original.Write();
        var verified = EMEVD.Read(outputBytes);
        Need(verified.Compression == original.Compression, "source EMEVD compression changed");
        Need(verified.Events.Select(e => e.ID).SequenceEqual(eventIdsBefore), "event IDs/order changed");
        foreach (var e in verified.Events) {
            if (e.ID != 0) Need(BossCanary.Fingerprint(e) == fingerprintsBefore[e.ID], $"unrelated event changed: {e.ID}");
        }
        Need(BossCanary.Fingerprint(GetEvent(verified, EventId)) == fingerprintsBefore[EventId], "wakeup callee changed");
        var verifiedConstructor = GetEvent(verified, 0);
        Need(verifiedConstructor.Instructions.Count == beforeConstructor.Length, "constructor instruction count changed");
        for (int i = 0; i < beforeConstructor.Length; i++) {
            var was = beforeConstructor[i]; var now = verifiedConstructor.Instructions[i];
            bool targeted = was.Bank == 2000 && was.ID == 0 && was.ArgData.Length == 36
                && Arg(was.ArgData, 1) == EventId && plannedEntity(rows, Arg(was.ArgData, 2));
            if (targeted) Need(now.Bank == 1001 && now.ID == 3 && now.ArgData.SequenceEqual(new byte[8]) && now.Layer == was.Layer, "wakeup initializer rewrite differs");
            else Need(now.Bank == was.Bank && now.ID == was.ID && now.ArgData.SequenceEqual(was.ArgData) && now.Layer == was.Layer, $"unrelated constructor instruction changed at {i}");
        }
        Need(verifiedConstructor.Parameters.Select(p => (p.InstructionIndex, p.TargetStartByte, p.SourceStartByte, p.ByteCount, p.UnkID)).SequenceEqual(constructorParametersBefore), "constructor event parameters changed");
        Directory.CreateDirectory(Path.GetDirectoryName(outputFull)!);
        File.WriteAllBytes(outputFull, outputBytes);
        var report = new { format = Format, applied = true, plan_sha256 = Hash(planBytes), source_event_sha256 = Hash(sourceBytes), output_event_sha256 = Hash(outputBytes), wakeup_fallbacks = rows };
        Directory.CreateDirectory(Path.GetDirectoryName(reportFull)!);
        File.WriteAllText(reportFull, JsonSerializer.Serialize(report, Json));
        Console.WriteLine(JsonSerializer.Serialize(report, Json));
        return 0;
    }
    static bool plannedEntity(IEnumerable<Row> rows, int entity) => rows.Any(r => r.entity_id == entity);
}
