// Forges the SYNTHETIC binary fixtures the integration CI leg runs the real
// tool chain against. Nothing here is derived from game data: every id, name,
// and row is invented, and the suppression plan's rows are rebuilt as a fresh
// synthetic ItemLotParam, so no licensed bytes are needed to prove that the
// miner, planner, and both writers actually agree on the formats.
//
// usage: BBFixtureForge <output-root> --suppression-plan <plan.json>
//
// Emits under <output-root>:
//   mapstudio/m99_00_00_00.msb, m99_00_00_01.msb
//     Two alternate map states carrying the same four placements: two
//     ordinary enemies (randomizable), one talk-bound NPC (protected), one
//     dummy/script spawn (protected). The pair exercises the planner's
//     logical-slot grouping across alternate states.
//   param/gameparam.parambnd.dcx
//     A one-param binder whose ItemLotParam rows are rebuilt from the plan's
//     edits: row id = item_lot_id, getItemFlagId = acquisition_flag, slot 01
//     carries the edit's category/item so the writer's preflight matches
//     exactly one slot per edit.
//   paramdef/paramdef.paramdefbnd.dcx
//     The matching synthetic ItemLotParam definition (s32 fields only).
//
// Every written file is re-read before the tool exits; a forge that cannot
// round-trip its own output fails loudly here, not inside a later tool.

using System.Numerics;
using System.Text.Json;
using System.Text.Json.Serialization;
using SoulsFormats;

if (args.Length != 3 || args[1] != "--suppression-plan")
{
    Console.Error.WriteLine("usage: BBFixtureForge <output-root> --suppression-plan <plan.json>");
    return 2;
}

string outputRoot = Path.GetFullPath(args[0]);
string planPath = Path.GetFullPath(args[2]);

Plan plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath))
    ?? throw new InvalidDataException("suppression plan is empty");
if (plan.Format != "bb-vanilla-suppression-plan-v2")
    throw new InvalidDataException($"unsupported plan format {plan.Format}");
if (plan.Edits.Count == 0)
    throw new InvalidDataException("suppression plan contains no edits");

string mapStudio = Path.Combine(outputRoot, "mapstudio");
Directory.CreateDirectory(mapStudio);

// The same four placements in two alternate states. Part names repeat across
// the pair on purpose: the planner must treat them as one logical slot.
var placements = new[]
{
    // name, model, npcParam, thinkParam, talkId, charaInit, entityId, position, dummy
    new Placement("c1000_0000", "c1000", 100000, 100001, 0, 0, 1000, new Vector3(0, 0, 0), false),
    new Placement("c2000_0000", "c2000", 200000, 200001, 0, 0, 1001, new Vector3(10, 0, 0), false),
    new Placement("c3000_0000", "c3000", 300000, 300001, 77, 0, 1002, new Vector3(20, 0, 0), false),
    new Placement("c9000_0000", "c9000", 900000, 900001, 0, 0, 1003, new Vector3(30, 0, 0), true),
};
foreach (string mapName in new[] { "m99_00_00_00", "m99_00_00_01" })
{
    var msb = new MSBB();
    foreach (Placement placement in placements)
    {
        if (!msb.Models.Enemies.Any(model => model.Name == placement.Model))
            msb.Models.Enemies.Add(new MSBB.Model.Enemy { Name = placement.Model, SibPath = "" });
        if (placement.Dummy)
        {
            msb.Parts.DummyEnemies.Add(new MSBB.Part.DummyEnemy {
                Name = placement.Name, ModelName = placement.Model,
                NPCParamID = placement.NpcParam, ThinkParamID = placement.ThinkParam,
                EntityID = placement.EntityId, Position = placement.Position,
            });
        }
        else
        {
            msb.Parts.Enemies.Add(new MSBB.Part.Enemy {
                Name = placement.Name, ModelName = placement.Model,
                NPCParamID = placement.NpcParam, ThinkParamID = placement.ThinkParam,
                TalkID = placement.TalkId, CharaInitID = placement.CharaInit,
                EntityID = placement.EntityId, Position = placement.Position,
            });
        }
    }
    msb.Write(Path.Combine(mapStudio, mapName + ".msb"));
}

