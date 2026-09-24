using System.Security.Cryptography;
using System.Text.Json;
using SoulsFormats;

internal static class ChaliceInfrastructureTests
{
    internal static void Run()
    {
        int assertions = 0;
        void Need(bool value, string reason) {
            assertions++;
            if (!value) throw new Exception(reason);
        }
        void Refused(Action action, string fragment) {
            try { action(); throw new Exception("expected chalice refusal: " + fragment); }
            catch (InvalidDataException error) { Need(error.Message.Contains(fragment), error.Message); }
        }
        string Hash(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
        string root = Path.Combine(Path.GetTempPath(), "bb-chalice-native-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try {
            string plan = Path.Combine(root, "plan.json");
            const string sourceMap = "m29_31_90_00", destinationMap = "m24_01_00_00";
            const string sourcePart = "c3050_0000", destinationPart = "c3050_at_cleric";
            const int sourceEntity = 2900109, destinationEntity = 2410800;
            const string bankA = "frpg_sfxbnd_m29a.ffxbnd.dcx";
            const string bankC = "frpg_sfxbnd_m29c.ffxbnd.dcx";
            const string targetBank = "frpg_sfxbnd_m24_01.ffxbnd.dcx";
            string originals = Path.Combine(root, "sfx"), output = Path.Combine(root, "sfx-output");
            Directory.CreateDirectory(originals);
            void Bank(string name, int effect, byte[] bytes) {
                var binder = new BND4 { Compression = DCX.Type.DCX_DFLT_10000_44_9,
                    Version = "CHALICETEST" };
                binder.Files.Add(new BinderFile(Binder.FileFlags.Flag1, effect,
                    $"N:\\sfx\\effect\\f{effect:D9}.fxr", bytes) { CompressionType = DCX.Type.Zlib });
                binder.Write(Path.Combine(originals, name));
            }
            Bank(bankA, 111, [1, 1]); Bank(bankC, 222, [2, 2]); Bank(targetBank, 900, [9]);
            var first = new CharacterFfxRequirements.Witness(3000, 1, 96, 100, 111);
            var second = new CharacterFfxRequirements.Witness(3001, 2, 96, 200, 222);
            var tae = new CharacterFfxRequirements.VerifiedTaeEntry(3,
                "chr/c3050/tae/c3050.tae", new string('b', 64), 2, [96],
                [first, second], [111, 222]);
            var proof = new CharacterFfxRequirements.Verified(sourceMap, sourcePart, sourceEntity,
                "c3050", "c3050.anibnd.dcx", new string('a', 64), [tae], [111, 222],
                "partial-typed-witness", "not-validated");
            object Actor() => new {
                source_map = sourceMap, source_part = sourcePart, source_entity_id = sourceEntity,
                source_archetype = new { model_name = "c3050", npc_param_id = 210305016,
                    think_param_id = 305010, chara_init_id = 0 },
                destination_map = destinationMap, destination_part = destinationPart,
                destination_entity_id = destinationEntity,
            };
            object Requirement(string sourceBank, CharacterFfxRequirements.Witness witness,
                string map = sourceMap) => new {
                format = "bb-boss-character-ffx-bank-requirement-v1",
                source_map = map, source_part = sourcePart, source_entity_id = sourceEntity,
                source_character = "c3050", destination_map = destinationMap,
                destination_part = destinationPart, destination_entity_id = destinationEntity,
                source_ffx_file = sourceBank, destination_ffx_file = targetBank,
                roots = new[] { new { source_tae_entry_id = 3, witness } },
            };
            object Merge(string sourceBank, int effect) => new {
                source_file = sourceBank,
                source_sha256 = Hash(Path.Combine(originals, sourceBank)),
                destination_file = targetBank,
                destination_sha256 = Hash(Path.Combine(originals, targetBank)),
                required_effect_ids = new[] { effect },
                policy = "preserve_destination_union_source_v1",
            };
            void WritePlan(object[] requirements, object[] merges) => File.WriteAllText(plan,
                JsonSerializer.Serialize(new {
                    boss_actor_initializations = new[] { Actor() },
                    boss_character_ffx_bank_requirements = requirements,
                    boss_ffx_merges = merges,
                }, new JsonSerializerOptions { PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower }));

            WritePlan([Requirement(bankA, first), Requirement(bankC, second)],
                [Merge(bankA, 111), Merge(bankC, 222)]);
            var bound = CharacterFfxBankRequirements.Validate(plan, [proof]);
            Need(bound.Count == 2 && bound.Select(item => item.SourceBank).ToHashSet().SetEquals([bankA, bankC]),
                "one actor accepts two distinct m29 source-bank requirements");
            FfxBundleTransplant.VerifyCoverage(plan, [], bound);
            var applied = FfxBundleTransplant.Apply(plan, originals, output);
            Need(applied.Count == 2 && applied.Select(item => item.OutputSha256).Distinct().Count() == 1,
                "two m29 banks share one pinned destination output");
            var merged = BND4.Read(Path.Combine(output, targetBank));
            Need(merged.Files.Count == 3 && merged.Files.Any(file => file.Name.EndsWith("f000000111.fxr"))
                && merged.Files.Any(file => file.Name.EndsWith("f000000222.fxr")),
                "m29a and m29c whole-bank union reaches the subarea bank");
            var delivered = CharacterFfxBankRequirements.VerifyDelivered(bound, applied, originals, output, plan);
            Need(delivered.Count == 2 && delivered.Select(item => item.Witness.EffectId).ToHashSet().SetEquals([111, 222]),
                "both typed roots have independent delivery receipts");

            WritePlan([Requirement(bankA, first), Requirement(bankA, first)], [Merge(bankA, 111)]);
            Refused(() => CharacterFfxBankRequirements.Read(plan),
                "duplicate character FFX destination actor requirement");
            WritePlan([Requirement(bankA, first, "m24_02_00_00")], [Merge(bankA, 111)]);
            Refused(() => CharacterFfxBankRequirements.Read(plan),
                "bank filename does not match map area/subarea");
            foreach (string invalidBank in new[] { "frpg_sfxbnd_m29e.ffxbnd.dcx",
                         "frpg_sfxbnd_m29f.ffxbnd.dcx" }) {
                WritePlan([Requirement(invalidBank, first)], [Merge(bankA, 111)]);
                Refused(() => CharacterFfxBankRequirements.Read(plan),
                    "bank filename does not match map area/subarea");
            }
            WritePlan([Requirement(bankC, second)], [Merge(bankC, 222)]);
            Need(CharacterFfxBankRequirements.Read(plan).Count == 1,
                "m29c is accepted for an m29 source map");
            foreach (string bank in new[] { "frpg_sfxbnd_m29b.ffxbnd.dcx",
                         "frpg_sfxbnd_m29d.ffxbnd.dcx" }) {
                WritePlan([Requirement(bank, first)], [Merge(bankA, 111)]);
                Need(CharacterFfxBankRequirements.Read(plan).Count == 1,
                    "each m29a-d split bank is accepted only for an m29 map");
            }
            NestedM29Primary(root, plan, Need);
        }
        finally {
            string full = Path.GetFullPath(root), temp = Path.GetFullPath(Path.GetTempPath());
            if (Path.GetDirectoryName(full) != temp.TrimEnd(Path.DirectorySeparatorChar)
                || !Path.GetFileName(full).StartsWith("bb-chalice-native-"))
                throw new Exception("unsafe chalice fixture cleanup path");
            Directory.Delete(full, recursive: true);
        }
        Console.WriteLine($"chalice_native_tests={assertions}");
    }

    static void NestedM29Primary(string root, string plan, Action<bool, string> Need)
    {
        const string sourceMap = "m29_31_90_00", destinationMap = "m24_01_00_00";
        string source = Path.Combine(root, "map-source"), destination = Path.Combine(root, "map-destination"),
            output = Path.Combine(root, "map-output");
        Directory.CreateDirectory(Path.Combine(source, sourceMap));
        Directory.CreateDirectory(destination); Directory.CreateDirectory(output);
        var sourceFile = new MSBB();
        sourceFile.Models.Enemies.Add(new MSBB.Model.Enemy { Name = "c3050", SibPath = "" });
        sourceFile.Parts.Enemies.Add(new MSBB.Part.Enemy {
            Name = "c3050_0000", EntityID = 2900109, ModelName = "c3050",
            NPCParamID = 210305016, ThinkParamID = 305010, CharaInitID = 0,
            TalkID = 0, UnkT18 = 0, InitAnimID = -1, DamageAnimID = -1,
        });
        sourceFile.Write(Path.Combine(source, sourceMap, sourceMap + ".msb"));
        var donor = MSBB.Read(Path.Combine(source, sourceMap, sourceMap + ".msb"))
            .Parts.Enemies.Single();
        var destinationFile = new MSBB();
        destinationFile.Models.Enemies.Add(new MSBB.Model.Enemy { Name = "c3050", SibPath = "" });
        destinationFile.Parts.Enemies.Add(new MSBB.Part.Enemy {
            Name = "c5000_0000", EntityID = 2410800, ModelName = "c3050",
            NPCParamID = 210305016, ThinkParamID = 305010, CharaInitID = 0,
            TalkID = 77, UnkT18 = 78, InitAnimID = 79, DamageAnimID = 80,
        });
        destinationFile.Write(Path.Combine(destination, destinationMap + ".msb"));
        File.Copy(Path.Combine(destination, destinationMap + ".msb"),
            Path.Combine(output, destinationMap + ".msb"));
        var primary = new {
            source_map = sourceMap, source_part = "c3050_0000", source_entity_id = 2900109,
            source_archetype = new { model_name = "c3050", npc_param_id = 210305016,
                think_param_id = 305010, chara_init_id = 0 },
            source_provenance = new { format = "bb-boss-actor-pin-v1",
                part_sha256 = BossActorTransplant.Fingerprint(sourceMap, donor) },
            source_initialization = new { talk_id = 0, unk_t18 = 0,
                init_anim_id = -1, damage_anim_id = -1 },
            destination_map = destinationMap, destination_part = "c5000_0000",
            destination_entity_id = 2410800,
        };
        File.WriteAllText(plan, JsonSerializer.Serialize(new { boss_actor_initializations = new[] { primary } }));
        Need(BossActorTransplant.Apply(plan, source, destination, output, false) == 1,
            "nested m29 original source map resolved for primary initialization");
        var initialized = MSBB.Read(Path.Combine(output, destinationMap + ".msb"))
            .Parts.Enemies.Single();
        Need(initialized.TalkID == 0 && initialized.UnkT18 == 0
            && initialized.InitAnimID == -1 && initialized.DamageAnimID == -1,
            "nested m29 source initialization tuple copied exactly");
    }
}
