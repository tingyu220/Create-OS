from __future__ import annotations

import ctypes
from ctypes import wintypes
from pathlib import Path


FILE_ATTRIBUTE_DIRECTORY = 0x00000010
FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400

_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
_GENERIC_READ = 0x80000000
_GENERIC_WRITE = 0x40000000
_DELETE = 0x00010000
_FILE_READ_ATTRIBUTES = 0x00000080
_FILE_SHARE_READ = 0x00000001
_FILE_SHARE_WRITE = 0x00000002
_FILE_SHARE_DELETE = 0x00000004
_OPEN_EXISTING = 3
_OPEN_ALWAYS = 4
_CREATE_NEW = 1
_FILE_ATTRIBUTE_NORMAL = 0x00000080
_FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
_FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
_DUPLICATE_SAME_ACCESS = 0x00000002


class _BY_HANDLE_FILE_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("dwFileAttributes", wintypes.DWORD),
        ("ftCreationTime", wintypes.FILETIME),
        ("ftLastAccessTime", wintypes.FILETIME),
        ("ftLastWriteTime", wintypes.FILETIME),
        ("dwVolumeSerialNumber", wintypes.DWORD),
        ("nFileSizeHigh", wintypes.DWORD),
        ("nFileSizeLow", wintypes.DWORD),
        ("nNumberOfLinks", wintypes.DWORD),
        ("nFileIndexHigh", wintypes.DWORD),
        ("nFileIndexLow", wintypes.DWORD),
    ]


class _FILE_RENAME_INFO(ctypes.Structure):
    _fields_ = [
        ("ReplaceIfExists", wintypes.DWORD),
        ("RootDirectory", wintypes.HANDLE),
        ("FileNameLength", wintypes.DWORD),
        ("FileName", wintypes.WCHAR * 1),
    ]


class _FILE_DISPOSITION_INFO(ctypes.Structure):
    _fields_ = [("DeleteFile", wintypes.BOOL)]


_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_CreateFileW = _kernel32.CreateFileW
_CreateFileW.argtypes = [
    wintypes.LPCWSTR,
    wintypes.DWORD,
    wintypes.DWORD,
    ctypes.c_void_p,
    wintypes.DWORD,
    wintypes.DWORD,
    wintypes.HANDLE,
]
_CreateFileW.restype = wintypes.HANDLE
_GetFileInformationByHandle = _kernel32.GetFileInformationByHandle
_GetFileInformationByHandle.argtypes = [
    wintypes.HANDLE,
    ctypes.POINTER(_BY_HANDLE_FILE_INFORMATION),
]
_GetFileInformationByHandle.restype = wintypes.BOOL
_ReadFile = _kernel32.ReadFile
_ReadFile.argtypes = [
    wintypes.HANDLE,
    ctypes.c_void_p,
    wintypes.DWORD,
    ctypes.POINTER(wintypes.DWORD),
    ctypes.c_void_p,
]
_ReadFile.restype = wintypes.BOOL
_WriteFile = _kernel32.WriteFile
_WriteFile.argtypes = _ReadFile.argtypes
_WriteFile.restype = wintypes.BOOL
_FlushFileBuffers = _kernel32.FlushFileBuffers
_FlushFileBuffers.argtypes = [wintypes.HANDLE]
_FlushFileBuffers.restype = wintypes.BOOL
_SetFileInformationByHandle = _kernel32.SetFileInformationByHandle
_SetFileInformationByHandle.argtypes = [
    wintypes.HANDLE,
    ctypes.c_int,
    ctypes.c_void_p,
    wintypes.DWORD,
]
_SetFileInformationByHandle.restype = wintypes.BOOL
_DuplicateHandle = _kernel32.DuplicateHandle
_DuplicateHandle.argtypes = [
    wintypes.HANDLE,
    wintypes.HANDLE,
    wintypes.HANDLE,
    ctypes.POINTER(wintypes.HANDLE),
    wintypes.DWORD,
    wintypes.BOOL,
    wintypes.DWORD,
]
_DuplicateHandle.restype = wintypes.BOOL
_GetCurrentProcess = _kernel32.GetCurrentProcess
_GetCurrentProcess.restype = wintypes.HANDLE
_CloseHandle = _kernel32.CloseHandle
_CloseHandle.argtypes = [wintypes.HANDLE]
_CloseHandle.restype = wintypes.BOOL


def _extended_path(path: Path) -> str:
    value = str(path.absolute())
    if value.startswith("\\\\?\\"):
        return value
    if value.startswith("\\\\"):
        return "\\\\?\\UNC\\" + value[2:]
    return "\\\\?\\" + value


def open_file(
    path: Path,
    access: int,
    share: int,
    disposition: int,
    flags: int,
) -> int:
    handle = _CreateFileW(
        _extended_path(path),
        access,
        share,
        None,
        disposition,
        flags,
        None,
    )
    if handle == _INVALID_HANDLE_VALUE:
        code = ctypes.get_last_error()
        if code in (2, 3):
            raise FileNotFoundError(code, ctypes.FormatError(code), str(path))
        if code in (80, 183):
            raise FileExistsError(code, ctypes.FormatError(code), str(path))
        raise ctypes.WinError(code)
    return int(handle)


