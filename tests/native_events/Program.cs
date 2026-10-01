using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using SoulsFormats;

// Binary integration checks from synthetic records; no game inputs or compiler.
string root = Path.Combine(Path.GetTempPath(), "bb-native-events-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
void Need(bool value, string why) { if (!value) throw new Exception(why); }
try {
    var original = new EMEVD(EMEVD.Game.Bloodborne);
    original.StringData = new byte[16];
    original.LinkedFileOffsets.Add(0);
    var constructor = new EMEVD.Event(0);
    constructor.Instructions.Add(new EMEVD.Instruction(2000, 0, new byte[12]));
    original.Events.Add(constructor);
    var untouched = new EMEVD.Event(77, EMEVD.Event.RestBehaviorType.Restart);
    untouched.Instructions.Add(new EMEVD.Instruction(2004, 2, new byte[8]) { Layer = 5 });
    untouched.Parameters.Add(new EMEVD.Parameter(0, 4, 8, 4));
    original.Events.Add(untouched);
    var owned = new EMEVD.Event(88);
    owned.Instructions.Add(new EMEVD.Instruction(1000, 0, new byte[4]));
    original.Events.Add(owned);
    string source = Path.Combine(root, "original.emevd.dcx");
    original.Write(source, DCX.Type.DCX_EDGE);
    string dump = Path.Combine(root, "dump.json");
    NativeEvents.Dump(source, dump);
    var dumped = JsonNode.Parse(File.ReadAllText(dump))![Path.GetFileName(source)]!;
    Need(dumped["fingerprints"]!["77"]!.GetValue<string>() == NativeEvents.Fingerprint(untouched), "dump fingerprint");
    var changed = new EMEVD.Event(88, EMEVD.Event.RestBehaviorType.End);
    changed.Instructions.Add(new EMEVD.Instruction(2004, 2, new byte[8]) { Layer = 3 });
    changed.Parameters.Add(new EMEVD.Parameter(0, 4, 0, 4));
    var added = new EMEVD.Event(99);
    added.Instructions.Add(new EMEVD.Instruction(1000, 0, new byte[4]));
    var options = new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower };
    var request = JsonSerializer.SerializeToNode(new {
        format = "bb-native-event-recipe-v1",
        original_sha256 = Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(source))).ToLowerInvariant(),
        events = new[] { changed, added }, protected_events = new[] { 77 },
        fingerprints = new Dictionary<long, string> { [88] = NativeEvents.Fingerprint(changed), [99] = NativeEvents.Fingerprint(added) },
    }, options)!;
    string requestPath = Path.Combine(root, "recipe.json");
    string output = Path.Combine(root, "output.emevd.dcx");
    File.WriteAllText(requestPath, request.ToJsonString());
    NativeEvents.Write(source, requestPath, output);
    var actual = EMEVD.Read(output);
    Need(actual.Events.Select(e => e.ID).SequenceEqual(new long[] { 0, 77, 88, 99 }), "event order");
    Need(actual.Events.Select(NativeEvents.Fingerprint).SequenceEqual(new[] { constructor, untouched, changed, added }.Select(NativeEvents.Fingerprint)), "instructions, layers and parameters");
    Need(actual.StringData.SequenceEqual(original.StringData) && actual.LinkedFileOffsets.SequenceEqual(original.LinkedFileOffsets), "links and strings");
    int refused = 0;
    void Refuse(Action<JsonNode> mutate, string fragment) {
        var invalid = request.DeepClone();
        mutate(invalid);
        File.WriteAllText(requestPath, invalid.ToJsonString());
        string target = Path.Combine(root, "refused-" + refused + ".emevd.dcx");
        try { NativeEvents.Write(source, requestPath, target); throw new Exception("accepted invalid recipe"); }
        catch (InvalidDataException ex) { Need(ex.Message.Contains(fragment), ex.Message); }
        Need(!File.Exists(target), "refused recipe published output");
        refused++;
    }
    Refuse(r => r["original_sha256"] = new string('0', 64), "source changed");
    Refuse(r => r["protected_events"]!.AsArray().Add(88), "protected progression");
    Refuse(r => r["events"]!.AsArray().Add(r["events"]![0]!.DeepClone()), "duplicate");
    Refuse(r => r["fingerprints"]!["88"] = new string('0', 64), "fingerprint");
    Refuse(r => r["fingerprints"]!.AsObject().Remove("99"), "coverage");
    Refuse(r => r["events"]![0]!["parameters"]![0]!["instruction_index"] = 9, "instruction index");
    Refuse(r => r["events"]![0]!["parameters"]![0]!["target_start_byte"] = 8, "target outside");
    Console.WriteLine($"native event binary round-trip and {refused} refusal checks passed");
} finally { Directory.Delete(root, true); }
