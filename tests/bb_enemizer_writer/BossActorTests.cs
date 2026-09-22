using System.Numerics;
using System.Security.Cryptography;
using System.Text.Json;
using SoulsFormats;

internal static class BossActorTests
{
    internal static void Run()
    {
        int assertions = 0;
        void Need(bool value) { assertions++; if (!value) throw new Exception("boss actor transplant invariant failed"); }
        void Refused(Action action, string fragment) {
            try { action(); throw new Exception("expected actor refusal: " + fragment); }
            catch (InvalidDataException error) { Need(error.Message.Contains(fragment)); }
        }
        void SetGeneratorNames(MSBB.Event.Generator generator, string[] parts, string[] points) {
            var type = typeof(MSBB.Event.Generator);
            type.GetProperty(nameof(MSBB.Event.Generator.SpawnPartNames))!.GetSetMethod(true)!.Invoke(generator, [parts]);
            type.GetProperty(nameof(MSBB.Event.Generator.SpawnPointNames))!.GetSetMethod(true)!.Invoke(generator, [points]);
        }
        string root = Path.Combine(Path.GetTempPath(), "bb-boss-actor-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try {
            string source = Path.Combine(root, "source"), destination = Path.Combine(root, "destination");
            Directory.CreateDirectory(source); Directory.CreateDirectory(destination);
            var donorMap = new MSBB(); donorMap.Models.Enemies.Add(new MSBB.Model.Enemy { Name = "c9000", SibPath = "" });
            donorMap.Parts.Enemies.Add(new MSBB.Part.Enemy { Name = "anchor", EntityID = 100, Position = new Vector3(10, 0, 10), Rotation = new Vector3(0, 15, 0) });
            var donor = new MSBB.Part.Enemy { Name = "donor", EntityID = 101, ModelName = "c9000", NPCParamID = 90, ThinkParamID = 91, CharaInitID = 92,
                TalkID = 93, UnkT18 = 94, InitAnimID = 95, DamageAnimID = 96, Position = new Vector3(12, 0, 13), Rotation = new Vector3(0, 30, 0) };
            donorMap.Parts.Enemies.Add(donor);
            donorMap.Parts.DummyEnemies.Add(new MSBB.Part.DummyEnemy { Name = "dummy_donor", EntityID = 102, ModelName = "c9000", NPCParamID = 90, ThinkParamID = 91, CharaInitID = 92,
                TalkID = 193, UnkT18 = 194, InitAnimID = 195, DamageAnimID = 196, Position = new Vector3(11, 0, 10), Rotation = new Vector3(0, .2f, 0) });
            donorMap.Regions.Regions.Add(new MSBB.Region { Name = "source_spawn", EntityID = 110, Position = new Vector3(10, 0, 13) });
            var sourceGenerator = new MSBB.Event.Generator { Name = "source_gen", EventID = 400, EntityID = 401, PartName = "donor", RegionName = "source_spawn",
                MaxNum = 4, GenType = 2, LimitNum = 3, MinGenNum = 1, MaxGenNum = 2, InitialSpawnCount = 1 };
            SetGeneratorNames(sourceGenerator, ["donor", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
                ["source_spawn", "", "", "", "", "", "", ""]);
            donorMap.Events.Generators.Add(sourceGenerator);
            donorMap.Write(Path.Combine(source, "m23_00_00_00.msb"));

            var targetMap = new MSBB(); targetMap.Models.Enemies.Add(new MSBB.Model.Enemy { Name = "c1000", SibPath = "" });
            targetMap.Parts.Collisions.Add(new MSBB.Part.Collision { Name = "h0000" });
            var anchor = new MSBB.Part.Enemy { Name = "target_anchor", EntityID = 200, ModelName = "c1000", Position = new Vector3(50, 0, 40), Rotation = new Vector3(0, 105, 0),
                CollisionName = "h0000", TalkID = 1, UnkT18 = 2, InitAnimID = 3, DamageAnimID = 4 };
            anchor.DrawGroups[0] = 7; anchor.DispGroups[0] = 8; anchor.BackreadGroups[0] = 9; targetMap.Parts.Enemies.Add(anchor);
            targetMap.Regions.Regions.Add(new MSBB.Region { Name = "target_spawn", EntityID = 210, Position = new Vector3(55, 0, 40) });
            var existing = new MSBB.Event.Generator { Name = "existing_gen", EventID = 300, EntityID = 301, MaxNum = 1 };
            targetMap.Events.Generators.Add(existing);
            targetMap.Write(Path.Combine(destination, "m24_01_00_00.msb"));

            var sourceRead = MSBB.Read(Path.Combine(source, "m23_00_00_00.msb"));
            var readDonor = sourceRead.Parts.Enemies.Single(part => part.Name == "donor");
            var readAnchor = sourceRead.Parts.Enemies.Single(part => part.Name == "anchor");
            var readDummy = sourceRead.Parts.DummyEnemies.Single(part => part.Name == "dummy_donor");
            var readGenerator = sourceRead.Events.Generators.Single();
            var primary = new {
                source_map = "m23_00_00_00", source_part = "donor", source_entity_id = 101,
                source_archetype = new { model_name = "c9000", npc_param_id = 90, think_param_id = 91, chara_init_id = 92 },
                source_provenance = new { format = "bb-boss-actor-pin-v1", part_sha256 = BossActorTransplant.Fingerprint("m23_00_00_00", readDonor) },
                source_initialization = new { talk_id = 93, unk_t18 = 94, init_anim_id = 95, damage_anim_id = 96 },
                destination_map = "m24_01_00_00", destination_part = "target_anchor", destination_entity_id = 200,
            };
            string planPath = Path.Combine(root, "plan.json");
            string primaryOutput = Path.Combine(root, "primary-output"); Directory.CreateDirectory(primaryOutput);
            var primaryMap = MSBB.Read(Path.Combine(destination, "m24_01_00_00.msb"));
            primaryMap.Models.Enemies.Add(new MSBB.Model.Enemy { Name = "c9000", SibPath = "" });
            var primaryTarget = primaryMap.Parts.Enemies.Single(part => part.Name == "target_anchor");
            primaryTarget.ModelName = "c9000"; primaryTarget.NPCParamID = 90; primaryTarget.ThinkParamID = 91; primaryTarget.CharaInitID = 92;
            primaryMap.Write(Path.Combine(primaryOutput, "m24_01_00_00.msb"));
            File.WriteAllText(planPath, JsonSerializer.Serialize(new { boss_actor_initializations = new[] { primary } }));
            Need(BossActorTransplant.Apply(planPath, source, destination, primaryOutput, false) == 1);
            var initialized = MSBB.Read(Path.Combine(primaryOutput, "m24_01_00_00.msb")).Parts.Enemies.Single(part => part.Name == "target_anchor");
            Need(initialized.TalkID == 93 && initialized.UnkT18 == 94 && initialized.InitAnimID == 95 && initialized.DamageAnimID == 96);
            Need(initialized.CollisionName == "h0000" && initialized.DrawGroups[0] == 7 && initialized.DispGroups[0] == 8 && initialized.BackreadGroups[0] == 9);
            var primaryWrongInit = new { primary.source_map, primary.source_part, primary.source_entity_id, primary.source_archetype, primary.source_provenance,
                source_initialization = new { talk_id = 999, unk_t18 = 94, init_anim_id = 95, damage_anim_id = 96 },
                primary.destination_map, primary.destination_part, primary.destination_entity_id };
            File.WriteAllText(planPath, JsonSerializer.Serialize(new { boss_actor_initializations = new[] { primaryWrongInit } }));
            Refused(() => BossActorTransplant.Apply(planPath, source, destination, Path.Combine(root, "bad-primary"), false), "initialization drift");
            var primaryStalePin = new { primary.source_map, primary.source_part, primary.source_entity_id, primary.source_archetype,
                source_provenance = new { format = "bb-boss-actor-pin-v1", part_sha256 = new string('0', 64) }, primary.source_initialization,
                primary.destination_map, primary.destination_part, primary.destination_entity_id };
            File.WriteAllText(planPath, JsonSerializer.Serialize(new { boss_actor_initializations = new[] { primaryStalePin } }));
            Refused(() => BossActorTransplant.Apply(planPath, source, destination, Path.Combine(root, "stale-primary"), false), "provenance pin drift");
            string untransplantedOutput = Path.Combine(root, "untransplanted-primary"); Directory.CreateDirectory(untransplantedOutput);
            File.Copy(Path.Combine(destination, "m24_01_00_00.msb"), Path.Combine(untransplantedOutput, "m24_01_00_00.msb"));
            File.WriteAllText(planPath, JsonSerializer.Serialize(new { boss_actor_initializations = new[] { primary } }));
            Refused(() => BossActorTransplant.Apply(planPath, source, destination, untransplantedOutput, false), "target does not match source combat archetype");
            string scaledOverlay = Path.Combine(root, "scaled-overlay");
            string scaledMaps = Path.Combine(scaledOverlay, "dvdroot_ps4", "map", "MapStudio");
            string scaledGame = Path.Combine(scaledOverlay, "dvdroot_ps4", "param", "gameparam", "gameparam.parambnd.dcx");
            string scaledSource = Path.Combine(scaledOverlay, "source-enemizer-plan.json");
            string scaledAdjusted = Path.Combine(scaledOverlay, "bb-enemizer-plan.json");
            string scaledReceipt = Path.Combine(scaledOverlay, "scaling-report.json");
            string HashFile(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
            void WriteScaledMap(int npcParamId) {
                Directory.CreateDirectory(scaledMaps);
                var map = MSBB.Read(Path.Combine(destination, "m24_01_00_00.msb"));
                map.Models.Enemies.Add(new MSBB.Model.Enemy { Name = "c9000", SibPath = "" });
                var part = map.Parts.Enemies.Single(entry => entry.Name == "target_anchor");
                part.ModelName = "c9000"; part.NPCParamID = npcParamId; part.ThinkParamID = 91; part.CharaInitID = 92;
                map.Write(Path.Combine(scaledMaps, "m24_01_00_00.msb"));
            }
            void WriteScaledEvidence(int sourceTargetNpc, int adjustedNpc, int changeSourceNpc, int changeCloneNpc) {
                var sourceTarget = new { model_name = "c9000", npc_param_id = sourceTargetNpc, think_param_id = 91, chara_init_id = 92 };
                var adjustedTarget = new { model_name = "c9000", npc_param_id = adjustedNpc, think_param_id = 91, chara_init_id = 92 };
                var change = new { logical_key = "m24_01_00_00:target_anchor", source_npc_param_id = changeSourceNpc,
                    cloned_npc_param_id = changeCloneNpc, sp_effect_slot = "spEffectID1", minted_sp_effect_id = 60000,
                    have_soul_rate = 1.0, source_level = 1, destination_level = 1,
                    hp_multiplier = 1.0, attack_multiplier = 1.0, defense_multiplier = 1.0 };
                var sourcePlan = new { format = "bb-enemizer-plan-v2", dry_run = true,
                    swaps = new[] { new { logical_key = "m24_01_00_00:target_anchor", destination_keys = new[] { "m24_01_00_00.msb:target_anchor" }, target = sourceTarget } },
                    scaling = new { enabled = true, mechanism = "inferred_static_npc_clone_sp_effect", change_count = 1, changes = new[] { change } },
                    boss_actor_initializations = new[] { primary } };
                File.WriteAllText(planPath, JsonSerializer.Serialize(sourcePlan));
                Directory.CreateDirectory(scaledOverlay); File.Copy(planPath, scaledSource, true);
                var adjustedPlan = new { format = "bb-enemizer-plan-v2", dry_run = true,
                    swaps = new[] { new { logical_key = "m24_01_00_00:target_anchor", destination_keys = new[] { "m24_01_00_00.msb:target_anchor" }, target = adjustedTarget, unscaled_target = sourceTarget } },
                    scaling = new { enabled = true, mechanism = "inferred_static_npc_clone_sp_effect", change_count = 1, applied = true, changes = new[] { change } },
                    boss_actor_initializations = new[] { primary } };
                File.WriteAllText(scaledAdjusted, JsonSerializer.Serialize(adjustedPlan));
                Directory.CreateDirectory(Path.GetDirectoryName(scaledGame)!); File.WriteAllBytes(scaledGame, [1, 2, 3]);
                File.WriteAllText(scaledReceipt, JsonSerializer.Serialize(new { format = "bb-enemizer-scaling-v1", applied = true,
                    source_plan_sha256 = HashFile(planPath), output_plan_sha256 = HashFile(scaledAdjusted), output_gameparam_sha256 = HashFile(scaledGame), changes = new[] { change } }));
            }
            WriteScaledMap(6000000); WriteScaledEvidence(90, 6000000, 90, 6000000);
            Need(BossActorTransplant.Apply(planPath, source, destination, scaledMaps, false) == 1);
            Need(MSBB.Read(Path.Combine(scaledMaps, "m24_01_00_00.msb")).Parts.Enemies.Single(part => part.Name == "target_anchor").TalkID == 93);
            WriteScaledMap(6000000); WriteScaledEvidence(89, 6000000, 89, 6000000);
            Refused(() => BossActorTransplant.Apply(planPath, source, destination, scaledMaps, false), "source does not match logical swap");
            WriteScaledMap(6000001); WriteScaledEvidence(90, 6000000, 90, 6000000);
            Refused(() => BossActorTransplant.Apply(planPath, source, destination, scaledMaps, false), "target is not reviewed normalized clone");
            var addition = new {
                source_map = "m23_00_00_00", source_part = "donor", source_anchor_part = "anchor", source_entity_id = 101,
                source_part_kind = "enemy",
                source_archetype = new { model_name = "c9000", npc_param_id = 90, think_param_id = 91, chara_init_id = 92 },
                source_provenance = new { format = "bb-boss-actor-pin-v1", part_sha256 = BossActorTransplant.Fingerprint("m23_00_00_00", readDonor), anchor_sha256 = BossActorTransplant.Fingerprint("m23_00_00_00", readAnchor) },
                source_initialization = new { talk_id = 93, unk_t18 = 94, init_anim_id = 95, damage_anim_id = 96 },
                destination_map = "m24_01_00_00", destination_anchor_part = "target_anchor", destination_part = "spawned", destination_entity_id = 300,
            };
            var generatorAddition = new {
                source_map = "m23_00_00_00", source_event = "source_gen", source_event_id = 400, source_entity_id = 401,
                source_fingerprint = BossActorTransplant.GeneratorFingerprint("m23_00_00_00", readGenerator),
                destination_map = "m24_01_00_00", destination_event = "spawned_gen", destination_event_id = 500, destination_entity_id = 501,
                destination_part_name = "spawned", destination_region_name = "target_spawn",
                spawn_part_map = new Dictionary<string, string> { ["donor"] = "spawned" },
                spawn_point_map = new Dictionary<string, string> { ["source_spawn"] = "target_spawn" },
            };
            void WritePlan(object actor, object[]? generators = null) => File.WriteAllText(planPath,
                generators is null
                    ? JsonSerializer.Serialize(new { boss_actor_additions = new[] { actor } })
                    : JsonSerializer.Serialize(new { boss_actor_additions = new[] { actor }, boss_generator_additions = generators }));
            WritePlan(addition, [generatorAddition]);
            string output = Path.Combine(root, "output");
            Need(BossActorTransplant.Apply(planPath, source, destination, output, false) == 2);
            var written = MSBB.Read(Path.Combine(output, "m24_01_00_00.msb")); var spawned = written.Parts.Enemies.Single(e => e.Name == "spawned");
            Need(spawned.EntityID == 300 && spawned.ModelName == "c9000" && spawned.NPCParamID == 90 && spawned.ThinkParamID == 91 && spawned.CharaInitID == 92);
            Need(spawned.TalkID == 93 && spawned.UnkT18 == 94 && spawned.InitAnimID == 95 && spawned.DamageAnimID == 96);
            Need(Vector3.Distance(spawned.Position, new Vector3(53, 0, 38)) < .001f && MathF.Abs(spawned.Rotation.Y - 120) < .001f);
            Need(spawned.CollisionName == "h0000" && spawned.DrawGroups[0] == 7 && spawned.DispGroups[0] == 8 && spawned.BackreadGroups[0] == 9);
            Need(written.Parts.Enemies.Single(e => e.Name == "target_anchor").EntityID == 200);
            var generated = written.Events.Generators.Single(e => e.Name == "spawned_gen");
            Need(generated.EventID == 500 && generated.EntityID == 501 && generated.PartName == "spawned" && generated.RegionName == "target_spawn");
            Need(generated.SpawnPartNames[0] == "spawned" && generated.SpawnPointNames[0] == "target_spawn" && generated.MaxNum == 4 && generated.GenType == 2);
            Need(BossActorTransplant.GeneratorFingerprint("m24_01_00_00", written.Events.Generators.Single(e => e.Name == "existing_gen"))
                == BossActorTransplant.GeneratorFingerprint("m24_01_00_00", existing));

            var helperScale = new {
                parent_logical_key = "m24_01_00_00:target_anchor",
                addition.source_map, addition.source_part, addition.source_entity_id, addition.source_archetype,
                addition.source_provenance, addition.source_initialization,
                addition.destination_map, addition.destination_part, addition.destination_entity_id,
                cloned_npc_param_id = 6000001, sp_effect_slot = "spEffectID1",
            };
            string helperOverlay = Path.Combine(root, "helper-overlay");
            string helperMaps = Path.Combine(helperOverlay, "dvdroot_ps4", "map", "MapStudio");
            string helperPlan = Path.Combine(root, "helper-plan.json");
            void HelperBinder(string path, bool includeClone) {
                var def = new PARAMDEF {ParamType = "NPC_PARAM_ST", DataVersion = 1, Unicode = true};
                var table = new PARAM {ParamType = def.ParamType, ParamdefDataVersion = 1, Rows = []}; table.ApplyParamdef(def);
                if (includeClone) table.Rows.Add(new PARAM.Row(6000001, "attested helper clone", def));
                var binder = new BND4 {Compression = DCX.Type.DCX_EDGE};
                binder.Files.Add(new BinderFile(Binder.FileFlags.Flag1, 1, "NpcParam.param", table.Write())); binder.Write(path);
            }
            void HelperEvidence(bool includeClone) {
                var change = new { logical_key = "m24_01_00_00:target_anchor", source_npc_param_id = 90,
                    cloned_npc_param_id = 6000000, sp_effect_slot = "spEffectID0", minted_sp_effect_id = 60000,
                    have_soul_rate = 1.0, source_level = 1, destination_level = 1,
                    hp_multiplier = 1.0, attack_multiplier = 1.0, defense_multiplier = 1.0 };
                var sourcePlan = new { format = "bb-enemizer-plan-v2", dry_run = true, swaps = Array.Empty<object>(),
                    boss_actor_additions = new[] { addition }, boss_actor_scaling = new[] { helperScale },
                    scaling = new { enabled = true, mechanism = "inferred_static_npc_clone_sp_effect", change_count = 1, changes = new[] { change } } };
                File.WriteAllText(helperPlan, JsonSerializer.Serialize(sourcePlan));
                Directory.CreateDirectory(helperOverlay); File.Copy(helperPlan, Path.Combine(helperOverlay, "source-enemizer-plan.json"), true);
                var adjusted = new { format = "bb-enemizer-plan-v2", dry_run = true, swaps = Array.Empty<object>(),
                    boss_actor_additions = new[] { addition }, boss_actor_scaling = new[] { helperScale },
                    scaling = new { enabled = true, mechanism = "inferred_static_npc_clone_sp_effect", change_count = 1, applied = true, changes = new[] { change } } };
                string adjustedPath = Path.Combine(helperOverlay, "bb-enemizer-plan.json"); File.WriteAllText(adjustedPath, JsonSerializer.Serialize(adjusted));
                string game = Path.Combine(helperOverlay, "dvdroot_ps4", "param", "gameparam", "gameparam.parambnd.dcx"); Directory.CreateDirectory(Path.GetDirectoryName(game)!); HelperBinder(game, includeClone);
                File.WriteAllText(Path.Combine(helperOverlay, "scaling-report.json"), JsonSerializer.Serialize(new { format = "bb-enemizer-scaling-v1", applied = true,
                    source_plan_sha256 = HashFile(helperPlan), output_plan_sha256 = HashFile(adjustedPath), output_gameparam_sha256 = HashFile(game), changes = new[] { change },
                    helper_changes = new[] { new { parent_logical_key = helperScale.parent_logical_key, source_npc_param_id = 90, cloned_npc_param_id = 6000001,
                        source_level = 1, destination_level = 1, sp_effect_slot = "spEffectID1", minted_sp_effect_id = 60000 } } }));
            }
            Directory.CreateDirectory(helperMaps); File.Copy(Path.Combine(destination, "m24_01_00_00.msb"), Path.Combine(helperMaps, "m24_01_00_00.msb"));
            HelperEvidence(true);
            Need(BossActorTransplant.Apply(helperPlan, source, destination, helperMaps, false) == 1);
            Need(MSBB.Read(Path.Combine(helperMaps, "m24_01_00_00.msb")).Parts.Enemies.Single(e => e.Name == "spawned").NPCParamID == 6000001);
            Directory.Delete(helperMaps, true); Directory.CreateDirectory(helperMaps); File.Copy(Path.Combine(destination, "m24_01_00_00.msb"), Path.Combine(helperMaps, "m24_01_00_00.msb"));
            HelperEvidence(false);
            Refused(() => BossActorTransplant.Apply(helperPlan, source, destination, helperMaps, false), "lacks the attested NPC clone");

            var stalePin = new { addition.source_map, addition.source_part, addition.source_anchor_part, addition.source_entity_id, addition.source_part_kind,
                addition.source_archetype, source_provenance = new { format = "bb-boss-actor-pin-v1", part_sha256 = new string('0', 64), addition.source_provenance.anchor_sha256 },
                addition.source_initialization, addition.destination_map, addition.destination_anchor_part, addition.destination_part, addition.destination_entity_id };
            WritePlan(stalePin);
            Refused(() => BossActorTransplant.Apply(planPath, source, destination, Path.Combine(root, "stale"), false), "provenance pin drift");
            var wrongInit = new { addition.source_map, addition.source_part, addition.source_anchor_part, addition.source_entity_id, addition.source_part_kind,
                addition.source_archetype, addition.source_provenance, source_initialization = new { talk_id = 999, unk_t18 = 94, init_anim_id = 95, damage_anim_id = 96 },
                addition.destination_map, addition.destination_anchor_part, addition.destination_part, addition.destination_entity_id };
            WritePlan(wrongInit);
            Refused(() => BossActorTransplant.Apply(planPath, source, destination, Path.Combine(root, "bad-init"), false), "initialization drift");
            var actorRegionCollision = new { addition.source_map, addition.source_part, addition.source_anchor_part, addition.source_entity_id,
                addition.source_part_kind, addition.source_archetype, addition.source_provenance, addition.source_initialization,
                addition.destination_map, addition.destination_anchor_part, destination_part = "actor_region_collision", destination_entity_id = 210 };
            WritePlan(actorRegionCollision);
            Refused(() => BossActorTransplant.Apply(planPath, source, destination, Path.Combine(root, "actor-region-collision"), false), "actor destination entity ID already exists");
            var actorEventCollision = new { addition.source_map, addition.source_part, addition.source_anchor_part, addition.source_entity_id,
                addition.source_part_kind, addition.source_archetype, addition.source_provenance, addition.source_initialization,
                addition.destination_map, addition.destination_anchor_part, destination_part = "actor_event_collision", destination_entity_id = 301 };
            WritePlan(actorEventCollision);
            Refused(() => BossActorTransplant.Apply(planPath, source, destination, Path.Combine(root, "actor-event-collision"), false), "actor destination entity ID already exists");
            var generatorCollision = new {
                generatorAddition.source_map, generatorAddition.source_event, generatorAddition.source_event_id, generatorAddition.source_entity_id, generatorAddition.source_fingerprint,
                generatorAddition.destination_map, generatorAddition.destination_event, generatorAddition.destination_event_id, destination_entity_id = 200,
                generatorAddition.destination_part_name, generatorAddition.destination_region_name, generatorAddition.spawn_part_map, generatorAddition.spawn_point_map,
            };
            WritePlan(addition, [generatorCollision]);
            Refused(() => BossActorTransplant.Apply(planPath, source, destination, Path.Combine(root, "generator-collision"), false), "generator destination identity already exists");
            var generatorRegionCollision = new {
                generatorAddition.source_map, generatorAddition.source_event, generatorAddition.source_event_id, generatorAddition.source_entity_id, generatorAddition.source_fingerprint,
                generatorAddition.destination_map, generatorAddition.destination_event, generatorAddition.destination_event_id, destination_entity_id = 210,
                generatorAddition.destination_part_name, generatorAddition.destination_region_name, generatorAddition.spawn_part_map, generatorAddition.spawn_point_map,
            };
            WritePlan(addition, [generatorRegionCollision]);
            Refused(() => BossActorTransplant.Apply(planPath, source, destination, Path.Combine(root, "generator-region-collision"), false), "generator destination identity already exists");

            var dummy = new {
                source_map = "m23_00_00_00", source_part = "dummy_donor", source_anchor_part = "anchor", source_entity_id = 102,
                source_part_kind = "dummy_enemy", materialize_as = "enemy",
                source_archetype = new { model_name = "c9000", npc_param_id = 90, think_param_id = 91, chara_init_id = 92 },
                source_provenance = new { format = "bb-boss-actor-pin-v1", part_sha256 = BossActorTransplant.Fingerprint("m23_00_00_00", readDummy), anchor_sha256 = BossActorTransplant.Fingerprint("m23_00_00_00", readAnchor) },
                destination_map = "m24_01_00_00", destination_anchor_part = "target_anchor", destination_part = "materialized", destination_entity_id = 302,
            };
            WritePlan(dummy);
            Need(BossActorTransplant.Apply(planPath, source, destination, Path.Combine(root, "dummy"), false) == 1);
            var dummyOutput = MSBB.Read(Path.Combine(root, "dummy", "m24_01_00_00.msb"));
            Need(dummyOutput.Parts.Enemies.Single(e => e.Name == "materialized").EntityID == 302 && !dummyOutput.Parts.DummyEnemies.Any(e => e.Name == "materialized"));
            var rejectedDummy = new { dummy.source_map, dummy.source_part, dummy.source_anchor_part, dummy.source_entity_id, dummy.source_part_kind,
                dummy.source_archetype, dummy.destination_map, dummy.destination_anchor_part, destination_part = "rejected", destination_entity_id = 303 };
            WritePlan(rejectedDummy);
            Refused(() => BossActorTransplant.Apply(planPath, source, destination, Path.Combine(root, "rejected-dummy"), false), "requires explicit materialize_as");
            var unpinnedDummy = new { dummy.source_map, dummy.source_part, dummy.source_anchor_part, dummy.source_entity_id, dummy.source_part_kind, dummy.materialize_as,
                dummy.source_archetype, dummy.destination_map, dummy.destination_anchor_part, destination_part = "unpinned", destination_entity_id = 304 };
            WritePlan(unpinnedDummy);
            Refused(() => BossActorTransplant.Apply(planPath, source, destination, Path.Combine(root, "unpinned-dummy"), false), "requires source provenance pin");

            Console.WriteLine($"PASS: {assertions} boss actor transplant assertions");
        } finally { Directory.Delete(root, true); }
    }
}
