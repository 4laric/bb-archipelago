using System.Text.Json;
using System.Text.Json.Serialization;
using SoulsFormats;

if (args.Length == 3 && args[0] == "--inspect-starting-attire")
{
    InspectStartingAttire(args[1], args[2]);
    return 0;
}

if (args.Length == 3 && args[0] == "--inspect-starting-attire-catalog")
{
    InspectStartingAttireCatalog(args[1], args[2]);
    return 0;
}

if (args.Length == 4 && args[0] == "--audit-starting-attire-catalog")
{
    AuditStartingAttireCatalog(args[1], args[2], args[3]);
    return 0;
}

if (args.Length == 9 && args[0] == "--write-starting-attire-canary" && args[8] == "--apply")
{
    WriteStartingAttireCanary(args[1], args[2], args[3], args[4..8]);
    return 0;
}

if (args.Length == 3 && args[0] == "--inspect-shops")
{
    InspectShops(args[1], args[2]);
    return 0;
}

if (args.Length == 4 && args[0] == "--audit-shop-gates")
{
    AuditShopGates(args[1], args[2], args[3]);
    return 0;
}

if (args.Length == 6 && args[0] == "--seed-weapons" && args[5] == "--apply")
{
    WriteSeedWeapons(args[1], args[2], args[3], args[4]);
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

static void InspectStartingAttire(string inputPath, string paramdefPath)
{
    BND4 game = BND4.Read(Path.GetFullPath(inputPath));
    BND4 defs = BND4.Read(Path.GetFullPath(paramdefPath));
    BinderFile initFile = RequireSingleFile(game, "CharaInitParam.param");
    PARAM init = PARAM.Read(initFile.Bytes);
    init.ApplyParamdef(ReadMatchingDefinition(defs, init));
    string[] attireFields = ["equip_Helm", "equip_Armer", "equip_Gaunt", "equip_Leg"];
    var referenced = new HashSet<int>();
    foreach (PARAM.Row row in init.Rows.Where(row =>
                 (row.ID >= 2000 && row.ID <= 2009) || (row.ID >= 3000 && row.ID <= 3009)))
    {
        int[] values = attireFields.Select(field => Convert.ToInt32(RequireCell(row, field).Value)).ToArray();
        foreach (int value in values.Where(value => value > 0))
            referenced.Add(value);
        Console.WriteLine($"CHARA_INIT\t{row.ID}\t{row.Name}\t{String.Join(';', attireFields.Zip(values).Select(pair => $"{pair.First}={pair.Second}"))}");
    }

    BinderFile protectorFile = RequireSingleFile(game, "EquipParamProtector.param");
    PARAM protectors = PARAM.Read(protectorFile.Bytes);
    protectors.ApplyParamdef(ReadMatchingDefinition(defs, protectors));
    string[] slotFields = ["headEquip", "bodyEquip", "armEquip", "legEquip"];
    foreach (PARAM.Row row in protectors.Rows.Where(row => referenced.Contains(row.ID)))
    {
        Console.WriteLine($"PROTECTOR\t{row.ID}\t{row.Name}\t{String.Join(';', slotFields.Select(field => $"{field}={RequireCell(row, field).Value}"))}");
    }
}

static void InspectStartingAttireCatalog(string inputPath, string paramdefPath)
{
    BND4 game = BND4.Read(Path.GetFullPath(inputPath));
    BND4 defs = BND4.Read(Path.GetFullPath(paramdefPath));
    PARAM protectors = PARAM.Read(RequireSingleFile(game, "EquipParamProtector.param").Bytes);
    protectors.ApplyParamdef(ReadMatchingDefinition(defs, protectors));
    string[] slotFields = ["headEquip", "bodyEquip", "armEquip", "legEquip"];
    foreach (PARAM.Row row in protectors.Rows)
    {
        int[] flags = slotFields.Select(field => Convert.ToInt32(RequireCell(row, field).Value)).ToArray();
        if (flags.Count(value => value == 1) != 1 || flags.Any(value => value is not (0 or 1)))
            continue;
        int slot = Array.IndexOf(flags, 1);
        Console.WriteLine($"PROTECTOR\t{row.ID}\t{slotFields[slot]}\t{row.Name}");
    }
}

static void AuditStartingAttireCatalog(string catalogPath, string inputPath, string paramdefPath)
{
    string[] lines = File.ReadAllLines(Path.GetFullPath(catalogPath));
    const string header = "set_key\tprotector_id\tslot\tname\tgrant_descriptor";
    if (lines.Length < 5 || lines[0] != header)
        throw new InvalidDataException("starting-attire catalog has an invalid header or no complete set");
    var rows = lines.Skip(1).Select(line => line.Split('\t')).ToList();
    if (rows.Any(row => row.Length != 5))
        throw new InvalidDataException("starting-attire catalog row does not contain five fields");

    BND4 game = BND4.Read(Path.GetFullPath(inputPath));
    BND4 defs = BND4.Read(Path.GetFullPath(paramdefPath));
    PARAM protectors = PARAM.Read(RequireSingleFile(game, "EquipParamProtector.param").Bytes);
    protectors.ApplyParamdef(ReadMatchingDefinition(defs, protectors));
    string[] slots = ["head", "body", "arms", "legs"];
    string[] slotFields = ["headEquip", "bodyEquip", "armEquip", "legEquip"];
    foreach (IGrouping<string, string[]> set in rows.GroupBy(row => row[0]))
    {
        List<string[]> pieces = set.ToList();
        if (pieces.Count != 4 || !pieces.Select(row => row[2]).SequenceEqual(slots))
            throw new InvalidDataException($"{set.Key}: expected one ordered piece for every attire slot");
        foreach (string[] piece in pieces)
        {
            if (!Int32.TryParse(piece[1], out int id) || piece[4] != $"1:{id}:1")
                throw new InvalidDataException($"{set.Key}: invalid protector/grant descriptor {piece[1]}/{piece[4]}");
            List<PARAM.Row> matches = protectors.Rows.Where(row => row.ID == id).ToList();
            if (matches.Count != 1)
                throw new InvalidDataException($"{set.Key}: expected one EquipParamProtector row {id}");
            int expectedSlot = Array.IndexOf(slots, piece[2]);
            for (int slot = 0; slot < slots.Length; slot++)
            {
                int actual = Convert.ToInt32(RequireCell(matches[0], slotFields[slot]).Value);
                if (actual != (slot == expectedSlot ? 1 : 0))
                    throw new InvalidDataException(
                        $"{set.Key}: protector {id} is not exclusively a {piece[2]} row");
            }
        }
    }
    if (rows.Select(row => row[1]).Distinct().Count() != rows.Count)
        throw new InvalidDataException("starting-attire catalog repeats a protector id");
    Console.WriteLine($"starting_attire_sets={rows.Count / 4} pieces={rows.Count} catalog={catalogPath}");
}

static void WriteStartingAttireCanary(string inputPath, string paramdefPath,
                                      string outputPath, string[] rawProtectorIds)
{
    inputPath = Path.GetFullPath(inputPath);
    outputPath = Path.GetFullPath(outputPath);
    if (StringComparer.OrdinalIgnoreCase.Equals(inputPath, outputPath))
        throw new InvalidDataException("input and output paths must differ");
    if (File.Exists(outputPath))
        throw new IOException($"refusing to overwrite existing output: {outputPath}");
    if (rawProtectorIds.Length != 4
        || rawProtectorIds.Any(value => !Int32.TryParse(value, out int id) || id <= 0))
        throw new InvalidDataException("starting attire requires four positive protector ids");

    string[] attireFields = ["equip_Helm", "equip_Armer", "equip_Gaunt", "equip_Leg"];
    string[] slotFields = ["headEquip", "bodyEquip", "armEquip", "legEquip"];
    int[] protectorIds = rawProtectorIds.Select(Int32.Parse).ToArray();
    BND4 game = BND4.Read(inputPath);
    BND4 defs = BND4.Read(Path.GetFullPath(paramdefPath));
    BinderFile initFile = RequireSingleFile(game, "CharaInitParam.param");
    PARAM init = PARAM.Read(initFile.Bytes);
    PARAMDEF initDefinition = ReadMatchingDefinition(defs, init);
    init.ApplyParamdef(initDefinition);
    BinderFile protectorFile = RequireSingleFile(game, "EquipParamProtector.param");
    PARAM protectors = PARAM.Read(protectorFile.Bytes);
    protectors.ApplyParamdef(ReadMatchingDefinition(defs, protectors));

    for (int index = 0; index < protectorIds.Length; index++)
    {
        List<PARAM.Row> matches = protectors.Rows.Where(row => row.ID == protectorIds[index]).ToList();
        if (matches.Count != 1)
            throw new InvalidDataException(
                $"expected one EquipParamProtector row {protectorIds[index]}, found {matches.Count}");
        PARAM.Row row = matches[0];
        for (int slot = 0; slot < slotFields.Length; slot++)
        {
            int actual = Convert.ToInt32(RequireCell(row, slotFields[slot]).Value);
            int expected = slot == index ? 1 : 0;
            if (actual != expected)
                throw new InvalidDataException(
                    $"protector {protectorIds[index]} is not exclusively a {slotFields[index]} row");
        }
    }

    List<PARAM.Row> initialRows = init.Rows.Where(row => row.ID is >= 2000 and <= 2009).ToList();
    if (initialRows.Count != 10)
        throw new InvalidDataException($"expected ten initial-character rows, found {initialRows.Count}");
    var originalFiles = game.Files.Select(file =>
        new FileState(file.ID, file.Name, (byte[])file.Bytes.Clone())).ToList();
    var originalRows = init.Rows.Select(RowState.Capture).ToList();
    foreach (PARAM.Row row in initialRows)
        for (int index = 0; index < attireFields.Length; index++)
            RequireCell(row, attireFields[index]).Value = protectorIds[index];

    initFile.Bytes = init.Write();
    Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
    game.Write(outputPath);

    BND4 check = BND4.Read(outputPath);
    BinderFile checkedInitFile = RequireSingleFile(check, "CharaInitParam.param");
    for (int index = 0; index < check.Files.Count; index++)
    {
        BinderFile file = check.Files[index];
        FileState before = originalFiles[index];
        if (file.ID != before.Id || file.Name != before.Name)
            throw new InvalidDataException($"round-trip changed binder identity at index {index}");
        if (file != checkedInitFile && !file.Bytes.SequenceEqual(before.Bytes))
            throw new InvalidDataException($"round-trip changed unrelated binder file {file.Name}");
    }
    PARAM checkedInit = PARAM.Read(checkedInitFile.Bytes);
    checkedInit.ApplyParamdef(initDefinition);
    var changedRows = initialRows.Select(row => row.ID).ToHashSet();
    if (checkedInit.Rows.Count != originalRows.Count)
        throw new InvalidDataException("round-trip changed CharaInitParam row count");
    for (int index = 0; index < checkedInit.Rows.Count; index++)
    {
        PARAM.Row row = checkedInit.Rows[index];
        originalRows[index].RequireEqualExcept(
            RowState.Capture(row), changedRows.Contains(row.ID)
                ? attireFields.ToHashSet() : new HashSet<string>(),
            $"CharaInitParam row {row.ID}");
    }
    foreach (PARAM.Row row in checkedInit.Rows.Where(row => changedRows.Contains(row.ID)))
        for (int index = 0; index < attireFields.Length; index++)
            if (Convert.ToInt32(RequireCell(row, attireFields[index]).Value) != protectorIds[index])
                throw new InvalidDataException(
                    $"initial-character row {row.ID} did not retain {attireFields[index]}={protectorIds[index]}");
    Console.WriteLine(
        $"starting_attire_canary={String.Join(',', protectorIds)} rows={changedRows.Count} output={outputPath}");
}

static void InspectShops(string inputPath, string paramdefPath)
{
    BND4 game = BND4.Read(Path.GetFullPath(inputPath));
    BND4 defs = BND4.Read(Path.GetFullPath(paramdefPath));
    BinderFile shopFile = RequireSingleFile(game, "ShopLineupParam.param");
    PARAM shops = PARAM.Read(shopFile.Bytes);
    shops.ApplyParamdef(ReadMatchingDefinition(defs, shops));
    foreach (PARAM.Row row in shops.Rows)
    {
        Console.WriteLine($"SHOP\t{row.ID}\t{row.Name}\t{String.Join(';', row.Cells.Select(cell => $"{cell.Def.InternalName}={cell.Value}"))}");
    }
}

static void AuditShopGates(string witnessPath, string inputPath, string paramdefPath)
{
    string[] lines = File.ReadAllLines(Path.GetFullPath(witnessPath));
    if (lines.Length != 11 || lines[0] != "qwc_id\tbadge_name\tgoods_id\trepresentative_row\tequip_type\tequip_id\tstock_witness")
        throw new InvalidDataException("shop witness table must contain its header and ten rows");
    var witnesses = lines.Skip(1).Select(line => line.Split('\t')).ToList();
    if (witnesses.Any(fields => fields.Length != 7))
        throw new InvalidDataException("shop witness row does not contain seven fields");
    int[] gates = witnesses.Select(fields => Int32.Parse(fields[0])).ToArray();
    if (!gates.ToHashSet().SetEquals(Enumerable.Range(12101000, 10))
        || gates.Distinct().Count() != 10)
        throw new InvalidDataException("shop witnesses must name every ordinary Bath gate once");

    BND4 game = BND4.Read(Path.GetFullPath(inputPath));
    BND4 defs = BND4.Read(Path.GetFullPath(paramdefPath));
    BinderFile shopFile = RequireSingleFile(game, "ShopLineupParam.param");
    PARAM shops = PARAM.Read(shopFile.Bytes);
    shops.ApplyParamdef(ReadMatchingDefinition(defs, shops));
    foreach (string[] fields in witnesses)
    {
        int gate = Int32.Parse(fields[0]);
        int rowId = Int32.Parse(fields[3]);
        int equipType = Int32.Parse(fields[4]);
        int equipId = Int32.Parse(fields[5]);
        List<PARAM.Row> matches = shops.Rows.Where(row => row.ID == rowId).ToList();
        if (matches.Count != 1)
            throw new InvalidDataException($"gate {gate}: representative row {rowId} is not unique");
        PARAM.Row row = matches[0];
        if (Convert.ToInt32(RequireCell(row, "qwcId").Value) != gate
            || Convert.ToInt32(RequireCell(row, "shopType").Value) != 0
            || Convert.ToInt32(RequireCell(row, "equipType").Value) != equipType
            || Convert.ToInt32(RequireCell(row, "equipId").Value) != equipId)
            throw new InvalidDataException(
                $"gate {gate}: representative row {rowId} no longer matches its stock witness");
    }
    var counts = shops.Rows
        .Where(row => Convert.ToInt32(RequireCell(row, "shopType").Value) == 0
            && gates.Contains(Convert.ToInt32(RequireCell(row, "qwcId").Value)))
        .GroupBy(row => Convert.ToInt32(RequireCell(row, "qwcId").Value))
        .ToDictionary(group => group.Key, group => group.Count());
    if (!counts.Keys.ToHashSet().SetEquals(gates))
        throw new InvalidDataException("ordinary Bath gate groups are incomplete in ShopLineupParam");
    Console.WriteLine("shop_gate_witnesses=10 status=verified");
    foreach (string[] fields in witnesses)
        Console.WriteLine($"  qwc={fields[0]} badge={fields[1]} goods={fields[2]} rows={counts[Int32.Parse(fields[0])]} witness={fields[3]}:{fields[6]}");
}

static void WriteSeedWeapons(string requestPath, string inputPath, string paramdefPath,
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
    bool randomizeStarting = root.TryGetProperty("randomize_starting_weapons", out JsonElement start)
        && start.ValueKind == JsonValueKind.True;
    bool removeRequirements = root.TryGetProperty("remove_weapon_requirements", out JsonElement remove)
        && remove.ValueKind == JsonValueKind.True;
    bool randomizeShops = root.TryGetProperty("randomize_shops", out JsonElement randomizeShopElement)
        && randomizeShopElement.ValueKind == JsonValueKind.True;
    if (!randomizeStarting && !removeRequirements && !randomizeShops)
        throw new InvalidDataException("request contains no seed parameter edits");
    int[] right = [];
    int[] left = [];
    if (randomizeStarting)
    {
        JsonElement choices = root.GetProperty("starting_weapons");
        right = choices.GetProperty("right_hand").EnumerateArray().Select(v => v.GetInt32()).ToArray();
        left = choices.GetProperty("left_hand").EnumerateArray().Select(v => v.GetInt32()).ToArray();
        if (right.Length != 3 || left.Length != 2 || right.Distinct().Count() != 3
            || left.Distinct().Count() != 2 || right.Concat(left).Any(id => id <= 0))
            throw new InvalidDataException("starting weapon choices must be three unique right-hand and two unique left-hand ids");
    }
    int[] families = removeRequirements
        ? root.GetProperty("weapon_requirement_families").EnumerateArray().Select(v => v.GetInt32()).ToArray()
        : [];
    if (removeRequirements && (families.Length == 0 || families.Distinct().Count() != families.Length
                               || families.Any(id => id <= 0)))
        throw new InvalidDataException("weapon requirement families must be unique positive ids");
    int[] shopGates = Enumerable.Range(12101000, 10).ToArray();
    Dictionary<int, int> shopPermutation = [];
    if (randomizeShops)
    {
        JsonElement permutation = root.GetProperty("shop_gate_permutation");
        if (permutation.ValueKind != JsonValueKind.Object)
            throw new InvalidDataException("shop gate permutation must be an object");
        foreach (JsonProperty property in permutation.EnumerateObject())
        {
            if (!Int32.TryParse(property.Name, out int stockGate)
                || property.Value.ValueKind != JsonValueKind.Number
                || !property.Value.TryGetInt32(out int unlockGate)
                || !shopPermutation.TryAdd(stockGate, unlockGate))
                throw new InvalidDataException("shop gate permutation contains an invalid entry");
        }
        if (!shopPermutation.Keys.ToHashSet().SetEquals(shopGates)
            || !shopPermutation.Values.ToHashSet().SetEquals(shopGates))
            throw new InvalidDataException("shop gate permutation must be a bijection over the ten ordinary Bath gates");
    }

    BND4 game = BND4.Read(inputPath);
    BND4 defs = BND4.Read(paramdefPath);
    BinderFile shopFile = RequireSingleFile(game, "ShopLineupParam.param");
    PARAM shops = PARAM.Read(shopFile.Bytes);
    PARAMDEF shopDefinition = ReadMatchingDefinition(defs, shops);
    shops.ApplyParamdef(shopDefinition);
    BinderFile weaponFile = RequireSingleFile(game, "EquipParamWeapon.param");
    PARAM weapons = PARAM.Read(weaponFile.Bytes);
    PARAMDEF weaponDefinition = ReadMatchingDefinition(defs, weapons);
    weapons.ApplyParamdef(weaponDefinition);
    var weaponIds = weapons.Rows.Select(row => row.ID).ToHashSet();
    if (right.Concat(left).Any(id => !weaponIds.Contains(id)))
        throw new InvalidDataException("starting weapon choices contain an unknown EquipParamWeapon id");
    var originalFiles = game.Files.Select(file =>
        new FileState(file.ID, file.Name, (byte[])file.Bytes.Clone())).ToList();
    var originalShopRows = shops.Rows.Select(RowState.Capture).ToDictionary(row => row.Id);
    var originalWeaponRows = weapons.Rows.Select(RowState.Capture).ToDictionary(row => row.Id);
    var assignments = new[] { 2000, 2001, 2002 }.Zip(right)
        .Concat(new[] { 2010, 2011 }.Zip(left)).ToList();
    foreach ((int rowId, int equipId) in assignments)
    {
        PARAM.Row row = shops.Rows.Single(candidate => candidate.ID == rowId);
        RequireCell(row, "equipId").Value = equipId;
    }
    var shopRows = new HashSet<int>();
    if (randomizeShops)
    {
        foreach (PARAM.Row row in shops.Rows.Where(row =>
            Convert.ToInt32(RequireCell(row, "shopType").Value) == 0
            && shopPermutation.ContainsKey(Convert.ToInt32(RequireCell(row, "qwcId").Value))))
        {
            int stockGate = Convert.ToInt32(RequireCell(row, "qwcId").Value);
            shopRows.Add(row.ID);
            RequireCell(row, "qwcId").Value = shopPermutation[stockGate];
        }
        if (shopRows.Count == 0)
            throw new InvalidDataException("ordinary Bath gate permutation matched no ShopLineupParam rows");
    }
    string[] requirementFields = ["properStrength", "properAgility", "properMagic", "properFaith"];
    var requirementRows = new HashSet<int>();
    foreach (int family in families)
    {
        List<PARAM.Row> rows = weapons.Rows.Where(row => row.ID >= family && row.ID <= family + 1000
            && (row.ID - family) % 100 == 0).ToList();
        if (rows.Count is not (1 or 11))
            throw new InvalidDataException(
                $"weapon family {family} has {rows.Count} reinforcement rows, expected 1 or 11");
        foreach (PARAM.Row row in rows)
        {
            requirementRows.Add(row.ID);
            foreach (string field in requirementFields)
                RequireCell(row, field).Value = (byte)0;
        }
    }
    shopFile.Bytes = shops.Write();
    weaponFile.Bytes = weapons.Write();
    Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
    game.Write(outputPath);

    BND4 check = BND4.Read(outputPath);
    BinderFile checkedShopFile = RequireSingleFile(check, "ShopLineupParam.param");
    BinderFile checkedWeaponFile = RequireSingleFile(check, "EquipParamWeapon.param");
    for (int index = 0; index < check.Files.Count; index++)
    {
        BinderFile file = check.Files[index];
        FileState before = originalFiles[index];
        if (file.ID != before.Id || file.Name != before.Name)
            throw new InvalidDataException($"round-trip changed binder identity at index {index}");
        if (file != checkedShopFile && file != checkedWeaponFile && !file.Bytes.SequenceEqual(before.Bytes))
            throw new InvalidDataException($"round-trip changed unrelated binder file {file.Name}");
    }
    PARAM checkedShops = PARAM.Read(checkedShopFile.Bytes);
    checkedShops.ApplyParamdef(shopDefinition);
    var startingRows = assignments.Select(pair => pair.First).ToHashSet();
    foreach (PARAM.Row row in checkedShops.Rows)
    {
        var allowed = new HashSet<string>();
        if (startingRows.Contains(row.ID))
            allowed.Add("equipId");
        if (shopRows.Contains(row.ID))
            allowed.Add("qwcId");
        originalShopRows[row.ID].RequireEqualExcept(
            RowState.Capture(row), allowed,
            $"ShopLineupParam row {row.ID}");
    }
    foreach ((int rowId, int equipId) in assignments)
    {
        PARAM.Row row = checkedShops.Rows.Single(candidate => candidate.ID == rowId);
        if (Convert.ToInt32(RequireCell(row, "equipId").Value) != equipId)
            throw new InvalidDataException($"starting row {rowId} did not retain equipId {equipId}");
    }
    if (randomizeShops)
    {
        foreach (PARAM.Row row in checkedShops.Rows.Where(row => shopRows.Contains(row.ID)))
        {
            int originalGate = Convert.ToInt32(originalShopRows[row.ID].Cells["qwcId"]);
            int actualGate = Convert.ToInt32(RequireCell(row, "qwcId").Value);
            if (actualGate != shopPermutation[originalGate])
                throw new InvalidDataException($"shop row {row.ID} did not retain its shuffled gate");
        }
    }
    PARAM checkedWeapons = PARAM.Read(checkedWeaponFile.Bytes);
    checkedWeapons.ApplyParamdef(weaponDefinition);
    foreach (PARAM.Row row in checkedWeapons.Rows)
    {
        originalWeaponRows[row.ID].RequireEqualExcept(
            RowState.Capture(row), requirementRows.Contains(row.ID)
                ? requirementFields.ToHashSet() : new HashSet<string>(),
            $"EquipParamWeapon row {row.ID}");
        if (requirementRows.Contains(row.ID)
            && requirementFields.Any(field => Convert.ToInt32(RequireCell(row, field).Value) != 0))
            throw new InvalidDataException($"weapon row {row.ID} retained a stat requirement");
    }
    Console.WriteLine($"starting_weapons={string.Join(',', right)} firearms={string.Join(',', left)} requirement_rows={requirementRows.Count} shop_rows={shopRows.Count} output={outputPath}");
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