// The synthetic ItemLotParam definition: the exact fields the suppression
// writer resolves by name, all s32, in a layout no real paramdef shares.
var definition = new PARAMDEF {
    ParamType = "ItemLotParam",
    DataVersion = 1,
    BigEndian = false,
    Unicode = true,
};
definition.Fields.Add(new PARAMDEF.Field(definition, PARAMDEF.DefType.s32, "getItemFlagId"));
for (int slot = 1; slot <= 8; slot++)
{
    definition.Fields.Add(new PARAMDEF.Field(definition, PARAMDEF.DefType.s32, $"lotItemCategory{slot:00}"));
    definition.Fields.Add(new PARAMDEF.Field(definition, PARAMDEF.DefType.s32, $"lotItemId{slot:00}"));
    definition.Fields.Add(new PARAMDEF.Field(definition, PARAMDEF.DefType.s32, $"lotItemNum{slot:00}"));
}

// Rows starts null on a fresh PARAM; ApplyParamdef iterates it.
var param = new PARAM { ParamType = "ItemLotParam", ParamdefDataVersion = 1, Rows = [] };
param.ApplyParamdef(definition);
foreach (Edit edit in plan.Edits)
{
    if (!int.TryParse(edit.ItemLotId, out int lotId)
        || !int.TryParse(edit.ItemCategory, out int itemCategory)
        || !int.TryParse(edit.GoodsId, out int goodsId)
        || !int.TryParse(edit.AcquisitionFlag, out int flag))
        throw new InvalidDataException($"{edit.ItemKey}: plan contains a non-integer field");
    var row = new PARAM.Row(lotId, edit.LotName ?? "", definition);
    row["getItemFlagId"].Value = flag;
    row["lotItemCategory01"].Value = itemCategory;
    row["lotItemId01"].Value = goodsId;
    row["lotItemNum01"].Value = 1;
    param.Rows.Add(row);
}
if (param.Rows.Select(row => row.ID).Distinct().Count() != param.Rows.Count)
    throw new InvalidDataException("suppression plan names the same lot id twice");

var game = new BND4 { Compression = DCX.Type.DCX_EDGE };
game.Files.Add(new BinderFile(
    Binder.FileFlags.Flag1, 0, @"N:\synthetic\param\ItemLotParam.param", param.Write()));

var goodsDefinition = new PARAMDEF {
    ParamType = "EquipParamGoods", DataVersion = 1, BigEndian = false, Unicode = true,
};
goodsDefinition.Fields.Add(new PARAMDEF.Field(
    goodsDefinition, PARAMDEF.DefType.s32, "yesNoDialogMessageId"));
goodsDefinition.Fields.Add(new PARAMDEF.Field(
    goodsDefinition, PARAMDEF.DefType.u8, "isOnlyOne"));
var goods = new PARAM { ParamType = "EquipParamGoods", ParamdefDataVersion = 1, Rows = [] };
goods.ApplyParamdef(goodsDefinition);
var vial = new PARAM.Row(1000, "Synthetic Blood Vial", goodsDefinition);
vial["yesNoDialogMessageId"].Value = 0;
vial["isOnlyOne"].Value = (byte)0;
goods.Rows.Add(vial);
game.Files.Add(new BinderFile(
    Binder.FileFlags.Flag1, 1, @"N:\synthetic\param\EquipParamGoods.param", goods.Write()));
string gameparamPath = Path.Combine(outputRoot, "param", "gameparam.parambnd.dcx");
game.Write(gameparamPath);

var defs = new BND4 { Compression = DCX.Type.DCX_EDGE };
defs.Files.Add(new BinderFile(
    Binder.FileFlags.Flag1, 0, @"N:\synthetic\paramdef\ItemLotParam.paramdef", definition.Write()));
