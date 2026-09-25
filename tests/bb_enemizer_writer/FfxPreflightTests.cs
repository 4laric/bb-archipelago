using System.Security.Cryptography;
using System.Text.Json;
using SoulsFormats;

internal static class FfxPreflightTests
{
    internal static void Run()
    {
        void Need(bool value, string message) { if (!value) throw new Exception(message); }
        void Refused(Action action, string reason) {
            try { action(); throw new Exception("expected FFX preflight refusal: " + reason); }
            catch (InvalidDataException error) { Need(error.Message.Contains(reason), error.Message); }
        }
        string Hash(byte[] value) => Convert.ToHexString(SHA256.HashData(value)).ToLowerInvariant();
        string root = Path.Combine(Path.GetTempPath(), "bb-ffx-preflight-" + Guid.NewGuid().ToString("N"));
        string originals = Path.Combine(root, "originals"), plan = Path.Combine(root, "plan.json");
        Directory.CreateDirectory(originals);
        const string dest = "frpg_sfxbnd_m34.ffxbnd.dcx";
        const string sourceA = "frpg_sfxbnd_m35.ffxbnd.dcx";
        const string sourceB = "frpg_sfxbnd_m36.ffxbnd.dcx";
        BinderFile Entry(int id, string name, byte[] bytes) =>
            new(Binder.FileFlags.Flag1, id, "N:\\sfx\\" + name, bytes);
        BND4 Bank(params BinderFile[] entries) {
            var bank = new BND4 { Compression = DCX.Type.DCX_DFLT_10000_44_9, Version = "FFXPREFL" };
            bank.Files.AddRange(entries);
            return bank;
        }
        void Write(string name, BND4 bank) => bank.Write(Path.Combine(originals, name));
        void Plan(int requiredA = 111) {
            object Merge(string source, int effect) => new {
                source_file = source, source_sha256 = Hash(File.ReadAllBytes(Path.Combine(originals, source))),
                destination_file = dest, destination_sha256 = Hash(File.ReadAllBytes(Path.Combine(originals, dest))),
                required_effect_ids = new[] { effect }, policy = "preserve_destination_union_source_v1",
            };
            File.WriteAllText(plan, JsonSerializer.Serialize(new {
                boss_ffx_merges = new[] { Merge(sourceA, requiredA), Merge(sourceB, 222) },
            }));
        }
        var destination = Bank(Entry(7, "tex/shared.tpf", [1]));
        var donorA = Bank(Entry(11, "effect/f000000111.fxr", [11]),
            Entry(12, "tex/shared.tpf", [2]), Entry(13, "model/source-shared.flver", [10]));
        var donorB = Bank(Entry(21, "effect/f000000222.fxr", [22]),
            Entry(22, "tex/shared.tpf", [3]), Entry(23, "model/source-shared.flver", [11]));
        try {
            Write(dest, destination); Write(sourceA, donorA); Write(sourceB, donorB); Plan();
            var originalHashes = Directory.GetFiles(originals).ToDictionary(
                file => Path.GetFileName(file), file => Hash(File.ReadAllBytes(file)));
            string planHash = Hash(File.ReadAllBytes(plan));
            string report = Path.Combine(root, "report.json");
            Need(FfxBundleTransplant.Preflight(plan, originals, report) == 0, "preflight returns success");
            using (var document = JsonDocument.Parse(File.ReadAllText(report))) {
                var value = document.RootElement;
                Need(value.GetProperty("format").GetString() == "bb-boss-ffx-preflight-v1", "preflight report format");
                var rows = value.GetProperty("conflicts").EnumerateArray().Select(row => (
                    Destination: row.GetProperty("destination_file").GetString()!,
                    Left: row.GetProperty("left_file").GetString()!,
                    Right: row.GetProperty("right_file").GetString()!,
                    Entry: row.GetProperty("entry").GetString()!)).ToList();
                Need(rows.Count == 3, "native/source and source/source conflicts all reported");
                Need(rows.SequenceEqual(new[] {
                    (dest, dest, sourceA, "tex/shared.tpf"),
                    (dest, dest, sourceB, "tex/shared.tpf"),
                    (dest, sourceA, sourceB, "model/source-shared.flver"),
                }), "conflicts are deterministic with one differing entry per bank pair");
            }
            Need(Directory.GetFiles(originals).Length == 3 && originalHashes.All(pair =>
                Hash(File.ReadAllBytes(Path.Combine(originals, pair.Key))) == pair.Value),
                "preflight leaves every original bank untouched");
            Need(Hash(File.ReadAllBytes(plan)) == planHash && Directory.GetFiles(root).Length == 2,
                "preflight writes only its requested report");
            Refused(() => FfxBundleTransplant.Preflight(plan, originals, Path.Combine(originals, "report.json")),
                "outside original SFX inputs");

            donorA.Files.Single(file => file.Name.EndsWith("shared.tpf")).Bytes = [1];
            donorA.Files.Single(file => file.Name.EndsWith("source-shared.flver")).Bytes = [10];
            donorB.Files.Single(file => file.Name.EndsWith("shared.tpf")).Bytes = [1];
            donorB.Files.Single(file => file.Name.EndsWith("source-shared.flver")).Bytes = [10];
            Write(sourceA, donorA); Write(sourceB, donorB); Plan();
            string equalReport = Path.Combine(root, "equal-report.json");
            FfxBundleTransplant.Preflight(plan, originals, equalReport);
            using (var document = JsonDocument.Parse(File.ReadAllText(equalReport)))
                Need(document.RootElement.GetProperty("conflicts").GetArrayLength() == 0,
                    "same-key equal bytes are compatible");
            Write(sourceA, Bank(Entry(11, "effect/f000000111.fxr", [99])));
            string driftReport = Path.Combine(root, "drift-report.json");
            Refused(() => FfxBundleTransplant.Preflight(plan, originals, driftReport), "provenance drift");
            Need(!File.Exists(driftReport), "invalid provenance cannot emit a compatibility report");
            Write(sourceA, donorA); Plan(999);
            string rootsReport = Path.Combine(root, "roots-report.json");
            Refused(() => FfxBundleTransplant.Preflight(plan, originals, rootsReport), "declared FFX effect missing");
            Need(!File.Exists(rootsReport), "missing required root cannot emit a compatibility report");
            destination.Files.Add(Entry(7, "tex/duplicate-id.tpf", [44]));
            Write(dest, destination); Plan();
            string indexReport = Path.Combine(root, "index-report.json");
            Refused(() => FfxBundleTransplant.Preflight(plan, originals, indexReport), "ambiguous FFX entry ID");
            Need(!File.Exists(indexReport), "ambiguous index cannot emit a compatibility report");
        }
        finally {
            Directory.Delete(root, recursive: true);
        }
    }
}
