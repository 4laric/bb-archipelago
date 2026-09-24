using System.Security.Cryptography;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using SoulsFormats;

// Static native rewards: no AP placeholders, client, or unrelated parameter edits.
internal static class StandaloneItems
{
    static readonly JsonSerializerOptions Json = new() {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        WriteIndented = true,
    };
    internal sealed record Reward(long ItemCategory, long ItemId, long Quantity);
    internal sealed record Source(long ItemCategory, long ItemId, long Quantity, long AcquisitionFlag);
    internal sealed record Target(int ItemLotId, int Slot, string Role, Source Source);
    internal sealed record Placement(string LocationKey, string ItemKey, Reward Reward, List<Target> AwardTargets);
    internal sealed record Plan(string Format, string Seed, string GeneratorBuild,
        Dictionary<string, string> SourceHashes, string CatalogSha256,
        List<Placement> Placements, List<JsonElement> Unsupported, Dictionary<string, JsonElement> Options);
    sealed record Catalog(string Format, List<CatalogEntry> Entries, List<CatalogItem> Items);
    sealed record CatalogEntry(string LocationKey, string Status, List<Target> Targets,
        Dictionary<string, bool> When);
    sealed record CatalogItem(string ItemKey, Reward Reward);
    sealed record Edit(PARAM.Row Row, int Slot, Reward Reward);

    static void Need([DoesNotReturnIf(false)] bool condition, string message) {
        if (!condition) throw new InvalidDataException(message);
    }
    static string Hash(byte[] bytes) => Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    static BinderFile FileIn(BND4 binder, string suffix) {
        var files = binder.Files.Where(file => file.Name.EndsWith(suffix, StringComparison.OrdinalIgnoreCase)).ToList();
        Need(files.Count == 1, $"expected one {suffix}, found {files.Count}");
        return files[0];
    }
    static PARAM.Cell Cell(PARAM.Row row, string name) => row[name]
        ?? throw new InvalidDataException($"row {row.ID} lacks {name}");
    static long Number(PARAM.Row row, string name) => Convert.ToInt64(Cell(row, name).Value);
    static void Put(PARAM.Row row, string name, long value) {
        var cell = Cell(row, name);
        // Checked conversion prevents category/quantity truncation at the PARAMDEF boundary.
        cell.Value = Convert.ChangeType(value, cell.Value.GetType(), System.Globalization.CultureInfo.InvariantCulture);
    }
    static PARAMDEF Definition(BND4 defs, PARAM param) {
        var matches = defs.Files.Where(file => file.Name.EndsWith(".paramdef", StringComparison.OrdinalIgnoreCase))
            .Select(file => PARAMDEF.Read(file.Bytes))
            .Where(def => def.ParamType == param.ParamType && def.DataVersion == param.ParamdefDataVersion
                && (param.DetectedSize == -1 || def.GetRowSize() == param.DetectedSize)).ToList();
        Need(matches.Count == 1, "missing or ambiguous ItemLotParam definition");
        return matches[0];
    }

