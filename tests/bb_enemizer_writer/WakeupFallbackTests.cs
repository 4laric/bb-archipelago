using System.Buffers.Binary;
using SoulsFormats;

internal static class WakeupFallbackTests
{
    static byte[] Args(params int[] values) {
        var bytes = new byte[values.Length * 4];
        for (int i = 0; i < values.Length; i++) BinaryPrimitives.WriteInt32LittleEndian(bytes.AsSpan(i * 4, 4), values[i]);
        return bytes;
    }
    internal static void Run()
    {
        int assertions = 0;
        void Need(bool value, string message = "wakeup fallback invariant failed") { assertions++; if (!value) throw new Exception(message); }
        void Refused(Action action) { try { action(); } catch (InvalidDataException) { assertions++; return; } throw new Exception("unsupported native wakeup witness accepted"); }

        EMEVD Fixture(int flag = 1, int entity = 2410148) {
            var file = new EMEVD(EMEVD.Game.Bloodborne);
            var constructor = new EMEVD.Event(0);
            constructor.Instructions.Add(new EMEVD.Instruction(3, 4, [9,8,7]));
            constructor.Instructions.Add(new EMEVD.Instruction(2000, 0, Args(8,12415130,entity,9000,9061,52410270,112499,112400,flag)) { Layer = 0x20 });
            constructor.Instructions.Add(new EMEVD.Instruction(2000, 0, Args(9,12415130,2410149,9000,9061,52410270,112499,112400,1)));
            file.Events.Add(constructor);
            var callee = new EMEVD.Event(12415130);
            callee.Instructions.Add(new EMEVD.Instruction(1003, 2, new byte[8]));
            for (int i = 1; i < 9; i++) callee.Instructions.Add(new EMEVD.Instruction(2003, i, BitConverter.GetBytes(i)));
            callee.Instructions.Add(new EMEVD.Instruction(1001, 3, Args(0,60)) { Layer = 0x40 });
            file.Events.Add(callee);
            file.Events.Add(new EMEVD.Event(77) { Instructions = { new EMEVD.Instruction(2,3,[1,2]) } });
            return EMEVD.Read(file.Write());
        }

        var row = new WakeupFallback.Row("m24_01_00_00:c1120_0009", 2410148, "m24_01_00_00", 12415130);
        var parsed = WakeupFallback.ValidatePlan("{\"swaps\":[{\"logical_key\":\"m24_01_00_00:c1120_0009\"}],\"wakeup_fallbacks\":[{\"logical_key\":\"m24_01_00_00:c1120_0009\",\"entity_id\":2410148,\"map\":\"m24_01_00_00\",\"event_id\":12415130}]} ");
        Need(parsed.Count == 1 && parsed[0] == row, "plan schema row not parsed exactly");
        Refused(() => WakeupFallback.ValidatePlan("{\"swaps\":[],\"wakeup_fallbacks\":[{\"logical_key\":\"m24_01_00_00:c1120_0009\",\"entity_id\":2410148,\"map\":\"m24_01_00_00\",\"event_id\":12415130}]}"));
        Refused(() => WakeupFallback.ValidatePlan("{\"swaps\":[{\"logical_key\":\"m24_01_00_00:c1120_0009\"}],\"wakeup_fallbacks\":[{\"logical_key\":\"m24_01_00_00:c1120_0009\",\"entity_id\":2410149,\"map\":\"m24_01_00_00\",\"event_id\":12415130}]}"));
        var original = Fixture();
        string calleeBefore = BossCanary.Fingerprint(original.Events.Single(e => e.ID == 12415130));
        var untouched = original.Events.Single(e => e.ID == 77).Instructions[0].ArgData.ToArray();
        WakeupFallback.Apply(original, [row], calleeBefore);
        var result = EMEVD.Read(original.Write());
        var constructor = result.Events.Single(e => e.ID == 0);
        Need(constructor.Instructions.Count == 3);
        Need(constructor.Instructions[0].Bank == 3 && constructor.Instructions[0].ID == 4 && constructor.Instructions[0].ArgData.SequenceEqual(new byte[] {9,8,7}));
        Need(constructor.Instructions[1].Bank == 1001 && constructor.Instructions[1].ID == 3 && constructor.Instructions[1].ArgData.SequenceEqual(new byte[8]));
        Need(constructor.Instructions[1].Layer == 0x20, "replacement must preserve constructor layer");
        Need(constructor.Instructions[2].Bank == 2000 && constructor.Instructions[2].ArgData.SequenceEqual(Args(9,12415130,2410149,9000,9061,52410270,112499,112400,1)), "other initializer changed");
        Need(BossCanary.Fingerprint(result.Events.Single(e => e.ID == 12415130)) == calleeBefore, "callee changed");
        Need(result.Events.Single(e => e.ID == 77).Instructions[0].ArgData.SequenceEqual(untouched), "unrelated event changed");

        var wrongBody = Fixture();
        Refused(() => WakeupFallback.Apply(wrongBody, [row], "wrong"));
        var wrongInitializer = Fixture(flag: 0);
        string validBody = BossCanary.Fingerprint(wrongInitializer.Events.Single(e => e.ID == 12415130));
        Refused(() => WakeupFallback.Apply(wrongInitializer, [row], validBody));
        var missing = Fixture(entity: 2410149);
        validBody = BossCanary.Fingerprint(missing.Events.Single(e => e.ID == 12415130));
        Refused(() => WakeupFallback.Apply(missing, [row], validBody));
        var duplicate = Fixture();
        duplicate.Events.Single(e => e.ID == 0).Instructions.Add(duplicate.Events.Single(e => e.ID == 0).Instructions[1]);
        validBody = BossCanary.Fingerprint(duplicate.Events.Single(e => e.ID == 12415130));
        Refused(() => WakeupFallback.Apply(duplicate, [row], validBody));
        var parameterized = Fixture();
        parameterized.Events.Single(e => e.ID == 0).Parameters.Add(new EMEVD.Parameter(1, 0, 0, 4));
        validBody = BossCanary.Fingerprint(parameterized.Events.Single(e => e.ID == 12415130));
        Refused(() => WakeupFallback.Apply(parameterized, [row], validBody));
        Console.WriteLine($"PASS: {assertions} native wakeup fallback assertions");
    }
}
