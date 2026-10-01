using System.Security.Cryptography;
using System.Text.Json;
using SoulsFormats;

// Structured encounter recipes. Shared by BBEventWriter and the enemy writer;
// no script parser, instruction metadata, or external compiler is loaded here.
internal static class NativeEvents
{
    static readonly JsonSerializerOptions Json = new() {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = true,
    };
    static void Need(bool ok, string why) { if (!ok) throw new InvalidDataException(why); }
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();

    // Matches the generalized encounter writer's instruction fingerprint.
    internal static string Fingerprint(EMEVD.Event e) {
        using var data = new MemoryStream();
        using var writer = new BinaryWriter(data);
        writer.Write(e.ID); writer.Write((int)e.RestBehavior);
        foreach (var i in e.Instructions) {
            writer.Write(i.Bank); writer.Write(i.ID); writer.Write(i.ArgData.Length);
            writer.Write(i.ArgData); writer.Write(i.Layer.GetValueOrDefault(uint.MaxValue));
        }
        foreach (var p in e.Parameters) {
            writer.Write(p.InstructionIndex); writer.Write(p.TargetStartByte);
            writer.Write(p.SourceStartByte); writer.Write(p.ByteCount); writer.Write(p.UnkID);
        }
        writer.Flush();
        return Hash(data.ToArray());
    }
    static EMEVD Read(string path) {
        var file = EMEVD.Read(path);
        Need(file.Format == EMEVD.Game.Bloodborne, "native events require Bloodborne EMEVD");
        Need(file.Events.Select(e => e.ID).Distinct().Count() == file.Events.Count, "duplicate original event IDs");
        return file;
    }
    public static int Dump(string source, string output) {
        Need(!File.Exists(output), "native dump output already exists");
        var paths = Directory.Exists(source)
            ? Directory.GetFiles(source, "*.emevd.dcx").Order().ToArray() : new[] { source };
        var files = paths.ToDictionary(path => Path.GetFileName(path)!, path => {
            var file = Read(path);
            return new {
                sha256 = Hash(File.ReadAllBytes(path)), events = file.Events,
                fingerprints = file.Events.ToDictionary(e => e.ID, Fingerprint),
            };
        });
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        File.WriteAllText(output, JsonSerializer.Serialize(files, Json));
        return 0;
    }
    sealed class Recipe {
        public string Format { get; set; } = "";
        public string OriginalSha256 { get; set; } = "";
        public List<EMEVD.Event> Events { get; set; } = [];
        public Dictionary<long, string> Fingerprints { get; set; } = [];
        public List<long> ProtectedEvents { get; set; } = [];
    }
    public static int Write(string source, string request, string output) {
        Need(!File.Exists(output), "native event output already exists");
        var recipe = JsonSerializer.Deserialize<Recipe>(File.ReadAllText(request), Json)!;
        Need(recipe.Format == "bb-native-event-recipe-v1", "unsupported native event recipe");
        Need(Hash(File.ReadAllBytes(source)) == recipe.OriginalSha256, "native event source changed");
        var original = Read(source);
        var before = original.Events.ToDictionary(e => e.ID, Fingerprint);
        var ids = recipe.Events.Select(e => e.ID).ToList();
        Need(ids.Count > 0 && ids.Distinct().Count() == ids.Count, "empty or duplicate native event edits");
        Need(ids.ToHashSet().SetEquals(recipe.Fingerprints.Keys), "native recipe fingerprint coverage differs");
        Need(!ids.Intersect(recipe.ProtectedEvents).Any(), "native recipe changes protected progression");
        Need(recipe.ProtectedEvents.All(before.ContainsKey), "missing protected progression event");
        foreach (var e in recipe.Events) {
            Need(e.ID >= 0 && Enum.IsDefined(e.RestBehavior), "invalid native event identity or restart behavior");
            foreach (var p in e.Parameters) {
                Need(p.InstructionIndex >= 0 && p.InstructionIndex < e.Instructions.Count,
                    "native parameter instruction index outside event");
                Need(p.ByteCount > 0 && p.TargetStartByte >= 0 && p.SourceStartByte >= 0
                    && p.TargetStartByte <= e.Instructions[(int)p.InstructionIndex].ArgData.Length - p.ByteCount,
                    "native parameter target outside instruction arguments");
            }
            Need(Fingerprint(e) == recipe.Fingerprints[e.ID], $"native recipe event {e.ID} differs from fingerprint");
        }
        var merged = EMEVD.Read(original.Write());
        foreach (var e in recipe.Events) {
            int at = merged.Events.FindIndex(old => old.ID == e.ID);
            if (at < 0) merged.Events.Add(e); else merged.Events[at] = e;
        }
        byte[] bytes = merged.Write();
        var persisted = EMEVD.Read(bytes);
        Need(persisted.Events.Select(e => e.ID).SequenceEqual(merged.Events.Select(e => e.ID)), "native event order changed");
        Need(persisted.LinkedFileOffsets.SequenceEqual(original.LinkedFileOffsets)
            && persisted.StringData.SequenceEqual(original.StringData), "native event link or string data changed");
        foreach (var e in persisted.Events)
            Need(Fingerprint(e) == (recipe.Fingerprints.TryGetValue(e.ID, out var fp) ? fp : before[e.ID]),
                $"native event {e.ID} failed persisted verification");
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(output))!);
        File.WriteAllBytes(output, bytes);
        return 0;
    }
}
