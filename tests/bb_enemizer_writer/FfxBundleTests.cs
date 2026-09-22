using System.Security.Cryptography;
using System.Text.Json;
using SoulsFormats;

internal static class FfxBundleTests
{
    internal static void Run()
    {
        int assertions = 0;
        void Need(bool value, string message) { assertions++; if (!value) throw new Exception(message); }
        void Refused(Action action, string fragment) {
            try { action(); throw new Exception("expected FFX refusal: " + fragment); }
            catch (InvalidDataException error) { Need(error.Message.Contains(fragment), error.Message); }
        }
        string Hash(byte[] value) => Convert.ToHexString(SHA256.HashData(value)).ToLowerInvariant();
        string root = Path.Combine(Path.GetTempPath(), "bb-ffx-bundle-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(root);
        try {
            string originals = Path.Combine(root, "originals"), output = Path.Combine(root, "output"), plan = Path.Combine(root, "plan.json");
            Directory.CreateDirectory(originals);
            const string m35 = "frpg_sfxbnd_m35.ffxbnd.dcx", m36 = "frpg_sfxbnd_m36.ffxbnd.dcx", m34 = "frpg_sfxbnd_m34.ffxbnd.dcx";
            BinderFile BinderEntry(int id, string name, byte[] bytes, bool compressed = false) => new(
                compressed ? Binder.FileFlags.Flag1 | Binder.FileFlags.Compressed : Binder.FileFlags.Flag1, id, name, bytes) {
                    CompressionType = compressed ? DCX.Type.DCX_DFLT_10000_44_9 : DCX.Type.Zlib,
                };
            void Write(string name, BND4 binder) => binder.Write(Path.Combine(originals, name));
            var donor35 = new BND4 { Compression = DCX.Type.DCX_DFLT_10000_44_9, Version = "FFX35TEST" };
            donor35.Files.Add(BinderEntry(70, "N:\\sfx\\effect\\f000000111.fxr", [1, 1, 1], compressed: true));
            donor35.Files.Add(BinderEntry(71, "N:\\sfx\\model\\m35.flver", [2, 2]));
            donor35.Files.Add(BinderEntry(72, "N:\\sfx\\tex\\m35.tpf", [3, 3, 3, 3]));
            donor35.Files.Add(BinderEntry(73, "N:\\sfx\\tex\\shared.tpf", [4, 4]));
            Write(m35, donor35);
            var donor36 = new BND4 { Compression = DCX.Type.DCX_DFLT_10000_44_9, Version = "FFX36TEST" };
            donor36.Files.Add(BinderEntry(80, "N:\\sfx\\effect\\f000000222.fxr", [5, 5, 5]));
            donor36.Files.Add(BinderEntry(81, "N:\\sfx\\model\\m36.flver", [6, 6]));
            donor36.Files.Add(BinderEntry(82, "N:\\sfx\\tex\\m36.tpf", [7, 7]));
            Write(m36, donor36);
            var destination = new BND4 { Compression = DCX.Type.DCX_DFLT_10000_44_9, Version = "FFX34TEST" };
            destination.Files.Add(BinderEntry(7, "N:\\sfx\\effect\\retained.fxr", [8, 8, 8]));
            destination.Files.Add(BinderEntry(19, "N:\\sfx\\tex\\shared.tpf", [4, 4]));
            Write(m34, destination);
            string source35Path = Path.Combine(originals, m35), source36Path = Path.Combine(originals, m36), destinationPath = Path.Combine(originals, m34);
            var originalDestination = BND4.Read(destinationPath); byte[] originalDestinationBytes = File.ReadAllBytes(destinationPath);
            object FirstMerge() => new {
                source_file = m35, source_sha256 = Hash(File.ReadAllBytes(source35Path)), destination_file = m34,
                destination_sha256 = Hash(File.ReadAllBytes(destinationPath)), required_effect_ids = new[] { 111 }, policy = "preserve_destination_union_source_v1",
            };
            object SecondMerge() => new {
                source_file = m36, source_sha256 = Hash(File.ReadAllBytes(source36Path)), destination_file = m34,
                destination_sha256 = Hash(File.ReadAllBytes(destinationPath)), required_effect_ids = new[] { 222 }, policy = "preserve_destination_union_source_v1",
            };
            void WritePlan(params object[] rows) => File.WriteAllText(plan, JsonSerializer.Serialize(new { boss_ffx_merges = rows }));

            WritePlan(FirstMerge(), SecondMerge());
            var applied = FfxBundleTransplant.Apply(plan, originals, output);
            Need(applied.Count == 2 && applied.Sum(row => row.ImportedEntries.Count) == 6,
                "both donor binders contribute their complete non-duplicate closure");
            var writtenPath = Path.Combine(output, m34); var written = BND4.Read(writtenPath);
            Need(written.Files.Count == 8 && written.Files.Take(2).Select(item => item.ID).SequenceEqual(new[] { 7, 19 }),
                "destination entries and IDs retain their original order before appended imports");
            Need(written.Files.Take(2).Select(item => Hash(item.Bytes)).SequenceEqual(originalDestination.Files.Select(item => Hash(item.Bytes))),
                "destination entry bytes remain unchanged");
            Need(written.Version == originalDestination.Version && written.Format == originalDestination.Format && written.Unk04 == originalDestination.Unk04
                && written.Unk05 == originalDestination.Unk05 && written.BigEndian == originalDestination.BigEndian && written.BitBigEndian == originalDestination.BitBigEndian
                && written.Unicode == originalDestination.Unicode && written.Extended == originalDestination.Extended && written.Compression == originalDestination.Compression,
                "destination BND4 header metadata remains unchanged");
            Need(written.Files.Count(item => item.Name.EndsWith("shared.tpf", StringComparison.OrdinalIgnoreCase)) == 1
                && written.Files.Single(item => item.Name.EndsWith("shared.tpf", StringComparison.OrdinalIgnoreCase)).ID == 19,
                "identical donor entry deduplicates without replacing destination identity");
            Need(new[] { "f000000111.fxr", "m35.flver", "m35.tpf", "f000000222.fxr", "m36.flver", "m36.tpf" }
                .All(name => written.Files.Any(item => item.Name.EndsWith(name, StringComparison.OrdinalIgnoreCase))),
                "full FXR, FLVER, and TPF donor closure is present");
            var compressed = written.Files.Single(item => item.Name.EndsWith("f000000111.fxr", StringComparison.OrdinalIgnoreCase));
            Need(compressed.Flags.HasFlag(Binder.FileFlags.Compressed) && compressed.CompressionType == DCX.Type.DCX_DFLT_10000_44_9,
                "import preserves non-default per-entry compression metadata");
            Need(Hash(File.ReadAllBytes(destinationPath)) == Hash(originalDestinationBytes),
                "merge never modifies or redirects original binder inputs");
            Need(applied.All(row => row.OutputSha256 == Hash(File.ReadAllBytes(writtenPath))),
                "each merge receipt pins the one verified shared destination output");

            File.WriteAllBytes(source35Path, File.ReadAllBytes(source35Path).Append((byte)0).ToArray());
            Refused(() => FfxBundleTransplant.Apply(plan, originals, Path.Combine(root, "pin-drift")), "FFX binder provenance drift");
            Write(m35, donor35);
            WritePlan(new { source_file = m35, source_sha256 = Hash(File.ReadAllBytes(source35Path)), destination_file = m34,
                destination_sha256 = Hash(File.ReadAllBytes(destinationPath)), required_effect_ids = new[] { 999 }, policy = "preserve_destination_union_source_v1" });
            Refused(() => FfxBundleTransplant.Apply(plan, originals, Path.Combine(root, "missing-effect")), "declared FFX effect missing from donor binder");
            WritePlan(FirstMerge()); Directory.CreateDirectory(Path.Combine(root, "no-overwrite")); File.WriteAllBytes(Path.Combine(root, "no-overwrite", m34), [9]);
            Refused(() => FfxBundleTransplant.Apply(plan, originals, Path.Combine(root, "no-overwrite")), "refusing to replace staged FFX output");
            var conflict = BND4.Read(source35Path); conflict.Files.Single(item => item.Name.EndsWith("shared.tpf")).Bytes = [99]; Write(m35, conflict);
            WritePlan(new { source_file = m35, source_sha256 = Hash(File.ReadAllBytes(source35Path)), destination_file = m34,
                destination_sha256 = Hash(File.ReadAllBytes(destinationPath)), required_effect_ids = new[] { 111 }, policy = "preserve_destination_union_source_v1" });
            Refused(() => FfxBundleTransplant.Apply(plan, originals, Path.Combine(root, "conflict")), "conflicting FFX entry: tex/shared.tpf");
            Write(m35, donor35);
            var duplicateId = new BND4 { Compression = DCX.Type.DCX_DFLT_10000_44_9 };
            duplicateId.Files.Add(BinderEntry(1, "N:\\sfx\\effect\\f000000333.fxr", [3])); duplicateId.Files.Add(BinderEntry(1, "N:\\sfx\\tex\\other.tpf", [4]));
            const string m37 = "frpg_sfxbnd_m37.ffxbnd.dcx"; Write(m37, duplicateId);
            WritePlan(new { source_file = m37, source_sha256 = Hash(File.ReadAllBytes(Path.Combine(originals, m37))), destination_file = m34,
                destination_sha256 = Hash(File.ReadAllBytes(destinationPath)), required_effect_ids = new[] { 333 }, policy = "preserve_destination_union_source_v1" });
            Refused(() => FfxBundleTransplant.Apply(plan, originals, Path.Combine(root, "duplicate-id")), "ambiguous FFX entry ID");
            var duplicateName = new BND4 { Compression = DCX.Type.DCX_DFLT_10000_44_9 };
            duplicateName.Files.Add(BinderEntry(1, "N:\\sfx\\effect\\f000000444.fxr", [4])); duplicateName.Files.Add(BinderEntry(2, "N:\\sfx\\effect\\f000000444.fxr", [4]));
            const string m38 = "frpg_sfxbnd_m38.ffxbnd.dcx"; Write(m38, duplicateName);
            WritePlan(new { source_file = m38, source_sha256 = Hash(File.ReadAllBytes(Path.Combine(originals, m38))), destination_file = m34,
                destination_sha256 = Hash(File.ReadAllBytes(destinationPath)), required_effect_ids = new[] { 444 }, policy = "preserve_destination_union_source_v1" });
            Refused(() => FfxBundleTransplant.Apply(plan, originals, Path.Combine(root, "duplicate-name")), "ambiguous FFX entry name");
            WritePlan(FirstMerge(), FirstMerge());
            Refused(() => FfxBundleTransplant.Read(plan), "duplicate FFX merge");
            WritePlan(FirstMerge());
            var covered = new BossSfxTransplant.Applied("m35_00_00_00", "m34_00_00_00", "ap_lf_sfx_1", 900, 980027, 111,
                new string('a', 64));
            FfxBundleTransplant.VerifyCoverage(plan, [covered]);
            Refused(() => FfxBundleTransplant.VerifyCoverage(plan, [covered with { SourceMap = "m36_00_00_00" }]),
                "FFX merge required effects do not exactly cover added map SFX");
            Refused(() => FfxBundleTransplant.VerifyCoverage(plan, [covered with { DestinationMap = "m33_00_00_00" }]),
                "FFX merge required effects do not exactly cover added map SFX");
            Refused(() => FfxBundleTransplant.VerifyCoverage(plan, [covered with { EffectId = 222 }]),
                "FFX merge required effects do not exactly cover added map SFX");
            WritePlan(new { source_file = m35, source_sha256 = Hash(File.ReadAllBytes(source35Path)), destination_file = m34,
                destination_sha256 = Hash(File.ReadAllBytes(destinationPath)), required_effect_ids = new[] { 111, 222 }, policy = "preserve_destination_union_source_v1" });
            Refused(() => FfxBundleTransplant.VerifyCoverage(plan, [covered]),
                "FFX merge required effects do not exactly cover added map SFX");
            WritePlan(FirstMerge(), SecondMerge());
            Refused(() => FfxBundleTransplant.VerifyCoverage(plan, [covered]),
                "FFX merge manifest does not exactly cover added map SFX");
            File.WriteAllText(plan, "{}");
            Refused(() => FfxBundleTransplant.VerifyCoverage(plan, [covered]),
                "FFX merge manifest does not exactly cover added map SFX");
            WritePlan(new { source_file = m35, source_sha256 = Hash(File.ReadAllBytes(source35Path)), destination_file = m35,
                destination_sha256 = Hash(File.ReadAllBytes(source35Path)), required_effect_ids = new[] { 111 }, policy = "preserve_destination_union_source_v1" });
            FfxBundleTransplant.VerifyCoverage(plan, [covered with { DestinationMap = "m35_00_00_00" }]);
            var reused = FfxBundleTransplant.Apply(plan, originals, Path.Combine(root, "same-bank"));
            var reusedBank = BND4.Read(Path.Combine(root, "same-bank", m35));
            Need(reused.Count == 1 && reused[0].ImportedEntries.Count == 0 && reused[0].RetainedEntryCount == 4,
                "shared-map effect bank reuse retains all four entries with no imports");
            Need(reusedBank.Files.Select(file => (file.ID, file.Name, Hash(file.Bytes))).SequenceEqual(
                BND4.Read(source35Path).Files.Select(file => (file.ID, file.Name, Hash(file.Bytes)))),
                "shared-map effect bank reuse preserves original entry identities and bytes");
            WritePlan(new { source_file = m35, source_sha256 = Hash(File.ReadAllBytes(source35Path)), destination_file = m35,
                destination_sha256 = new string('0', 64), required_effect_ids = new[] { 111 }, policy = "preserve_destination_union_source_v1" });
            Refused(() => FfxBundleTransplant.Read(plan), "same-bank FFX reuse requires identical");
            Console.WriteLine($"PASS: {assertions} FFX bundle transplant assertions");
        } finally {
            if (Path.GetDirectoryName(root) != Path.GetTempPath().TrimEnd(Path.DirectorySeparatorChar) || !Path.GetFileName(root).StartsWith("bb-ffx-bundle-")) throw new Exception("unsafe cleanup path");
            Directory.Delete(root, true);
        }
    }
}
