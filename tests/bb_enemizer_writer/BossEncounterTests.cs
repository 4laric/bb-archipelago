using SoulsFormats;
using System.Text.Json.Nodes;

internal static class BossEncounterTests
{
    internal static void Run()
    {
        int assertions = 0;
        void Need(bool value) { assertions++; if (!value) throw new Exception("boss encounter merge invariant failed"); }
        void Refused(Action action) {
            try { action(); } catch (InvalidDataException) { assertions++; return; }
            throw new Exception("boss encounter merge accepted invalid input");
        }
        var original = new EMEVD(EMEVD.Game.Bloodborne);
        foreach (long id in new[] {0L, 10L, 30L, 99L}) {
            var e = new EMEVD.Event(id);
            e.Instructions.Add(new EMEVD.Instruction(1000, 4, new byte[] {0, 0, 0, 0}));
            original.Events.Add(e);
        }
        var compiled = EMEVD.Read(original.Write());
        compiled.Events.Single(e => e.ID == 0).Instructions[0].ArgData[0] = 1;
        var encounter = new BossEncounter.Encounter("m24_01_00_00.emevd.dcx", new string('a', 64), [0],
            new Dictionary<long, string> { [0] = BossEncounter.Fingerprint(compiled.Events.Single(e => e.ID == 0)) }, [30]);
        var merged = EMEVD.Read(BossEncounter.Merge(original, compiled, encounter));
        Need(merged.Events.Select(e => e.ID).SequenceEqual(original.Events.Select(e => e.ID)));
        Need(merged.Events.Single(e => e.ID == 0).Instructions[0].ArgData[0] == 1);
        Need(merged.Events.Where(e => e.ID != 0).All(e => e.Instructions[0].ArgData[0] == 0));
        Need(BossEncounter.Fingerprint(merged.Events.Single(e => e.ID == 30))
             == BossEncounter.Fingerprint(original.Events.Single(e => e.ID == 30)));
        var compiledWithAdded = EMEVD.Read(compiled.Write());
        var addedEvent = new EMEVD.Event(77); addedEvent.Instructions.Add(new EMEVD.Instruction(1000, 4, new byte[] {7, 0, 0, 0}));
        compiledWithAdded.Events.Add(addedEvent);
        var addedContract = encounter with { AddedEventIds = [77], CompiledEventFingerprints = new Dictionary<long, string> {
            [0] = encounter.CompiledEventFingerprints[0], [77] = BossEncounter.Fingerprint(addedEvent) }};
        var mergedAdded = EMEVD.Read(BossEncounter.Merge(original, compiledWithAdded, addedContract));
        Need(mergedAdded.Events.Select(e => e.ID).SequenceEqual(new[] {0L, 10L, 30L, 99L, 77L}));
        Need(BossEncounter.Fingerprint(mergedAdded.Events.Last()) == addedContract.CompiledEventFingerprints[77]);

        var terminalOriginal = EMEVD.Read(original.Write());
        byte[] deathArgs = new byte[12]; BitConverter.GetBytes(2410800).CopyTo(deathArgs, 4); deathArgs[8] = 1;
        terminalOriginal.Events.Single(e => e.ID == 30).Instructions.Insert(0, new EMEVD.Instruction(4, 0, deathArgs));
        var terminalCompiled = EMEVD.Read(terminalOriginal.Write());
        terminalCompiled.Events.Add(addedEvent);
        byte[] flagArgs = new byte[8]; flagArgs[1] = 1; BitConverter.GetBytes(77u).CopyTo(flagArgs, 4);
        terminalCompiled.Events.Single(e => e.ID == 30).Instructions[0] = new EMEVD.Instruction(3, 0, flagArgs);
        var terminalContract = encounter with { ChangedEventIds = [30], AddedEventIds = [77],
            TerminalPredicates = [new(30, 2410800, 77)], CompiledEventFingerprints = new Dictionary<long, string> {
                [30] = BossEncounter.Fingerprint(terminalCompiled.Events.Single(e => e.ID == 30)),
                [77] = BossEncounter.Fingerprint(addedEvent) }};
        var terminalResult = EMEVD.Read(BossEncounter.Merge(terminalOriginal, terminalCompiled, terminalContract));
        Need(terminalResult.Events.Single(e => e.ID == 30).Instructions[0].Bank == 3);
        Need(terminalResult.Events.Single(e => e.ID == 30).Instructions[1].ArgData.SequenceEqual(
             terminalOriginal.Events.Single(e => e.ID == 30).Instructions[1].ArgData));
        Refused(() => BossEncounter.Merge(terminalOriginal, terminalCompiled,
            terminalContract with { TerminalPredicates = [new(30, 2410801, 77)] }));
        Refused(() => BossEncounter.Merge(terminalOriginal, terminalCompiled,
            terminalContract with { TerminalPredicates = [new(30, 2410800, 78)] }));
        terminalCompiled.Events.Single(e => e.ID == 30).Instructions[1].ArgData[0] = 9;
        terminalContract.CompiledEventFingerprints[30] = BossEncounter.Fingerprint(terminalCompiled.Events.Single(e => e.ID == 30));
        Refused(() => BossEncounter.Merge(terminalOriginal, terminalCompiled, terminalContract));

        Refused(() => BossEncounter.Merge(original, compiled, encounter with {
            CompiledEventFingerprints = new Dictionary<long, string> { [10] = new string('b', 64) }}));
        Refused(() => BossEncounter.Merge(original, compiled, encounter with { ChangedEventIds = [0, 30],
            CompiledEventFingerprints = new Dictionary<long, string> {
                [0] = encounter.CompiledEventFingerprints[0], [30] = BossEncounter.Fingerprint(compiled.Events.Single(e => e.ID == 30)) }}));
        compiled.Events.Single(e => e.ID == 10).Instructions[0].ArgData[0] = 2;
        var isolated = EMEVD.Read(BossEncounter.Merge(original, compiled, encounter));
        Need(isolated.Events.Single(e => e.ID == 0).Instructions[0].ArgData[0] == 1);
        Need(isolated.Events.Single(e => e.ID == 10).Instructions[0].ArgData[0] == 0);
        compiled.Events.Single(e => e.ID == 10).Instructions[0].ArgData[0] = 0;
        compiled.Events.Add(new EMEVD.Event(101));
        Refused(() => BossEncounter.Merge(original, compiled, encounter));

        var unscaled = JsonNode.Parse("""
            {"swaps":[{"logical_key":"m24_01_00_00:c5000_0000"}],"scaling":{"enabled":false,"mechanism":"inferred_static_npc_clone_sp_effect",
            "change_count":0,"changes":[],"skip_count":1,
            "skips":[{"logical_key":"m24_01_00_00:c5000_0000","reason":"unknown source or destination tier"}]}}
            """)!.AsObject();
        Need(!BossEncounter.ScalingEnabled(unscaled));
        var playerDisabled = unscaled.DeepClone().AsObject();
        playerDisabled["options"] = JsonNode.Parse("""{"normalize_scaling":false}""");
        playerDisabled["scaling"]!["skips"]![0]!["reason"] = "disabled by player";
        Need(!BossEncounter.ScalingEnabled(playerDisabled));
        var undeclared = playerDisabled.DeepClone().AsObject();
        undeclared["options"]!["normalize_scaling"] = true;
        Refused(() => BossEncounter.ScalingEnabled(undeclared));
        var enabledWithPlayerSkip = playerDisabled.DeepClone().AsObject();
        enabledWithPlayerSkip["scaling"]!["enabled"] = true;
        Refused(() => BossEncounter.ScalingEnabled(enabledWithPlayerSkip));
        var randomKey = unscaled.DeepClone().AsObject();
        randomKey["scaling"]!["skips"]![0]!["logical_key"] = "m99_00_00_00:invented";
        Refused(() => BossEncounter.ScalingEnabled(randomKey));
        var duplicate = unscaled.DeepClone().AsObject();
        duplicate["scaling"]!["skips"]!.AsArray().Add(duplicate["scaling"]!["skips"]![0]!.DeepClone());
        duplicate["scaling"]!["skip_count"] = 2;
        Refused(() => BossEncounter.ScalingEnabled(duplicate));
        var missing = unscaled.DeepClone().AsObject();
        missing["scaling"]!["skips"] = new JsonArray();
        missing["scaling"]!["skip_count"] = 0;
        Refused(() => BossEncounter.ScalingEnabled(missing));
        Console.WriteLine($"PASS: {assertions} boss encounter merge assertions");
    }
}
