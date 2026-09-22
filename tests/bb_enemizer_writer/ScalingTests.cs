using System.Text.Json;
using System.Text.Json.Nodes;
using SoulsFormats;

internal static class ScalingTests
{
    public static void Run(string root, string aiGame, string aiDefs, string aiScripts)
    {
        int assertions = 0;
        void Check(bool condition, string name) { assertions++; if (!condition) throw new Exception(name); }
        string input = Path.Combine(root, "scaling-input");
        Directory.CreateDirectory(input);
        string gamePath = Path.Combine(input, "gameparam.dcx"), defsPath = Path.Combine(input, "paramdef.dcx");
        string planPath = Path.Combine(input, "plan.json"), maps = Path.Combine(input, "maps"), scripts = Path.Combine(input, "scripts");
        Directory.CreateDirectory(maps); Directory.CreateDirectory(scripts);
        foreach (string path in Directory.GetFiles(aiScripts)) File.Copy(path, Path.Combine(scripts, Path.GetFileName(path)));
        File.Copy(Path.Combine(scripts, "m99_00_00_00.luabnd.dcx"), Path.Combine(scripts, "m24_01_00_00.luabnd.dcx"));
        var game = BND4.Read(aiGame); var defs = BND4.Read(aiDefs);
        PARAMDEF Def(string name, PARAMDEF.DefType type, IEnumerable<string> fields) {
            var def = new PARAMDEF {ParamType = name, DataVersion = 1, Unicode = true};
            foreach (string field in fields) def.Fields.Add(new PARAMDEF.Field(def, type, field));
            defs.Files.Add(new BinderFile(Binder.FileFlags.Flag1, defs.Files.Count, name + ".paramdef", def.Write()));
            return def;
        }
        PARAM Table(PARAMDEF def) {
            var table = new PARAM {ParamType = def.ParamType, ParamdefDataVersion = 1, Rows = []}; table.ApplyParamdef(def); return table;
        }
        string[] attack = ["physicsAttackPowerRate", "magicAttackPowerRate", "fireAttackPowerRate", "thunderAttackPowerRate"];
        string[] defense = ["physicsDiffenceRate", "magicDiffenceRate", "fireDiffenceRate", "thunderDiffenceRate"];
        string[] disabled = ["effectEndurance", "iconId", "behaviorId", "animIdOffset", "replaceSpEffectId", "cycleOccurrenceSpEffectId", "atkOccurrenceSpEffectId"];
        var effectDef = Def("TEST_EFFECT", PARAMDEF.DefType.f32, attack.Concat(defense).Concat(disabled)
            .Concat(new[] {"maxHpRate", "staminaAttackRate", "haveSoulRate", "bGameClearBonus", "spCategory", "useSpEffectEffect",
                "soulRate", "soul", "clearSoul", "soulStealRate", "itemDropRate"}));
        var npcDef = Def("TEST_NPC", PARAMDEF.DefType.s32, Enumerable.Range(0, 8).Select(i => $"spEffectID{i}")
            .Concat(new[] {"GameClearSpEffectID", "getSoul", "itemLotId_1", "hp"}));
        var npcs = Table(npcDef); var effects = Table(effectDef);
        var donor = new PARAM.Row(11, "donor", npcDef);
        foreach (var c in donor.Cells) c.Value = -1;
        donor["GameClearSpEffectID"].Value = 7402; donor["getSoul"].Value = 77;
        donor["itemLotId_1"].Value = 123; donor["hp"].Value = 400;
        donor["spEffectID0"].Value = 999; // existing authored effect must survive
        npcs.Rows.Add(donor);
        var helperDonor = new PARAM.Row(donor) {ID = 12, Name = "combat helper"};
        helperDonor["spEffectID0"].Value = -1;
        npcs.Rows.Add(helperDonor);
        var wrongTierHelper = new PARAM.Row(helperDonor) {ID = 13, Name = "wrong-tier helper"};
        wrongTierHelper["GameClearSpEffectID"].Value = 7401;
        npcs.Rows.Add(wrongTierHelper);
        var bossTierHelper = new PARAM.Row(helperDonor) {ID = 14, Name = "boss tier-one helper"};
        bossTierHelper["GameClearSpEffectID"].Value = 7421;
        npcs.Rows.Add(bossTierHelper);
        Check(ScalingTransplant.NativeLevel(bossTierHelper, bossTiers: true) == 1
            && ScalingTransplant.NativeLevel(bossTierHelper) == 0, "named boss tier is boss-route only");
        Check(ScalingTransplant.DestinationLevel("m24_02_00_00", bossPrepared: true) == 11
            && ScalingTransplant.DestinationLevel("m24_02_00_00", bossPrepared: false) == 0,
            "Upper Cathedral boss tier remains unavailable to ordinary scaling");
        npcs.Rows.Add(new PARAM.Row(donor) {ID = 9000000, Name = "original higher ID"});
        for (int level = 1; level <= 2; level++) {
            var effect = new PARAM.Row(7400 + level, "synthetic ladder", effectDef);
            foreach (var c in effect.Cells) c.Value = 0f;
            foreach (string f in disabled) effect[f].Value = -1f;
            foreach (string f in attack.Concat(defense)) effect[f].Value = level == 1 ? 2f : 1.5f;
            effect["maxHpRate"].Value = level == 1 ? 4f : 2f;
            effect["staminaAttackRate"].Value = 3f; effect["haveSoulRate"].Value = 11f;
            effect["bGameClearBonus"].Value = 1f;
            effect["soulRate"].Value = 1f; effect["soulStealRate"].Value = 1f;
            effects.Rows.Add(effect);
        }
        game.Files.Add(new BinderFile(Binder.FileFlags.Flag1, 1, "NpcParam.param", npcs.Write()));
        game.Files.Add(new BinderFile(Binder.FileFlags.Flag1, 2, "SpEffectParam.param", effects.Write()));
        // Represents an already-suppressed, opaque binder member. Must be byte-identical.
        game.Files.Add(new BinderFile(Binder.FileFlags.Flag1, 3, "ItemLotParam.param", new byte[] {1,3,5,7}));
        game.Write(gamePath); defs.Write(defsPath);
        var source = new {model_name = "c1000", npc_param_id = 10, think_param_id = 42, chara_init_id = 0};
        string[] destinations = ["m24_01_00_00.msb:c1000_0000", "m24_01_00_01.msb:c1000_0000"];
        foreach (string map in new[] {"m24_01_00_00", "m24_01_00_01"}) {
            var msb = new MSBB();
            msb.Models.Enemies.Add(new MSBB.Model.Enemy {Name = "c1000", SibPath = ""});
            foreach (string name in new[] {"c1000_0000", "c1000_0001"}) msb.Parts.Enemies.Add(new MSBB.Part.Enemy {
                Name = name, ModelName = "c1000", NPCParamID = 10, ThinkParamID = 42, CharaInitID = 0,
                EntityID = name.EndsWith("0") ? 100 : 101,
            });
            msb.Write(Path.Combine(maps, map + ".msb"));
        }
        var plan = JsonNode.Parse(JsonSerializer.Serialize(new {
            format = "bb-enemizer-plan-v2", dry_run = true, swaps = new[] {new {
                logical_key = "m24_01_00_00:c1000_0000", destination_keys = destinations,
                destination_sources = destinations.ToDictionary(d => d, _ => source), source,
                target = new {model_name = "c9000", npc_param_id = 11, think_param_id = 42, chara_init_id = 0},
            }}, boss_actor_additions = new[] {new {
                source_map = "m24_01_00_00", source_part = "c1000_0001", source_anchor_part = "c1000_0000", source_entity_id = 101,
                source_archetype = new {model_name = "c9000", npc_param_id = 12, think_param_id = 42, chara_init_id = 0},
                source_provenance = new {format = "bb-boss-actor-pin-v1", part_sha256 = new string('a', 64), anchor_sha256 = new string('b', 64)},
                source_initialization = new {talk_id = 0, unk_t18 = -1, init_anim_id = -1, damage_anim_id = -1},
                destination_map = "m24_01_00_00", destination_anchor_part = "c1000_0000", destination_part = "combat_helper", destination_entity_id = 102,
            }}, boss_actor_scaling = new[] {new {
                parent_logical_key = "m24_01_00_00:c1000_0000",
                source_map = "m24_01_00_00", source_part = "c1000_0001", source_entity_id = 101,
                source_archetype = new {model_name = "c9000", npc_param_id = 12, think_param_id = 42, chara_init_id = 0},
                source_provenance = new {format = "bb-boss-actor-pin-v1", part_sha256 = new string('a', 64), anchor_sha256 = new string('b', 64)},
                source_initialization = new {talk_id = 0, unk_t18 = -1, init_anim_id = -1, damage_anim_id = -1},
                destination_map = "m24_01_00_00", destination_part = "combat_helper", destination_entity_id = 102,
                cloned_npc_param_id = 6000001, sp_effect_slot = "spEffectID2",
            }}, scaling = new {enabled = true, mechanism = "inferred_static_npc_clone_sp_effect", change_count = 1,
                changes = new[] {new {logical_key = "m24_01_00_00:c1000_0000", source_npc_param_id = 11,
                    cloned_npc_param_id = 6000000, sp_effect_slot = "spEffectID1", minted_sp_effect_id = 60013,
                    have_soul_rate = 1.0, source_level = 2, destination_level = 1,
                    hp_multiplier = 0.5, attack_multiplier = 0.75, defense_multiplier = 0.75}},
            }
        }))!;
        void Save() => File.WriteAllText(planPath, plan.ToJsonString());
        Save();
        string output = Path.Combine(root, "scaled-output");
        ScalingTransplant.Run(planPath, gamePath, defsPath, maps, scripts, output, bossPrepared: true);
        var written = BND4.Read(Path.Combine(output, "dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx"));
        PARAM Read(string name, PARAMDEF def) { var p = PARAM.Read(written.Files.Single(f => f.Name == name).Bytes); p.ApplyParamdef(def); return p; }
        var cloned = Read("NpcParam.param", npcDef).Rows.Single(r => r.ID == 6000000);
        Check(Read("NpcParam.param", npcDef).Rows.Select(r => r.ID).SequenceEqual(new[] {11,12,13,14,6000000,6000001,9000000}), "ordered NPC table stays ordered");
        foreach (var c in donor.Cells) Check(Equals(cloned[c.Def.InternalName].Value,
            c.Def.InternalName == "spEffectID1" ? 60013 : c.Value), "clone preserves donor " + c.Def.InternalName);
        var helperClone = Read("NpcParam.param", npcDef).Rows.Single(r => r.ID == 6000001);
        foreach (var c in helperDonor.Cells) Check(Equals(helperClone[c.Def.InternalName].Value,
            c.Def.InternalName == "spEffectID2" ? 60013 : c.Value), "helper clone preserves donor " + c.Def.InternalName);
        var minted = Read("SpEffectParam.param", effectDef).Rows.Single(r => r.ID == 60013);
        Check((float)minted["haveSoulRate"].Value == 1f, "reward neutral");
        Check((float)minted["staminaAttackRate"].Value == 1f, "stamina neutral");
        Check((float)minted["bGameClearBonus"].Value == 0f, "not an NG-cycle bonus");
        Check((float)minted["maxHpRate"].Value == 0.5f, "HP normalized");
        foreach (string f in attack.Concat(defense)) Check((float)minted[f].Value == 0.75f, f);
        Check(written.Files.Single(f => f.Name == "ItemLotParam.param").Bytes.SequenceEqual(new byte[] {1,3,5,7}), "suppression preserved");
        foreach (string path in Directory.GetFiles(Path.Combine(output, "dvdroot_ps4/map/MapStudio"))) {
            var msb = MSBB.Read(path);
            Check(msb.Parts.Enemies.Single(e => e.Name == "c1000_0000").NPCParamID == 6000000, "all alternate states retargeted");
            Check(msb.Parts.Enemies.Single(e => e.Name == "c1000_0001").NPCParamID == 10, "unselected part unchanged");
        }
        Check(File.Exists(Path.Combine(output, "dvdroot_ps4/script/m24_01_00_00.luabnd.dcx")), "AI included");
        Check(File.Exists(Path.Combine(output, "scaling-report.json")), "receipt included");
        using (var helperReceipt = JsonDocument.Parse(File.ReadAllText(Path.Combine(output, "scaling-report.json")))) {
            var row = helperReceipt.RootElement.GetProperty("helper_changes").EnumerateArray().Single();
            Check(row.GetProperty("source_npc_param_id").GetInt32() == 12
                && row.GetProperty("cloned_npc_param_id").GetInt32() == 6000001
                && row.GetProperty("minted_sp_effect_id").GetInt32() == 60013, "helper receipt attests reused parent effect");
        }
        string repeated = Path.Combine(root, "scaled-repeat");
        ScalingTransplant.Run(planPath, gamePath, defsPath, maps, scripts, repeated, bossPrepared: true);
        foreach (string file in Directory.GetFiles(output, "*", SearchOption.AllDirectories)) {
            string relative = Path.GetRelativePath(output, file);
            Check(File.ReadAllBytes(file).SequenceEqual(File.ReadAllBytes(Path.Combine(repeated, relative))), "deterministic " + relative);
        }
        Check(File.ReadAllBytes(gamePath).SequenceEqual(game.Write()), "input binder untouched");
        string failure = Path.Combine(root, "scaled-failure");
        void Refused(Action action, string fragment) {
            try { action(); throw new Exception("expected refusal " + fragment); }
            catch (InvalidDataException ex) { Check(ex.Message.Contains(fragment), ex.Message); }
            Check(!Directory.Exists(failure), "failure published no output");
            Check(!Directory.GetDirectories(root, ".bb-scaled-*").Any(), "staging cleaned");
        }
        Refused(() => MapTransplant.Run(planPath, maps, failure), "actor additions require");
        plan["boss_actor_additions"]![0]!["destination_anchor_part"] = "c1000_0001"; Save();
        Refused(() => ScalingTransplant.Run(planPath, gamePath, defsPath, maps, scripts, failure, bossPrepared: true), "parent does not own");
        plan["boss_actor_additions"]![0]!["destination_anchor_part"] = "c1000_0000";
        plan["boss_actor_scaling"]![0]!["source_archetype"]!["npc_param_id"] = 11;
        plan["boss_actor_additions"]![0]!["source_archetype"]!["npc_param_id"] = 11; Save();
        string sameNpcOutput = Path.Combine(root, "same-npc-helper-output");
        ScalingTransplant.Run(planPath, gamePath, defsPath, maps, scripts, sameNpcOutput, bossPrepared: true);
        var sameNpcBinder = BND4.Read(Path.Combine(sameNpcOutput, "dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx"));
        var sameNpcTable = PARAM.Read(sameNpcBinder.Files.Single(f => f.Name == "NpcParam.param").Bytes);
        sameNpcTable.ApplyParamdef(npcDef);
        var sameNpcClone = sameNpcTable.Rows.Single(row => row.ID == 6000001);
        foreach (var cell in donor.Cells) Check(Equals(sameNpcClone[cell.Def.InternalName].Value,
            cell.Def.InternalName == "spEffectID2" ? 60013 : cell.Value), "same-NPC helper preserves original " + cell.Def.InternalName);
        plan["boss_actor_additions"]![0]!["source_anchor_part"] = "c1000_0001"; Save();
        Refused(() => ScalingTransplant.Run(planPath, gamePath, defsPath, maps, scripts, failure, bossPrepared: true), "distinct original actor");
        plan["boss_actor_additions"]![0]!["source_anchor_part"] = "c1000_0000";
        plan["boss_actor_scaling"]![0]!["source_archetype"]!["npc_param_id"] = 12;
        plan["boss_actor_additions"]![0]!["source_archetype"]!["npc_param_id"] = 12;
        plan["boss_actor_scaling"]![0]!["source_archetype"]!["npc_param_id"] = 13; Save();
        plan["boss_actor_additions"]![0]!["source_archetype"]!["npc_param_id"] = 13; Save();
        Refused(() => ScalingTransplant.Run(planPath, gamePath, defsPath, maps, scripts, failure, bossPrepared: true), "source tier");
        plan["boss_actor_scaling"]![0]!["source_archetype"]!["npc_param_id"] = 12;
        plan["boss_actor_additions"]![0]!["source_archetype"]!["npc_param_id"] = 12; Save();
        plan["boss_adapter"] = BossCanary.Adapter;
        Save();
        Refused(() => MapTransplant.Run(planPath, maps, failure), "requires --boss-scaled");
        Refused(() => ScalingTransplant.Run(planPath, gamePath, defsPath, maps, scripts, failure), "requires --boss-scaled");
        plan.AsObject().Remove("boss_adapter");
        Save();
        foreach (var (field, value, message) in new[] {
            ("have_soul_rate", 2.0, "echo-neutral"), ("hp_multiplier", 3.0, "native ladder"),
            ("cloned_npc_param_id", 7.0, "claimed range"), ("source_level", 3.0, "tier pair"),
        }) {
            var c = plan["scaling"]!["changes"]![0]!; var original = c[field]!.DeepClone();
            c[field] = field.EndsWith("_id") || field.EndsWith("_level") ? JsonValue.Create((int)value) : JsonValue.Create(value);
            Save(); Refused(() => ScalingTransplant.Run(planPath, gamePath, defsPath, maps, scripts, failure, bossPrepared: true), message);
            c[field] = original;
        }
        plan["scaling"]!["changes"]![0]!["sp_effect_slot"] = "spEffectID0"; Save();
        Refused(() => ScalingTransplant.Run(planPath, gamePath, defsPath, maps, scripts, failure, bossPrepared: true), "occupied");
        plan["scaling"]!["changes"]![0]!["sp_effect_slot"] = "spEffectID1"; Save();
        foreach (int id in new[] {60000, 6000000}) {
            var table = id == 60000 ? effects : npcs;
            table.Rows.Add(new PARAM.Row(table.Rows[0]) {ID = id});
            game.Files.Single(f => f.Name == (id == 60000 ? "SpEffectParam.param" : "NpcParam.param")).Bytes = table.Write();
            game.Write(gamePath);
            Refused(() => ScalingTransplant.Run(planPath, gamePath, defsPath, maps, scripts, failure, bossPrepared: true), "collision");
            table.Rows.RemoveAt(table.Rows.Count - 1);
            game.Files.Single(f => f.Name == (id == 60000 ? "SpEffectParam.param" : "NpcParam.param")).Bytes = table.Write();
        }
        game.Write(gamePath);
        effects.Rows[0]["soulRate"].Value = 2f;
        game.Files.Single(f => f.Name == "SpEffectParam.param").Bytes = effects.Write(); game.Write(gamePath);
        Refused(() => ScalingTransplant.Run(planPath, gamePath, defsPath, maps, scripts, failure, bossPrepared: true), "unsafe scaling template");
        effects.Rows[0]["soulRate"].Value = 1f;
        game.Files.Single(f => f.Name == "SpEffectParam.param").Bytes = effects.Write(); game.Write(gamePath);
        plan["scaling"]!["changes"]!.AsArray().Add(plan["scaling"]!["changes"]![0]!.DeepClone());
        plan["scaling"]!["change_count"] = 2; Save();
        Refused(() => ScalingTransplant.Run(planPath, gamePath, defsPath, maps, scripts, failure, bossPrepared: true), "duplicate scaling");
        plan["scaling"]!["changes"]!.AsArray().RemoveAt(1); plan["scaling"]!["change_count"] = 1; Save();
        // Late failure after parameter serialization must not publish a partial overlay.
        File.Delete(Path.Combine(scripts, "m24_01_00_00.luabnd.dcx"));
        try { ScalingTransplant.Run(planPath, gamePath, defsPath, maps, scripts, failure, bossPrepared: true); throw new Exception("missing AI accepted"); }
        catch (Exception ex) when (ex is InvalidDataException or FileNotFoundException) { Check(true, "late AI failure"); }
        Check(!Directory.Exists(failure) && !Directory.GetDirectories(root, ".bb-scaled-*").Any(), "late failure atomicity");
        Console.WriteLine($"PASS: {assertions} scaling integration assertions");
    }
}
