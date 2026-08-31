using System.Text.Json;
using System.Text.Json.Serialization;
using SoulsFormats;

if (args.Length != 8 || args[6] != "--probe-confirmed" || args[7] != "--apply")
{
    Console.Error.WriteLine(
        "usage: BBToastWriter <toast-plan.json> <input-gameparam> <paramdef> "
        + "<input-item.msgbnd.dcx> <output-gameparam> <output-item.msgbnd.dcx> "
        + "--probe-confirmed --apply");
    Console.Error.WriteLine(
        "The two explicit gates mean the msgbnd runtime-read and popup-not-modal probe was witnessed.");
    return 2;
}

string planPath = Path.GetFullPath(args[0]);
string inputGameparam = Path.GetFullPath(args[1]);
string paramdefPath = Path.GetFullPath(args[2]);
string inputMsgbnd = Path.GetFullPath(args[3]);
string outputGameparam = Path.GetFullPath(args[4]);
string outputMsgbnd = Path.GetFullPath(args[5]);
foreach ((string input, string output) in new[] {
    (inputGameparam, outputGameparam), (inputMsgbnd, outputMsgbnd) })
{
    if (StringComparer.OrdinalIgnoreCase.Equals(input, output))
        throw new InvalidDataException("input and output paths must differ");
    if (File.Exists(output))
        throw new IOException($"refusing to overwrite existing output: {output}");
}

ToastPlan plan = JsonSerializer.Deserialize<ToastPlan>(File.ReadAllText(planPath))
    ?? throw new InvalidDataException("toast plan is empty");
if (plan.Format != "bb-toast-placeholder-plan-v1")
    throw new InvalidDataException($"unsupported toast plan format {plan.Format}");
if (!plan.Enabled)
    throw new InvalidDataException(
        "toast plan is inert: promote enabled only with a reviewed runtime-read and popup-not-modal witness");
if (plan.SourceGoodsId != 1000)
    throw new InvalidDataException("the reviewed clone source must remain Blood Vial goods 1000");
if (plan.Entries.Count == 0)
    throw new InvalidDataException("toast plan has no entries");
if (plan.Entries.Any(entry => entry.GoodsId < 900000 || entry.GoodsId > 900999))
    throw new InvalidDataException("toast plan claims a goods id outside 900000..900999");
if (plan.Entries.Select(entry => entry.GoodsId).Distinct().Count() != plan.Entries.Count
    || plan.Entries.Select(entry => entry.ItemLotId).Distinct().Count() != plan.Entries.Count)
    throw new InvalidDataException("toast plan repeats a goods id or ItemLotParam row");
if (plan.Entries.Any(entry => entry.DisplayName.Length is < 1 or > 48))
    throw new InvalidDataException("toast display names must contain 1..48 characters");

WriteGameparam(plan, inputGameparam, paramdefPath, outputGameparam);
WriteMessageBinder(plan, inputMsgbnd, outputMsgbnd);
Verify(plan, outputGameparam, paramdefPath, outputMsgbnd);
Console.WriteLine(
    $"toast_placeholders={plan.Entries.Count} gameparam={outputGameparam} msgbnd={outputMsgbnd}");
return 0;

static void WriteGameparam(ToastPlan plan, string inputPath, string paramdefPath, string outputPath)
{
    BND4 game = BND4.Read(inputPath);
    BND4 defs = BND4.Read(paramdefPath);
    BinderFile goodsFile = RequireSingleFile(game, "EquipParamGoods.param");
    BinderFile lotsFile = RequireSingleFile(game, "ItemLotParam.param");
    PARAM goods = PARAM.Read(goodsFile.Bytes);
    PARAM lots = PARAM.Read(lotsFile.Bytes);
    PARAMDEF goodsDef = ReadMatchingDefinition(defs, goods);
    PARAMDEF lotsDef = ReadMatchingDefinition(defs, lots);
    goods.ApplyParamdef(goodsDef);
    lots.ApplyParamdef(lotsDef);
    PARAM.Row source = goods.Rows.SingleOrDefault(row => row.ID == plan.SourceGoodsId)
        ?? throw new InvalidDataException("EquipParamGoods has no Blood Vial row 1000");
    if (goods.Rows.Any(row => row.ID is >= 900000 and <= 900999))
        throw new InvalidDataException("claimed toast goods range collides with the input gameparam");

    foreach (ToastEntry entry in plan.Entries)
    {
        var clone = new PARAM.Row(source) { ID = entry.GoodsId, Name = entry.DisplayName };
        // The source row is the non-modal, stackable Vial shape. These are the
        // two safety-critical fields; refuse drift instead of inheriting hope.
        if (Convert.ToInt32(RequireCell(clone, "yesNoDialogMessageId").Value) != 0
            || Convert.ToByte(RequireCell(clone, "isOnlyOne").Value) != 0)
            throw new InvalidDataException("Blood Vial clone source is no longer non-modal/stackable");
        goods.Rows.Add(clone);

        PARAM.Row lot = lots.Rows.SingleOrDefault(row => row.ID == entry.ItemLotId)
            ?? throw new InvalidDataException($"missing ItemLotParam row {entry.ItemLotId}");
        List<int> slots = Enumerable.Range(1, 8).Where(slot =>
            Convert.ToInt32(RequireCell(lot, $"lotItemCategory{slot:00}").Value) == 4
            && Convert.ToInt32(RequireCell(lot, $"lotItemId{slot:00}").Value) == plan.SourceGoodsId
        ).ToList();
        if (slots.Count != 1)
            throw new InvalidDataException(
                $"lot {entry.ItemLotId} has {slots.Count} Blood Vial placeholder slots, expected one");
        RequireCell(lot, $"lotItemId{slots[0]:00}").Value = entry.GoodsId;
    }
    goodsFile.Bytes = goods.Write();
    lotsFile.Bytes = lots.Write();
    Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
    game.Write(outputPath);
}

