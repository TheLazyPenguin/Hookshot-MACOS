using System.Diagnostics;
using System.Globalization;

namespace HookshotBuilder;

/// A choice for this window only. Automatic leaves the build tools' inherited override and memory policy alone.
static class BuildWorkers
{
    public const string Automatic = "Automatic";

    public static IEnumerable<object> Choices(int processors)
    {
        yield return Automatic;
        for (var count = 1; count <= Math.Max(1, processors); count++) yield return count;
    }

    public static int? Selected(object? value) => value switch
    {
        string text when text == Automatic => null,
        int count when count > 0 => count,
        _ => throw new ArgumentException("Choose Automatic or a positive number of build workers."),
    };

    public static void Apply(ProcessStartInfo info, int? count)
    {
        if (count is <= 0) throw new ArgumentOutOfRangeException(nameof(count), "Build workers must be positive.");
        if (count is int selected) info.Environment["HOOKSHOT_JOBS"] = selected.ToString(CultureInfo.InvariantCulture);
    }
}

/// A choice for this window only. Automatic leaves the build tools' free-memory policy alone; a number of GB replaces it.
static class BuildMemory
{
    public const string Automatic = BuildWorkers.Automatic;
    const int Step = 4;

    public static IEnumerable<object> Choices(int totalGb)
    {
        yield return Automatic;
        for (var gb = Step; gb < totalGb + Step; gb += Step) yield return gb;
    }

    // (Windows reports a little less than the installed memory: 31.6 GB on a 32 GB PC)
    public static int TotalGb() => (int)Math.Round(GC.GetGCMemoryInfo().TotalAvailableMemoryBytes / (double)(1L << 30));

    /// The menu's item for a saved choice: Automatic when none was saved or this PC's menu no longer offers it
    public static object Saved(IEnumerable<object> choices, int? gb) => gb is int g && choices.Contains(g) ? g : Automatic;

    public static int? Selected(object? value) => value switch
    {
        string text when text == Automatic => null,
        int gb when gb > 0 => gb,
        _ => throw new ArgumentException("Choose Automatic or a positive amount of build memory."),
    };

    public static void Apply(ProcessStartInfo info, int? gb)
    {
        if (gb is <= 0) throw new ArgumentOutOfRangeException(nameof(gb), "Build memory must be positive.");
        if (gb is int selected) info.Environment["HOOKSHOT_MEM_LIMIT_GB"] = selected.ToString(CultureInfo.InvariantCulture);
    }
}
