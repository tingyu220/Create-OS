from __future__ import annotations

import ctypes
import errno
import os
import secrets
import stat
import sys
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO

if os.name == "nt":
    import msvcrt

    from creative_os.domains.contract_record_win32 import (
        FILE_ATTRIBUTE_DIRECTORY as _FILE_ATTRIBUTE_DIRECTORY,
        FILE_ATTRIBUTE_REPARSE_POINT as _FILE_ATTRIBUTE_REPARSE_POINT,
        close_handle as _win_close_handle,
        create_new as _win_create_new_file,
        duplicate_handle as _win_duplicate_handle,
        flush as _win_flush,
        information as _win_handle_information,
        mark_delete as _win_mark_delete,
        open_directory as _win_open_directory,
        open_lock as _win_open_lock,
        open_metadata as _win_open_metadata,
        open_regular as _win_open_file,
        read_all as _win_read_all,
        rename_handle as _win_rename_handle,
        write_all as _win_write_all,
    )
else:
    import fcntl


_ATOMIC_TEMP_PREFIX = ".record-"
_ATOMIC_TEMP_SUFFIX = ".tmp"


class TrustedStoreFilesystem:
    """Handle-anchored filesystem boundary for authoritative records."""

    def __init__(
        self,
        project_root: Path,
        directories: tuple[Path, ...],
        lock_path: Path,
        *,
        error_type: type[ValueError],
        conflict_type: type[ValueError],
        hook: Callable[[str, Path], None],
    ) -> None:
        self.project_root = project_root
        self.lock_path = lock_path
        self._error_type = error_type
        self._conflict_type = conflict_type
        self._hook = hook
        self._directory_handles: dict[Path, int] = {}
        self._directory_identities: dict[Path, tuple[int, int]] = {}
        self._lock_handle: int | None = None
        try:
            self._open_root()
            for directory in directories:
                self._open_or_create_chain(directory)
            self.validate_all()
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        lock_handle, self._lock_handle = self._lock_handle, None
        if lock_handle is not None:
            self._close_handle(lock_handle)
        for path in sorted(self._directory_handles, key=lambda value: len(value.parts), reverse=True):
            self._close_handle(self._directory_handles[path])
        self._directory_handles.clear()
        self._directory_identities.clear()

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    def validate_all(self) -> None:
        for directory in sorted(self._directory_handles, key=lambda value: len(value.parts)):
            self.validate_directory(directory)

    def validate_directory(self, directory: Path) -> None:
        handle = self._directory_handle(directory)
        expected = self._directory_identities[directory]
        actual = self._handle_identity(handle)
        if actual != expected:
            self._fail("trusted contract record directory handle changed")
        try:
            named = self._named_directory_identity(directory)
        except (FileNotFoundError, NotADirectoryError, OSError) as error:
            self._fail("trusted contract record directory path changed", error)
        if named != expected:
            self._fail("trusted contract record directory path changed")

    def exists_regular(self, path: Path) -> bool:
        self.validate_directory(path.parent)
        try:
            handle = self._open_regular_file(path, write=False)
        except FileNotFoundError:
            self.validate_directory(path.parent)
            return False
        try:
            self._validate_named_file(path, self._handle_identity(handle))
            return True
        finally:
            self._close_handle(handle)
            self.validate_directory(path.parent)

    def read_bytes(self, path: Path) -> bytes:
        self.validate_directory(path.parent)
        self._hook("before_file_open", path)
        handle = self._open_regular_file(path, write=False)
        try:
            identity = self._handle_identity(handle)
            self._hook("after_file_open", path)
            payload = self._read_handle(handle)
            self._validate_regular_handle(handle, "contract record file")
            self._validate_named_file(path, identity)
            return payload
        finally:
            self._close_handle(handle)
            self.validate_directory(path.parent)

    def list_names(self, directory: Path) -> tuple[str, ...]:
        self.validate_directory(directory)
        self._hook("before_scan", directory)
        handle = self._directory_handle(directory)
        if os.name == "nt":
            names = tuple(sorted(os.listdir(_extended_path(directory))))
        else:
            names = tuple(sorted(os.listdir(handle)))
        self._hook("after_scan", directory)
        if os.name == "nt":
            current_names = tuple(sorted(os.listdir(_extended_path(directory))))
        else:
            current_names = tuple(sorted(os.listdir(handle)))
        if current_names != names:
            self._fail("contract record directory changed during scan")
        self.validate_directory(directory)
        return names

    def require_regular_entry(self, path: Path, name: str) -> None:
        self.validate_directory(path.parent)
        handle = _win_open_metadata(path) if os.name == "nt" else self._open_regular_file(
            path, write=False
        )
        try:
            identity = self._handle_identity(handle)
            self._validate_regular_handle(handle, name)
            self._validate_named_file(path, identity)
        finally:
            self._close_handle(handle)
            self.validate_directory(path.parent)

    def atomic_write_bytes(
        self,
        path: Path,
        payload: bytes,
        *,
        expected: bytes | None,
    ) -> None:
        self.validate_all()
        directory_handle = self._directory_handle(path.parent)
        self._hook("before_temp_create", path)
        temporary_name, temporary_handle = self._create_temporary(path.parent)
        published = False
        try:
            temporary_identity = self._handle_identity(temporary_handle)
            self._write_handle(temporary_handle, payload)
            self._flush_handle(temporary_handle)
            self._hook("before_atomic_publish", path)
            self._validate_named_file(path.parent / temporary_name, temporary_identity)
            if expected is None:
                if self.exists_regular(path):
                    self._conflict(f"append-only contract record conflict: {path.stem}")
            else:
                current = self.read_bytes(path)
                if current != expected:
                    self._conflict(f"append-only contract record conflict: {path.stem}")
            self._rename_temporary(
                path.parent,
                directory_handle,
                temporary_name,
                temporary_handle,
                path.name,
                replace=expected is not None,
            )
            published = True
            self._validate_named_file(path, temporary_identity)
            self._fsync_directory_handle(directory_handle)
        finally:
            if not published:
                self._discard_temporary(path.parent, temporary_name, temporary_handle)
            self._close_handle(temporary_handle)
            self.validate_all()

    @contextmanager
    def exclusive_lock(self) -> Iterator[None]:
        if os.name == "nt":
            with self._windows_exclusive_lock():
                yield
        else:
            with self._posix_exclusive_lock():
                yield

    def _open_root(self) -> None:
        try:
            if os.name == "nt":
                handle = _win_open_directory(self.project_root)
            else:
                flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
                handle = os.open(self.project_root, flags)
            self._remember_directory(self.project_root, handle)
        except OSError as error:
            self._fail("trusted project root cannot be opened safely", error)

    def _open_or_create_chain(self, target: Path) -> None:
        try:
            relative = target.relative_to(self.project_root)
        except ValueError as error:
            self._fail("contract record path escapes trusted project root", error)
        current = self.project_root
        for part in relative.parts:
            parent = current
            current = current / part
            if current in self._directory_handles:
                continue
            try:
                handle = self._open_child_directory(parent, part)
            except FileNotFoundError:
                self._create_child_directory(parent, part)
                handle = self._open_child_directory(parent, part)
            self._remember_directory(current, handle)

    def _open_child_directory(self, parent: Path, name: str) -> int:
        if os.name == "nt":
            return _win_open_directory(parent / name)
        flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
        return os.open(name, flags, dir_fd=self._directory_handle(parent))

    def _create_child_directory(self, parent: Path, name: str) -> None:
        try:
            if os.name == "nt":
                os.mkdir(_extended_path(parent / name))
            else:
                os.mkdir(name, dir_fd=self._directory_handle(parent))
        except FileExistsError:
            pass
        except OSError as error:
            self._fail("contract record directory creation failed", error)

    def _remember_directory(self, path: Path, handle: int) -> None:
        try:
            self._validate_directory_handle(handle)
            self._directory_handles[path] = handle
            self._directory_identities[path] = self._handle_identity(handle)
        except Exception:
            self._close_handle(handle)
            raise

    def _directory_handle(self, path: Path) -> int:
        try:
            return self._directory_handles[path]
        except KeyError as error:
            self._fail("untrusted contract record directory", error)

    def _named_directory_identity(self, path: Path) -> tuple[int, int]:
        if path == self.project_root:
            if os.name == "nt":
                handle = _win_open_directory(path)
            else:
                info = os.stat(path, follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode):
                    raise NotADirectoryError(path)
                return info.st_dev, info.st_ino
        else:
            parent = path.parent
            if os.name == "nt":
                handle = _win_open_directory(path)
            else:
                info = os.stat(path.name, dir_fd=self._directory_handle(parent), follow_symlinks=False)
                if not stat.S_ISDIR(info.st_mode):
                    raise NotADirectoryError(path)
                return info.st_dev, info.st_ino
        try:
            self._validate_directory_handle(handle)
            return self._handle_identity(handle)
        finally:
            self._close_handle(handle)

    def _open_regular_file(self, path: Path, *, write: bool) -> int:
        try:
            if os.name == "nt":
                handle = _win_open_file(path, write=write)
            else:
                flags = (os.O_RDWR if write else os.O_RDONLY) | getattr(os, "O_NOFOLLOW", 0)
                handle = os.open(path.name, flags, dir_fd=self._directory_handle(path.parent))
            self._validate_regular_handle(handle, "contract record file")
            return handle
        except FileNotFoundError:
            raise
        except OSError as error:
            self._fail(f"contract record file cannot be opened safely: {path.name}", error)

    def _validate_regular_handle(self, handle: int, name: str) -> None:
        if os.name == "nt":
            info = _win_handle_information(handle)
            if info.dwFileAttributes & (_FILE_ATTRIBUTE_DIRECTORY | _FILE_ATTRIBUTE_REPARSE_POINT):
                self._fail(f"{name} must be a non-reparse regular file")
            if info.nNumberOfLinks != 1:
                self._fail(f"{name} must not have hard-link aliases")
        else:
            info = os.fstat(handle)
            if not stat.S_ISREG(info.st_mode):
                self._fail(f"{name} must be a regular file")
            if info.st_nlink != 1:
                self._fail(f"{name} must not have hard-link aliases")

    def _validate_directory_handle(self, handle: int) -> None:
        if os.name == "nt":
            info = _win_handle_information(handle)
            if not info.dwFileAttributes & _FILE_ATTRIBUTE_DIRECTORY:
                self._fail("trusted contract record component must be a directory")
            if info.dwFileAttributes & _FILE_ATTRIBUTE_REPARSE_POINT:
                self._fail("trusted contract record directory cannot be a reparse point")
        else:
            info = os.fstat(handle)
            if not stat.S_ISDIR(info.st_mode):
                self._fail("trusted contract record component must be a directory")

    def _validate_named_file(self, path: Path, expected: tuple[int, int]) -> None:
        try:
            if os.name == "nt":
                handle = _win_open_metadata(path)
                try:
                    self._validate_regular_handle(handle, "contract record file")
                    actual = self._handle_identity(handle)
                finally:
                    self._close_handle(handle)
            else:
                info = os.stat(
                    path.name,
                    dir_fd=self._directory_handle(path.parent),
                    follow_symlinks=False,
                )
                if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
                    self._fail("contract record file identity is unsafe")
                actual = (info.st_dev, info.st_ino)
        except (FileNotFoundError, OSError) as error:
            self._fail("contract record file identity changed", error)
        if actual != expected:
            self._fail("contract record file identity changed")

    def _handle_identity(self, handle: int) -> tuple[int, int]:
        if os.name == "nt":
            info = _win_handle_information(handle)
            return info.dwVolumeSerialNumber, (info.nFileIndexHigh << 32) | info.nFileIndexLow
        info = os.fstat(handle)
        return info.st_dev, info.st_ino

    def _read_handle(self, handle: int) -> bytes:
        if os.name == "nt":
            return _win_read_all(handle)
        os.lseek(handle, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        while chunk := os.read(handle, 64 * 1024):
            chunks.append(chunk)
        return b"".join(chunks)

    def _write_handle(self, handle: int, payload: bytes) -> None:
        if os.name == "nt":
            _win_write_all(handle, payload)
            return
        view = memoryview(payload)
        while view:
            written = os.write(handle, view)
            view = view[written:]

    def _flush_handle(self, handle: int) -> None:
        if os.name == "nt":
            _win_flush(handle)
        else:
            os.fsync(handle)

    def _create_temporary(self, directory: Path) -> tuple[str, int]:
        for _ in range(128):
            name = f"{_ATOMIC_TEMP_PREFIX}{secrets.token_hex(4)}{_ATOMIC_TEMP_SUFFIX}"
            try:
                if os.name == "nt":
                    handle = _win_create_new_file(directory / name)
                else:
                    flags = (
                        os.O_RDWR
                        | os.O_CREAT
                        | os.O_EXCL
                        | getattr(os, "O_NOFOLLOW", 0)
                    )
                    handle = os.open(name, flags, 0o600, dir_fd=self._directory_handle(directory))
                self._validate_regular_handle(handle, "atomic temporary file")
                return name, handle
            except FileExistsError:
                continue
        self._fail("cannot allocate atomic temporary file")

    def _rename_temporary(
        self,
        directory: Path,
        directory_handle: int,
        temporary_name: str,
        temporary_handle: int,
        target_name: str,
        *,
        replace: bool,
    ) -> None:
        try:
            if os.name == "nt":
                _win_rename_handle(
                    temporary_handle,
                    directory / target_name,
                    replace=replace,
                )
            elif replace:
                os.replace(
                    temporary_name,
                    target_name,
                    src_dir_fd=directory_handle,
                    dst_dir_fd=directory_handle,
                )
            else:
                _posix_publish_noreplace(directory_handle, temporary_name, target_name)
        except FileExistsError as error:
            self._conflict(
                f"append-only contract record conflict: {Path(target_name).stem}", error
            )
        except OSError as error:
            if getattr(error, "winerror", None) in (80, 183):
                self._conflict(
                    f"append-only contract record conflict: {Path(target_name).stem}", error
                )
            self._fail("atomic contract record publication failed", error)

    def _discard_temporary(self, directory: Path, name: str, handle: int) -> None:
        try:
            expected = self._handle_identity(handle)
            self._validate_named_file(directory / name, expected)
            if os.name == "nt":
                _win_mark_delete(handle)
            else:
                os.unlink(name, dir_fd=self._directory_handle(directory))
        except Exception:
            pass

    def _fsync_directory_handle(self, handle: int) -> None:
        if os.name != "nt":
            os.fsync(handle)

    @contextmanager
    def _windows_exclusive_lock(self) -> Iterator[None]:
        self.validate_all()
        if self._lock_handle is None:
            self._hook("before_lock_open", self.lock_path)
            try:
                handle = _win_open_lock(self.lock_path)
                self._validate_regular_handle(handle, "contract record lock")
                if _win_handle_information(handle).nFileSizeLow == 0:
                    _win_write_all(handle, b"\0")
                    self._flush_handle(handle)
                self._hook("after_lock_open", self.lock_path)
                self._lock_handle = handle
            except self._error_type:
                if "handle" in locals():
                    self._close_handle(handle)
                raise
            except OSError as error:
                if "handle" in locals():
                    self._close_handle(handle)
                self._fail("contract record lock must be a non-reparse regular file", error)
        duplicate = _win_duplicate_handle(self._lock_handle)
        descriptor = msvcrt.open_osfhandle(duplicate, os.O_RDWR | getattr(os, "O_BINARY", 0))
        stream: BinaryIO = os.fdopen(descriptor, "r+b", closefd=True)
        try:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_LOCK, 1)
            try:
                self._validate_named_file(
                    self.lock_path,
                    self._handle_identity(self._lock_handle),
                )
                self.validate_all()
                yield
                self.validate_all()
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            stream.close()

    @contextmanager
    def _posix_exclusive_lock(self) -> Iterator[None]:
        root_handle = self._directory_handle(self.project_root)
        fcntl.flock(root_handle, fcntl.LOCK_EX)
        try:
            if self._lock_handle is None:
                self._hook("before_lock_open", self.lock_path)
                flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
                handle = os.open(
                    self.lock_path.name,
                    flags,
                    0o600,
                    dir_fd=self._directory_handle(self.lock_path.parent),
                )
                self._validate_regular_handle(handle, "contract record lock")
                if os.fstat(handle).st_size == 0:
                    os.write(handle, b"\0")
                    os.fsync(handle)
                self._hook("after_lock_open", self.lock_path)
                self._lock_handle = handle
            fcntl.flock(self._lock_handle, fcntl.LOCK_EX)
            try:
                self._validate_named_file(
                    self.lock_path,
                    self._handle_identity(self._lock_handle),
                )
                self.validate_all()
                yield
                self.validate_all()
            finally:
                fcntl.flock(self._lock_handle, fcntl.LOCK_UN)
        finally:
            fcntl.flock(root_handle, fcntl.LOCK_UN)

    def _close_handle(self, handle: int) -> None:
        if os.name == "nt":
            _win_close_handle(handle)
        else:
            os.close(handle)

    def _fail(self, message: str, cause: BaseException | None = None):
        error = self._error_type(message)
        if cause is None:
            raise error
        raise error from cause

    def _conflict(self, message: str, cause: BaseException | None = None):
        error = self._conflict_type(message)
        if cause is None:
            raise error
        raise error from cause


def _extended_path(path: Path) -> str:
    value = str(path.absolute())
    if os.name != "nt" or value.startswith("\\\\?\\"):
        return value
    return "\\\\?\\" + value


def _posix_publish_noreplace(directory_handle: int, source: str, target: str) -> None:
    if sys.platform.startswith("linux"):
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = getattr(libc, "renameat2", None)
        if renameat2 is not None:
            renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
            renameat2.restype = ctypes.c_int
            result = renameat2(
                directory_handle,
                os.fsencode(source),
                directory_handle,
                os.fsencode(target),
                1,
            )
            if result == 0:
                return
            code = ctypes.get_errno()
            if code == errno.EEXIST:
                raise FileExistsError(code, os.strerror(code), target)
            if code not in (errno.ENOSYS, errno.EINVAL):
                raise OSError(code, os.strerror(code), target)
    os.link(
        source,
        target,
        src_dir_fd=directory_handle,
        dst_dir_fd=directory_handle,
        follow_symlinks=False,
    )
    os.unlink(source, dir_fd=directory_handle)
