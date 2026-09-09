using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using SoulsFormats;

internal static class BossCanary
{
    internal const string Adapter = "bsb-at-cleric-v1";
    internal const long CompletionEvent = 12411700;
    internal static readonly long[] ChangedEvents = [12411701,12411702,12414702,12414703,12414704,12414707,12414708,12414710,12414720];
    const string OriginalHash = "f6a580b0e827dd113393bd115fa0ce54f84b9f8f8ec1451ee62ba84d532fba17";
    static readonly JsonSerializerOptions Json = new() {PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower, PropertyNameCaseInsensitive = true, WriteIndented = true};
    static void Need(bool condition, string why) { if (!condition) throw new InvalidDataException(why); }
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    internal static string Fingerprint(EMEVD.Event e) {
        var text = new StringBuilder();
        text.Append(e.ID.ToString(CultureInfo.InvariantCulture)).Append('|').Append(e.RestBehavior).Append('|');
        foreach (var instruction in e.Instructions)
            text.Append(FormattableString.Invariant($"{instruction.Bank}:{instruction.ID}:{Convert.ToHexString(instruction.ArgData)}:{instruction.Layer};"));
        foreach (var p in e.Parameters)
            text.Append(FormattableString.Invariant($"{p.InstructionIndex},{p.TargetStartByte},{p.SourceStartByte},{p.ByteCount},{p.UnkID};"));
        return Hash(Encoding.UTF8.GetBytes(text.ToString()));
    }
    static EMEVD.Event Event(EMEVD file, long id) {
        var rows = file.Events.Where(e => e.ID == id).ToList();
        Need(rows.Count == 1, $"missing or ambiguous boss event {id}");
        return rows[0];
    }
    public static int Inspect(string path) {
        var file = EMEVD.Read(path);
        Console.WriteLine(JsonSerializer.Serialize(ChangedEvents.ToDictionary(id => id, id => Fingerprint(Event(file, id))), Json));
        return 0;
    }
    public static int ExportRecipe(string path) {
        var file = EMEVD.Read(path);
        Console.WriteLine(JsonSerializer.Serialize(ChangedEvents.Select(id => Event(file, id)).ToArray(), Json));
        return 0;
    }
    internal static EMEVD NativeRecipe() {
        using var stream = typeof(BossCanary).Assembly.GetManifestResourceStream("boss-event-recipe.json")!;
        return new EMEVD(EMEVD.Game.Bloodborne) { Events = JsonSerializer.Deserialize<List<EMEVD.Event>>(stream, Json)! };
    }

    // Compiled events are used only as a development oracle. Copy the nine
    // hash-pinned events into the original file, not a whole compiler rewrite.
    internal static byte[] Merge(EMEVD original, EMEVD compiled, IReadOnlyDictionary<long, string> pins) {
        Need(original.Format == EMEVD.Game.Bloodborne && compiled.Format == EMEVD.Game.Bloodborne, "boss adapter requires Bloodborne events");
        Need(pins.Keys.ToHashSet().SetEquals(ChangedEvents), "boss event pin set differs from adapter");
        Need(original.Events.Select(e => e.ID).Distinct().Count() == original.Events.Count, "duplicate original event IDs");
        var before = original.Events.ToDictionary(e => e.ID, Fingerprint);
        Need(before.ContainsKey(CompletionEvent), "missing AP completion event");
        var expected = new Dictionary<long, string>(before);
        foreach (long id in ChangedEvents) {
            Event(original, id);
            var replacement = Event(compiled, id);
            Need(Fingerprint(replacement) == pins[id], $"compiled boss event {id} does not match reviewed adapter");
            expected[id] = pins[id];
        }
        // Deep copy so failed validation never mutates the caller's source object.
        var merged = EMEVD.Read(original.Write());
        foreach (long id in ChangedEvents) merged.Events[merged.Events.FindIndex(e => e.ID == id)] = Event(compiled, id);
        byte[] bytes = merged.Write();
        var check = EMEVD.Read(bytes);
        Need(check.Events.Select(e => e.ID).SequenceEqual(original.Events.Select(e => e.ID)), "boss event set or order changed");
        Need(check.LinkedFileOffsets.SequenceEqual(original.LinkedFileOffsets) && check.StringData.SequenceEqual(original.StringData), "event link/string data changed");
        foreach (var e in check.Events) Need(Fingerprint(e) == expected[e.ID], $"persisted boss event verification failed: {e.ID}");
        Need(Fingerprint(Event(check, CompletionEvent)) == before[CompletionEvent], "AP completion event changed");
        return bytes;
    }

