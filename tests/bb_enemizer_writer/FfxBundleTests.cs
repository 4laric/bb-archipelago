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
            void WritePlanWithRequirements(object[] rows, object[] requirements) => File.WriteAllText(plan,
                JsonSerializer.Serialize(new { boss_ffx_merges = rows, boss_emevd_ffx_requirements = requirements }));

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
                "FFX merge required effects do not exactly cover declared SFX dependencies");
            Refused(() => FfxBundleTransplant.VerifyCoverage(plan, [covered with { DestinationMap = "m33_00_00_00" }]),
                "FFX merge required effects do not exactly cover declared SFX dependencies");
            Refused(() => FfxBundleTransplant.VerifyCoverage(plan, [covered with { EffectId = 222 }]),
                "FFX merge required effects do not exactly cover declared SFX dependencies");
            WritePlan(new { source_file = m35, source_sha256 = Hash(File.ReadAllBytes(source35Path)), destination_file = m34,
                destination_sha256 = Hash(File.ReadAllBytes(destinationPath)), required_effect_ids = new[] { 111, 222 }, policy = "preserve_destination_union_source_v1" });
            Refused(() => FfxBundleTransplant.VerifyCoverage(plan, [covered]),
                "FFX merge required effects do not exactly cover declared SFX dependencies");
            WritePlan(FirstMerge(), SecondMerge());
            Refused(() => FfxBundleTransplant.VerifyCoverage(plan, [covered]),
                "FFX merge manifest does not exactly cover declared SFX dependencies");
            File.WriteAllText(plan, "{}");
            Refused(() => FfxBundleTransplant.VerifyCoverage(plan, [covered]),
                "FFX merge manifest does not exactly cover declared SFX dependencies");
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

            string events = Path.Combine(root, "events"), finalEvents = Path.Combine(root, "final-events");
            Directory.CreateDirectory(events); Directory.CreateDirectory(finalEvents);
            byte[] SfxArgs(int effect) => new[] { 4, 500, -1, effect }
                .SelectMany(value => BitConverter.GetBytes(value)).ToArray();
            EMEVD OneSfxEvent(long id, int effect) {
                var file = new EMEVD(EMEVD.Game.Bloodborne); var item = new EMEVD.Event(id);
                item.Instructions.Add(new EMEVD.Instruction(2006, 3, SfxArgs(effect))); file.Events.Add(item); return file;
            }
            const string sourceEventFile = "m35_00_00_00.emevd.dcx", destinationEventFile = "m34_00_00_00.emevd.dcx";
            string sourceEventPath = Path.Combine(events, sourceEventFile), finalEventPath = Path.Combine(finalEvents, destinationEventFile);
            File.WriteAllBytes(sourceEventPath, OneSfxEvent(500, 111).Write());
            File.WriteAllBytes(finalEventPath, OneSfxEvent(900, 111).Write());
            object Requirement(string hash) => new {
                format = "bb-boss-emevd-ffx-requirement-v1", source_map = "m35_00_00_00",
                destination_map = "m34_00_00_00", source_event_file = sourceEventFile,
                source_event_sha256 = hash, source_event_id = 500, destination_event_file = destinationEventFile,
                destination_event_id = 900, effect_id = 111,
            };
            var encounter = new BossEncounter.Encounter(destinationEventFile, new string('0', 64), [900],
                new Dictionary<long, string>(), [30]);
            WritePlanWithRequirements([FirstMerge()], [Requirement(Hash(File.ReadAllBytes(sourceEventPath)))]);
            var requirements = FfxBundleTransplant.ValidateEmevdInputs(plan, events, [encounter]);
            Need(requirements.Count == 1 && requirements[0].EffectId == 111,
                "source-pinned EMEVD effect requirement binds one reviewed destination edit");
            FfxBundleTransplant.ValidateEmevdFinal(requirements, finalEvents);
            FfxBundleTransplant.VerifyCoverage(plan, []);
            FfxBundleTransplant.VerifyCoverage(plan, [covered]);
            File.WriteAllBytes(sourceEventPath, OneSfxEvent(500, 222).Write());
            Refused(() => FfxBundleTransplant.ValidateEmevdInputs(plan, events, [encounter]),
                "EMEVD FFX source provenance drift");
            var duplicateEffect = OneSfxEvent(500, 111);
            duplicateEffect.Events[0].Instructions.Add(new EMEVD.Instruction(2006, 3, SfxArgs(111)));
            File.WriteAllBytes(sourceEventPath, duplicateEffect.Write());
            WritePlanWithRequirements([FirstMerge()], [Requirement(Hash(File.ReadAllBytes(sourceEventPath)))]);
            Refused(() => FfxBundleTransplant.ValidateEmevdInputs(plan, events, [encounter]),
                "exactly one declared SpawnOneshotSFX effect");
            object CountedRequirement(int count) {
                var node = System.Text.Json.Nodes.JsonNode.Parse(JsonSerializer.Serialize(
                    Requirement(Hash(File.ReadAllBytes(sourceEventPath)))))!;
                node["occurrence_count"] = count; return node;
            }
            WritePlanWithRequirements([FirstMerge()], [CountedRequirement(2)]);
            var repeatedRequirements = FfxBundleTransplant.ValidateEmevdInputs(plan, events, [encounter]);
            Need(repeatedRequirements[0].OccurrenceCount == 2, "explicit repeated source effect count is preserved");
            var repeatedFinal = OneSfxEvent(900, 111);
            repeatedFinal.Events[0].Instructions.Add(new EMEVD.Instruction(2006, 3, SfxArgs(111)));
            File.WriteAllBytes(finalEventPath, repeatedFinal.Write());
            FfxBundleTransplant.ValidateEmevdFinal(repeatedRequirements, finalEvents);
            FfxBundleTransplant.VerifyCoverage(plan, []);
            Need(FfxBundleTransplant.Read(plan).Single().RequiredEffectIds.SequenceEqual(new[] { 111 }),
                "repeated event occurrences require one effect asset, not duplicate roots");
            File.WriteAllBytes(finalEventPath, OneSfxEvent(900, 111).Write());
            Refused(() => FfxBundleTransplant.ValidateEmevdFinal(repeatedRequirements, finalEvents),
                "exactly 2 declared SpawnOneshotSFX");
            repeatedFinal.Events[0].Instructions.Add(new EMEVD.Instruction(2006, 3, SfxArgs(111)));
            File.WriteAllBytes(finalEventPath, repeatedFinal.Write());
            Refused(() => FfxBundleTransplant.ValidateEmevdFinal(repeatedRequirements, finalEvents),
                "exactly 2 declared SpawnOneshotSFX");
            duplicateEffect.Events[0].Parameters.Add(new EMEVD.Parameter(1, 12, 0, 4));
            File.WriteAllBytes(sourceEventPath, duplicateEffect.Write());
            WritePlanWithRequirements([FirstMerge()], [CountedRequirement(2)]);
            Refused(() => FfxBundleTransplant.ValidateEmevdInputs(plan, events, [encounter]),
                "parameterizes the declared SpawnOneshotSFX effect operand");
            foreach (int invalidCount in new[] { 0, -1 }) {
                WritePlanWithRequirements([FirstMerge()], [CountedRequirement(invalidCount)]);
                Refused(() => FfxBundleTransplant.ReadEmevdRequirements(plan), "occurrence count");
            }
            File.WriteAllBytes(sourceEventPath, OneSfxEvent(500, 111).Write());
            WritePlanWithRequirements([FirstMerge()], [Requirement(Hash(File.ReadAllBytes(sourceEventPath)))]);
            Refused(() => FfxBundleTransplant.ValidateEmevdInputs(plan, events,
                [encounter with { ChangedEventIds = [901] }]), "not one reviewed encounter edit");
            File.WriteAllBytes(finalEventPath, OneSfxEvent(900, 222).Write());
            Refused(() => FfxBundleTransplant.ValidateEmevdFinal(requirements, finalEvents),
                "exactly one declared SpawnOneshotSFX effect");
            var parameterized = OneSfxEvent(500, 111);
            parameterized.Events[0].Parameters.Add(new EMEVD.Parameter(0, 12, 0, 4));
            File.WriteAllBytes(sourceEventPath, parameterized.Write());
            WritePlanWithRequirements([FirstMerge()], [Requirement(Hash(File.ReadAllBytes(sourceEventPath)))]);
            Refused(() => FfxBundleTransplant.ValidateEmevdInputs(plan, events, [encounter]),
                "parameterizes the declared SpawnOneshotSFX effect operand");
            File.WriteAllText(plan, JsonSerializer.Serialize(new {
                boss_emevd_ffx_requirements = new[] { Requirement(Hash(File.ReadAllBytes(sourceEventPath))) },
            }));
            Refused(() => FfxBundleTransplant.VerifyCoverage(plan, []),
                "FFX merge manifest does not exactly cover declared SFX dependencies");
            Console.WriteLine($"PASS: {assertions} FFX bundle transplant assertions");
        } finally {
            if (Path.GetDirectoryName(root) != Path.GetTempPath().TrimEnd(Path.DirectorySeparatorChar) || !Path.GetFileName(root).StartsWith("bb-ffx-bundle-")) throw new Exception("unsafe cleanup path");
            Directory.Delete(root, true);
        }
    }
}
