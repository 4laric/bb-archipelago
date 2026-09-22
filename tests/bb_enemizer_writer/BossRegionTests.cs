using System.Numerics;
using System.Text.Json;
using SoulsFormats;

internal static class BossRegionTests
{
    internal static void Run()
    {
        int assertions = 0;
        void Need(bool value, string message) { assertions++; if (!value) throw new Exception(message); }
        void Refused(Action action, string fragment) {
            try { action(); throw new Exception("expected region refusal: " + fragment); }
            catch (InvalidDataException error) { Need(error.Message.Contains(fragment), error.Message); }
        }
        void SetGeneratorNames(MSBB.Event.Generator generator, string[] parts, string[] points) {
            var type = typeof(MSBB.Event.Generator);
            type.GetProperty(nameof(MSBB.Event.Generator.SpawnPartNames))!.GetSetMethod(true)!.Invoke(generator, [parts]);
            type.GetProperty(nameof(MSBB.Event.Generator.SpawnPointNames))!.GetSetMethod(true)!.Invoke(generator, [points]);
        }
        string root = Path.Combine(Path.GetTempPath(), "bb-boss-region-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try {
            string source = Path.Combine(root, "source"), destination = Path.Combine(root, "destination");
            Directory.CreateDirectory(source); Directory.CreateDirectory(destination);
            string sourcePath = Path.Combine(source, "m23_00_00_00.msb");
            string destinationPath = Path.Combine(destination, "m26_00_00_00.msb");
            var donor = new MSBB();
            donor.Parts.Enemies.Add(new MSBB.Part.Enemy {
                Name = "source_anchor", EntityID = 100, Position = new Vector3(10, 0, 10), Rotation = new Vector3(0, 15, 0),
            });
            donor.Regions.Regions.Add(new MSBB.Region {
                Name = "source_marker", EntityID = 110, Position = new Vector3(12, 1, 13), Rotation = new Vector3(10, 30, 20),
                Shape = new MSB.Shape.Cylinder(2, 4),
            });
            var sourceGenerator = new MSBB.Event.Generator {
                Name = "source_gen", EventID = 400, EntityID = 401, PartName = "source_anchor", RegionName = "source_marker", MaxNum = 4, GenType = 2,
            };
            SetGeneratorNames(sourceGenerator,
                ["source_anchor", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", "", ""],
                ["source_marker", "", "", "", "", "", "", ""]);
            donor.Events.Generators.Add(sourceGenerator); donor.Write(sourcePath);

            var target = new MSBB();
            target.Parts.Enemies.Add(new MSBB.Part.Enemy {
                Name = "destination_anchor", EntityID = 200, Position = new Vector3(50, 0, 40), Rotation = new Vector3(0, 105, 0),
            });
            target.Regions.Regions.Add(new MSBB.Region {
                Name = "existing_region", EntityID = 210, Position = new Vector3(40, 1, 40), Shape = new MSB.Shape.Box(3, 4, 5),
            });
            target.Write(destinationPath);

            var sourceRead = MSBB.Read(sourcePath); var targetRead = MSBB.Read(destinationPath);
            var sourceAnchor = sourceRead.Parts.Enemies.Single(item => item.Name == "source_anchor");
            var targetAnchor = targetRead.Parts.Enemies.Single(item => item.Name == "destination_anchor");
            var sourceRegion = sourceRead.Regions.Regions.Single(item => item.Name == "source_marker");
            var originalRegion = targetRead.Regions.Regions.Single(item => item.Name == "existing_region");
            var sourceGen = sourceRead.Events.Generators.Single(item => item.Name == "source_gen");
            var region = new {
                source_map = "m23_00_00_00", source_region = "source_marker", source_entity_id = 110,
                source_provenance = new { format = "bb-boss-region-pin-v1", region_sha256 = BossRegionTransplant.Fingerprint("m23_00_00_00", sourceRegion) },
                source_anchor_part = "source_anchor",
                source_anchor_provenance = new { format = "bb-boss-actor-pin-v1", part_sha256 = BossActorTransplant.Fingerprint("m23_00_00_00", sourceAnchor) },
                destination_map = "m26_00_00_00", destination_region = "spawned_marker", destination_entity_id = 300,
                destination_anchor_part = "destination_anchor",
                destination_anchor_provenance = new { format = "bb-boss-actor-pin-v1", part_sha256 = BossActorTransplant.Fingerprint("m26_00_00_00", targetAnchor) },
            };
            var generator = new {
                source_map = "m23_00_00_00", source_event = "source_gen", source_event_id = 400, source_entity_id = 401,
                source_fingerprint = BossActorTransplant.GeneratorFingerprint("m23_00_00_00", sourceGen),
                destination_map = "m26_00_00_00", destination_event = "spawned_gen", destination_event_id = 500, destination_entity_id = 501,
                destination_part_name = "destination_anchor", destination_region_name = "spawned_marker",
                spawn_part_map = new Dictionary<string, string> { ["source_anchor"] = "destination_anchor" }, spawn_point_map = new Dictionary<string, string> { ["source_marker"] = "spawned_marker" },
            };
            string plan = Path.Combine(root, "plan.json");
            File.WriteAllText(plan, JsonSerializer.Serialize(new { boss_region_additions = new[] { region }, boss_generator_additions = new[] { generator } }));
            string output = Path.Combine(root, "output");
            var applied = BossRegionTransplant.Apply(plan, source, destination, output, false);
            Need(applied.Count == 1 && applied[0].DestinationRegion == "spawned_marker", "one reviewed region applied");
            BossActorTransplant.ApplyGeneratorsOnly(plan, source, destination, output);
            BossRegionTransplant.VerifyFinal(applied, destination, output);
            var written = MSBB.Read(Path.Combine(output, "m26_00_00_00.msb"));
            var spawned = written.Regions.Regions.Single(item => item.Name == "spawned_marker");
            Need(spawned.EntityID == 300 && spawned.Shape is MSB.Shape.Cylinder cylinder && cylinder.Radius == 2 && cylinder.Height == 4,
                "region preserves source identity and full cylinder shape");
            Need(Vector3.Distance(spawned.Position, new Vector3(53, 1, 38)) < .001f
                && MathF.Abs(spawned.Rotation.Y - 120) < .001f,
                "region uses the same anchor-relative rotation and translation as actors");
            Need(BossRegionTransplant.Fingerprint("m26_00_00_00", written.Regions.Regions[0])
                == BossRegionTransplant.Fingerprint("m26_00_00_00", originalRegion), "original region is byte-model stable");
            var generated = written.Events.Generators.Single(item => item.Name == "spawned_gen");
            Need(generated.RegionName == "spawned_marker" && generated.SpawnPointNames[0] == "spawned_marker",
                "generator runs after and references the reviewed added region");

            byte[] sourceBytes = File.ReadAllBytes(sourcePath), destinationBytes = File.ReadAllBytes(destinationPath);
            var regionDrift = MSBB.Read(sourcePath); regionDrift.Regions.Regions.Single().Position += Vector3.UnitY; regionDrift.Write(sourcePath);
            Refused(() => BossRegionTransplant.Apply(plan, source, destination, Path.Combine(root, "region-drift"), false), "region provenance pin drift");
            File.WriteAllBytes(sourcePath, sourceBytes);
            var sourceDrift = MSBB.Read(sourcePath); sourceDrift.Parts.Enemies.Single().Position += Vector3.UnitX; sourceDrift.Write(sourcePath);
            Refused(() => BossRegionTransplant.Apply(plan, source, destination, Path.Combine(root, "source-drift"), false), "source region anchor provenance pin drift");
            File.WriteAllBytes(sourcePath, sourceBytes);
            var destinationDrift = MSBB.Read(destinationPath); destinationDrift.Parts.Enemies.Single().Position += Vector3.UnitZ; destinationDrift.Write(destinationPath);
            Refused(() => BossRegionTransplant.Apply(plan, source, destination, Path.Combine(root, "destination-drift"), false), "destination region anchor provenance pin drift");
            File.WriteAllBytes(destinationPath, destinationBytes);

            var nameCollision = new { region.source_map, region.source_region, region.source_entity_id, region.source_provenance,
                region.source_anchor_part, region.source_anchor_provenance, region.destination_map, destination_region = "existing_region",
                region.destination_entity_id, region.destination_anchor_part, region.destination_anchor_provenance };
            File.WriteAllText(plan, JsonSerializer.Serialize(new { boss_region_additions = new[] { nameCollision } }));
            Refused(() => BossRegionTransplant.Apply(plan, source, destination, Path.Combine(root, "name-collision"), false), "region destination name already exists");
            var idCollision = new { region.source_map, region.source_region, region.source_entity_id, region.source_provenance,
                region.source_anchor_part, region.source_anchor_provenance, region.destination_map, region.destination_region,
                destination_entity_id = 200, region.destination_anchor_part, region.destination_anchor_provenance };
            File.WriteAllText(plan, JsonSerializer.Serialize(new { boss_region_additions = new[] { idCollision } }));
            Refused(() => BossRegionTransplant.Apply(plan, source, destination, Path.Combine(root, "id-collision"), false), "region destination entity ID already exists");
            File.WriteAllText(plan, JsonSerializer.Serialize(new { boss_region_additions = new[] { region, region } }));
            Refused(() => BossRegionTransplant.Read(plan, false), "duplicate region destination name");
            var unbound = new { region.source_map, region.source_region, region.source_entity_id, region.source_provenance,
                region.source_anchor_part, region.source_anchor_provenance, region.destination_map, destination_region = "unbound_marker",
                destination_entity_id = -1, region.destination_anchor_part, region.destination_anchor_provenance };
            File.WriteAllText(plan, JsonSerializer.Serialize(new { boss_region_additions = new[] { unbound } }));
            var unboundOutput = Path.Combine(root, "unbound-output");
            var unboundApplied = BossRegionTransplant.Apply(plan, source, destination, unboundOutput, false);
            Need(unboundApplied.Single().DestinationEntityId == -1
                && MSBB.Read(Path.Combine(unboundOutput, "m26_00_00_00.msb")).Regions.Regions.Any(item => item.Name == "unbound_marker"),
                "unbound source-style region identity remains name-addressable");

            string nonBossPlan = Path.Combine(root, "nonboss.json");
            File.WriteAllText(nonBossPlan, JsonSerializer.Serialize(new {
                format = "bb-enemizer-plan-v2", dry_run = true, swaps = Array.Empty<object>(), boss_region_additions = new[] { region },
            }));
            Refused(() => MapTransplant.Run(nonBossPlan, destination, Path.Combine(root, "nonboss-output")),
                "boss region additions require --boss-encounters");
            Console.WriteLine($"PASS: {assertions} boss region transplant assertions");
        }
        finally {
            if (Path.GetDirectoryName(root) != Path.GetTempPath().TrimEnd(Path.DirectorySeparatorChar)
                || !Path.GetFileName(root).StartsWith("bb-boss-region-")) throw new Exception("unsafe cleanup path");
            Directory.Delete(root, true);
        }
    }
}
