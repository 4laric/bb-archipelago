using System.Text;
using System.Text.Json;
using SoulsFormats;

// Synthetic, executable integration tests. No game bytes or external test packages.
string root = Path.Combine(Path.GetTempPath(), "bb-enemy-ai-test-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(root);
int assertions = 0;
void Require(bool value, string message) { assertions++; if (!value) throw new Exception(message); }
void Refused(Action action, string fragment) {
    try { action(); throw new Exception("expected refusal: " + fragment); }
    catch (InvalidDataException ex) { Require(ex.Message.Contains(fragment), ex.Message); }
}

// Matches Lua 5.0's bytecode layout, including nested prototypes. Reads and
// writes exercise GETGLOBAL / SETGLOBAL; the importer never runs the chunks.
byte[] Chunk(string[] writes, string[] reads, byte[]? child = null, bool header = true)
{
    using var stream = new MemoryStream();
    using var w = new BinaryWriter(stream);
    void Str(string? value) {
        if (value == null) { w.Write(0UL); return; }
        var bytes = Encoding.UTF8.GetBytes(value); w.Write((ulong)bytes.Length + 1); w.Write(bytes); w.Write((byte)0);
    }
    if (header) { w.Write(new byte[] {0x1b,0x4c,0x75,0x61,0x50,1,4,8,4,6,8,9,9,8}); w.Write(31415926.53589793); }
    Str(null); w.Write(0); w.Write(new byte[] {0,0,0,2});
    w.Write(0); w.Write(0); w.Write(0); // lines, locals, upvalues
    var names = writes.Concat(reads).Distinct().ToArray();
    w.Write(names.Length);
    foreach (string name in names) { w.Write((byte)4); Str(name); }
    w.Write(child == null ? 0 : 1); if (child != null) w.Write(child);
    w.Write(writes.Length + reads.Length + 1);
    foreach (string name in writes) w.Write((uint)(7 | (Array.IndexOf(names, name) << 6)));
    foreach (string name in reads) w.Write((uint)(5 | (Array.IndexOf(names, name) << 6)));
    w.Write(27U | (1U << 15)); // RETURN, no values
    return stream.ToArray();
}

void Archive(string directory, string name, (string, byte[])[] scripts, LUAINFO.Goal[] goals, string[] globals)
{
    Directory.CreateDirectory(directory);
    var bnd = new BND4 { Compression = DCX.Type.DCX_EDGE, Version = "TESTAI01" };
    for (int i = 0; i < scripts.Length; i++)
        bnd.Files.Add(new BinderFile(Binder.FileFlags.Flag1, i, "N:\\synthetic\\" + scripts[i].Item1, scripts[i].Item2));
    var info = new LUAINFO(false, true) { Goals = goals.ToList() };
    var gnl = new LUAGNL(false, true) { Globals = globals.ToList() };
    bnd.Files.Add(new BinderFile(Binder.FileFlags.Flag1, 1000000, "N:\\synthetic\\map.luagnl", gnl.Write()));
    bnd.Files.Add(new BinderFile(Binder.FileFlags.Flag1, 1000001, "N:\\synthetic\\map.luainfo", info.Write()));
    bnd.Write(Path.Combine(directory, name + ".luabnd.dcx"));
}

try
{
    string scriptRoot = Path.Combine(root, "scripts");
    var shared = Chunk(["Common_Logic"], []);
    Archive(scriptRoot, "aicommon", [("010000_logic.lua", shared)],
        [new(10000, "Common_Logic", false, true, "Common_Interrupt")], ["Common_Logic"]);
    var original = Chunk(["OriginalBattle_Activate"], []);
    Archive(scriptRoot, "m99_00_00_00", [("800000_battle.lua", original)],
        [new(800000, "OriginalBattle", true, false)], ["OriginalBattle_Activate"]);
    var battle = Chunk(["DonorBattle_Activate", "DonorBattle_Interupt"], ["Helper", "GOAL_ChildBattle"]);
    var logic = Chunk(["Donor_Logic", "Donor_Interupt"], []);
    var helper = Chunk(["Helper"], []);
    var child = Chunk(["ChildBattle_Activate"], []);
    Archive(scriptRoot, "m98_00_00_00", [
        ("900000_battle.lua", battle), ("900000_logic.lua", logic), ("helper.lua", helper), ("900001_battle.lua", child)],
        [new(900000, "DonorBattle", true, false), new(900000, "Donor_Logic", false, true, "Donor_Interupt"),
         new(900001, "ChildBattle", true, false)],
        ["DonorBattle_Activate", "DonorBattle_Interupt", "Donor_Logic", "Donor_Interupt", "Helper", "ChildBattle_Activate"]);

    var def = new PARAMDEF {ParamType = "NPC_THINK_PARAM_ST", DataVersion = 1, Unicode = true};
    foreach (string name in new[] {"logicId", "battleGoalID", "goalID_ToCaution", "goalID_ToFind", "goalID_ToInterest"})
        def.Fields.Add(new PARAMDEF.Field(def, PARAMDEF.DefType.s32, name));
    var think = new PARAM {ParamType = def.ParamType, ParamdefDataVersion = 1, Rows = []};
    think.ApplyParamdef(def);
    var row = new PARAM.Row(42, "synthetic donor", def);
    foreach (var cell in row.Cells) cell.Value = cell.Def.InternalName is "logicId" or "battleGoalID" ? 900000 : 0;
    think.Rows.Add(row);
    var game = new BND4 {Compression = DCX.Type.DCX_EDGE};
    game.Files.Add(new BinderFile(Binder.FileFlags.Flag1, 0, "NpcThinkParam.param", think.Write()));
    var defs = new BND4 {Compression = DCX.Type.DCX_EDGE};
    defs.Files.Add(new BinderFile(Binder.FileFlags.Flag1, 0, "NpcThinkParam.paramdef", def.Write()));
    string gamePath = Path.Combine(root, "game.dcx"), defsPath = Path.Combine(root, "defs.dcx");
    game.Write(gamePath); defs.Write(defsPath);
    string plan = Path.Combine(root, "plan.json");
    void Plan(int thinkId = 42) => File.WriteAllText(plan, JsonSerializer.Serialize(new {
        format = "bb-enemizer-plan-v2", dry_run = true, swaps = new[] {new {
            logical_key = "m99_00_00_00:c1000_0000",
            destination_keys = new[] {"m99_00_00_00.msb:c1000_0000", "m99_00_00_01.msb:c1000_0000"},
            target = new {model_name = "c9000", npc_param_id = 11, think_param_id = thinkId, chara_init_id = 0},
        }}
    }));
    Plan();
    var sourceHashes = Directory.GetFiles(scriptRoot).ToDictionary(p => Path.GetFileName(p), File.ReadAllBytes);
    string output = Path.Combine(root, "output");
    Require(AiTransplant.Run(plan, gamePath, defsPath, scriptRoot, output, true) == 0, "apply");
    var result = BND4.Read(Path.Combine(output, "m99_00_00_00.luabnd.dcx"));
    Require(Directory.GetFiles(output).Length == 1, "alternate states share one binder");
    Require(result.Files.Count == 7, "imports battle, logic, helper, child plus original and metadata");
    Require(result.Files.Select(f => f.ID).Distinct().Count() == result.Files.Count, "unique IDs despite donor collisions");
    Require(result.Files.Single(f => f.Name.EndsWith("800000_battle.lua")).Bytes.SequenceEqual(original), "original unchanged");
    Require(result.Files.Single(f => f.Name.EndsWith("900000_battle.lua")).Bytes.SequenceEqual(battle), "donor unchanged");
    var info = LUAINFO.Read(result.Files.Single(f => f.Name.EndsWith(".luainfo")).Bytes);
    Require(info.Goals.Count(g => g.ID == 900000) == 2, "logic and battle with same numeric ID both registered");
    Require(info.Goals.Any(g => g.ID == 900001), "subgoal registered");
    var globals = LUAGNL.Read(result.Files.Single(f => f.Name.EndsWith(".luagnl")).Bytes).Globals;
    Require(globals.Contains("Helper") && globals.Contains("Donor_Interupt"), "global/helper/interrupt registration");
    foreach (var (name, bytes) in sourceHashes) Require(File.ReadAllBytes(Path.Combine(scriptRoot, name!)).SequenceEqual(bytes), "source untouched");
    string second = Path.Combine(root, "second");
    AiTransplant.Run(plan, gamePath, defsPath, scriptRoot, second, true);
    Require(File.ReadAllBytes(Path.Combine(output, "m99_00_00_00.luabnd.dcx"))
        .SequenceEqual(File.ReadAllBytes(Path.Combine(second, "m99_00_00_00.luabnd.dcx"))), "deterministic output");
    string audit = Path.Combine(root, "audit.json");
    AiTransplant.Run(plan, gamePath, defsPath, scriptRoot, audit, false);
    Require(File.Exists(audit) && !Directory.Exists(audit), "audit only emits report");
    using (var receipt = JsonDocument.Parse(File.ReadAllText(audit))) {
        var requirements = receipt.RootElement.GetProperty("think_parameters")[0];
        Require(requirements.GetProperty("think_param_id").GetInt32() == 42, "receipt retains Think row ID");
        Require(requirements.GetProperty("goals").EnumerateArray().All(g => g.GetProperty("id").GetInt32() == 900000),
            "receipt records actual goal IDs rather than assuming Think ID");
        Require(requirements.GetProperty("goals").GetArrayLength() == 2, "receipt preserves same-number logic and battle");
    }
    ScalingTests.Run(root, gamePath, defsPath, scriptRoot);
    Plan(999);
    string failure = Path.Combine(root, "failure");
    Refused(() => AiTransplant.Run(plan, gamePath, defsPath, scriptRoot, failure, true), "missing NpcThinkParam");
    Require(!Directory.Exists(failure), "preflight creates no output on missing think row");
    Plan();
    Refused(() => AiTransplant.Run(plan, gamePath, defsPath, scriptRoot, Path.Combine(scriptRoot, "nested"), true), "outside");
    Archive(scriptRoot, "m97_00_00_00", [("900000_battle.lua", Chunk(["ConflictBattle_Activate"], []))],
        [new(900000, "ConflictBattle", true, false)], ["ConflictBattle_Activate"]);
    Refused(() => AiTransplant.Run(plan, gamePath, defsPath, scriptRoot, failure, true), "ambiguous");
    Require(!Directory.Exists(failure), "preflight creates no output on ambiguity");
    byte[] unsupported = (byte[])battle.Clone(); unsupported[4] = 0x51;
    Refused(() => Lua50.Read(unsupported), "unsupported");
    Refused(() => Lua50.Read(battle.Concat(new byte[] {0}).ToArray()), "trailing");
    var nested = Lua50.Read(Chunk(["Top"], [], Chunk(["Scratch"], ["Dependency"], header:false)));
    Require(nested.Reads.Contains("Dependency") && nested.Writes.Contains("Scratch"), "nested symbols inspected");
    Require(nested.Definitions.SetEquals(["Top"]), "runtime scratch writes are not initialization providers");
    Console.WriteLine($"PASS: {assertions} enemy AI integration assertions");
}
finally
{
    // The freshly created, fixed-prefix temporary directory is the only target.
    if (Path.GetDirectoryName(root) != Path.GetTempPath().TrimEnd(Path.DirectorySeparatorChar)
        || !Path.GetFileName(root).StartsWith("bb-enemy-ai-test-")) throw new Exception("unsafe cleanup path");
    Directory.Delete(root, true);
}
