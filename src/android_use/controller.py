"""Device operations, validation and observation lifetime; no transport concerns."""

import inspect
import math
import os
import re
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from uuid import uuid4

from PIL import Image
from pydantic import ValidationError

from android_use.backend import SystemBackend
from android_use.errors import AndroidUseError
from android_use.hierarchy import Hierarchy, Selector
from android_use.locking import DeviceLease
from android_use.models import BatchStep


@dataclass
class Snapshot:
    created: float
    info: dict
    hierarchy: Hierarchy
    image_size: tuple[int, int] | None


class AndroidController:
    def __init__(
        self,
        serial: str | None = None,
        *,
        backend=None,
        lock_dir: Path | None = None,
        observation_ttl: float = 60,
    ) -> None:
        self.serial = serial or os.getenv("ANDROID_SERIAL")
        self.backend = backend or SystemBackend()
        self.lock_dir = lock_dir
        self.observation_ttl = observation_ttl
        self._lock = threading.RLock()
        self._cancel_event = threading.Event()
        self._lease = None
        self._active = None
        self._connections = []
        self._snapshots: OrderedDict[str, Snapshot] = OrderedDict()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def cancel(self) -> None:
        """Stop queued steps and polling; an in-flight device command cannot be undone."""
        self._cancel_event.set()

    def reset_cancel(self) -> None:
        self._cancel_event.clear()

    def _check_cancel(self, dispatched: bool = False) -> None:
        if self._cancel_event.is_set():
            raise AndroidUseError(
                "cancelled",
                "Operation cancelled; no further actions dispatched",
                dispatched=dispatched,
                outcome="unknown" if dispatched else "not_executed",
            )

    def close(self) -> None:
        with self._lock:
            try:
                for connection in self._connections:
                    if hasattr(connection, "close"):
                        connection.close()
            finally:
                self._connections.clear()
                self._active = None
                self._snapshots.clear()
                if self._lease:
                    self._lease.close()
                    self._lease = None

    def devices(self) -> dict:
        try:
            return {"devices": self.backend.devices(), "selected_serial": self.serial}
        except Exception as error:
            raise AndroidUseError(
                "adb_unavailable",
                "Cannot query ADB; run adb start-server",
                cause=type(error).__name__,
            ) from error

    def _device(self):
        records = self.devices()["devices"]
        if self.serial is None:
            available = [record for record in records if record["state"] == "device"]
            if len(available) != 1:
                raise AndroidUseError(
                    "device_selection_required",
                    "Exactly one authorized device is required; set ANDROID_SERIAL",
                    devices=records,
                )
            self.serial = available[0]["serial"]
        state = next(
            (record["state"] for record in records if record["serial"] == self.serial),
            "disconnected",
        )
        if state != "device":
            self._snapshots.clear()
            self._active = None
            raise AndroidUseError(
                "device_unavailable", "Selected device is not authorized and online", state=state
            )
        if not self._lease:
            self._lease = DeviceLease(self.serial, self.lock_dir)
        if not self._active:
            self._active = self.backend.connect(self.serial)
            self._connections.append(self._active)
        return self._active

    @contextmanager
    def _operation(self, *, mutation: bool = False):
        with self._lock:
            try:
                self._check_cancel()
                yield self._device()
            except AndroidUseError:
                raise
            except ValidationError as error:
                raise AndroidUseError(
                    "invalid_argument", "Arguments violate the tool schema"
                ) from error
            except Exception as error:
                self._active = None
                self._snapshots.clear()
                raise AndroidUseError(
                    "action_uncertain" if mutation else "device_error",
                    "Device operation failed; observe before retrying"
                    if mutation
                    else "Device read failed; check the connection",
                    cause=type(error).__name__,
                    outcome="unknown" if mutation else "not_executed",
                ) from error
            finally:
                if mutation:
                    self._snapshots.clear()

    @staticmethod
    def _same_view(left: dict, right: dict) -> bool:
        return all(left[key] == right[key] for key in ("width", "height", "rotation", "package"))

    def _read(self, device) -> tuple[dict, Hierarchy]:
        before = device.info()
        if not before["screen_on"]:
            raise AndroidUseError("screen_off", "Turn on and unlock the screen manually")
        hierarchy = Hierarchy.parse(device.hierarchy())
        after = device.info()
        if not self._same_view(before, after) or hierarchy.rotation != after["rotation"]:
            raise AndroidUseError(
                "unstable_screen", "Screen changed during observation; observe again"
            )
        return after, hierarchy

    def observe(
        self, screenshot: bool = True, max_nodes: int = 150, max_image_edge: int = 1280
    ) -> dict:
        if type(screenshot) is not bool:
            raise AndroidUseError("invalid_argument", "screenshot must be a boolean")
        if type(max_nodes) is not int or not 1 <= max_nodes <= 1000:
            raise AndroidUseError(
                "invalid_argument", "max_nodes must be an integer between 1 and 1000"
            )
        if type(max_image_edge) is not int or not 320 <= max_image_edge <= 4096:
            raise AndroidUseError("invalid_argument", "max_image_edge must be between 320 and 4096")
        with self._operation() as device:
            for attempt in range(3):
                self._check_cancel()
                try:
                    return self._capture(device, screenshot, max_nodes, max_image_edge)
                except AndroidUseError as error:
                    if error.code != "unstable_screen" or attempt == 2:
                        raise
                    time.sleep(0.15)
        raise AssertionError("Unreachable observation attempt")

    def _capture(self, device, screenshot: bool, max_nodes: int, max_image_edge: int) -> dict:
        info, hierarchy = self._read(device)
        nodes, truncated = hierarchy.compact(max_nodes)
        result = {
            "serial": self.serial,
            "observation_id": uuid4().hex,
            "observed_at": datetime.now(UTC).isoformat(),
            "screen": info,
            "nodes": nodes,
            "truncated": truncated,
            "screenshot": None,
        }
        image_size = None
        if screenshot:
            try:
                image = device.screenshot().convert("RGB")
                if image.size != (info["width"], info["height"]):
                    raise ValueError("Screenshot dimensions differ from UI Automator display")
                image.thumbnail((max_image_edge, max_image_edge), Image.Resampling.LANCZOS)
                output = BytesIO()
                image.save(output, format="JPEG", quality=80)
                result["_image"] = output.getvalue()
                result["screenshot"] = {
                    "width": image.width,
                    "height": image.height,
                    "mime_type": "image/jpeg",
                    "scale_x": info["width"] / image.width,
                    "scale_y": info["height"] / image.height,
                }
                image_size = image.size
            except Exception as error:
                result["screenshot_error"] = {
                    "code": "screenshot_unavailable",
                    "cause": type(error).__name__,
                    "message": "Screenshot unavailable; the window may be protected",
                }
        final_info, final_hierarchy = self._read(device)
        if (
            not self._same_view(info, final_info)
            or hierarchy.fingerprint != final_hierarchy.fingerprint
        ):
            raise AndroidUseError(
                "unstable_screen",
                "Screen changed during capture; wait for the transition to finish",
            )
        self._snapshots[result["observation_id"]] = Snapshot(
            time.monotonic(), info, hierarchy, image_size
        )
        while len(self._snapshots) > 32:
            self._snapshots.popitem(last=False)
        return result

    def ready(self) -> dict:
        with self._lock:
            observation = self.observe(screenshot=True, max_nodes=1)
            return {
                "ready": True,
                "serial": self.serial,
                "screen": observation["screen"],
                "hierarchy_available": bool(
                    self._snapshots[observation["observation_id"]].hierarchy.nodes
                ),
                "screenshot_available": observation["screenshot"] is not None,
                "screenshot_error": observation.get("screenshot_error"),
            }

    def find(self, selector: Selector | dict, max_matches: int = 50) -> dict:
        if type(max_matches) is not int or not 1 <= max_matches <= 200:
            raise AndroidUseError("invalid_argument", "max_matches must be between 1 and 200")
        with self._operation() as device:
            _, hierarchy = self._read(device)
            matches = hierarchy.find(Selector.model_validate(selector))
            return {
                "match_count": len(matches),
                "matches": [node.as_dict() for node in matches[:max_matches]],
                "truncated": len(matches) > max_matches,
            }

    def _snapshot(self, observation_id: str | None, info: dict, hierarchy: Hierarchy) -> Snapshot:
        if not isinstance(observation_id, str):
            raise AndroidUseError("stale_observation", "A valid observation_id is required")
        snapshot = self._snapshots.get(observation_id)
        if snapshot is None or time.monotonic() - snapshot.created > self.observation_ttl:
            raise AndroidUseError(
                "stale_observation", "Observation is missing or expired; observe again"
            )
        if (
            not self._same_view(snapshot.info, info)
            or snapshot.hierarchy.fingerprint != hierarchy.fingerprint
        ):
            raise AndroidUseError(
                "stale_observation", "Screen content, app or rotation changed; observe again"
            )
        return snapshot

    @staticmethod
    def _point(x, y, width: int, height: int) -> tuple[int, int]:
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in (x, y)):
            raise AndroidUseError("invalid_argument", "Coordinates must be finite numbers")
        if not 0 <= x < width or not 0 <= y < height:
            raise AndroidUseError("invalid_argument", "Coordinates are outside the screen")
        return int(x), int(y)

    def tap(
        self,
        selector: Selector | dict | None = None,
        x: float | None = None,
        y: float | None = None,
        observation_id: str | None = None,
        coordinate_space: str = "native",
        node_id: str | None = None,
    ) -> dict:
        with self._operation(mutation=True) as device:
            info, hierarchy = self._read(device)
            modes = sum((selector is not None, node_id is not None, x is not None or y is not None))
            if modes != 1:
                raise AndroidUseError(
                    "invalid_argument", "Provide exactly one of selector, node_id or x/y"
                )
            if selector is not None:
                node = hierarchy.resolve(Selector.model_validate(selector))
            elif node_id is not None:
                snapshot = self._snapshot(observation_id, info, hierarchy)
                node = next((item for item in snapshot.hierarchy.nodes if item.id == node_id), None)
                if node is None:
                    raise AndroidUseError("not_found", "Node does not belong to this observation")
            else:
                snapshot = self._snapshot(observation_id, info, hierarchy)
                if coordinate_space == "screenshot":
                    if snapshot.image_size is None:
                        raise AndroidUseError("invalid_argument", "Observation has no screenshot")
                    image_x, image_y = self._point(x, y, *snapshot.image_size)
                    x = image_x * info["width"] / snapshot.image_size[0]
                    y = image_y * info["height"] / snapshot.image_size[1]
                elif coordinate_space != "native":
                    raise AndroidUseError(
                        "invalid_argument", "coordinate_space must be native or screenshot"
                    )
                node = None
            if node:
                if not node.enabled:
                    raise AndroidUseError("element_disabled", "Target element is disabled")
                left, top, right, bottom = node.bounds
                if right <= left or bottom <= top:
                    raise AndroidUseError("not_visible", "Target element has no visible bounds")
                x, y = (left + right) / 2, (top + bottom) / 2
            point = self._point(x, y, info["width"], info["height"])
            device.tap(*point)
            self._snapshots.clear()
            return {
                "action": "tap",
                "dispatched": True,
                "verified": False,
                "native_point": list(point),
            }

    def press(self, key: str) -> dict:
        if not isinstance(key, str) or key not in {
            "back",
            "home",
            "recent",
            "enter",
            "delete",
            "search",
            "menu",
            "left",
            "right",
            "up",
            "down",
            "volume_up",
            "volume_down",
        }:
            raise AndroidUseError("invalid_argument", "Unsupported key")
        with self._operation(mutation=True) as device:
            device.press(key)
            self._snapshots.clear()
            return {"action": "press", "dispatched": True, "verified": False, "key": key}

    def swipe(
        self,
        direction: str | None = None,
        sx: float | None = None,
        sy: float | None = None,
        ex: float | None = None,
        ey: float | None = None,
        duration: float = 0.3,
        observation_id: str | None = None,
        coordinate_space: str = "native",
        bounds: list[int] | None = None,
    ) -> dict:
        if (
            type(duration) not in (int, float)
            or not math.isfinite(duration)
            or not 0.1 <= duration <= 2
        ):
            raise AndroidUseError("invalid_argument", "duration must be between 0.1 and 2 seconds")
        with self._operation(mutation=True) as device:
            info, hierarchy = self._read(device)
            width, height = info["width"], info["height"]
            if direction is not None:
                if (
                    not isinstance(direction, str)
                    or direction not in {"up", "down", "left", "right"}
                    or any(value is not None for value in (sx, sy, ex, ey))
                ):
                    raise AndroidUseError(
                        "invalid_argument", "Provide a direction or explicit coordinates"
                    )
                left, top, right, bottom = 0, 0, width, height
                if bounds is not None:
                    self._snapshot(observation_id, info, hierarchy)
                    if (
                        not isinstance(bounds, list)
                        or len(bounds) != 4
                        or any(type(value) is not int for value in bounds)
                    ):
                        raise AndroidUseError(
                            "invalid_argument", "bounds must contain four native integers"
                        )
                    left, top, right, bottom = bounds
                    if not 0 <= left < right <= width or not 0 <= top < bottom <= height:
                        raise AndroidUseError("invalid_argument", "Invalid swipe bounds")
                mid_x, mid_y = (left + right) / 2, (top + bottom) / 2
                low_x, high_x = left + (right - left) * 0.2, left + (right - left) * 0.8
                low_y, high_y = top + (bottom - top) * 0.2, top + (bottom - top) * 0.8
                points = {
                    "up": (mid_x, high_y, mid_x, low_y),
                    "down": (mid_x, low_y, mid_x, high_y),
                    "left": (high_x, mid_y, low_x, mid_y),
                    "right": (low_x, mid_y, high_x, mid_y),
                }
                sx, sy, ex, ey = points[direction]
            else:
                if bounds is not None:
                    raise AndroidUseError("invalid_argument", "bounds requires a direction")
                snapshot = self._snapshot(observation_id, info, hierarchy)
                if coordinate_space == "screenshot":
                    if snapshot.image_size is None:
                        raise AndroidUseError("invalid_argument", "Observation has no screenshot")
                    sx, sy = self._point(sx, sy, *snapshot.image_size)
                    ex, ey = self._point(ex, ey, *snapshot.image_size)
                    sx, ex = (
                        sx * width / snapshot.image_size[0],
                        ex * width / snapshot.image_size[0],
                    )
                    sy, ey = (
                        sy * height / snapshot.image_size[1],
                        ey * height / snapshot.image_size[1],
                    )
                elif coordinate_space != "native":
                    raise AndroidUseError(
                        "invalid_argument", "coordinate_space must be native or screenshot"
                    )
            start, end = self._point(sx, sy, width, height), self._point(ex, ey, width, height)
            device.swipe(*start, *end, duration)
            return {
                "action": "swipe",
                "dispatched": True,
                "verified": False,
                "native_start": list(start),
                "native_end": list(end),
            }

    def wait(self, selector: Selector | dict, timeout: float = 10, present: bool = True) -> dict:
        if (
            type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or not 0 <= timeout <= 30
        ):
            raise AndroidUseError("invalid_argument", "timeout must be between 0 and 30 seconds")
        if type(present) is not bool:
            raise AndroidUseError("invalid_argument", "present must be a boolean")
        with self._operation() as device:
            selector = Selector.model_validate(selector)
            deadline = time.monotonic() + timeout
            while True:
                self._check_cancel()
                _, hierarchy = self._read(device)
                matches = hierarchy.find(selector)
                if bool(matches) == present:
                    return {
                        "matched": True,
                        "present": present,
                        "match_count": len(matches),
                        "matches": [node.as_dict() for node in matches[:20]],
                    }
                if time.monotonic() >= deadline:
                    raise AndroidUseError(
                        "wait_timeout",
                        "Target state did not appear before timeout",
                        timeout=timeout,
                    )
                time.sleep(min(0.25, max(0, deadline - time.monotonic())))

    def launch_app(self, package: str, activity: str | None = None, timeout: float = 10) -> dict:
        if not isinstance(package, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z][A-Za-z0-9_]*)+", package
        ):
            raise AndroidUseError("invalid_argument", "Invalid Android package name")
        if activity is not None and (
            not isinstance(activity, str) or not re.fullmatch(r"[A-Za-z0-9_.$]+", activity)
        ):
            raise AndroidUseError("invalid_argument", "Invalid Android activity name")
        if (
            type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or not 0 <= timeout <= 30
        ):
            raise AndroidUseError("invalid_argument", "timeout must be between 0 and 30 seconds")
        with self._operation(mutation=True) as device:
            device.launch_app(package, activity)
            deadline = time.monotonic() + timeout
            while True:
                self._check_cancel(dispatched=True)
                info = device.info()
                if info["package"] == package:
                    return {
                        "action": "launch_app",
                        "package": package,
                        "dispatched": True,
                        "verified": True,
                    }
                if time.monotonic() >= deadline:
                    raise AndroidUseError(
                        "verification_failed",
                        "App launch was dispatched but target package did not become active",
                        dispatched=True,
                        outcome="unknown",
                    )
                time.sleep(0.25)

    def type_text(
        self,
        text: str,
        selector: Selector | dict | None = None,
        clear: bool = True,
        verify: bool = True,
        method: str = "accessibility",
    ) -> dict:
        if not isinstance(text, str) or len(text) > 4096:
            raise AndroidUseError("invalid_argument", "text must contain at most 4096 characters")
        if (
            type(clear) is not bool
            or type(verify) is not bool
            or not isinstance(method, str)
            or method not in {"accessibility", "ime"}
        ):
            raise AndroidUseError("invalid_argument", "Invalid clear, verify or input method")
        with self._operation(mutation=True) as device:
            _, hierarchy = self._read(device)
            target = hierarchy.resolve(
                Selector.model_validate(selector)
                if selector is not None
                else Selector(focused=True)
            )
            if target.password:
                raise AndroidUseError("protected_input", "Password fields require manual input")
            if not target.enabled or not target.class_name.endswith(
                ("EditText", "AutoCompleteTextView")
            ):
                raise AndroidUseError("not_editable", "Target must be an enabled native text input")
            value = text if clear else target.text + text
            if len(value) > 4096:
                raise AndroidUseError("invalid_argument", "Resulting input exceeds 4096 characters")
            restored = device.type_text(target, value, method)
            result = {
                "action": "type_text",
                "dispatched": True,
                "verified": False,
                "characters": len(value),
                "method": method,
                **restored,
            }
            if verify:
                stable = (
                    Selector(resource_id=target.resource_id, class_name=target.class_name)
                    if target.resource_id
                    else Selector(focused=True, class_name=target.class_name)
                )
                deadline = time.monotonic() + 3
                while True:
                    self._check_cancel(dispatched=True)
                    _, current = self._read(device)
                    matches = current.find(stable)
                    if len(matches) == 1 and matches[0].text == value:
                        result["verified"] = True
                        break
                    if time.monotonic() >= deadline:
                        raise AndroidUseError(
                            "verification_failed",
                            "Text was dispatched but readback mismatched; observe before retrying",
                            dispatched=True,
                            outcome="unknown",
                        )
                    time.sleep(0.2)
            return result

    def batch(self, steps: list[BatchStep | dict]) -> dict:
        if not isinstance(steps, list) or not 1 <= len(steps) <= 20:
            raise AndroidUseError("invalid_argument", "Batch requires 1 to 20 steps")
        try:
            parsed = [BatchStep.model_validate(step) for step in steps]
            for step in parsed:
                method = getattr(self, step.action)
                inspect.signature(method).bind(**step.params)
        except (ValidationError, TypeError, AttributeError) as error:
            raise AndroidUseError(
                "invalid_argument", "Invalid batch action or arguments; no steps dispatched"
            ) from error
        completed = []
        with self._lock:
            for index, step in enumerate(parsed):
                try:
                    result = getattr(self, step.action)(**step.params)
                    completed.append({"index": index, "action": step.action, "result": result})
                except AndroidUseError as error:
                    return {
                        "ok": False,
                        "failed_index": index,
                        "completed": completed,
                        "error": error.as_dict(),
                        "remaining_steps_executed": False,
                    }
        return {"ok": True, "completed": completed}
