using System.Text.Json;
using System.Text.Json.Serialization;
using SoulsFormats;

if (args.Length == 6 && args[0] == "--starting-weapons" && args[5] == "--apply")
{
    WriteStartingWeapons(args[1], args[2], args[3], args[4]);
    return 0;
}

if (args.Length != 5 || args[4] != "--apply")
{
    Console.Error.WriteLine(
        "usage: BBSuppressionWriter <plan.json> <gameparam.parambnd.dcx> "
        + "<paramdef.paramdefbnd.dcx> <output.parambnd.dcx> --apply");
    Console.Error.WriteLine("Refuses to write without the explicit --apply argument.");
    return 2;
}

string planPath = Path.GetFullPath(args[0]);
string inputPath = Path.GetFullPath(args[1]);
string paramdefPath = Path.GetFullPath(args[2]);
string outputPath = Path.GetFullPath(args[3]);
if (StringComparer.OrdinalIgnoreCase.Equals(inputPath, outputPath))
    throw new InvalidDataException("input and output paths must differ");
if (File.Exists(outputPath))
    throw new IOException($"refusing to overwrite existing output: {outputPath}");

Plan plan = JsonSerializer.Deserialize<Plan>(File.ReadAllText(planPath))
    ?? throw new InvalidDataException("plan is empty");
if (plan.Format != "bb-vanilla-suppression-plan-v2")
    throw new InvalidDataException($"unsupported plan format {plan.Format}");
if (!Int32.TryParse(plan.Placeholder.GoodsId, out int placeholderGoods))
    throw new InvalidDataException("placeholder goods id is not a 32-bit integer");
if (plan.Placeholder.Quantity < 1)
    throw new InvalidDataException("placeholder quantity must be positive");
if (plan.Edits.Count == 0)
    throw new InvalidDataException("plan contains no edits");

BND4 game = BND4.Read(inputPath);
BND4 defs = BND4.Read(paramdefPath);
BinderFile itemLotFile = RequireSingleFile(game, "ItemLotParam.param");
PARAM itemLots = PARAM.Read(itemLotFile.Bytes);
PARAMDEF definition = ReadMatchingDefinition(defs, itemLots);
itemLots.ApplyParamdef(definition);

var originalFiles = game.Files.Select(file =>
    new FileState(file.ID, file.Name, (byte[])file.Bytes.Clone())).ToList();
var originalRows = itemLots.Rows.Select(RowState.Capture).ToList();
var changes = new List<Applied>();

// Transactional preflight: resolve and validate every requested row before
// changing the in-memory binder or creating the output file.
foreach (Edit edit in plan.Edits)
{
    if (!Int32.TryParse(edit.ItemLotId, out int lotId)
        || !Int32.TryParse(edit.ItemCategory, out int itemCategory)
        || !Int32.TryParse(edit.GoodsId, out int goodsId)
        || !Int32.TryParse(edit.AcquisitionFlag, out int expectedFlag))
        throw new InvalidDataException($"{edit.ItemKey}: plan contains a non-integer field");
    List<PARAM.Row> lotRows = itemLots.Rows.Where(row => row.ID == lotId).ToList();
    if (lotRows.Count != 1)
        throw new InvalidDataException(
            $"{edit.ItemKey}: expected one ItemLotParam row {lotId}, found {lotRows.Count}");
    PARAM.Row row = lotRows[0];
    int actualFlag = Convert.ToInt32(RequireCell(row, "getItemFlagId").Value);
    if (actualFlag != expectedFlag)
        throw new InvalidDataException(
            $"{edit.ItemKey}: row {lotId} flag is {actualFlag}, plan says {expectedFlag}");
    var matchingSlots = Enumerable.Range(1, 8).Where(slot =>
        Convert.ToInt32(RequireCell(row, $"lotItemCategory{slot:00}").Value) == itemCategory
        && Convert.ToInt32(RequireCell(row, $"lotItemId{slot:00}").Value) == goodsId).ToList();
    if (matchingSlots.Count != 1)
        throw new InvalidDataException(
            $"{edit.ItemKey}: row {lotId} has {matchingSlots.Count} matching "
            + $"category {itemCategory} item slots");
    changes.Add(new Applied(
        edit.ItemKey, lotId, matchingSlots[0], itemCategory, goodsId, expectedFlag));
}
if (changes.Select(change => change.LotId).Distinct().Count() != changes.Count)
    throw new InvalidDataException("plan edits the same ItemLotParam row more than once");

