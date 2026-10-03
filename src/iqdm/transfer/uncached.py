"""Read a file past the PC's file cache (DECISIONS.md D55).

Windows keeps recently written file data in a cache that belongs to the system. A
hash read straight after a copy may then come from the PC's memory instead of the
NAS. read_chunks(path, uncached=True) opens the file with FILE_FLAG_NO_BUFFERING,
so each read goes to the file's storage.

Unbuffered reads must use a buffer, a length and a file offset that are multiples of
the volume's sector size. The buffer here comes from an anonymous mmap, which is
page-aligned, and each read asks for a whole number of ALIGN_BYTES. The last read of
a file returns fewer bytes; that is allowed.

Off Windows, or with uncached=False, the file is read with an ordinary open.
"""

import ctypes
import mmap
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ALIGN_BYTES = 64 * 1024  # a multiple of every sector size in use (512 B, 4 KiB)

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 0x00000001
OPEN_EXISTING = 3
FILE_FLAG_NO_BUFFERING = 0x20000000
FILE_FLAG_SEQUENTIAL_SCAN = 0x08000000


def aligned(n: int) -> int:
    """n rounded up to a whole number of ALIGN_BYTES, at least one."""
    return max(1, -(-n // ALIGN_BYTES)) * ALIGN_BYTES


def _buffered(path: Path, chunk_bytes: int) -> Iterator[bytes]:
    with path.open("rb") as f:
        while chunk := f.read(chunk_bytes):
            yield chunk


def _last_error(path: Path) -> OSError:
    """The Windows error of the last failed call, as an OSError that names the file."""
    error = ctypes.get_last_error()
    return OSError(None, ctypes.FormatError(error).strip(), str(path), error)


def _kernel32() -> "ctypes.WinDLL":
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    k32.CreateFileW.restype = wintypes.HANDLE
    k32.ReadFile.argtypes = [
        wintypes.HANDLE,
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.c_void_p,
    ]
    k32.ReadFile.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    return k32


@contextmanager
def _open_unbuffered(path: Path) -> Iterator[int]:
    """A Windows file handle opened with FILE_FLAG_NO_BUFFERING. Raises OSError."""
    k32 = _kernel32()
    handle = k32.CreateFileW(
        str(path),
        GENERIC_READ,
        FILE_SHARE_READ,
        None,
        OPEN_EXISTING,
        FILE_FLAG_NO_BUFFERING | FILE_FLAG_SEQUENTIAL_SCAN,
        None,
    )
    if handle is None or handle == ctypes.c_void_p(-1).value:  # INVALID_HANDLE_VALUE
        raise _last_error(path)
    try:
        yield handle
    finally:
        k32.CloseHandle(handle)


def _unbuffered(path: Path, chunk_bytes: int) -> Iterator[bytes]:
    from ctypes import wintypes

    k32 = _kernel32()
    size = aligned(chunk_bytes)
    with _open_unbuffered(path) as handle:
        buf = mmap.mmap(-1, size)
        try:
            address = ctypes.addressof(ctypes.c_char.from_buffer(buf))
            while True:
                n = wintypes.DWORD(0)
                if not k32.ReadFile(handle, address, size, ctypes.byref(n), None):
                    raise _last_error(path)
                if n.value == 0:
                    return
                yield buf[: n.value]
        finally:
            buf.close()


def read_chunks(path: Path, chunk_bytes: int, *, uncached: bool = False) -> Iterator[bytes]:
    """The file's bytes in chunks. uncached=True reads past the Windows file cache.

    Use it in a `with contextlib.closing(...)` block or read it to the end, so the
    file is closed when the caller stops early.
    """
    if uncached and sys.platform == "win32":
        return _unbuffered(path, chunk_bytes)
    return _buffered(path, chunk_bytes)