def open_directory(path: Path) -> int:
    return open_file(
        path,
        _GENERIC_READ,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE,
        _OPEN_EXISTING,
        _FILE_FLAG_BACKUP_SEMANTICS | _FILE_FLAG_OPEN_REPARSE_POINT,
    )


def open_regular(path: Path, *, write: bool) -> int:
    access = _GENERIC_READ | (_GENERIC_WRITE if write else 0)
    return open_file(
        path,
        access,
        _FILE_SHARE_READ,
        _OPEN_EXISTING,
        _FILE_ATTRIBUTE_NORMAL | _FILE_FLAG_OPEN_REPARSE_POINT,
    )


def create_new(path: Path) -> int:
    return open_file(
        path,
        _GENERIC_READ | _GENERIC_WRITE | _DELETE,
        _FILE_SHARE_READ,
        _CREATE_NEW,
        _FILE_ATTRIBUTE_NORMAL | _FILE_FLAG_OPEN_REPARSE_POINT,
    )


def open_metadata(path: Path) -> int:
    return open_file(
        path,
        _FILE_READ_ATTRIBUTES,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE | _FILE_SHARE_DELETE,
        _OPEN_EXISTING,
        _FILE_ATTRIBUTE_NORMAL | _FILE_FLAG_OPEN_REPARSE_POINT,
    )


def open_lock(path: Path) -> int:
    return open_file(
        path,
        _GENERIC_READ | _GENERIC_WRITE,
        _FILE_SHARE_READ | _FILE_SHARE_WRITE,
        _OPEN_ALWAYS,
        _FILE_ATTRIBUTE_NORMAL | _FILE_FLAG_OPEN_REPARSE_POINT,
    )


def information(handle: int) -> _BY_HANDLE_FILE_INFORMATION:
    info = _BY_HANDLE_FILE_INFORMATION()
    if not _GetFileInformationByHandle(handle, ctypes.byref(info)):
        raise ctypes.WinError(ctypes.get_last_error())
    return info


def read_all(handle: int) -> bytes:
    info = information(handle)
    remaining = (info.nFileSizeHigh << 32) | info.nFileSizeLow
    chunks: list[bytes] = []
    while remaining:
        requested = min(remaining, 64 * 1024)
        buffer = ctypes.create_string_buffer(requested)
        read = wintypes.DWORD()
        if not _ReadFile(handle, buffer, requested, ctypes.byref(read), None):
            raise ctypes.WinError(ctypes.get_last_error())
        if read.value == 0:
            break
        chunks.append(buffer.raw[: read.value])
        remaining -= read.value
    return b"".join(chunks)


def write_all(handle: int, payload: bytes) -> None:
    view = memoryview(payload)
    while view:
        chunk = bytes(view[: 64 * 1024])
        written = wintypes.DWORD()
        if not _WriteFile(handle, chunk, len(chunk), ctypes.byref(written), None):
            raise ctypes.WinError(ctypes.get_last_error())
        if written.value == 0:
            raise OSError("Win32 write made no progress")
        view = view[written.value :]


def flush(handle: int) -> None:
    if not _FlushFileBuffers(handle):
        raise ctypes.WinError(ctypes.get_last_error())


def rename_handle(source_handle: int, target: Path, *, replace: bool) -> None:
    encoded = _extended_path(target).encode("utf-16-le")
    size = _FILE_RENAME_INFO.FileName.offset + len(encoded) + 2
    buffer = ctypes.create_string_buffer(size)
    rename = _FILE_RENAME_INFO.from_buffer(buffer)
    rename.ReplaceIfExists = replace
    rename.RootDirectory = None
    rename.FileNameLength = len(encoded)
    ctypes.memmove(
        ctypes.addressof(buffer) + _FILE_RENAME_INFO.FileName.offset,
        encoded,
        len(encoded),
    )
    if not _SetFileInformationByHandle(source_handle, 3, buffer, size):
        raise ctypes.WinError(ctypes.get_last_error())


def mark_delete(handle: int) -> None:
    disposition = _FILE_DISPOSITION_INFO(True)
    _SetFileInformationByHandle(handle, 4, ctypes.byref(disposition), ctypes.sizeof(disposition))


def duplicate_handle(handle: int) -> int:
    process = _GetCurrentProcess()
    duplicate = wintypes.HANDLE()
    if not _DuplicateHandle(
        process,
        handle,
        process,
        ctypes.byref(duplicate),
        0,
        False,
        _DUPLICATE_SAME_ACCESS,
    ):
        raise ctypes.WinError(ctypes.get_last_error())
    return int(duplicate.value)


def close_handle(handle: int) -> None:
    _CloseHandle(handle)
