using System.Globalization;
using System.Numerics;
using System.Text;
using SoulsFormats;

if (args.Length != 2)
{
    Console.Error.WriteLine("usage: MSBBMiner <mapstudio-root> <output-directory>");
    return 2;
}

string root = Path.GetFullPath(args[0]);
string output = Path.GetFullPath(args[1]);
Directory.CreateDirectory(output);

string[] files = Directory.GetFiles(root, "*.msb", SearchOption.AllDirectories);
Array.Sort(files, StringComparer.OrdinalIgnoreCase);

using var treasures = Tsv("msb_treasures.tsv",
    "map_path", "map_name", "scope", "event_name", "event_id", "event_entity_id",
    "event_part_name", "event_region_name", "treasure_part_name", "part_match_count",
    "part_type", "part_entity_id", "model_name", "x", "y", "z",
    "item_lot_1", "item_lot_2", "item_lot_3", "in_chest", "start_disabled");
using var enemies = Tsv("msb_enemies.tsv",
    "map_path", "map_name", "part_name", "part_entity_id", "model_name", "npc_param_id",
    "think_param_id", "talk_id", "chara_init_id", "collision_name", "x", "y", "z", "dummy");
using var regions = Tsv("msb_regions.tsv",
    "map_path", "map_name", "region_name", "entity_id", "shape", "x", "y", "z");
using var failures = Tsv("msb_failures.tsv", "map_path", "error_type", "message");

int parsed = 0, treasureCount = 0, enemyCount = 0, regionCount = 0, failed = 0;
foreach (string file in files)
{
    string relative = Path.GetRelativePath(root, file).Replace('\\', '/');
    string mapName = Path.GetFileNameWithoutExtension(file);
    try
    {
        MSBB msb = MSBB.Read(file);
        var parts = msb.Parts.GetEntries().GroupBy(p => p.Name, StringComparer.Ordinal)
            .ToDictionary(g => g.Key, g => g.ToArray(), StringComparer.Ordinal);

        foreach (MSBB.Event.Treasure t in msb.Events.Treasures)
        {
            parts.TryGetValue(t.TreasurePartName ?? "", out MSBB.Part[]? matches);
            MSBB.Part? part = matches?.Length == 1 ? matches[0] : null;
            Vector3? pos = part?.Position;
            Row(treasures, relative, mapName, Scope(relative, mapName), t.Name, t.EventID, t.EntityID,
                t.PartName, t.RegionName, t.TreasurePartName,
                matches?.Length ?? 0,
                part?.GetType().Name, part?.EntityID, part?.ModelName,
                pos?.X, pos?.Y, pos?.Z, t.ItemLot1, t.ItemLot2, t.ItemLot3,
                t.InChest, t.StartDisabled);
            treasureCount++;
        }

        foreach (MSBB.Part.Enemy e in msb.Parts.Enemies)
        {
            Row(enemies, relative, mapName, e.Name, e.EntityID, e.ModelName, e.NPCParamID,
                e.ThinkParamID, e.TalkID, e.CharaInitID, e.CollisionName,
                e.Position.X, e.Position.Y, e.Position.Z, false);
            enemyCount++;
        }
        foreach (MSBB.Part.DummyEnemy e in msb.Parts.DummyEnemies)
        {
            Row(enemies, relative, mapName, e.Name, e.EntityID, e.ModelName, e.NPCParamID,
                e.ThinkParamID, e.TalkID, e.CharaInitID, e.CollisionName,
                e.Position.X, e.Position.Y, e.Position.Z, true);
            enemyCount++;
        }

        foreach (MSBB.Region r in msb.Regions.Regions.Where(r => r.EntityID > 0))
        {
            Row(regions, relative, mapName, r.Name, r.EntityID, r.Shape.GetType().Name,
                r.Position.X, r.Position.Y, r.Position.Z);
            regionCount++;
        }
        parsed++;
    }
    catch (Exception ex)
    {
        Row(failures, relative, ex.GetType().Name, ex.Message);
        failed++;
    }
}

Console.WriteLine($"files={files.Length} parsed={parsed} failed={failed} treasures={treasureCount} enemies={enemyCount} entity_regions={regionCount}");
return failed == 0 ? 0 : 1;

StreamWriter Tsv(string name, params string[] header)
{
    var writer = new StreamWriter(Path.Combine(output, name), false, new UTF8Encoding(false));
    Row(writer, header.Cast<object?>().ToArray());
    return writer;
}

static void Row(StreamWriter writer, params object?[] values)
{
    writer.WriteLine(string.Join('\t', values.Select(Format)));
}

static string Format(object? value)
{
    string text = value switch
    {
        null => "",
        float f => f.ToString("R", CultureInfo.InvariantCulture),
        double d => d.ToString("R", CultureInfo.InvariantCulture),
        IFormattable formattable => formattable.ToString(null, CultureInfo.InvariantCulture) ?? "",
        _ => value.ToString() ?? "",
    };
    return text.Replace("\t", " ").Replace("\r", " ").Replace("\n", " ");
}

static string Scope(string relative, string mapName)
{
    if (relative.Contains('/', StringComparison.Ordinal) || mapName.StartsWith("m29_", StringComparison.Ordinal))
        return "chalice_template";
    return "fixed_map";
}