defs.Files.Add(new BinderFile(
    Binder.FileFlags.Flag1, 1, @"N:\synthetic\paramdef\EquipParamGoods.paramdef", goodsDefinition.Write()));
string paramdefPath = Path.Combine(outputRoot, "paramdef", "paramdef.paramdefbnd.dcx");
defs.Write(paramdefPath);

var names = new FMG(FMG.FMGVersion.DarkSouls3);
names[1000] = "Blood Vial";
var messages = new BND4 { Compression = DCX.Type.DCX_EDGE };
messages.Files.Add(new BinderFile(
    Binder.FileFlags.Flag1, 0, @"N:\synthetic\msg\アイテム名.fmg", names.Write()));
string messagePath = Path.Combine(outputRoot, "msg", "engus", "item.msgbnd.dcx");
Directory.CreateDirectory(Path.GetDirectoryName(messagePath)!);
messages.Write(messagePath);

// Re-read everything before declaring success; the next tools in the chain
// trust these bytes.
int forgedEnemies = 0;
foreach (string mapName in new[] { "m99_00_00_00", "m99_00_00_01" })
{
    MSBB check = MSBB.Read(Path.Combine(mapStudio, mapName + ".msb"));
    forgedEnemies += check.Parts.Enemies.Count + check.Parts.DummyEnemies.Count;
}
BND4 gameCheck = BND4.Read(gameparamPath);
BND4 defsCheck = BND4.Read(paramdefPath);
FMG namesCheck = FMG.Read(BND4.Read(messagePath).Files.Single().Bytes);
if (namesCheck[1000] != "Blood Vial")
    throw new InvalidDataException("synthetic item-name FMG did not round-trip");
PARAM paramCheck = PARAM.Read(gameCheck.Files.Single(file =>
    file.Name is not null && file.Name.EndsWith("ItemLotParam.param", StringComparison.OrdinalIgnoreCase)).Bytes);
PARAMDEF defCheck = PARAMDEF.Read(defsCheck.Files.Single(file =>
    file.Name is not null
    && file.Name.EndsWith("ItemLotParam.paramdef", StringComparison.OrdinalIgnoreCase)).Bytes);
if (!paramCheck.ApplyParamdefCarefully(defCheck))
    throw new InvalidDataException("forged param does not accept its forged paramdef");
if (paramCheck.Rows.Count != plan.Edits.Count)
    throw new InvalidDataException("forged param lost rows on round-trip");

// Synthetic opcode shapes for exercising the real event writer in CI.
// Zero arguments witness byte lengths only, not game semantics or licensed data.
var common = new EMEVD(EMEVD.Game.Bloodborne);
common.Events.Add(new EMEVD.Event(0));
var shapes = new EMEVD.Event(1);
foreach (var (bank, id, length) in new[] {
    (2000, 0, 12), (2000, 2, 4), (3, 16, 12), (2003, 2, 8),
    (1001, 0, 4), (1014, 0, 0), (2003, 24, 12), (1000, 101, 4),
    (2003, 4, 4), (1000, 4, 4),
})
    shapes.Instructions.Add(new EMEVD.Instruction(bank, id, new byte[length]));
common.Events.Add(shapes);
Directory.CreateDirectory(Path.Combine(outputRoot, "event"));
string commonPath = Path.Combine(outputRoot, "event", "common.emevd.dcx");
common.Write(commonPath);
if (EMEVD.Read(commonPath).Events.Count != 2)
    throw new InvalidDataException("synthetic event fixture did not round-trip");

