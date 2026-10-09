"""Adapter to the pinned uiautomator2 production contract."""

import base64
import re
from importlib.resources import files
from typing import Any

import adbutils
import uiautomator2 as u2
from uiautomator2.core import _jsonrpc_call

from android_use.errors import AndroidUseError
from android_use.hierarchy import Node


class SingleAttemptDevice(u2.Device):
    """Disable upstream restart-and-replay; timed-out actions are never repeated.

    This small private adapter is intentionally pinned to uiautomator2 3.7.0.
    The contract is checked in tests and on the actual device.
    """

    def jsonrpc_call(self, method: str, params: Any = None, timeout: float = 10) -> Any:
        return _jsonrpc_call(
            self.adb_device, self._device_server_port, method, params, timeout, False
        )


class AndroidDevice:
    def __init__(self, serial: str) -> None:
        self.device = SingleAttemptDevice(adbutils.adb.device(serial=serial))

    def info(self) -> dict:
        info = self.device.info
        # Some OEM dumpsys implementations report a background task as app_current.
        # UI Automator's currentPackageName describes the observed active window.
        return {
            "width": info["displayWidth"],
            "height": info["displayHeight"],
            "rotation": info["displayRotation"],
            "screen_on": info["screenOn"],
            "package": info["currentPackageName"],
            "activity": None,
        }

    def hierarchy(self) -> str:
        return self.device.dump_hierarchy(compressed=False)

    def close(self) -> None:
        # Complete owned service shutdown before the controller releases its lease.
        # Otherwise a new process can attach while the previous atexit kills it.
        if self.device._process is not None:
            self.device.stop_uiautomator(wait=True)

    def screenshot(self):
        return self.device.screenshot()

    def tap(self, x: int, y: int) -> None:
        # Device.click() in the pinned SDK discards the server's boolean result.
        # Use the same single-attempt RPC directly so a rejected click is visible.
        if self.device.jsonrpc.click(x, y) is not True:
            raise RuntimeError("Device rejected click")

    def press(self, key: str) -> None:
        # OEM UI Automator pressBack acknowledgements can return false even when
        # navigation succeeds. Choose ADB key injection up front, never replay.
        aliases = {
            "recent": "APP_SWITCH",
            "delete": "DEL",
            "left": "DPAD_LEFT",
            "right": "DPAD_RIGHT",
            "up": "DPAD_UP",
            "down": "DPAD_DOWN",
        }
        keycode = "KEYCODE_" + aliases.get(key, key.upper())
        response = self.device.shell(["input", "keyevent", keycode], timeout=10)
        if response.exit_code != 0:
            raise RuntimeError("ADB key injection failed")

    def swipe(self, sx: int, sy: int, ex: int, ey: int, duration: float) -> None:
        if self.device.swipe(sx, sy, ex, ey, duration=duration) is False:
            raise RuntimeError("Device rejected swipe")

    def launch_app(self, package: str, activity: str | None) -> None:
        self.device.app_start(package, activity=activity, stop=False, wait=False)

    def type_text(self, node: Node, text: str, method: str) -> dict:
        filters = {"className": node.class_name}
        if node.resource_id:
            filters["resourceId"] = node.resource_id
        else:
            filters["focused"] = True
        if node.package_name:
            filters["packageName"] = node.package_name
        target = self.device(**filters)
        if target.count != 1:
            raise AndroidUseError(
                "ambiguous_selector",
                "Input must resolve to one stable resource ID or focused element",
            )
        if method == "accessibility":
            target.set_text(text, timeout=0)
            return {"input_method_restored": True}
        original = self.device.current_ime()
        if not original or original == "null":
            raise AndroidUseError(
                "input_method_unavailable", "Cannot determine the original input method"
            )
        helper = "com.github.uiautomator/.AdbKeyboard"
        enabled_before = self.device.shell(
            ["settings", "get", "secure", "enabled_input_methods"], timeout=10
        ).output
        was_enabled = helper in [item.split(";")[0] for item in enabled_before.strip().split(":")]
        if not self.device.is_input_ime_installed():
            # Never use the upstream uninstall-and-retry installation fallback.
            apk = files("uiautomator2").joinpath("assets/app-uiautomator.apk")
            self.device.adb_device.install(str(apk), nolaunch=True, uninstall=False)
        try:
            target.click(timeout=0)
            if self.device(**(filters | {"focused": True})).count != 1:
                raise AndroidUseError(
                    "input_focus_failed",
                    "Input did not gain focus; observe before retrying",
                    dispatched=True,
                    outcome="unknown",
                )
            self.device.set_input_ime()
            target.set_text("", timeout=0)
            encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
            response = self.device.shell(
                ["am", "broadcast", "-a", "ADB_KEYBOARD_INPUT_TEXT", "--es", "text", encoded],
                timeout=10,
            )
            if response.exit_code != 0 or not re.search(r"result=-1\b", response.output):
                raise RuntimeError("Input broadcast was not acknowledged")
        finally:
            try:
                restored = self.device.shell(["ime", "set", original], timeout=10)
                if restored.exit_code != 0 or self.device.current_ime() != original:
                    raise RuntimeError("Cannot restore original IME")
                if not was_enabled and original != helper:
                    disabled = self.device.shell(["ime", "disable", helper], timeout=10)
                    if disabled.exit_code != 0:
                        raise RuntimeError("Cannot restore IME enabled state")
            except Exception as error:
                raise AndroidUseError(
                    "input_method_restore_failed",
                    "Input may have executed; restore the keyboard manually before retrying",
                    outcome="unknown",
                ) from error
        return {"input_method_restored": True}


class SystemBackend:
    def devices(self) -> list[dict]:
        return [{"serial": item.serial, "state": item.state} for item in adbutils.adb.list()]

    def connect(self, serial: str) -> AndroidDevice:
        return AndroidDevice(serial)
