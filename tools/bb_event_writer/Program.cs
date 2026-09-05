using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using SoulsFormats;

namespace BBEventWriter;

/// <summary>
/// Writes the Archipelago event overlays for Bloodborne (CUSA03173 01.09)
/// directly with SoulsFormats, without a script compiler.
///
/// Every emitted instruction is cloned from a vanilla instruction of the same
/// bank/id in the same licensed file, so no instruction table ships with this
/// tool. Every untouched event is byte-identical to the source, and the owned
/// events are instruction-identical to a DarkScript3 3.6.3 compile of the
/// reviewed source transforms (tools/patch_laurence_skull.py,
/// tools/patch_emblem_chokepoint.py, tools/patch_category8_awards.py); see
/// docs/EVENT-WRITER.md for the verification record.
/// </summary>
internal static class Program
{
    private static int Main(string[] args)
    {
        try
        {
            if (args.Length == 0) throw new UsageException();
            return args[0] switch
            {
                "dump" => Dump(args.Skip(1).ToArray()),
                "decompress" => Decompress(args.Skip(1).ToArray()),
                "cathedral" => Cathedral(args.Skip(1).ToArray()),
                "common" => Common(args.Skip(1).ToArray()),
                _ => throw new UsageException(),
            };
        }
        catch (UsageException)
        {
            Console.Error.WriteLine(
                "usage: BBEventWriter dump <emevd.dcx> [eventId ...]\n" +
                "       BBEventWriter decompress <in.emevd.dcx> <out.emevd>\n" +
                "       BBEventWriter cathedral --source <m24_00_00_00.emevd.dcx> --output <path> --manifest <path>\n" +
                "       BBEventWriter common --source <common.emevd.dcx> --request <rows.json> --output <path> --manifest <path>");
            return 2;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine($"error: {error.Message}");
            return 1;
        }
    }

    private sealed class UsageException : Exception { }

    private static Dictionary<string, string> Options(string[] args, params string[] required)
    {
        var options = new Dictionary<string, string>();
        for (var i = 0; i + 1 < args.Length; i += 2)
        {
            if (!args[i].StartsWith("--", StringComparison.Ordinal)) throw new UsageException();
            options[args[i][2..]] = args[i + 1];
        }
        foreach (var name in required)
            if (!options.ContainsKey(name)) throw new UsageException();
        return options;
    }

    private static EMEVD Load(string path)
    {
        var emevd = EMEVD.Read(path);
        if (emevd.Format != EMEVD.Game.Bloodborne)
            throw new InvalidDataException($"{path}: not a Bloodborne EMEVD (format {emevd.Format})");
        return emevd;
    }

    private static string Sha256(string path)
    {
        using var stream = File.OpenRead(path);
        return Convert.ToHexString(SHA256.HashData(stream)).ToLowerInvariant();
    }

    private static string Hex(byte[] data) => Convert.ToHexString(data).ToLowerInvariant();

    private static void RefuseOverwrite(params string[] paths)
    {
        foreach (var path in paths)
            if (File.Exists(path)) throw new IOException($"refusing to overwrite {path}");
    }

    // ------------------------------------------------------------------ dump

    private static int Dump(string[] args)
    {
        if (args.Length == 0) throw new UsageException();
        var emevd = Load(args[0]);
        var wanted = args.Skip(1).Select(long.Parse).ToHashSet();
        Console.WriteLine($"format={emevd.Format} events={emevd.Events.Count} compression={emevd.Compression}");
        foreach (var e in emevd.Events)
        {
            if (wanted.Count > 0 && !wanted.Contains(e.ID)) continue;
            Console.WriteLine($"event {e.ID} rest={e.RestBehavior} instructions={e.Instructions.Count} parameters={e.Parameters.Count}");
            for (var i = 0; i < e.Instructions.Count; i++)
            {
                var ins = e.Instructions[i];
                var layer = ins.Layer.HasValue ? $" layer={ins.Layer.Value:x8}" : "";
                Console.WriteLine($"  [{i}] {ins.Bank}[{ins.ID}] {Hex(ins.ArgData)}{layer}");
            }
            foreach (var p in e.Parameters)
                Console.WriteLine($"  param instr={p.InstructionIndex} target={p.TargetStartByte} source={p.SourceStartByte} bytes={p.ByteCount} unk={p.UnkID}");
        }
        return 0;
    }

    private static int Decompress(string[] args)
    {
        if (args.Length != 2) throw new UsageException();
        File.WriteAllBytes(args[1], DCX.Decompress(args[0]));
        Console.WriteLine($"in={Sha256(args[0])} out={Sha256(args[1])}");
        return 0;
    }

    // -------------------------------------------------------------- helpers

