using System.IO;
using System.Runtime.InteropServices;
using Microsoft.Win32.SafeHandles;

namespace HookshotBuilder;

/// Whether a folder is on a hard drive (a spinning disk) or an SSD: a build reads and writes tens of gigabytes, and an SSD makes
/// that much faster. The answer is a warning only (the player may have no other drive), never a stop.
static class Disk
{
    /// True on a hard drive, false on an SSD, null when the drive cannot be told (a network share, an unknown volume)
    public static bool? Spinning(string path)
    {
        try
        {
            var root = Path.GetPathRoot(Path.GetFullPath(path));
            if (string.IsNullOrEmpty(root)) return null;
            using var volume = CreateFile(@"\\.\" + root.TrimEnd('\\'), 0, FileShare.ReadWrite, IntPtr.Zero, FileMode.Open,
                                          FileOptions.None, IntPtr.Zero);
            if (volume.IsInvalid) return null;
            var query = new StoragePropertyQuery { PropertyId = SeekPenalty, QueryType = 0 };
            var answer = new DeviceSeekPenaltyDescriptor();
            // (a spinning disk says it incurs a seek penalty; an SSD says it does not)
            if (!DeviceIoControl(volume, QueryProperty, ref query, Marshal.SizeOf<StoragePropertyQuery>(), ref answer,
                                 Marshal.SizeOf<DeviceSeekPenaltyDescriptor>(), out _, IntPtr.Zero))
                return null;
            return answer.IncursSeekPenalty;
        }
        catch (Exception e) when (e is IOException or UnauthorizedAccessException or ArgumentException) { return null; }
    }

    const uint QueryProperty = 0x002D1400;   // (IOCTL_STORAGE_QUERY_PROPERTY)
    const uint SeekPenalty = 7;              // (StorageDeviceSeekPenaltyProperty)

    [StructLayout(LayoutKind.Sequential)]
    struct StoragePropertyQuery   // (STORAGE_PROPERTY_QUERY: AdditionalParameters[1], padded to a DWORD)
    {
        public uint PropertyId, QueryType, Additional;
    }

    [StructLayout(LayoutKind.Sequential)]
    struct DeviceSeekPenaltyDescriptor
    {
        public uint Version, Size;
        [MarshalAs(UnmanagedType.U1)] public bool IncursSeekPenalty;
    }

    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    static extern SafeFileHandle CreateFile(string name, uint access, FileShare share, IntPtr security, FileMode mode,
                                            FileOptions flags, IntPtr template);

    [DllImport("kernel32.dll", SetLastError = true)]
    static extern bool DeviceIoControl(SafeFileHandle device, uint code, ref StoragePropertyQuery input, int inputSize,
                                      ref DeviceSeekPenaltyDescriptor output, int outputSize, out uint returned, IntPtr overlapped);
}
