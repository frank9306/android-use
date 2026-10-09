"""OS-released per-device leases across independent MCP/CLI processes."""

import hashlib
import os
import tempfile
from pathlib import Path

from android_use.errors import AndroidUseError


class DeviceLease:
    def __init__(self, serial: str, directory: Path | None = None) -> None:
        directory = directory or Path(tempfile.gettempdir()) / "android-use-locks"
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / (hashlib.sha256(serial.encode()).hexdigest() + ".lock")
        self.file = path.open("a+b")
        self.file.seek(0, os.SEEK_END)
        if self.file.tell() == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self.file.close()
            raise AndroidUseError(
                "device_busy", "Another android-use process owns this device"
            ) from error

    def close(self) -> None:
        if self.file.closed:
            return
        self.file.seek(0)
        if os.name == "nt":
            import msvcrt

            msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        self.file.close()