foreach (Applied change in changes)
{
    PARAM.Row row = itemLots.Rows.Single(row => row.ID == change.LotId);
    RequireCell(row, $"lotItemCategory{change.Slot:00}").Value = 4;
    RequireCell(row, $"lotItemId{change.Slot:00}").Value = placeholderGoods;
    RequireCell(row, $"lotItemNum{change.Slot:00}").Value = plan.Placeholder.Quantity;
}

itemLotFile.Bytes = itemLots.Write();
Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
game.Write(outputPath);

VerifyOutput(
    outputPath, definition, originalFiles, originalRows, changes,
    placeholderGoods, plan.Placeholder.Quantity);
Console.WriteLine(
    $"suppressed={changes.Count} placeholder_goods={placeholderGoods} output={outputPath}");
foreach (Applied change in changes)
    Console.WriteLine(
        $"  lot={change.LotId} slot={change.Slot:00} "
        + $"category:item={change.ItemCategory}:{change.GoodsId}->4:{placeholderGoods} "
        + $"flag={change.AcquisitionFlag} unchanged key={change.ItemKey}");
return 0;

static void WriteStartingWeapons(string requestPath, string inputPath, string paramdefPath,
                                 string outputPath)
{
    inputPath = Path.GetFullPath(inputPath);
    outputPath = Path.GetFullPath(outputPath);
    if (StringComparer.OrdinalIgnoreCase.Equals(inputPath, outputPath))
        throw new InvalidDataException("input and output paths must differ");
    if (File.Exists(outputPath))
        throw new IOException($"refusing to overwrite existing output: {outputPath}");

    using JsonDocument document = JsonDocument.Parse(File.ReadAllText(requestPath));
    JsonElement root = document.RootElement;
    if (!root.TryGetProperty("randomize_starting_weapons", out JsonElement enabled)
        || enabled.ValueKind != JsonValueKind.True)
        throw new InvalidDataException("request does not enable starting-weapon randomization");
    JsonElement choices = root.GetProperty("starting_weapons");
    int[] right = choices.GetProperty("right_hand").EnumerateArray().Select(v => v.GetInt32()).ToArray();
    int[] left = choices.GetProperty("left_hand").EnumerateArray().Select(v => v.GetInt32()).ToArray();
    if (right.Length != 3 || left.Length != 2 || right.Distinct().Count() != 3
        || left.Distinct().Count() != 2 || right.Concat(left).Any(id => id <= 0))
        throw new InvalidDataException("starting weapon choices must be three unique right-hand and two unique left-hand ids");

    BND4 game = BND4.Read(inputPath);
    BND4 defs = BND4.Read(paramdefPath);
    BinderFile shopFile = RequireSingleFile(game, "ShopLineupParam.param");
    PARAM shops = PARAM.Read(shopFile.Bytes);
    PARAMDEF definition = ReadMatchingDefinition(defs, shops);
    shops.ApplyParamdef(definition);
    PARAM weapons = PARAM.Read(RequireSingleFile(game, "EquipParamWeapon.param").Bytes);
    var weaponIds = weapons.Rows.Select(row => row.ID).ToHashSet();
    if (right.Concat(left).Any(id => !weaponIds.Contains(id)))
        throw new InvalidDataException("starting weapon choices contain an unknown EquipParamWeapon id");
    var originalFiles = game.Files.Select(file =>
        new FileState(file.ID, file.Name, (byte[])file.Bytes.Clone())).ToList();
    var originalRows = shops.Rows.Select(RowState.Capture).ToDictionary(row => row.Id);
    var assignments = new[] { 2000, 2001, 2002 }.Zip(right)
        .Concat(new[] { 2010, 2011 }.Zip(left)).ToList();
    foreach ((int rowId, int equipId) in assignments)
    {
        PARAM.Row row = shops.Rows.Single(candidate => candidate.ID == rowId);
        RequireCell(row, "equipId").Value = equipId;
    }
    shopFile.Bytes = shops.Write();
    Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
    game.Write(outputPath);

    BND4 check = BND4.Read(outputPath);
    BinderFile checkedShopFile = RequireSingleFile(check, "ShopLineupParam.param");
    for (int index = 0; index < check.Files.Count; index++)
    {
        BinderFile file = check.Files[index];
        FileState before = originalFiles[index];
        if (file.ID != before.Id || file.Name != before.Name)
            throw new InvalidDataException($"round-trip changed binder identity at index {index}");
        if (file != checkedShopFile && !file.Bytes.SequenceEqual(before.Bytes))
            throw new InvalidDataException($"round-trip changed unrelated binder file {file.Name}");
    }
    PARAM checkedShops = PARAM.Read(checkedShopFile.Bytes);
    checkedShops.ApplyParamdef(definition);
    var changedRows = assignments.Select(pair => pair.First).ToHashSet();
    foreach (PARAM.Row row in checkedShops.Rows)
        originalRows[row.ID].RequireEqualExcept(
            RowState.Capture(row), changedRows.Contains(row.ID)
                ? new HashSet<string> { "equipId" } : new HashSet<string>(),
            $"ShopLineupParam row {row.ID}");
    foreach ((int rowId, int equipId) in assignments)
    {
        PARAM.Row row = checkedShops.Rows.Single(candidate => candidate.ID == rowId);
        if (Convert.ToInt32(RequireCell(row, "equipId").Value) != equipId)
            throw new InvalidDataException($"starting row {rowId} did not retain equipId {equipId}");
    }
    Console.WriteLine($"starting_weapons={string.Join(',', right)} firearms={string.Join(',', left)} output={outputPath}");
}

