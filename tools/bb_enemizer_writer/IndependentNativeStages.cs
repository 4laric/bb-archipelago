using System.Runtime.ExceptionServices;

internal static class IndependentNativeStages
{
    // Both jobs read the finalized plan and original inputs. Their output
    // directories are disjoint; publication and cleanup follow only after both
    // tasks have completed, including when one fails.
    internal static void Run(Action maps, Action ai)
    {
        Task mapTask = Task.Run(maps);
        Task aiTask = Task.Run(ai);
        try
        {
            Task.WaitAll(mapTask, aiTask);
        }
        catch (AggregateException)
        {
            // Preserve the old map-then-AI failure precedence without
            // discarding either task before its stage directory is cleaned.
            ExceptionDispatchInfo.Capture((mapTask.Exception ?? aiTask.Exception)!.InnerException!).Throw();
            throw;
        }
    }
}
