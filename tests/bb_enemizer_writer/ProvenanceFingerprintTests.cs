using SoulsFormats;

internal static class ProvenanceFingerprintTests
{
    internal static void Run()
    {
        const string map = "m99_00_00_00";
        var msb = new MSBB();
        msb.Models.Objects.Add(new MSBB.Model.Object { Name = "o1000", SibPath = "" });
        var pins = new[] {
            BossActorTransplant.Fingerprint(map, new MSBB.Part.Enemy { Name = "actor", ModelName = "c1000", EntityID = 100 }),
            BossActorTransplant.GeneratorFingerprint(map, new MSBB.Event.Generator { Name = "generator", EntityID = 101 }),
            BossRegionTransplant.Fingerprint(map, new MSBB.Region { Name = "region", EntityID = 102 }),
            BossObjectTransplant.Fingerprint(map, msb, new MSBB.Part.Object { Name = "object", ModelName = "o1000", EntityID = 103 }),
            BossSfxTransplant.Fingerprint(map, new MSBB.Event.SFX { Name = "sfx", EntityID = 104 }),
        };
        // Fixed synthetic Windows witnesses must also match on Linux. Comparing
        // two freshly generated pins would miss host-dependent JSON formatting.
        string[] expected = [
            "905a2d2dd3b348b4285257b8a0ee2ecf8c5efd77ae9d8f7d4be61d7bc4bd6639",
            "5c2732996dca0a929cee71a47afe0febc90864a102e83cba53d7623757e7553b",
            "fc8af3273256ac238c90023efd316181a844165ecf265abb9ef3704168fe164e",
            "4ebc330983438362f014e7e939a10461d5b6890ed8c66880a1ca504b74565c31",
            "370f1d92f454e92814f4dc5f8061bbf091e6f42e8b6d55d84cd239f5626a10e1",
        ];
        for (int i = 0; i < pins.Length; i++)
            if (pins[i] != expected[i]) throw new Exception($"provenance fixture {i} hash drifted");
        Console.WriteLine("PASS: 5 platform-independent provenance hash witnesses");
    }
}