static BinderFile RequireSingleFile(BND4 binder, string suffix)
{
    List<BinderFile> matches = binder.Files.Where(file =>
        file.Name is not null && file.Name.EndsWith(suffix, StringComparison.OrdinalIgnoreCase)).ToList();
    if (matches.Count != 1)
        throw new InvalidDataException($"expected one binder file ending {suffix}, found {matches.Count}");
    return matches[0];
}

static PARAMDEF ReadMatchingDefinition(BND4 binder, PARAM param)
{
    var candidates = new List<PARAMDEF>();
    foreach (BinderFile file in binder.Files)
    {
        if (file.Name is null || !file.Name.EndsWith(".paramdef", StringComparison.OrdinalIgnoreCase))
            continue;
        PARAMDEF definition = PARAMDEF.Read(file.Bytes);
        if (definition.ParamType == param.ParamType
            && definition.DataVersion == param.ParamdefDataVersion
            && (param.DetectedSize == -1 || definition.GetRowSize() == param.DetectedSize))
            candidates.Add(definition);
    }
    if (candidates.Count != 1)
        throw new InvalidDataException(
            $"expected one matching PARAMDEF for {param.ParamType}, found {candidates.Count}");
    return candidates[0];
}

static PARAM.Cell RequireCell(PARAM.Row row, string name) => row[name]
    ?? throw new InvalidDataException($"ItemLotParam row {row.ID} has no field {name}");

