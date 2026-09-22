using System.Numerics;
using System.Text.Json;
using SoulsFormats;

internal static class BossActorTests
{
    internal static void Run()
    {
        int assertions = 0;
        void Need(bool value) { assertions++; if (!value) throw new Exception("boss actor transplant invariant failed"); }
        string root = Path.Combine(Path.GetTempPath(), "bb-boss-actor-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try {
            string source = Path.Combine(root, "source"), destination = Path.Combine(root, "destination"), output = Path.Combine(root, "output");
            Directory.CreateDirectory(source); Directory.CreateDirectory(destination);
            var donorMap = new MSBB(); donorMap.Models.Enemies.Add(new MSBB.Model.Enemy { Name = "c9000", SibPath = "" });
            donorMap.Parts.Enemies.Add(new MSBB.Part.Enemy { Name = "anchor", EntityID = 100, Position = new Vector3(10, 0, 10), Rotation = new Vector3(0, 0, 0) });
            donorMap.Parts.Enemies.Add(new MSBB.Part.Enemy { Name = "donor", EntityID = 101, ModelName = "c9000", NPCParamID = 90, ThinkParamID = 91, CharaInitID = 0, Position = new Vector3(12, 0, 13), Rotation = new Vector3(0, .5f, 0) });
            donorMap.Write(Path.Combine(source, "m23_00_00_00.msb"));
            var targetMap = new MSBB(); targetMap.Models.Enemies.Add(new MSBB.Model.Enemy { Name = "c1000", SibPath = "" });
            targetMap.Parts.Collisions.Add(new MSBB.Part.Collision { Name = "h0000" });
            var anchor = new MSBB.Part.Enemy { Name = "target_anchor", EntityID = 200, ModelName = "c1000", Position = new Vector3(50, 0, 40), Rotation = new Vector3(0, MathF.PI / 2, 0), CollisionName = "h0000" };
            anchor.DrawGroups[0] = 7; anchor.DispGroups[0] = 8; anchor.BackreadGroups[0] = 9; targetMap.Parts.Enemies.Add(anchor);
            targetMap.Write(Path.Combine(destination, "m24_01_00_00.msb"));
            var plan = new { boss_actor_additions = new[] { new { source_map = "m23_00_00_00", source_part = "donor", source_anchor_part = "anchor", source_entity_id = 101, source_archetype = new { model_name = "c9000", npc_param_id = 90, think_param_id = 91, chara_init_id = 0 }, destination_map = "m24_01_00_00", destination_anchor_part = "target_anchor", destination_part = "spawned", destination_entity_id = 300 } } };
            string planPath = Path.Combine(root, "plan.json"); File.WriteAllText(planPath, JsonSerializer.Serialize(plan));
            Need(BossActorTransplant.Apply(planPath, source, destination, output, false) == 1);
            var written = MSBB.Read(Path.Combine(output, "m24_01_00_00.msb")); var spawned = written.Parts.Enemies.Single(e => e.Name == "spawned");
            Need(spawned.EntityID == 300 && spawned.ModelName == "c9000" && spawned.NPCParamID == 90 && spawned.ThinkParamID == 91);
            Need(Vector3.Distance(spawned.Position, new Vector3(53, 0, 38)) < .001f && MathF.Abs(spawned.Rotation.Y - (.5f + MathF.PI / 2)) < .001f);
            Need(spawned.CollisionName == "h0000" && spawned.DrawGroups[0] == 7 && spawned.DispGroups[0] == 8 && spawned.BackreadGroups[0] == 9);
            Need(written.Parts.Enemies.Single(e => e.Name == "target_anchor").EntityID == 200);
            Console.WriteLine($"PASS: {assertions} boss actor transplant assertions");
        } finally { Directory.Delete(root, true); }
    }
}
