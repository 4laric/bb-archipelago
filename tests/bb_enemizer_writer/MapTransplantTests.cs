using System.Text.Json;
using SoulsFormats;

internal static class MapTransplantTests
{
    internal static void Run()
    {
        int assertions = 0;
        void Need(bool value) { assertions++; if (!value) throw new Exception("map transplant alias invariant failed"); }
        void Refused(Action action, string fragment) {
            try { action(); throw new Exception("expected map transplant refusal: " + fragment); }
            catch (InvalidDataException error) { Need(error.Message.Contains(fragment)); }
        }

        string root = Path.Combine(Path.GetTempPath(), "bb-map-transplant-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(root);
        try {
            string maps = Path.Combine(root, "maps"); Directory.CreateDirectory(maps);
            var map = new MSBB();
            foreach (string model in new[] { "c1000", "c2000", "c3000", "c4000" })
                map.Models.Enemies.Add(new MSBB.Model.Enemy { Name = model, SibPath = "" });
            map.Parts.Enemies.Add(new MSBB.Part.Enemy {
                Name = "first", EntityID = 100, ModelName = "c1000", NPCParamID = 10,
                ThinkParamID = 11, CharaInitID = 12,
            });
            map.Parts.Enemies.Add(new MSBB.Part.Enemy {
                Name = "second", EntityID = 200, ModelName = "c1000", NPCParamID = 10,
                ThinkParamID = 11, CharaInitID = 12,
            });
            map.Parts.Enemies.Add(new MSBB.Part.Enemy {
                Name = "third", EntityID = 300, ModelName = "c1000", NPCParamID = 10,
                ThinkParamID = 11, CharaInitID = 12,
            });
            map.Write(Path.Combine(maps, "m99_00_00_00.msb"));

            var source = new { model_name = "c1000", npc_param_id = 10, think_param_id = 11, chara_init_id = 12 };
            var firstTarget = new { model_name = "c2000", npc_param_id = 20, think_param_id = 21, chara_init_id = 22 };
            var secondTarget = new { model_name = "c3000", npc_param_id = 30, think_param_id = 31, chara_init_id = 32 };
            var thirdTarget = new { model_name = "c4000", npc_param_id = 40, think_param_id = 41, chara_init_id = 42 };
            object Swap(string logicalKey, string destinationKey, object target) => new {
                logical_key = logicalKey,
                destination_keys = new[] { destinationKey },
                destination_sources = new Dictionary<string, object> { [destinationKey] = source },
                source,
                target,
            };
            string plan = Path.Combine(root, "plan.json");
            File.WriteAllText(plan, JsonSerializer.Serialize(new {
                format = "bb-enemizer-plan-v2", dry_run = true,
                swaps = new[] {
                    Swap("first", "m99_00_00_00:first", firstTarget),
                    Swap("second", "m99_00_00_00.msb:second", secondTarget),
                    Swap("third", "m99_00_00_00.msb.dcx:third", thirdTarget),
                },
            }));
            string output = Path.Combine(root, "output");
            Need(MapTransplant.Run(plan, maps, output) == 0);
            var written = MSBB.Read(Path.Combine(output, "m99_00_00_00.msb"));
            var first = written.Parts.Enemies.Single(part => part.Name == "first");
            var second = written.Parts.Enemies.Single(part => part.Name == "second");
            var third = written.Parts.Enemies.Single(part => part.Name == "third");
            Need(first.ModelName == "c2000" && first.NPCParamID == 20
                && first.ThinkParamID == 21 && first.CharaInitID == 22);
            Need(second.ModelName == "c3000" && second.NPCParamID == 30
                && second.ThinkParamID == 31 && second.CharaInitID == 32);
            Need(third.ModelName == "c4000" && third.NPCParamID == 40
                && third.ThinkParamID == 41 && third.CharaInitID == 42);

            foreach (string alias in new[] { "m99_00_00_00.msb", "m99_00_00_00.msb.dcx", "M99_00_00_00" }) {
                string label = alias.Replace('.', '-');
                string aliasPlan = Path.Combine(root, $"alias-plan{label}.json");
                File.WriteAllText(aliasPlan, JsonSerializer.Serialize(new {
                    format = "bb-enemizer-plan-v2", dry_run = true,
                    swaps = new[] {
                        Swap("bare", "m99_00_00_00:first", firstTarget),
                        Swap("aliased", $"{alias}:first", firstTarget),
                    },
                }));
                string refused = Path.Combine(root, $"refused{label}");
                Refused(() => MapTransplant.Run(aliasPlan, maps, refused), "duplicate physical destination Part alias");
                Need(!Directory.Exists(refused));
            }
            Console.WriteLine($"PASS: {assertions} map transplant alias assertions");
        }
        finally {
            if (Path.GetDirectoryName(root) != Path.GetTempPath().TrimEnd(Path.DirectorySeparatorChar)
                || !Path.GetFileName(root).StartsWith("bb-map-transplant-")) throw new Exception("unsafe cleanup path");
            Directory.Delete(root, true);
        }
    }
}