static void VerifyOutput(
    string outputPath,
    PARAMDEF definition,
    List<FileState> originalFiles,
    List<RowState> originalRows,
    List<Applied> changes,
    int placeholderGoods,
    int placeholderQuantity)
{
    BND4 output = BND4.Read(outputPath);
    if (output.Files.Count != originalFiles.Count)
        throw new InvalidDataException("round-trip changed the binder file count");
    BinderFile itemLotFile = RequireSingleFile(output, "ItemLotParam.param");
    for (int index = 0; index < output.Files.Count; index++)
    {
        BinderFile file = output.Files[index];
        FileState before = originalFiles[index];
        if (file.ID != before.Id || file.Name != before.Name)
            throw new InvalidDataException($"round-trip changed binder identity at index {index}");
        if (file != itemLotFile && !file.Bytes.SequenceEqual(before.Bytes))
            throw new InvalidDataException($"round-trip changed unrelated binder file {file.Name}");
    }

    PARAM itemLots = PARAM.Read(itemLotFile.Bytes);
    itemLots.ApplyParamdef(definition);
    if (itemLots.Rows.Count != originalRows.Count)
        throw new InvalidDataException("round-trip changed the ItemLotParam row count");
    var changedByLot = changes.ToDictionary(change => change.LotId);
    for (int index = 0; index < itemLots.Rows.Count; index++)
    {
        PARAM.Row row = itemLots.Rows[index];
        RowState before = originalRows[index];
        RowState after = RowState.Capture(row);
        if (!changedByLot.TryGetValue(row.ID, out Applied? change))
        {
            before.RequireEqual(after, $"unplanned row {row.ID}");
            continue;
        }
        string field = $"lotItemId{change.Slot:00}";
        string categoryField = $"lotItemCategory{change.Slot:00}";
        string quantityField = $"lotItemNum{change.Slot:00}";
        before.RequireEqualExcept(
            after, new HashSet<string> { field, categoryField, quantityField },
            $"planned row {row.ID}");
        if (Convert.ToInt32(RequireCell(row, field).Value) != placeholderGoods)
            throw new InvalidDataException($"row {row.ID}: placeholder was not written");
        if (Convert.ToInt32(RequireCell(row, categoryField).Value) != 4)
            throw new InvalidDataException($"row {row.ID}: placeholder category was not written");
        if (Convert.ToInt32(RequireCell(row, quantityField).Value) != placeholderQuantity)
            throw new InvalidDataException($"row {row.ID}: placeholder quantity was not written");
        if (Convert.ToInt32(RequireCell(row, "getItemFlagId").Value) != change.AcquisitionFlag)
            throw new InvalidDataException($"row {row.ID}: acquisition flag changed");
    }
}

sealed record Plan(
    [property: JsonPropertyName("format")] string Format,
    [property: JsonPropertyName("placeholder")] Placeholder Placeholder,
    [property: JsonPropertyName("edits")] List<Edit> Edits);
sealed record Placeholder(
    [property: JsonPropertyName("goods_id")] string GoodsId,
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("quantity")] int Quantity);
sealed record Edit(
    [property: JsonPropertyName("item_key")] string ItemKey,
    [property: JsonPropertyName("item_category")] string ItemCategory,
    [property: JsonPropertyName("goods_id")] string GoodsId,
    [property: JsonPropertyName("item_lot_id")] string ItemLotId,
    [property: JsonPropertyName("acquisition_flag")] string AcquisitionFlag);
sealed record Applied(
    string ItemKey, int LotId, int Slot, int ItemCategory, int GoodsId, int AcquisitionFlag);
sealed record FileState(int Id, string Name, byte[] Bytes);

sealed record RowState(int Id, string? Name, Dictionary<string, object> Cells)
{
    public static RowState Capture(PARAM.Row row) => new(
        row.ID,
        row.Name,
        row.Cells.ToDictionary(cell => cell.Def.InternalName, cell => CopyValue(cell.Value)));

    private static object CopyValue(object value) =>
        value is byte[] bytes ? (byte[])bytes.Clone() : value;

    public void RequireEqual(RowState after, string context) =>
        RequireEqualExcept(after, new HashSet<string>(), context);

    public void RequireEqualExcept(
        RowState after, IReadOnlySet<string> allowedFields, string context)
    {
        if (Id != after.Id)
            throw new InvalidDataException($"{context}: row id changed {Id} -> {after.Id}");
        if (Name != after.Name)
            throw new InvalidDataException(
                $"{context}: row name changed '{Name ?? "<null>"}' -> '{after.Name ?? "<null>"}'");
        if (!Cells.Keys.ToHashSet().SetEquals(after.Cells.Keys))
        {
            IEnumerable<string> missing = Cells.Keys.Except(after.Cells.Keys);
            IEnumerable<string> added = after.Cells.Keys.Except(Cells.Keys);
            throw new InvalidDataException(
                $"{context}: field set changed (missing: {string.Join(", ", missing)}; "
                + $"added: {string.Join(", ", added)})");
        }
        foreach ((string field, object before) in Cells)
        {
            if (allowedFields.Contains(field))
                continue;
            object value = after.Cells[field];
            bool same = before is byte[] left && value is byte[] right
                ? left.SequenceEqual(right)
                : Equals(before, value);
            if (!same)
                throw new InvalidDataException($"{context}: protected field {field} changed");
        }
    }
}