// A synthetic Cathedral source exercises both owned transforms. Its Laurence
// event has the reviewed vanilla instruction shape, while the separate shape
// event supplies the opcodes cloned by the writer. No game bytes are included.
var cathedral = new EMEVD(EMEVD.Game.Bloodborne);
var laurence = new EMEVD.Event(12401803);
foreach (var (bank, id, hex) in new[] {
    (2006, 1, "55ac240000000000"),
    (1003, 2, "0001010000000000"),
    (1003, 101, "00010000883cbd00"),
    (3, 0, "00010000883cbd00"),
    (1014, 0, ""),
    (2006, 2, "55ac2400"),
    (1003, 6, "00010000"),
    (4, 3, "010000001027000000000000"),
    (3, 24, "010000000a9f240009a62400"),
    (0, 0, "00010100"),
    (2003, 2, "dc23000001000000"),
    (1001, 1, "01000000"),
    (2006, 1, "55ac240001000000"),
    (2002, 6, "1e366e0100000000ffffffff180000001027000002000000"),
    (1001, 1, "01000000"),
    (2003, 2, "dc23000000000000"),
})
    laurence.Instructions.Add(new EMEVD.Instruction(bank, id, Convert.FromHexString(hex)));
cathedral.Events.Add(laurence);

var emblem = new EMEVD.Event(12400760);
for (int i = 0; i < 58; i++)
    emblem.Instructions.Add(new EMEVD.Instruction(1014, 0, Array.Empty<byte>()));
emblem.Instructions[11] = new EMEVD.Instruction(5, 2, Convert.FromHexString("030000002a36bd00"));
emblem.Instructions[14] = new EMEVD.Instruction(0, 0, Convert.FromHexString("ff010300"));
emblem.Instructions[15] = new EMEVD.Instruction(0, 0, Convert.FromHexString("0001ff00"));
cathedral.Events.Add(emblem);

var workshopDoor = new EMEVD.Event(12405710, EMEVD.Event.RestBehaviorType.Restart);
foreach (var (bank, id, hex) in new[] {
    (1003, 101, "00000000ed240000"),
    (2005, 7, "b2a3240001000000"),
    (2010, 5, "b2a3240003000000"),
    (1000, 4, "00000000"),
    (1014, 0, ""),
    (2000, 2, "00000000"),
    (3, 24, "00000000581b0000b2a32400"),
    (2007, 1, "3bbe980001000100b2a324000000a040"),
    (1000, 4, "01000000"),
})
    workshopDoor.Instructions.Add(new EMEVD.Instruction(bank, id, Convert.FromHexString(hex)));
cathedral.Events.Add(workshopDoor);

var cathedralShapes = new EMEVD.Event(2);
foreach (var (bank, id, length) in new[] {
    (3, 0, 8), (3, 4, 12), (3, 6, 4), (0, 0, 4), (2003, 2, 8), (1000, 4, 4),
    (1000, 101, 4),
})
    cathedralShapes.Instructions.Add(new EMEVD.Instruction(bank, id, new byte[length]));
cathedral.Events.Add(cathedralShapes);
string cathedralPath = Path.Combine(outputRoot, "event", "m24_00_00_00.emevd.dcx");
cathedral.Write(cathedralPath);
if (EMEVD.Read(cathedralPath).Events.Single(e => e.ID == 12401803).Instructions.Count != 16)
    throw new InvalidDataException("synthetic Cathedral event fixture did not round-trip");

Console.WriteLine(
    $"forge maps=2 placements_per_map={placements.Length} enemies_total={forgedEnemies} "
    + $"suppression_rows={paramCheck.Rows.Count} output={outputRoot}");
return 0;

sealed record Placement(
    string Name, string Model, int NpcParam, int ThinkParam, int TalkId,
    int CharaInit, int EntityId, Vector3 Position, bool Dummy);

sealed record Plan(
    [property: JsonPropertyName("format")] string Format,
    [property: JsonPropertyName("edits")] List<Edit> Edits);

sealed record Edit(
    [property: JsonPropertyName("item_key")] string ItemKey,
    [property: JsonPropertyName("item_category")] string ItemCategory,
    [property: JsonPropertyName("goods_id")] string GoodsId,
    [property: JsonPropertyName("item_lot_id")] string ItemLotId,
    [property: JsonPropertyName("acquisition_flag")] string AcquisitionFlag,
    [property: JsonPropertyName("lot_name")] string? LotName);
