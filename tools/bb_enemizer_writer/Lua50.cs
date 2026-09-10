using System.Text;

// Read-only Lua 5.0 bytecode inspection. Layout and opcodes:
// https://www.lua.org/source/5.0/lundump.c.html
// https://www.lua.org/source/5.0/lopcodes.h.html
// This never executes or rewrites game bytecode. Other VM layouts are refused.
internal sealed record LuaSymbols(HashSet<string> Reads, HashSet<string> Writes, HashSet<string> Definitions);

internal static class Lua50
{
    public static LuaSymbols Read(byte[] bytes)
    {
        using var stream = new MemoryStream(bytes, false);
        using var reader = new BinaryReader(stream, Encoding.UTF8);
        // CUSA03173 01.09: little endian, int32, size_t64, instruction32,
        // OP=6, A=8, B=C=9, IEEE double. Lua 5.0 stores A in the HIGH bits.
        byte[] header = [0x1b, 0x4c, 0x75, 0x61, 0x50, 1, 4, 8, 4, 6, 8, 9, 9, 8];
        if (!reader.ReadBytes(header.Length).SequenceEqual(header))
            throw new InvalidDataException("unsupported Lua bytecode header (expected Bloodborne Lua 5.0)");
        double test = reader.ReadDouble();
        if (!double.IsFinite(test) || (long)test != 31415926)
            throw new InvalidDataException("invalid Lua number format");
        var result = new LuaSymbols(new(StringComparer.Ordinal), new(StringComparer.Ordinal), new(StringComparer.Ordinal));
        Function(reader, result, 0);
        if (stream.Position != stream.Length)
            throw new InvalidDataException("trailing Lua bytecode data");
        return result;
    }

    static int Count(BinaryReader reader, int elementSize = 1)
    {
        int count = reader.ReadInt32();
        if (count < 0 || count > (reader.BaseStream.Length - reader.BaseStream.Position) / elementSize)
            throw new InvalidDataException("invalid Lua array length");
        return count;
    }

    static void Skip(BinaryReader reader, int count)
    {
        if (count < 0 || count > reader.BaseStream.Length - reader.BaseStream.Position)
            throw new InvalidDataException("truncated Lua bytecode");
        reader.BaseStream.Position += count;
    }

    static string? String(BinaryReader reader)
    {
        ulong length = reader.ReadUInt64();
        if (length == 0) return null;
        if (length > (ulong)(reader.BaseStream.Length - reader.BaseStream.Position) || length > int.MaxValue)
            throw new InvalidDataException("invalid Lua string length");
        byte[] bytes = reader.ReadBytes((int)length);
        if (bytes[^1] != 0) throw new InvalidDataException("unterminated Lua string");
        return Encoding.UTF8.GetString(bytes, 0, bytes.Length - 1);
    }

    static void Function(BinaryReader reader, LuaSymbols symbols, int depth)
    {
        if (depth > 100) throw new InvalidDataException("excessively nested Lua bytecode");
        String(reader); // source
        reader.ReadInt32(); // line defined
        Skip(reader, 4); // upvalues, parameters, varargs, stack size
        Skip(reader, checked(Count(reader, 4) * 4)); // debug line table
        int locals = Count(reader);
        for (int i = 0; i < locals; i++) { String(reader); Skip(reader, 8); }
        int upvalues = Count(reader);
        for (int i = 0; i < upvalues; i++) String(reader);
        var constants = new string?[Count(reader)];
        for (int i = 0; i < constants.Length; i++)
        {
            switch (reader.ReadByte())
            {
                case 0: break;
                case 3: Skip(reader, 8); break;
                case 4: constants[i] = String(reader); break;
                default: throw new InvalidDataException("unsupported Lua constant type");
            }
        }
        int children = Count(reader);
        for (int i = 0; i < children; i++) Function(reader, symbols, depth + 1);
        int instructions = Count(reader, 4);
        for (int i = 0; i < instructions; i++)
        {
            uint instruction = reader.ReadUInt32();
            uint opcode = instruction & 63;
            if (opcode > 34) throw new InvalidDataException("invalid Lua 5.0 opcode");
            if (opcode is not (5 or 7)) continue; // GETGLOBAL / SETGLOBAL
            int index = (int)((instruction >> 6) & 0x3ffff);
            if (index >= constants.Length || constants[index] is not string name)
                throw new InvalidDataException("Lua global operand is not a string constant");
            (opcode == 5 ? symbols.Reads : symbols.Writes).Add(name);
            if (opcode == 7 && depth == 0) symbols.Definitions.Add(name);
        }
    }
}