    private static EMEVD.Event EventById(EMEVD emevd, long id) =>
        emevd.Events.SingleOrDefault(e => e.ID == id)
        ?? throw new InvalidDataException($"event {id} is absent or ambiguous");

    /// <summary>
    /// A vanilla instruction of the given bank/id, used as the shape witness
    /// for a new instruction: it proves the game exercises that instruction
    /// and fixes its argument length. Layered instructions are skipped so
    /// the clone carries no layer mask.
    /// </summary>
    private static EMEVD.Instruction Template(EMEVD emevd, int bank, int id, int argLength)
    {
        foreach (var e in emevd.Events)
            foreach (var ins in e.Instructions)
                if (ins.Bank == bank && ins.ID == id && !ins.Layer.HasValue && ins.ArgData.Length == argLength)
                    return ins;
        throw new InvalidDataException($"no vanilla instruction {bank}[{id}] with {argLength} argument bytes to clone");
    }

    private static EMEVD.Instruction Clone(EMEVD emevd, int bank, int id, byte[] args) =>
        new(Template(emevd, bank, id, args.Length).Bank, id, args);

    private static byte[] Args(params object[] values)
    {
        using var stream = new MemoryStream();
        using var writer = new BinaryWriter(stream);
        foreach (var value in values)
        {
            switch (value)
            {
                case byte b: writer.Write(b); break;
                case int i: writer.Write(i); break;
                case float f: writer.Write(f); break;
                default: throw new ArgumentException($"unsupported argument {value}");
            }
        }
        while (stream.Length % 4 != 0) writer.Write((byte)0);
        return stream.ToArray();
    }

    private static string Fingerprint(EMEVD.Event e)
    {
        var text = new StringBuilder();
        text.Append(e.ID).Append('|').Append(e.RestBehavior).Append('|');
        foreach (var ins in e.Instructions)
            text.Append(ins.Bank).Append(':').Append(ins.ID).Append(':').Append(Hex(ins.ArgData)).Append(':').Append(ins.Layer).Append(';');
        foreach (var p in e.Parameters)
            text.Append(p.InstructionIndex).Append(',').Append(p.TargetStartByte).Append(',').Append(p.SourceStartByte).Append(',').Append(p.ByteCount).Append(',').Append(p.UnkID).Append(';');
        return text.ToString();
    }

    private static void Expect(EMEVD.Instruction ins, int bank, int id, string argHex, string what)
    {
        if (ins.Bank != bank || ins.ID != id || Hex(ins.ArgData) != argHex || ins.Layer.HasValue)
            throw new InvalidDataException(
                $"{what}: expected {bank}[{id}] {argHex}, found {ins.Bank}[{ins.ID}] {Hex(ins.ArgData)}");
    }

