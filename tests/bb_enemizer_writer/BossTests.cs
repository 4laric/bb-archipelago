using SoulsFormats;

internal static class BossTests
{
    internal static void Run()
    {
        int assertions = 0;
        void Need(bool value) { assertions++; if (!value) throw new Exception("boss merge invariant failed"); }
        void Refused(Action action) {
            try { action(); } catch (InvalidDataException) { assertions++; return; }
            throw new Exception("boss merge accepted invalid input");
        }
        var original = new EMEVD(EMEVD.Game.Bloodborne);
        foreach (long id in BossCanary.ChangedEvents.Concat(new[] {BossCanary.CompletionEvent, 999L})) {
            var e = new EMEVD.Event(id);
            e.Instructions.Add(new EMEVD.Instruction(1000, 4, new byte[] {0,0,0,0}));
            original.Events.Add(e);
        }
        var compiled = EMEVD.Read(original.Write());
        foreach (var e in compiled.Events) e.Instructions[0].ArgData[0] = 1;
        var pins = BossCanary.ChangedEvents.ToDictionary(id => id,
            id => BossCanary.Fingerprint(compiled.Events.Single(e => e.ID == id)));
        var merged = EMEVD.Read(BossCanary.Merge(original, compiled, pins));
        foreach (var e in original.Events) {
            Need(e.Instructions[0].ArgData[0] == 0);
            Need(merged.Events.Single(x => x.ID == e.ID).Instructions[0].ArgData[0]
                == (BossCanary.ChangedEvents.Contains(e.ID) ? 1 : 0));
        }
        var badPins = new Dictionary<long,string>(pins) {[BossCanary.ChangedEvents[0]] = "wrong"};
        Refused(() => BossCanary.Merge(original, compiled, badPins));
        badPins.Remove(BossCanary.ChangedEvents[0]);
        Refused(() => BossCanary.Merge(original, compiled, badPins));
        compiled.Events.Add(compiled.Events[0]);
        Refused(() => BossCanary.Merge(original, compiled, pins));
        compiled.Events.RemoveAt(compiled.Events.Count - 1);
        compiled.Events.RemoveAt(0);
        Refused(() => BossCanary.Merge(original, compiled, pins));
        Console.WriteLine($"PASS: {assertions} boss event merge assertions");
    }
}
