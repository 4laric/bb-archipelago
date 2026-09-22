using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Nodes;
using SoulsFormats;

internal static class BossExternalReferenceTests
{
    internal static void Run()
    {
        int assertions = 0;
        void Need(bool value) { assertions++; if (!value) throw new Exception("external reference invariant failed"); }
        void Refused(Action action) {
            try { action(); throw new Exception("expected external reference refusal"); }
            catch (InvalidDataException) { assertions++; }
        }
        string HashFile(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path))).ToLowerInvariant();
        byte[] TargetArgs(int actor, int target) {
            byte[] bytes = new byte[8]; BitConverter.GetBytes(actor).CopyTo(bytes, 0); BitConverter.GetBytes(target).CopyTo(bytes, 4); return bytes;
        }
        EMEVD TargetEvent(long id, int actor, int target, int count = 1) {
            var file = new EMEVD(EMEVD.Game.Bloodborne); var item = new EMEVD.Event(id);
            for (int i = 0; i < count; i++) item.Instructions.Add(new EMEVD.Instruction(2004, 11, TargetArgs(actor, target)));
            file.Events.Add(item); return file;
        }
        string root = Path.Combine(Path.GetTempPath(), "bb-external-reference-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try {
            string maps = Path.Combine(root, "maps"), events = Path.Combine(root, "events"), outputMaps = Path.Combine(root, "output-maps"), outputEvents = Path.Combine(root, "output-events");
            Directory.CreateDirectory(maps); Directory.CreateDirectory(events); Directory.CreateDirectory(outputMaps); Directory.CreateDirectory(outputEvents);
            void WriteMap(string directory, string map, int? entityId = null) {
                var msb = new MSBB();
                if (entityId is int id) {
                    msb.Models.Enemies.Add(new MSBB.Model.Enemy { Name = "c9000", SibPath = "" });
                    msb.Parts.Enemies.Add(new MSBB.Part.Enemy { Name = "materialized", EntityID = id, ModelName = "c9000" });
                }
                msb.Write(Path.Combine(directory, map + ".msb"));
            }
            WriteMap(maps, "m35_00_00_00");
            foreach (string map in new[] { "m24_01_00_00", "m24_01_00_01", "m24_01_00_11" }) {
                WriteMap(maps, map); File.Copy(Path.Combine(maps, map + ".msb"), Path.Combine(outputMaps, map + ".msb"));
            }
            string sourceEvent = Path.Combine(events, "m35_00_00_00.emevd.dcx");
            TargetEvent(13504802, 3500800, 3500801).Write(sourceEvent);
            string destinationEvent = Path.Combine(outputEvents, "m24_01_00_00.emevd.dcx");
            TargetEvent(12414702, 2410800, 3500801).Write(destinationEvent);
            var reference = new {
                format = "bb-boss-external-reference-v1", entity_id = 3500801, source_map = "m35_00_00_00",
                destination_maps = new[] { "m24_01_00_00", "m24_01_00_01", "m24_01_00_11" },
                source_map_sha256 = HashFile(Path.Combine(maps, "m35_00_00_00.msb")),
                destination_map_sha256 = new Dictionary<string, string> {
                    ["m24_01_00_00"] = HashFile(Path.Combine(maps, "m24_01_00_00.msb")),
                    ["m24_01_00_01"] = HashFile(Path.Combine(maps, "m24_01_00_01.msb")),
                    ["m24_01_00_11"] = HashFile(Path.Combine(maps, "m24_01_00_11.msb")),
                },
                source_event_file = "m35_00_00_00.emevd.dcx", source_event_sha256 = HashFile(sourceEvent),
                source_event_id = 13504802, source_actor = 3500800,
                destination_event_file = "m24_01_00_00.emevd.dcx", destination_event_id = 12414702, destination_actor = 2410800,
                evidence_status = "inferred", runtime_status = "unobserved",
            };
            string plan = Path.Combine(root, "plan.json");
            File.WriteAllText(plan, JsonSerializer.Serialize(new { boss_external_references = new[] { reference } }));
            var records = BossExternalReference.Read(plan, required: false);
            Need(records.Count == 1 && records[0].EntityId == 3500801);
            BossExternalReference.ValidateInputs(records, maps, events);
            BossExternalReference.ValidateFinal(records, outputMaps, outputEvents);
            string retained = Path.Combine(root, "bb-enemizer-plan.json"); File.Copy(plan, retained);
            BossExternalReference.ValidateRetainedPlan(plan, retained);
            Need(BossExternalReference.Read(retained, false).Single().DestinationActor == 2410800);
            BossExternalReference.ValidateEncounterBindings(records, [new BossEncounter.Encounter("m24_01_00_00.emevd.dcx", new string('a', 64), [12414702], new(), [1])]);

            WriteMap(maps, "m24_01_00_01", 3500801);
            var altered = records[0] with { DestinationMapSha256 = new Dictionary<string, string>(records[0].DestinationMapSha256) {
                ["m24_01_00_01"] = HashFile(Path.Combine(maps, "m24_01_00_01.msb")) } };
            Refused(() => BossExternalReference.ValidateInputs([altered], maps, events));
            TargetEvent(12414702, 2410800, 3500801, 2).Write(destinationEvent);
            Refused(() => BossExternalReference.ValidateFinal(records, outputMaps, outputEvents));
            File.WriteAllText(plan, JsonSerializer.Serialize(new { boss_external_references = new[] { reference }, boss_external_materializations = new[] { 3500801 } }));
            Refused(() => BossExternalReference.Read(plan, required: false));
            var materializedRecord = JsonNode.Parse(JsonSerializer.Serialize(new { boss_external_references = new[] { reference } }))!.AsObject();
            materializedRecord["boss_external_references"]!.AsArray()[0]!["materialize"] = true;
            File.WriteAllText(plan, materializedRecord.ToJsonString());
            Refused(() => BossExternalReference.Read(plan, required: false));
            Refused(() => BossExternalReference.ValidateEncounterBindings(records,
                [new BossEncounter.Encounter("m24_01_00_00.emevd.dcx", new string('a', 64), [99], new(), [1])]));
            Console.WriteLine($"PASS: {assertions} boss external reference assertions");
        } finally { Directory.Delete(root, true); }
    }
}
