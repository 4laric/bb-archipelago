using System.Security.Cryptography;
using System.Text.Json;
using SoulsFormats;

internal static class CharacterFfxBankRequirementTests
{
    internal static void Run()
    {
        int assertions = 0;
        void Need(bool value, string reason) { assertions++; if (!value) throw new Exception(reason); }
        void Refused(Action action, string fragment) {
            try { action(); throw new Exception("expected character bank refusal: " + fragment); }
            catch (InvalidDataException error) { Need(error.Message.Contains(fragment), error.Message); }
        }
        string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
        string root = Path.Combine(Path.GetTempPath(), "bb-character-ffx-bank-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try {
            string plan = Path.Combine(root, "plan.json"), originals = Path.Combine(root, "originals"),
                output = Path.Combine(root, "output"), maps = Path.Combine(root, "maps");
            Directory.CreateDirectory(originals); Directory.CreateDirectory(maps);
            const string sourceBank = "frpg_sfxbnd_m24_02.ffxbnd.dcx";
            const string destinationBank = "frpg_sfxbnd_m23.ffxbnd.dcx";
            const string sourceMap = "m24_02_00_00", destinationMap = "m23_00_00_00";
            const string sourcePart = "c2570_0001", destinationPart = "ap_celestial_giant";
            var witness = new CharacterFfxRequirements.Witness(3100, 4, 96, 2480, 625700);
            var entry = new CharacterFfxRequirements.VerifiedTaeEntry(3,
                "chr/c2570/tae/a00.tae", new string('b', 64), 1, [96, 100, 118],
                [witness], [625700]);
            var verified = new CharacterFfxRequirements.Verified(sourceMap, sourcePart, 257010,
                "c2570", "c2570.anibnd.dcx", new string('a', 64), [entry], [625700],
                "partial-typed-witness", "not-validated");
            var donor = new BND4 { Compression = DCX.Type.DCX_DFLT_10000_44_9, Version = "FFX24TEST" };
            donor.Files.Add(new BinderFile(Binder.FileFlags.Flag1, 1,
                "N:\\sfx\\effect\\f000625700.fxr", [1, 2, 3]) { CompressionType = DCX.Type.Zlib });
            donor.Files.Add(new BinderFile(Binder.FileFlags.Flag1, 2,
                "N:\\sfx\\tex\\shared.tpf", [4, 5]) { CompressionType = DCX.Type.Zlib });
            donor.Write(Path.Combine(originals, sourceBank));
            var destination = new BND4 { Compression = DCX.Type.DCX_DFLT_10000_44_9, Version = "FFX23TEST" };
            destination.Files.Add(new BinderFile(Binder.FileFlags.Flag1, 8,
                "N:\\sfx\\effect\\retained.fxr", [9]) { CompressionType = DCX.Type.Zlib });
            destination.Write(Path.Combine(originals, destinationBank));
            var map = new MSBB();
            map.Models.Enemies.Add(new MSBB.Model.Enemy { Name = "c2570", SibPath = "" });
            map.Parts.Enemies.Add(new MSBB.Part.Enemy {
                Name = destinationPart, EntityID = 257011, ModelName = "c2570",
            });
            map.Write(Path.Combine(maps, destinationMap + ".msb"));

            object Actor(string actorSourcePart = sourcePart, string actorDestinationPart = destinationPart) => new {
                source_map = sourceMap, source_part = actorSourcePart, source_anchor_part = "anchor",
                source_entity_id = 257010,
                source_archetype = new { model_name = "c2570", npc_param_id = 1, think_param_id = 2, chara_init_id = 3 },
                destination_map = destinationMap, destination_anchor_part = "target_anchor",
                destination_part = actorDestinationPart, destination_entity_id = 257011,
            };
            object Requirement(CharacterFfxRequirements.Witness? rootWitness = null,
                string requiredDestinationPart = destinationPart, int effectId = 625700,
                string requiredSourceBank = sourceBank, string requiredDestinationBank = destinationBank) => new {
                format = "bb-boss-character-ffx-bank-requirement-v1",
                source_map = sourceMap, source_part = sourcePart, source_entity_id = 257010,
                source_character = "c2570", destination_map = destinationMap,
                destination_part = requiredDestinationPart, destination_entity_id = 257011,
                source_ffx_file = requiredSourceBank, destination_ffx_file = requiredDestinationBank,
                roots = new[] { new { source_tae_entry_id = 3,
                    witness = rootWitness ?? witness with { EffectId = effectId } } },
            };
            object Merge(int effectId = 625700) => new {
                source_file = sourceBank, source_sha256 = Hash(File.ReadAllBytes(Path.Combine(originals, sourceBank))),
                destination_file = destinationBank,
                destination_sha256 = Hash(File.ReadAllBytes(Path.Combine(originals, destinationBank))),
                required_effect_ids = new[] { effectId }, policy = "preserve_destination_union_source_v1",
            };
            void WritePlan(object[] requirements, object[] actors, object[] merges) => File.WriteAllText(plan,
                JsonSerializer.Serialize(new { boss_character_ffx_bank_requirements = requirements,
                    boss_actor_additions = actors, boss_ffx_merges = merges },
                    new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower }));

            WritePlan([Requirement()], [Actor()], [Merge()]);
            var bound = CharacterFfxBankRequirements.Validate(plan, [verified]);
            Need(bound.Count == 1 && bound[0].SourceBank == sourceBank && bound[0].DestinationBank == destinationBank,
                "typed character root derives the correct bank pair");
            CharacterFfxBankRequirements.VerifyFinalActors(bound, maps);
            FfxBundleTransplant.VerifyCoverage(plan, [], bound);
            var applied = FfxBundleTransplant.Apply(plan, originals, output);
            var delivered = CharacterFfxBankRequirements.VerifyDelivered(bound, applied, originals, output, plan);
            Need(delivered.Count == 1 && delivered[0].Witness == witness
                && delivered[0].SourceTaeSha256 == entry.SourceTaeSha256
                && delivered[0].DeliveryScope == "explicit-typed-tae-direct-root-bank-delivery"
                && delivered[0].RecursiveFxrDependencies == "not-validated"
                && !delivered[0].RuntimeValidated,
                "receipt records only the witnessed direct root delivery");
            Need(BND4.Read(Path.Combine(output, destinationBank)).Files.Count == 3,
                "whole donor bank, including texture, was preserved with destination entry");

            WritePlan([Requirement(witness with { EventIndex = 5 })], [Actor()], [Merge()]);
            Refused(() => CharacterFfxBankRequirements.Validate(plan, [verified]), "exact verified typed TAE witness");
            WritePlan([Requirement(effectId: 625701)], [Actor()], [Merge(effectId: 625701)]);
            Refused(() => CharacterFfxBankRequirements.Validate(plan, [verified]), "exact verified typed TAE witness");
            WritePlan([Requirement()], [Actor(actorSourcePart: "wrong")], [Merge()]);
            Refused(() => CharacterFfxBankRequirements.Validate(plan, [verified]), "one transplanted actor destination");
            WritePlan([Requirement(requiredDestinationPart: "wrong")], [Actor()], [Merge()]);
            Refused(() => CharacterFfxBankRequirements.Validate(plan, [verified]), "one transplanted actor destination");
            WritePlan([Requirement(requiredSourceBank: "frpg_sfxbnd_m24_01.ffxbnd.dcx")], [Actor()], [Merge()]);
            Refused(() => CharacterFfxBankRequirements.Read(plan), "bank filename does not match map area/subarea");
            WritePlan([Requirement(requiredDestinationBank: "frpg_sfxbnd_m23_01.ffxbnd.dcx")], [Actor()], [Merge()]);
            Refused(() => CharacterFfxBankRequirements.Read(plan), "bank filename does not match map area/subarea");
            WritePlan([Requirement(), Requirement()], [Actor()], [Merge()]);
            Refused(() => CharacterFfxBankRequirements.Read(plan), "duplicate character FFX destination actor requirement");
            var repeatedRoot = new CharacterFfxBankRequirements.Requirement(
                "bb-boss-character-ffx-bank-requirement-v1", sourceMap, sourcePart, 257010,
                "c2570", destinationMap, destinationPart, 257011, sourceBank, destinationBank,
                [new(3, witness), new(3, witness with { EventIndex = 8 })]);
            WritePlan([repeatedRoot], [Actor()], [Merge()]);
            Refused(() => CharacterFfxBankRequirements.Read(plan), "duplicate or invalid character FFX bank root");
            WritePlan([Requirement()], [Actor()], [Merge(effectId: 625701)]);
            Refused(() => FfxBundleTransplant.VerifyCoverage(plan, [], bound), "do not exactly cover");
            Refused(() => CharacterFfxBankRequirements.Validate(plan, [verified]),
                "root lacks pinned declared merge");
            WritePlan([Requirement()], [Actor()], []);
            Refused(() => FfxBundleTransplant.VerifyCoverage(plan, [], bound),
                "boss_ffx_merges must not be empty");

            WritePlan([Requirement()], [Actor()], [Merge()]);
            var wrongMap = new MSBB();
            wrongMap.Models.Enemies.Add(new MSBB.Model.Enemy { Name = "c2571", SibPath = "" });
            wrongMap.Parts.Enemies.Add(new MSBB.Part.Enemy {
                Name = destinationPart, EntityID = 257011, ModelName = "c2571",
            });
            wrongMap.Write(Path.Combine(maps, destinationMap + ".msb"));
            Refused(() => CharacterFfxBankRequirements.VerifyFinalActors(bound, maps),
                "staged character FFX destination actor identity drift");
            map.Write(Path.Combine(maps, destinationMap + ".msb"));

            string outputPath = Path.Combine(output, destinationBank);
            var changed = BND4.Read(outputPath);
            changed.Files.Single(file => file.Name.EndsWith("f000625700.fxr")).Bytes = [8];
            changed.Write(outputPath);
            var changedReport = applied.Select(item => item with {
                OutputSha256 = Hash(File.ReadAllBytes(outputPath)),
            }).ToList();
            Refused(() => CharacterFfxBankRequirements.VerifyDelivered(bound, changedReport,
                originals, output, plan), "delivered root bytes differ");
            changed.Files.Remove(changed.Files.Single(file => file.Name.EndsWith("f000625700.fxr")));
            changed.Write(outputPath);
            changedReport = applied.Select(item => item with {
                OutputSha256 = Hash(File.ReadAllBytes(outputPath)),
            }).ToList();
            Refused(() => CharacterFfxBankRequirements.VerifyDelivered(bound, changedReport,
                originals, output, plan), "missing or ambiguous output character FFX root");
            var changedSource = BND4.Read(Path.Combine(originals, sourceBank));
            changedSource.Files.Single(file => file.Name.EndsWith("f000625700.fxr")).Bytes = [7];
            changedSource.Write(Path.Combine(originals, sourceBank));
            Refused(() => CharacterFfxBankRequirements.VerifyDelivered(bound, applied,
                originals, output, plan), "source bank provenance drift");
            changedSource.Files.Remove(changedSource.Files.Single(file => file.Name.EndsWith("f000625700.fxr")));
            changedSource.Write(Path.Combine(originals, sourceBank));
            WritePlan([Requirement()], [Actor()], [Merge()]);
            Refused(() => FfxBundleTransplant.Apply(plan, originals, Path.Combine(root, "missing-source")),
                "declared FFX effect missing");
        }
        finally {
            string full = Path.GetFullPath(root), temp = Path.GetFullPath(Path.GetTempPath());
            if (full.StartsWith(temp, StringComparison.OrdinalIgnoreCase)) Directory.Delete(full, recursive: true);
        }
        Console.WriteLine($"character_ffx_bank_tests={assertions}");
    }
}
