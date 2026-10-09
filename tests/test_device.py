"""Actual MCP stdio → uiautomator2 → USB → isolated Android fixture."""

import base64
import json
import os
import shutil
import subprocess
import sys
from datetime import timedelta
from io import BytesIO
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import ImageContent
from PIL import Image

PACKAGE = "com.androiduse.fixture"


def adb(serial, *args):
    executable = shutil.which("adb")
    if executable is None:
        pytest.fail("ADB must be available on PATH for the real-device test")
    return subprocess.run(
        [executable, "-s", serial, *args],
        check=True,
        capture_output=True,
        encoding="utf-8",
        timeout=30,
    ).stdout.strip()


@pytest.mark.device
async def test_real_device_mcp_workflow(device_serial, request):
    assert adb(device_serial, "shell", "pm", "path", PACKAGE).startswith("package:"), (
        "Install the fixture APK first"
    )
    # The production launch tool intentionally preserves existing app state.
    # Reset only our ephemeral fixture so repeated acceptance runs start at Row 1.
    adb(device_serial, "shell", "am", "force-stop", PACKAGE)
    original_ime = adb(device_serial, "shell", "settings", "get", "secure", "default_input_method")
    original_rotation = adb(device_serial, "shell", "settings", "get", "system", "user_rotation")
    original_auto = adb(
        device_serial, "shell", "settings", "get", "system", "accelerometer_rotation"
    )
    environment = {
        **os.environ,
        "PYTHONIOENCODING": "utf-8",
        "ANDROID_SERIAL": device_serial,
    }
    restore_file = Path("artifacts/device-settings-restore.json")
    if restore_file.exists():
        pytest.fail("Recover the previous test using artifacts/device-settings-restore.json first")
    restore_file.parent.mkdir(exist_ok=True)
    restore_file.write_text(
        json.dumps(
            {
                "serial": device_serial,
                "user_rotation": original_rotation,
                "accelerometer_rotation": original_auto,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    parameters = StdioServerParameters(
        command=sys.executable,
        args=["-m", "android_use.server", "--serial", device_serial],
        env=environment,
    )
    plugin_root = request.config.getoption("--plugin-root")
    if plugin_root:
        launch = json.loads((Path(plugin_root) / ".mcp.json").read_text(encoding="utf-8"))[
            "mcpServers"
        ]["android-use"]
        parameters = StdioServerParameters(
            command=launch["command"],
            args=launch["args"],
            cwd=str(Path(plugin_root) / launch["cwd"]),
            env=environment,
        )
    evidence = {"transport": "MCP stdio / USB ADB", "fixture": PACKAGE, "checks": []}
    try:
        async with stdio_client(parameters) as (reader, writer):
            async with ClientSession(
                reader, writer, read_timeout_seconds=timedelta(seconds=45)
            ) as session:
                await session.initialize()

                async def call(name, arguments=None, error=None):
                    result = await session.call_tool(name, arguments or {})
                    assert result.content[0].text.startswith("{"), result.content[0].text
                    payload = json.loads(result.content[0].text)
                    if error:
                        assert result.isError is True, payload
                        assert payload["error"]["code"] == error, payload
                    else:
                        assert result.isError is False, payload
                    evidence["checks"].append(
                        {"tool": name, "expected_error": error, "passed": True}
                    )
                    return payload.get("data"), result

                tools = (await session.list_tools()).tools
                assert len(tools) >= 11
                devices, _ = await call("android_devices")
                assert any(
                    item["serial"] == device_serial and item["state"] == "device"
                    for item in devices["devices"]
                )
                await call("android_launch_app", {"package": PACKAGE, "activity": ".MainActivity"})
                await call("android_wait", {"selector": {"resource_id": f"{PACKAGE}:id/input"}})
                ready, _ = await call("android_ready")
                assert ready["hierarchy_available"] and ready["screenshot_available"]
                observed, image_result = await call("android_observe")
                assert observed["screen"]["package"] == PACKAGE
                evidence["screen"] = {
                    key: observed["screen"][key] for key in ("width", "height", "rotation")
                }
                image_content = next(
                    item for item in image_result.content if isinstance(item, ImageContent)
                )
                image = Image.open(BytesIO(base64.b64decode(image_content.data)))
                assert image.size == (
                    observed["screenshot"]["width"],
                    observed["screenshot"]["height"],
                )
                input_selector = {"resource_id": f"{PACKAGE}:id/input"}
                await call("android_tap", {"selector": input_selector})
                typed, _ = await call(
                    "android_type_text", {"selector": input_selector, "text": "你好，安卓"}
                )
                assert typed["verified"] and typed["input_method_restored"]
                typed, _ = await call(
                    "android_type_text", {"selector": input_selector, "text": " AI", "clear": False}
                )
                assert typed["verified"]
                await call("android_wait", {"selector": {"text": "你好，安卓 AI"}})
                await call("android_press", {"key": "back"})
                observed, _ = await call("android_observe")
                apply = next(
                    node
                    for node in observed["nodes"]
                    if node["resource_id"] == f"{PACKAGE}:id/apply"
                )
                bounds = apply["bounds"]
                x = (bounds[0] + bounds[2]) / 2 / observed["screenshot"]["scale_x"]
                y = (bounds[1] + bounds[3]) / 2 / observed["screenshot"]["scale_y"]
                await call(
                    "android_tap",
                    {
                        "x": x,
                        "y": y,
                        "coordinate_space": "screenshot",
                        "observation_id": observed["observation_id"],
                    },
                )
                await call("android_wait", {"selector": {"text": "Applied: 你好，安卓 AI"}})
                duplicates, _ = await call("android_find", {"selector": {"text": "Duplicate"}})
                assert duplicates["match_count"] == 2
                await call(
                    "android_tap", {"selector": {"text": "Duplicate"}}, error="ambiguous_selector"
                )
                await call("android_tap", {"selector": {"text": "Duplicate", "index": 1}})
                await call("android_wait", {"selector": {"text": "Second"}})
                await call(
                    "android_batch",
                    {
                        "steps": [
                            {"action": "tap", "params": {"selector": {"text": "Apply"}}},
                            {"action": "tap", "params": {"selector": {"text": "Duplicate"}}},
                            {
                                "action": "tap",
                                "params": {"selector": {"resource_id": f"{PACKAGE}:id/first"}},
                            },
                        ]
                    },
                    error="ambiguous_selector",
                )
                await call("android_wait", {"selector": {"text": "Applied: 你好，安卓 AI"}})
                await call(
                    "android_wait",
                    {"selector": {"text": "Never exists"}, "present": False, "timeout": 0},
                )
                await call(
                    "android_wait",
                    {"selector": {"text": "Never exists"}, "timeout": 0},
                    error="wait_timeout",
                )
                before, _ = await call("android_find", {"selector": {"text_contains": "Row "}})
                observed, _ = await call("android_observe", {"screenshot": False})
                scroll = next(
                    node
                    for node in observed["nodes"]
                    if node["resource_id"] == f"{PACKAGE}:id/scroll"
                )
                await call(
                    "android_swipe",
                    {
                        "direction": "up",
                        "bounds": scroll["bounds"],
                        "observation_id": observed["observation_id"],
                    },
                )
                after, _ = await call("android_find", {"selector": {"text_contains": "Row "}})
                assert [(node["text"], node["bounds"]) for node in before["matches"]] != [
                    (node["text"], node["bounds"]) for node in after["matches"]
                ]
                observed, _ = await call("android_observe", {"screenshot": False})
                target_rotation = 1 if observed["screen"]["rotation"] != 1 else 0
                adb(
                    device_serial,
                    "shell",
                    "settings",
                    "put",
                    "system",
                    "accelerometer_rotation",
                    "0",
                )
                adb(
                    device_serial,
                    "shell",
                    "settings",
                    "put",
                    "system",
                    "user_rotation",
                    str(target_rotation),
                )
                rotated, _ = await call("android_observe")
                assert rotated["screen"]["rotation"] == target_rotation
                assert rotated["screenshot"] is not None
                assert rotated["screen"]["width"] != observed["screen"]["width"]
                # A stale observation must be rejected before any coordinate action.
                await call(
                    "android_tap",
                    {"x": 50, "y": 50, "observation_id": observed["observation_id"]},
                    error="stale_observation",
                )
                await call("android_press", {"key": "home"})
                final, _ = await call("android_observe", {"screenshot": False, "max_nodes": 1})
                assert final["screen"]["package"] != PACKAGE
                assert (
                    adb(device_serial, "shell", "settings", "get", "secure", "default_input_method")
                    == original_ime
                )
    finally:
        active_error = sys.exc_info()[1]
        restoration_errors = []
        for key, value in (
            ("user_rotation", original_rotation),
            ("accelerometer_rotation", original_auto),
        ):
            try:
                if value == "null":
                    adb(device_serial, "shell", "settings", "delete", "system", key)
                else:
                    adb(device_serial, "shell", "settings", "put", "system", key, value)
            except (subprocess.SubprocessError, OSError):
                restoration_errors.append(key)
        # Keep failures away from the user's app and never leave text in a production app.
        try:
            adb(device_serial, "shell", "input", "keyevent", "KEYCODE_HOME")
        except (subprocess.SubprocessError, OSError):
            restoration_errors.append("home")
        if restoration_errors:
            message = "Cleanup incomplete; restore using artifacts/device-settings-restore.json"
            if active_error is None:
                pytest.fail(message)
            active_error.add_note(message)
        else:
            restore_file.unlink()
    output = Path("artifacts/device-verification.json")
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


@pytest.mark.device
def test_real_device_ime_input_restores_original_default_and_enabled_methods(device_serial):
    from android_use.controller import AndroidController

    adb(device_serial, "shell", "am", "force-stop", PACKAGE)

    original_default = adb(
        device_serial, "shell", "settings", "get", "secure", "default_input_method"
    )
    original_enabled = adb(
        device_serial, "shell", "settings", "get", "secure", "enabled_input_methods"
    )
    try:
        with AndroidController(serial=device_serial) as controller:
            controller.launch_app(PACKAGE, activity=".MainActivity")
            result = controller.type_text(
                "输入法中文验证",
                selector={"resource_id": f"{PACKAGE}:id/input"},
                method="ime",
            )
            assert result["verified"] is True
            assert result["input_method_restored"] is True
            assert (
                adb(device_serial, "shell", "settings", "get", "secure", "default_input_method")
                == original_default
            )
            assert (
                adb(device_serial, "shell", "settings", "get", "secure", "enabled_input_methods")
                == original_enabled
            )
            controller.press("home")
    finally:
        adb(device_serial, "shell", "ime", "set", original_default)
        adb(device_serial, "shell", "input", "keyevent", "KEYCODE_HOME")
