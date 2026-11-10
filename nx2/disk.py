"""Is a folder on a hard drive (a spinning disk) or on an SSD? A build reads and writes tens of gigabytes for the best part of an
hour, and an SSD makes that much faster. The answer is only ever a warning: a player may have no other drive, so the build goes
ahead on a hard drive.

spinning(path) -> True for a spinning disk, False for an SSD or flash, None when it cannot be told (a network share, an unknown
device, another operating system). Windows asks the volume for its seek penalty (IOCTL_STORAGE_QUERY_PROPERTY,
StorageDeviceSeekPenaltyProperty: a disk that seeks says so); Linux reads the kernel's queue/rotational for the device behind the
folder, through its partitions and device-mapper/RAID slaves.
"""
import os
import sys


def existing_parent(path):
    """The nearest folder above path that exists (the path's own folder may be made later, as the game folder often is)"""
    p = os.path.abspath(os.path.expanduser(path or "."))
    while not os.path.exists(p):
        up = os.path.dirname(p)
        if up == p:
            break
        p = up
    return p


def spinning(path):
    """True on a hard drive, False on an SSD, None when the drive cannot be told"""
    folder = existing_parent(path)
    try:
        if os.name == "nt":
            return _windows_spinning(folder)
        if sys.platform.startswith("linux"):
            return _linux_spinning(folder)
    except (OSError, ValueError, AttributeError, ImportError):
        return None
    return None


def _windows_spinning(path):
    """The volume's DEVICE_SEEK_PENALTY_DESCRIPTOR (kernel32's DeviceIoControl): a spinning disk incurs a seek penalty"""
    import ctypes
    from ctypes import wintypes

    root = os.path.splitdrive(path)[0]
    if not root:
        return None
    class Query(ctypes.Structure):
        _fields_ = [("PropertyId", wintypes.DWORD), ("QueryType", wintypes.DWORD), ("Additional", wintypes.DWORD)]

    class SeekPenalty(ctypes.Structure):
        _fields_ = [("Version", wintypes.DWORD), ("Size", wintypes.DWORD), ("IncursSeekPenalty", ctypes.c_ubyte)]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p,
                                     wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD,
                                         ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), ctypes.c_void_p]
    kernel32.DeviceIoControl.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    invalid = wintypes.HANDLE(-1).value
    handle = kernel32.CreateFileW("\\\\.\\" + root, 0, 0x1 | 0x2, None, 3, 0, None)   # (read + write share, OPEN_EXISTING)
    if not handle or handle == invalid:
        return None
    try:
        query, answer, returned = Query(7, 0, 0), SeekPenalty(), wintypes.DWORD()   # (StorageDeviceSeekPenaltyProperty, standard query)
        ok = kernel32.DeviceIoControl(handle, 0x002D1400, ctypes.byref(query), ctypes.sizeof(query), ctypes.byref(answer),
                                      ctypes.sizeof(answer), ctypes.byref(returned), None)
        if not ok or returned.value < ctypes.sizeof(answer):
            return None
        return bool(answer.IncursSeekPenalty)
    finally:
        kernel32.CloseHandle(handle)


def _linux_spinning(path):
    """queue/rotational of the block device behind path's file system"""
    try:
        st = os.stat(path)
    except OSError:
        return None
    return _device_rotational("/sys/dev/block/%d:%d" % (os.major(st.st_dev), os.minor(st.st_dev)))


def _device_rotational(node, depth=0):
    """The device behind sysfs's node: its slaves decide for device-mapper and RAID (any spinning one makes it slow), and a
    partition's own folder has no queue/rotational, so the disk above it is read"""
    path = os.path.realpath(node)
    if depth < 4:
        slaves = os.path.join(path, "slaves")
        try:
            names = sorted(os.listdir(slaves))
        except OSError:
            names = []
        answers = [a for a in (_device_rotational(os.path.join(slaves, n), depth + 1) for n in names) if a is not None]
        if answers:
            return any(answers)
    while True:
        try:
            with open(os.path.join(path, "queue", "rotational"), encoding="ascii") as f:
                return f.read().strip() == "1"
        except OSError:
            up = os.path.dirname(path)
            if up == path:
                return None
            path = up