    public static int Run(string planPath, string gamePath, string defsPath, string mapsPath,
        string scriptsPath, string originalEvent, string? compiledEvent, string outputPath)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(planPath));
        var root = document.RootElement;
        Need(root.GetProperty("boss_adapter").GetString() == Adapter, "unsupported boss adapter");
        var plan = root.Deserialize<Manifest>(Json)!;
        Need(plan.Swaps.Count == 1, "boss canary requires exactly one logical placement");
        var swap = plan.Swaps[0];
        Need(swap.LogicalKey == "m24_01_00_00:c5000_0000" && swap.Target == new Archetype("c2090",209000,209000,0), "unsupported boss donor or destination");
        var expectedKeys = new[] {"m24_01_00_00:c5000_0000", "m24_01_00_01:c5000_0000", "m24_01_00_11:c5000_0000"};
        Need(swap.DestinationKeys.Count == 3 && swap.DestinationKeys.ToHashSet().SetEquals(expectedKeys), "boss canary requires all three original map states");
        Need(swap.DestinationSources.Keys.ToHashSet().SetEquals(expectedKeys)
            && swap.DestinationSources.Values.All(a => a == new Archetype("c5000",500241,500241,0)), "boss source tuple drift");
        Need(Hash(File.ReadAllBytes(originalEvent)) == OriginalHash, "unsupported original Central Yharnam EMEVD");
        using var pinStream = typeof(BossCanary).Assembly.GetManifestResourceStream("boss-event-pins.json")!;
        var pins = JsonSerializer.Deserialize<Dictionary<long, string>>(pinStream)!;
        byte[] events = Merge(EMEVD.Read(originalEvent), compiledEvent == null ? NativeRecipe() : EMEVD.Read(compiledEvent), pins);
        string output = Path.GetFullPath(outputPath), parent = Path.GetDirectoryName(output)!;
        Need(!Directory.Exists(output) && !File.Exists(output), "boss output must not exist");
        foreach (string input in new[] {planPath, gamePath, defsPath, originalEvent, compiledEvent, mapsPath, scriptsPath}.OfType<string>()) {
            string directory = Directory.Exists(input) ? Path.GetFullPath(input) : Path.GetDirectoryName(Path.GetFullPath(input))!;
            string relative = Path.GetRelativePath(directory, output);
            Need(relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal) || Path.IsPathRooted(relative), "boss output must be outside input directories");
        }
        Directory.CreateDirectory(parent);
        string stage = Path.Combine(parent, ".bb-boss-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(stage);
        try {
            string overlay = Path.Combine(stage, "overlay");
            ScalingTransplant.Run(planPath, gamePath, defsPath, mapsPath, scriptsPath, overlay, bossPrepared: true);
            string eventPath = Path.Combine(overlay, "dvdroot_ps4/event/m24_01_00_00.emevd.dcx");
            Directory.CreateDirectory(Path.GetDirectoryName(eventPath)!);
            File.WriteAllBytes(eventPath, events);
            Need(Hash(File.ReadAllBytes(eventPath)) == Hash(events), "boss event copy verification failed");
            var files = Directory.GetFiles(overlay, "*", SearchOption.AllDirectories)
                .OrderBy(path => Path.GetRelativePath(overlay, path), StringComparer.Ordinal)
                .Select(path => new { path = Path.GetRelativePath(overlay, path).Replace('\\', '/'),
                    sha256 = Hash(File.ReadAllBytes(path)), size = new FileInfo(path).Length }).ToArray();
            File.WriteAllText(Path.Combine(overlay, "boss-adapter-report.json"), JsonSerializer.Serialize(new {
                format = "bb-boss-adapter-v1", adapter = Adapter, applied = true, runtime_validated = false,
                ap_location = "boss_cleric_beast", completion_event = CompletionEvent,
                original_event_sha256 = OriginalHash, output_event_sha256 = Hash(events),
                changed_events = ChangedEvents, patched_event_fingerprints = pins,
                files,
                warning = "Experimental single encounter. Entrance, combat phases, arena fit and AP completion need live validation.",
            }, Json));
            Directory.Move(overlay, output);
            Console.WriteLine($"boss_adapter={Adapter} events={ChangedEvents.Length} ap_completion_preserved={CompletionEvent} output={output}");
            return 0;
        }
        finally {
            if (Directory.Exists(stage) && Path.GetDirectoryName(stage) == parent && Path.GetFileName(stage).StartsWith(".bb-boss-", StringComparison.Ordinal)) Directory.Delete(stage, true);
        }
    }
}
