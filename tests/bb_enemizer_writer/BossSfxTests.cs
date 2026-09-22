using System.Text.Json;
using SoulsFormats;

internal static class BossSfxTests
{
    internal static void Run()
    {
        int assertions = 0;
        void Need(bool value, string message) { assertions++; if (!value) throw new Exception(message); }
        void Refused(Action action, string fragment) {
            try { action(); throw new Exception("expected SFX refusal: " + fragment); }
            catch (InvalidDataException error) { Need(error.Message.Contains(fragment), error.Message); }
        }
        string root = Path.Combine(Path.GetTempPath(), "bb-boss-sfx-" + Guid.NewGuid().ToString("N")); Directory.CreateDirectory(root);
        try {
            string source = Path.Combine(root, "source"), destination = Path.Combine(root, "destination"), plan = Path.Combine(root, "plan.json");
            Directory.CreateDirectory(source); Directory.CreateDirectory(destination);
            string sourcePath = Path.Combine(source, "m35_00_00_00.msb"), destinationPath = Path.Combine(destination, "m34_00_00_00.msb");
            var donor = new MSBB(); donor.Models.Enemies.Add(new MSBB.Model.Enemy { Name = "c4030", SibPath = "" });
            donor.Parts.Enemies.Add(new MSBB.Part.Enemy { Name = "source_anchor", EntityID = 3500800, ModelName = "c4030" });
            donor.Parts.Enemies.Add(new MSBB.Part.Enemy { Name = "source_part", EntityID = 3500801, ModelName = "c4030" });
            donor.Regions.Regions.Add(new MSBB.Region { Name = "source_region", EntityID = -1 });
            donor.Events.SFX.Add(new MSBB.Event.SFX { Name = "source_sfx", EventID = 144, EntityID = 3503850,
                PartName = "source_part", RegionName = "source_region", UnkE0C = 11, UnkE0D = 12, UnkE0E = 13,
                UnkE0F = 14, EffectID = 640320, StartDisabled = false });
            donor.Write(sourcePath);
            var target = new MSBB(); target.Models.Enemies.Add(new MSBB.Model.Enemy { Name = "c3400", SibPath = "" });
            target.Parts.Enemies.Add(new MSBB.Part.Enemy { Name = "destination_anchor", EntityID = 3400800, ModelName = "c3400" });
            target.Parts.Enemies.Add(new MSBB.Part.Enemy { Name = "destination_part", EntityID = 3400801, ModelName = "c3400" });
            target.Regions.Regions.Add(new MSBB.Region { Name = "destination_region", EntityID = -1 });
            target.Regions.Regions.Add(new MSBB.Region { Name = "bound_region", EntityID = 980030 });
            target.Events.SFX.Add(new MSBB.Event.SFX { Name = "original_sfx", EventID = 45, EntityID = 3403850,
                PartName = "destination_part", RegionName = "destination_region", EffectID = 1, StartDisabled = true });
            target.Events.Generators.Add(new MSBB.Event.Generator { Name = "existing_generator", EventID = 46, EntityID = 3403851 });
            target.Write(destinationPath);
            var sourceRead = MSBB.Read(sourcePath); var destinationRead = MSBB.Read(destinationPath);
            var sourceSfx = sourceRead.Events.SFX.Single(); var sourceAnchor = sourceRead.Parts.Enemies.Single(item => item.Name == "source_anchor");
            var destinationAnchor = destinationRead.Parts.Enemies.Single(item => item.Name == "destination_anchor"); var originalSfx = destinationRead.Events.SFX.Single();
            var addition = new {
                source_map = "m35_00_00_00", source_event = "source_sfx", source_event_id = 144, source_entity_id = 3503850,
                source_provenance = new { format = "bb-boss-sfx-pin-v1", event_sha256 = BossSfxTransplant.Fingerprint("m35_00_00_00", sourceSfx) },
                source_anchor_part = "source_anchor", source_anchor_provenance = new { format = "bb-boss-actor-pin-v1", part_sha256 = BossActorTransplant.Fingerprint("m35_00_00_00", sourceAnchor) },
                destination_map = "m34_00_00_00", destination_event = "ap_lf_sfx_1", destination_event_id = 900, destination_entity_id = 980027,
                destination_part_name = "destination_part", destination_region_name = "destination_region",
                destination_anchor_part = "destination_anchor", destination_anchor_provenance = new { format = "bb-boss-actor-pin-v1", part_sha256 = BossActorTransplant.Fingerprint("m34_00_00_00", destinationAnchor) },
            };
            var addition2 = new {
                addition.source_map, addition.source_event, addition.source_event_id, addition.source_entity_id, addition.source_provenance,
                addition.source_anchor_part, addition.source_anchor_provenance, addition.destination_map,
                destination_event = "ap_lf_sfx_2", destination_event_id = 899, destination_entity_id = 980028,
                addition.destination_part_name, addition.destination_region_name, addition.destination_anchor_part, addition.destination_anchor_provenance,
            };
            void WritePlan(params object[] items) => File.WriteAllText(plan, JsonSerializer.Serialize(new { boss_sfx_additions = items }));
            WritePlan(addition, addition2); string output = Path.Combine(root, "output");
            var applied = BossSfxTransplant.Apply(plan, source, destination, output, false);
            Need(applied.Select(item => item.DestinationEventId).SequenceEqual(new[] { 900, 899 })
                && applied.Select(item => item.DestinationEntityId).SequenceEqual(new[] { 980027, 980028 }),
                "reviewed SFX additions retain manifest order even when EventIDs descend");
            BossSfxTransplant.VerifyFinal(applied, destination, output);
            var written = MSBB.Read(Path.Combine(output, "m34_00_00_00.msb"));
            Need(written.Events.SFX.Count == 3 && written.Events.SFX.Select(item => item.EventID).SequenceEqual(new[] { 45, 900, 899 }),
                "SFX additions append in reviewed order after preserved native SFX order");
            var clone = written.Events.SFX.Single(item => item.Name == "ap_lf_sfx_1");
            Need(clone.EventID == 900 && clone.EntityID == 980027 && clone.PartName == "destination_part" && clone.RegionName == "destination_region",
                "SFX uses only declared destination identity and references");
            Need(clone.EffectID == 640320 && !clone.StartDisabled && clone.UnkE0C == 11 && clone.UnkE0D == 12 && clone.UnkE0E == 13 && clone.UnkE0F == 14,
                "SFX copies all source Event.SFX persisted fields");
            Need(BossSfxTransplant.Fingerprint("m34_00_00_00", written.Events.SFX[0]) == BossSfxTransplant.Fingerprint("m34_00_00_00", originalSfx),
                "original destination SFX record remains byte-semantic identical");
            var sourceBytes = File.ReadAllBytes(sourcePath); var destinationBytes = File.ReadAllBytes(destinationPath);
            var sourceDrift = MSBB.Read(sourcePath); sourceDrift.Events.SFX.Single().EffectID = 640321; sourceDrift.Write(sourcePath);
            Refused(() => BossSfxTransplant.Apply(plan, source, destination, Path.Combine(root, "source-drift"), false), "SFX provenance pin drift"); File.WriteAllBytes(sourcePath, sourceBytes);
            var destinationDrift = MSBB.Read(destinationPath); destinationDrift.Parts.Enemies.Single(item => item.Name == "destination_anchor").EntityID++;
            destinationDrift.Write(destinationPath);
            Refused(() => BossSfxTransplant.Apply(plan, source, destination, Path.Combine(root, "anchor-drift"), false), "destination SFX anchor provenance pin drift"); File.WriteAllBytes(destinationPath, destinationBytes);
            var eventIdCollision = new { addition.source_map, addition.source_event, addition.source_event_id, addition.source_entity_id, addition.source_provenance, addition.source_anchor_part, addition.source_anchor_provenance, addition.destination_map, addition.destination_event, destination_event_id = 46, addition.destination_entity_id, addition.destination_part_name, addition.destination_region_name, addition.destination_anchor_part, addition.destination_anchor_provenance };
            WritePlan(eventIdCollision); Refused(() => BossSfxTransplant.Apply(plan, source, destination, Path.Combine(root, "event-id-collision"), false), "SFX destination event ID already exists");
            var entityCollision = new { addition.source_map, addition.source_event, addition.source_event_id, addition.source_entity_id, addition.source_provenance, addition.source_anchor_part, addition.source_anchor_provenance, addition.destination_map, addition.destination_event, addition.destination_event_id, destination_entity_id = 980030, addition.destination_part_name, addition.destination_region_name, addition.destination_anchor_part, addition.destination_anchor_provenance };
            WritePlan(entityCollision); Refused(() => BossSfxTransplant.Apply(plan, source, destination, Path.Combine(root, "entity-collision"), false), "SFX destination entity ID already exists");
            var missingRegion = new { addition.source_map, addition.source_event, addition.source_event_id, addition.source_entity_id, addition.source_provenance, addition.source_anchor_part, addition.source_anchor_provenance, addition.destination_map, addition.destination_event, addition.destination_event_id, addition.destination_entity_id, addition.destination_part_name, destination_region_name = "missing_region", addition.destination_anchor_part, addition.destination_anchor_provenance };
            WritePlan(missingRegion); Refused(() => BossSfxTransplant.Apply(plan, source, destination, Path.Combine(root, "missing-region"), false), "SFX destination Region mapping is missing or ambiguous");
            File.WriteAllText(plan, JsonSerializer.Serialize(new { format = "bb-enemizer-plan-v2", dry_run = true, swaps = Array.Empty<object>(), boss_sfx_additions = new[] { addition } }));
            Refused(() => MapTransplant.Run(plan, destination, Path.Combine(root, "nonboss")), "boss SFX additions require --boss-encounters");
            Console.WriteLine($"PASS: {assertions} boss SFX transplant assertions");
        } finally {
            if (Path.GetDirectoryName(root) != Path.GetTempPath().TrimEnd(Path.DirectorySeparatorChar) || !Path.GetFileName(root).StartsWith("bb-boss-sfx-")) throw new Exception("unsafe cleanup path");
            Directory.Delete(root, true);
        }
    }
}