static void WriteMessageBinder(ToastPlan plan, string inputPath, string outputPath)
{
    BND4 binder = BND4.Read(inputPath);
    BinderFile namesFile = RequireSingleFile(binder, "アイテム名.fmg");
    FMG names = FMG.Read(namesFile.Bytes);
    if (names.Entries.Any(entry => entry.ID is >= 900000 and <= 900999))
        throw new InvalidDataException("claimed toast FMG range collides with item names");
    foreach (ToastEntry entry in plan.Entries)
        names[entry.GoodsId] = entry.DisplayName;
    namesFile.Bytes = names.Write();
    Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
    binder.Write(outputPath);
}

static void Verify(ToastPlan plan, string gameparamPath, string paramdefPath, string msgbndPath)
{
    BND4 game = BND4.Read(gameparamPath);
    BND4 defs = BND4.Read(paramdefPath);
    PARAM goods = PARAM.Read(RequireSingleFile(game, "EquipParamGoods.param").Bytes);
    PARAM lots = PARAM.Read(RequireSingleFile(game, "ItemLotParam.param").Bytes);
    goods.ApplyParamdef(ReadMatchingDefinition(defs, goods));
    lots.ApplyParamdef(ReadMatchingDefinition(defs, lots));
    FMG names = FMG.Read(RequireSingleFile(BND4.Read(msgbndPath), "アイテム名.fmg").Bytes);
    foreach (ToastEntry entry in plan.Entries)
    {
        PARAM.Row row = goods.Rows.SingleOrDefault(row => row.ID == entry.GoodsId)
            ?? throw new InvalidDataException($"output omitted goods {entry.GoodsId}");
        if (Convert.ToInt32(RequireCell(row, "yesNoDialogMessageId").Value) != 0
            || Convert.ToByte(RequireCell(row, "isOnlyOne").Value) != 0)
            throw new InvalidDataException($"goods {entry.GoodsId} is not a safe popup dummy");
        if (names[entry.GoodsId] != entry.DisplayName)
            throw new InvalidDataException($"FMG omitted or changed goods {entry.GoodsId}");
        PARAM.Row lot = lots.Rows.Single(row => row.ID == entry.ItemLotId);
        if (!Enumerable.Range(1, 8).Any(slot =>
            Convert.ToInt32(RequireCell(lot, $"lotItemCategory{slot:00}").Value) == 4
            && Convert.ToInt32(RequireCell(lot, $"lotItemId{slot:00}").Value) == entry.GoodsId))
            throw new InvalidDataException($"lot {entry.ItemLotId} does not award goods {entry.GoodsId}");
    }
}

static BinderFile RequireSingleFile(BND4 binder, string suffix)
{
    List<BinderFile> matches = binder.Files.Where(file => file.Name is not null
        && file.Name.EndsWith(suffix, StringComparison.OrdinalIgnoreCase)).ToList();
    if (matches.Count != 1)
        throw new InvalidDataException($"expected one binder file ending {suffix}, found {matches.Count}");
    return matches[0];
}

static PARAMDEF ReadMatchingDefinition(BND4 binder, PARAM param)
{
    List<PARAMDEF> candidates = binder.Files
        .Where(file => file.Name is not null && file.Name.EndsWith(".paramdef", StringComparison.OrdinalIgnoreCase))
        .Select(file => PARAMDEF.Read(file.Bytes))
        .Where(definition => definition.ParamType == param.ParamType
            && definition.DataVersion == param.ParamdefDataVersion
            && (param.DetectedSize == -1 || definition.GetRowSize() == param.DetectedSize))
        .ToList();
    if (candidates.Count != 1)
        throw new InvalidDataException($"expected one matching PARAMDEF for {param.ParamType}, found {candidates.Count}");
    return candidates[0];
}

static PARAM.Cell RequireCell(PARAM.Row row, string name) => row[name]
    ?? throw new InvalidDataException($"row {row.ID} has no field {name}");

sealed record ToastPlan(
    [property: JsonPropertyName("format")] string Format,
    [property: JsonPropertyName("enabled")] bool Enabled,
    [property: JsonPropertyName("source_goods_id")] int SourceGoodsId,
    [property: JsonPropertyName("entries")] List<ToastEntry> Entries);
sealed record ToastEntry(
    [property: JsonPropertyName("location_key")] string LocationKey,
    [property: JsonPropertyName("location_id")] long LocationId,
    [property: JsonPropertyName("item_lot_id")] int ItemLotId,
    [property: JsonPropertyName("goods_id")] int GoodsId,
    [property: JsonPropertyName("display_name")] string DisplayName);
