using System.Globalization;
using System.Text;
using SoulsFormats;

if (args.Length != 3)
{
    Console.Error.WriteLine(
        "usage: BBObjActMiner <gameparam.parambnd.dcx> <paramdef.paramdefbnd.dcx> <output.tsv>");
    return 2;
}

string gamePath = Path.GetFullPath(args[0]);
string defsPath = Path.GetFullPath(args[1]);
string outputPath = Path.GetFullPath(args[2]);

BND4 game = BND4.Read(gamePath);
BND4 defs = BND4.Read(defsPath);
BinderFile paramFile = RequireSingleFile(game, "ObjActParam.param");
PARAM param = PARAM.Read(paramFile.Bytes);
PARAMDEF definition = ReadMatchingDefinition(defs, param);
param.ApplyParamdef(definition);

string[] fields = param.Rows.SelectMany(row => row.Cells)
    .Select(cell => cell.Def.InternalName)
    .Distinct(StringComparer.Ordinal)
    .ToArray();
var output = new StringBuilder();
output.Append("row_id\trow_name");
foreach (string field in fields)
    output.Append('\t').Append(field);
output.AppendLine();
foreach (PARAM.Row row in param.Rows.OrderBy(row => row.ID))
{
    output.Append(row.ID).Append('\t').Append(Clean(row.Name));
    foreach (string field in fields)
        output.Append('\t').Append(Format(row[field]?.Value));
    output.AppendLine();
}
Directory.CreateDirectory(Path.GetDirectoryName(outputPath)!);
File.WriteAllText(outputPath, output.ToString(), new UTF8Encoding(false));
Console.WriteLine($"rows={param.Rows.Count} fields={fields.Length} output={outputPath}");
return 0;

static string Clean(string? value) => (value ?? "").Replace('\t', ' ').Replace('\r', ' ').Replace('\n', ' ');

static string Format(object? value) => value switch
{
    null => "",
    byte[] bytes => Convert.ToHexString(bytes),
    IFormattable formattable => formattable.ToString(null, CultureInfo.InvariantCulture),
    _ => Clean(value.ToString()),
};

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
