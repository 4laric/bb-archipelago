internal static class IndependentNativeStagesTests
{
    internal static void Run()
    {
        using var bothStarted = new CountdownEvent(2);
        int completed = 0;
        void Stage()
        {
            bothStarted.Signal();
            if (!bothStarted.Wait(TimeSpan.FromSeconds(5)))
                throw new Exception("map and AI stages did not overlap");
            Interlocked.Increment(ref completed);
        }
        IndependentNativeStages.Run(Stage, Stage);
        if (completed != 2) throw new Exception("stage completion was not joined");

        using var otherFinished = new ManualResetEventSlim();
        bool failed = false;
        try
        {
            IndependentNativeStages.Run(
                () => throw new InvalidDataException("map stage refused"),
                () => { Thread.Sleep(50); otherFinished.Set(); });
        }
        catch (InvalidDataException ex) when (ex.Message == "map stage refused")
        {
            failed = true;
        }
        if (!failed || !otherFinished.IsSet)
            throw new Exception("failure escaped before the other stage completed");

        try
        {
            IndependentNativeStages.Run(
                () => throw new InvalidDataException("map stage refused"),
                () => throw new InvalidDataException("AI stage refused"));
            throw new Exception("two failed stages were accepted");
        }
        catch (InvalidDataException ex) when (ex.Message == "map stage refused") { }
    }
}