    internal static void Write(string planPath, string catalogPath, string inputPath, string defsPath, string outputPath) {
        inputPath = Path.GetFullPath(inputPath); outputPath = Path.GetFullPath(outputPath);
        Need(!StringComparer.OrdinalIgnoreCase.Equals(inputPath, outputPath), "input and output paths must differ");
        Need(!File.Exists(outputPath), "refusing to overwrite existing standalone output");
        byte[] planBytes = System.IO.File.ReadAllBytes(planPath);
        var plan = JsonSerializer.Deserialize<Plan>(planBytes, Json)
            ?? throw new InvalidDataException("empty standalone plan");
        Need(plan.Format == "bb-standalone-item-plan-v1", "unsupported standalone item plan format");
        Need(plan.Unsupported is { Count: 0 }, "standalone plan contains unresolved award targets");
        Need(plan.Placements is { Count: > 0 }, "standalone plan contains no placements");
        Need(!string.IsNullOrWhiteSpace(plan.GeneratorBuild) && !string.IsNullOrWhiteSpace(plan.Seed)
            && plan.CatalogSha256 is { Length: 64 } && plan.CatalogSha256.All(Uri.IsHexDigit),
            "standalone plan lacks seed/build/catalog provenance");
        byte[] catalogBytes = System.IO.File.ReadAllBytes(catalogPath);
        Need(Hash(catalogBytes) == plan.CatalogSha256, "standalone catalog hash mismatch");
        var catalog = JsonSerializer.Deserialize<Catalog>(catalogBytes, Json);
        Need(catalog is not null && catalog.Format == "bb-standalone-award-target-catalog-v1"
            && catalog.Entries is { Count: > 0 } && catalog.Items is { Count: > 0 }, "invalid standalone catalog");
        Need(plan.Options is not null, "standalone plan lacks options");
        bool Active(CatalogEntry entry) {
            return (entry.When ?? new Dictionary<string, bool>()).All(pair => {
                Need(pair.Key is "include_dlc" or "alternate_hypogean_gaol_routes" or "one_time_enemy_checks",
                    "unknown catalog option predicate");
                bool enabled = false;
                if (plan.Options.TryGetValue(pair.Key, out var value)) {
                    Need(value.ValueKind is JsonValueKind.True or JsonValueKind.False, "catalog option must be boolean");
                    enabled = value.GetBoolean();
                }
                return enabled == pair.Value;
            });
        }
        Need(catalog.Entries.Select(entry => entry.LocationKey).Distinct().Count() == catalog.Entries.Count
            && catalog.Items.Select(item => item.ItemKey).Distinct().Count() == catalog.Items.Count,
            "duplicate catalog location or item");
        var active = catalog.Entries.Where(Active).ToList();
        Need(active.All(entry => entry.Status is "placeable" or "fixed_progression" or "completion_only"),
            "active standalone catalog location is unsupported");
        var expectedLocations = active.Where(entry => entry.Status == "placeable")
            .ToDictionary(entry => entry.LocationKey);
        Need(expectedLocations.Keys.ToHashSet().SetEquals(plan.Placements.Select(item => item.LocationKey)),
            "standalone placement set differs from active catalog");
        var expectedItems = catalog.Items.ToDictionary(item => item.ItemKey, item => item.Reward);
        byte[] original = System.IO.File.ReadAllBytes(inputPath);
        Need(plan.SourceHashes is not null && plan.SourceHashes.TryGetValue(
            "dvdroot_ps4/param/gameparam/gameparam.parambnd.dcx", out string? sourceHash)
            && sourceHash == Hash(original), "standalone source gameparam hash mismatch");
        byte[] definitionBytes = System.IO.File.ReadAllBytes(defsPath);
        Need(plan.SourceHashes.TryGetValue("dvdroot_ps4/paramdef/paramdef.paramdefbnd.dcx", out string? defsHash)
            && defsHash == Hash(definitionBytes), "standalone source paramdef hash mismatch");
        var binder = BND4.Read(original);
        var lotFile = FileIn(binder, "ItemLotParam.param");
        var lots = PARAM.Read(lotFile.Bytes);
        var definition = Definition(BND4.Read(definitionBytes), lots);
        lots.ApplyParamdef(definition);
        var originals = binder.Files.Select(file => (file.ID, file.Name, file.Flags,
            file.CompressionType, Bytes: file.Bytes.ToArray())).ToList();
        var originalHeader = (binder.Version, binder.Format, binder.Unk04, binder.Unk05, binder.BigEndian,
            binder.BitBigEndian, binder.Unicode, binder.Extended, binder.Compression);
        var originalRows = lots.Rows.Select(row => (row.ID, row.Name, Cells: row.Cells.Select(cell =>
            (cell.Def.InternalName, Value: cell.Value is byte[] bytes ? bytes.ToArray() : cell.Value)).ToList())).ToList();
        var rows = lots.Rows.GroupBy(row => row.ID).ToDictionary(group => group.Key, group => group.ToList());
        // Equipment/goods may be shop-only or starting gear, so bind them to their
        // native parameter row IDs. Category 8 additionally needs an original
        // ItemLot recipe witness; it is not a runtime inventory descriptor.
        var inventoryIds = new Dictionary<long, HashSet<long>> {
            [0] = PARAM.Read(FileIn(binder, "EquipParamWeapon.param").Bytes).Rows.Select(row => (long)row.ID).ToHashSet(),
            [1] = PARAM.Read(FileIn(binder, "EquipParamProtector.param").Bytes).Rows.Select(row => (long)row.ID).ToHashSet(),
            [4] = PARAM.Read(FileIn(binder, "EquipParamGoods.param").Bytes).Rows.Select(row => (long)row.ID).ToHashSet(),
        };
        var witnessed = lots.Rows.SelectMany(row => Enumerable.Range(1, 8).Select(slot => (
            Category: Number(row, $"lotItemCategory{slot:00}"), Id: Number(row, $"lotItemId{slot:00}"))))
            .ToHashSet();
        var locations = new HashSet<string>(StringComparer.Ordinal);
        var targets = new HashSet<(int, int)>();
        var edits = new List<Edit>();
        foreach (var placement in plan.Placements) {
            Need(placement is not null && !string.IsNullOrWhiteSpace(placement.LocationKey)
                && !string.IsNullOrWhiteSpace(placement.ItemKey) && locations.Add(placement.LocationKey),
                "invalid or duplicate standalone location");
            var reward = placement!.Reward;
            Need(expectedItems.TryGetValue(placement.ItemKey, out var expectedReward) && reward == expectedReward,
                "standalone item reward differs from catalog");
            Need(placement.AwardTargets is not null && expectedLocations[placement.LocationKey].Targets
                .SequenceEqual(placement.AwardTargets), "standalone award targets differ from catalog");
            Need(reward is not null && reward.ItemCategory is 0 or 1 or 4 or 8
                && reward.ItemId > 0 && reward.Quantity > 0
                && (reward.ItemCategory == 8 ? witnessed.Contains((8, reward.ItemId))
                    : inventoryIds[reward.ItemCategory].Contains(reward.ItemId)),
                $"unwitnessed or invalid native reward at {placement.LocationKey}");
            Need(placement.AwardTargets is { Count: > 0 }
                && placement.AwardTargets.Count(target => target is not null && target.Role == "delivery") == 1,
                "each location requires exactly one delivery target");
            foreach (var target in placement.AwardTargets!) {
                Need(target is not null && target.Slot is >= 1 and <= 8
                    && target.Role is ("delivery" or "alternative" or "retire")
                    && target.Source is not null && targets.Add((target.ItemLotId, target.Slot)),
                    "invalid or duplicate standalone award target");
                Need(rows.TryGetValue(target!.ItemLotId, out var matches) && matches.Count == 1,
                    $"missing or ambiguous standalone lot {target.ItemLotId}");
                var row = matches![0]; var source = target.Source;
                Need(Number(row, $"lotItemCategory{target.Slot:00}") == source.ItemCategory
                    && Number(row, $"lotItemId{target.Slot:00}") == source.ItemId
                    && Number(row, $"lotItemNum{target.Slot:00}") == source.Quantity
                    && Number(row, "getItemFlagId") == source.AcquisitionFlag,
                    $"standalone source witness drift at lot {target.ItemLotId} slot {target.Slot}");
                edits.Add(new Edit(row, target.Slot, target.Role == "retire" ? new Reward(0, 0, 0) : reward!));
            }
        }
        // Validation completes before staging. Only the three explicitly planned cells change.
        foreach (var edit in edits) {
            Put(edit.Row, $"lotItemCategory{edit.Slot:00}", edit.Reward.ItemCategory);
            Put(edit.Row, $"lotItemId{edit.Slot:00}", edit.Reward.ItemId);
            Put(edit.Row, $"lotItemNum{edit.Slot:00}", edit.Reward.Quantity);
        }
        lotFile.Bytes = lots.Write();
        string parent = Path.GetDirectoryName(outputPath)!;
        Directory.CreateDirectory(parent);
        string stage = Path.Combine(parent, ".standalone-items-" + Guid.NewGuid().ToString("N") + ".tmp");
        try {
            binder.Write(stage);
            var reread = BND4.Read(stage);
            Need(originalHeader == (reread.Version, reread.Format, reread.Unk04, reread.Unk05,
                reread.BigEndian, reread.BitBigEndian, reread.Unicode, reread.Extended, reread.Compression),
                "round-trip binder metadata changed");
            Need(reread.Files.Count == originals.Count, "round-trip binder file count changed");
            for (int index = 0; index < originals.Count; index++) {
                var before = originals[index]; var after = reread.Files[index];
                Need(before.ID == after.ID && before.Name == after.Name && before.Flags == after.Flags
                    && before.CompressionType == after.CompressionType, "round-trip binder identity changed");
                if (after.Name != lotFile.Name)
                    Need(before.Bytes.SequenceEqual(after.Bytes), $"round-trip unrelated file changed: {after.Name}");
            }
            var verified = PARAM.Read(FileIn(reread, "ItemLotParam.param").Bytes);
            verified.ApplyParamdef(definition);
            Need(verified.Rows.Count == lots.Rows.Count, "round-trip ItemLot row count changed");
            for (int index = 0; index < lots.Rows.Count; index++) {
                var before = originalRows[index]; var actual = verified.Rows[index];
                Need(before.ID == actual.ID && before.Name == actual.Name, "round-trip ItemLot identity changed");
                Need(before.Cells.Count == actual.Cells.Count, "round-trip ItemLot cell count changed");
                var allowed = edits.Where(edit => edit.Row.ID == before.ID).SelectMany(edit => new[] {
                    ($"lotItemCategory{edit.Slot:00}", edit.Reward.ItemCategory),
                    ($"lotItemId{edit.Slot:00}", edit.Reward.ItemId),
                    ($"lotItemNum{edit.Slot:00}", edit.Reward.Quantity),
                }).ToDictionary(item => item.Item1, item => item.Item2);
                for (int cell = 0; cell < before.Cells.Count; cell++) {
                    var left = before.Cells[cell]; var right = actual.Cells[cell];
                    Need(left.InternalName == right.Def.InternalName, "round-trip cell layout changed");
                    if (allowed.TryGetValue(left.InternalName, out long changed)) {
                        Need(Convert.ToInt64(right.Value) == changed, "planned standalone reward was not written");
                        continue;
                    }
                    bool equal = left.Value is byte[] a && right.Value is byte[] b
                        ? a.SequenceEqual(b) : Equals(left.Value, right.Value);
                    Need(equal, $"unplanned cell changed: {before.ID}/{left.InternalName}");
                }
            }
            // File.Move without overwrite also refuses a destination created during validation.
            System.IO.File.Move(stage, outputPath);
            Console.WriteLine(JsonSerializer.Serialize(new {
                format = "bb-standalone-item-receipt-v1", plan.Seed,
                plan_sha256 = Hash(planBytes), source_sha256 = Hash(original),
                output_sha256 = Hash(System.IO.File.ReadAllBytes(outputPath)),
                locations = plan.Placements.Count, award_targets = edits.Count,
                runtime_validated = false,
            }, Json));
        } finally {
            if (System.IO.File.Exists(stage)) System.IO.File.Delete(stage);
        }
    }
}