    private static void WriteManifest(string path, object document)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(path))!);
        File.WriteAllText(path, JsonSerializer.Serialize(document, new JsonSerializerOptions { WriteIndented = true }) + "\n");
    }

    // ------------------------------------------------------------ cathedral

    private const long LaurenceEvent = 12401803;
    private const long EmblemEvent = 12400760;
    private const int WitnessFlag = 12401898;
    private const int PasswordFlag = 12401803;
    private const int FarSideFlag = 12400170;

    private static int Cathedral(string[] args)
    {
        var o = Options(args, "source", "output", "manifest");
        RefuseOverwrite(o["output"], o["manifest"]);
        if (!Path.GetFileName(o["source"]).Equals("m24_00_00_00.emevd.dcx", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("source must be named m24_00_00_00.emevd.dcx");
        var emevd = Load(o["source"]);
        var untouched = emevd.Events.Where(e => e.ID != LaurenceEvent && e.ID != EmblemEvent)
            .Select(e => (e.ID, Fingerprint(e))).ToList();
        var eventCount = emevd.Events.Count;

        PatchLaurence(emevd);
        PatchEmblem(emevd);

        if (emevd.Events.Count != eventCount)
            throw new InvalidDataException("Cathedral transform must not add or remove events");
        foreach (var (id, fingerprint) in untouched)
            if (Fingerprint(EventById(emevd, id)) != fingerprint)
                throw new InvalidDataException($"unrelated event {id} changed");

        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(o["output"]))!);
        emevd.Write(o["output"]);
        WriteManifest(o["manifest"], new
        {
            format = "bb-cathedral-emevd-build-v2",
            writer = "BBEventWriter",
            source_sha256 = Sha256(o["source"]),
            output_sha256 = Sha256(o["output"]),
            output_relative_path = "dvdroot_ps4/event/m24_00_00_00.emevd.dcx",
            owned_events = new[] { EmblemEvent, LaurenceEvent },
            laurence_witness_flag = WitnessFlag,
            suppressed_password_flag = PasswordFlag,
        });
        return 0;
    }

    /// <summary>
    /// tools/patch_laurence_skull.py in instructions: the guard
    /// <c>EndIf(ThisEvent())</c> becomes <c>EndIf(EventFlag(12401898))</c>,
    /// and the tail gains <c>SetEventFlag(12401898, ON); RestartEvent();</c>
    /// so the event never completes and never awards password flag 12401803.
    /// </summary>
    private static void PatchLaurence(EMEVD emevd)
    {
        var e = EventById(emevd, LaurenceEvent);
        if (e.Instructions.Count != 16 || e.Parameters.Count != 0)
            throw new InvalidDataException($"event {LaurenceEvent} does not have the supported interaction shape");
        // 1003[2] EndIfEventFlag(endType=End, state=ON, flagType=ThisEvent, flag=0)
        Expect(e.Instructions[1], 1003, 2, "0001010000000000", "Laurence guard");
        e.Instructions[1] = Clone(emevd, 1003, 2, Args((byte)0, (byte)1, (byte)0, (byte)0, WitnessFlag));
        var setWitness = Clone(emevd, 2003, 2, Args(WitnessFlag, (byte)1));
        var restart = Clone(emevd, 1000, 4, Args((byte)1));
        e.Instructions.Add(setWitness);
        e.Instructions.Add(restart);

        var passwordOn = Hex(Args(PasswordFlag, (byte)1));
        foreach (var ins in e.Instructions)
            if (ins.Bank == 2003 && ins.ID == 2 && Hex(ins.ArgData) == passwordOn)
                throw new InvalidDataException("altar patch must not write the shuffled password flag");
        if (e.Instructions.Count(ins => ins.Bank == 2003 && ins.ID == 2 && Hex(ins.ArgData) == Hex(setWitness.ArgData)) != 1)
            throw new InvalidDataException("altar patch must write exactly one synthetic witness");
    }

    /// <summary>
    /// tools/patch_emblem_chokepoint.py in instructions: the far-side success
    /// disjunct <c>ObjActEventFlag(12400170)</c> of the plaza gate's
    /// <c>WaitFor(itemAct || itemAct2 || ...)</c> is removed, which drops the
    /// condition instruction and its OR-group compile.
    /// </summary>
    private static void PatchEmblem(EMEVD emevd)
    {
        var e = EventById(emevd, EmblemEvent);
        if (e.Instructions.Count != 58 || e.Parameters.Count != 0)
            throw new InvalidDataException($"event {EmblemEvent} does not have the supported gate shape");
        // 5[2] IfObjActEventFlag(OR_03, 12400170); 0[0] IfConditionGroup(OR_01?, ON, OR_03)
        Expect(e.Instructions[11], 5, 2, Hex(Args((byte)3, (byte)0, (byte)0, (byte)0, FarSideFlag)), "far-side condition");
        Expect(e.Instructions[15], 0, 0, "0001ff00", "far-side group compile successor");
        Expect(e.Instructions[14], 0, 0, "ff010300", "far-side group compile");
        e.Instructions.RemoveAt(14);
        e.Instructions.RemoveAt(11);
        var farSide = Hex(Args(FarSideFlag));
        foreach (var ins in e.Instructions)
            if (ins.Bank == 5 && ins.ID == 2 && Hex(ins.ArgData).EndsWith(farSide, StringComparison.Ordinal))
                throw new InvalidDataException("gate patch left a far-side success path");
    }

    // --------------------------------------------------------------- common

    private const long BridgeEvent = 98_000_000;

    private sealed record AwardRow(int token_goods_id, int item_lot_id, int ack_flag, string? item_key);

    /// <summary>
    /// Rows from a request document's <c>category8_awards</c>: either the
    /// launcher's list, or the seed's dictionary keyed by AP item id.
    /// </summary>
    private static List<AwardRow> ReadRows(string path)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        if (!document.RootElement.TryGetProperty("category8_awards", out var element))
            throw new InvalidDataException("request carries no category8_awards");
        var items = element.ValueKind switch
        {
            JsonValueKind.Array => element.EnumerateArray().ToList(),
            JsonValueKind.Object => element.EnumerateObject().Select(p => p.Value).ToList(),
            _ => throw new InvalidDataException("category8_awards must be a list or an object"),
        };
        return items.Select(row => new AwardRow(
            row.GetProperty("token_goods_id").GetInt32(),
            row.GetProperty("item_lot_id").GetInt32(),
            row.GetProperty("ack_flag").GetInt32(),
            row.TryGetProperty("item_key", out var key) ? key.GetString() : null)).ToList();
    }

    private static int Common(string[] args)
    {
        var o = Options(args, "source", "request", "output", "manifest");
        RefuseOverwrite(o["output"], o["manifest"]);
        if (!Path.GetFileName(o["source"]).Equals("common.emevd.dcx", StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("source must be named common.emevd.dcx");
        var rows = ReadRows(o["request"]);
        if (rows.Count == 0) throw new InvalidDataException("request carries no category-8 rows");
        if (rows.Select(r => r.token_goods_id).Distinct().Count() != rows.Count
            || rows.Select(r => r.item_lot_id).Distinct().Count() != rows.Count
            || rows.Select(r => r.ack_flag).Distinct().Count() != rows.Count)
            throw new InvalidDataException("category-8 rows must have distinct tokens, lots, and ack flags");

        var emevd = Load(o["source"]);
        var bridgeEventIds = rows.Select((_, index) => BridgeEvent + index).ToHashSet();
        if (emevd.Events.Any(e => bridgeEventIds.Contains(e.ID)))
            throw new InvalidDataException("category-8 award bridge is already present");
        var constructor = EventById(emevd, 0);
        var untouched = emevd.Events.Where(e => e.ID != 0).Select(e => (e.ID, Fingerprint(e))).ToList();
        var constructorBefore = constructor.Instructions.ToList();

        // Give every row an isolated event ID. The two-row pilot happened to work
        // with shared event slots, but expanded tables can leave later instances
        // inert even though their arguments decompile correctly.
        Template(emevd, 2000, 0, 12); // the game exercises InitializeEvent
        var initializers = rows.Select((row, index) =>
            new EMEVD.Instruction(2000, 0, Args(0, (int)(BridgeEvent + index), row.token_goods_id, row.item_lot_id, row.ack_flag))).ToList();
        constructor.Instructions.InsertRange(0, initializers);

        foreach (var (row, index) in rows.Select((row, index) => (row, index)))
        {
            var bridge = new EMEVD.Event(BridgeEvent + index, EMEVD.Event.RestBehaviorType.Restart);
            // Instruction encodings and parameter order are those DarkScript3 3.6.3
            // emits for tools/patch_category8_awards.py (see docs/EVENT-WRITER.md).
            bridge.Instructions.Add(Clone(emevd, 2000, 2, Args((byte)0)));
            bridge.Instructions.Add(Clone(emevd, 3, 16, Args((byte)0, (byte)3, (byte)0, (byte)0, 0, (byte)1)));
            bridge.Instructions.Add(Clone(emevd, 2003, 2, Args(0, (byte)0)));
            bridge.Instructions.Add(Clone(emevd, 1001, 0, Args(1.0f)));
            bridge.Instructions.Add(Clone(emevd, 1014, 0, Array.Empty<byte>()));
            bridge.Instructions.Add(Clone(emevd, 2003, 24, Args(3, 0, 1)));
            bridge.Instructions.Add(Clone(emevd, 1001, 0, Args(1.0f)));
            bridge.Instructions.Add(Clone(emevd, 3, 16, Args((byte)1, (byte)3, (byte)0, (byte)0, 0, (byte)1)));
            bridge.Instructions.Add(Clone(emevd, 1000, 101, Args((byte)0, (byte)1, (byte)1, (byte)0)));
            bridge.Instructions.Add(Clone(emevd, 2003, 4, Args(0)));
            bridge.Instructions.Add(Clone(emevd, 2003, 2, Args(0, (byte)1)));
            bridge.Instructions.Add(Clone(emevd, 1000, 4, Args((byte)1)));
            bridge.Parameters.Add(new EMEVD.Parameter(1, 4, 0, 4));
            bridge.Parameters.Add(new EMEVD.Parameter(5, 4, 0, 4));
            bridge.Parameters.Add(new EMEVD.Parameter(7, 4, 0, 4));
            bridge.Parameters.Add(new EMEVD.Parameter(9, 0, 4, 4));
            bridge.Parameters.Add(new EMEVD.Parameter(2, 0, 8, 4));
            bridge.Parameters.Add(new EMEVD.Parameter(10, 0, 8, 4));
            emevd.Events.Add(bridge);
        }

        // Verification: nothing else moved.
        foreach (var (id, fingerprint) in untouched)
            if (Fingerprint(EventById(emevd, id)) != fingerprint)
                throw new InvalidDataException($"unrelated event {id} changed");
        if (!constructor.Instructions.Skip(rows.Count).SequenceEqual(constructorBefore))
            throw new InvalidDataException("constructor lost a vanilla initializer");

        Directory.CreateDirectory(Path.GetDirectoryName(Path.GetFullPath(o["output"]))!);
        emevd.Write(o["output"]);
        WriteManifest(o["manifest"], new
        {
            format = "bb-common-emevd-build-v2",
            writer = "BBEventWriter",
            source_sha256 = Sha256(o["source"]),
            output_sha256 = Sha256(o["output"]),
            output_relative_path = "dvdroot_ps4/event/common.emevd.dcx",
            @event = BridgeEvent,
            events = bridgeEventIds.Order().ToList(),
            rows,
        });
        return 0;
    }
}
