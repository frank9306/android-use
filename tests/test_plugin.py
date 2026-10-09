"""Exercise the bundled launcher with the real MCP transport in a clean directory."""

import json
import os
import shutil
from datetime import timedelta
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]


async def test_plugin_mcp_starts_from_installed_copy_outside_the_working_directory(tmp_path):
    config = json.loads((ROOT / ".mcp.json").read_text(encoding="utf-8"))
    installed = tmp_path / "installed plugin with spaces"
    installed.mkdir()
    for name in ("pyproject.toml", "uv.lock", ".python-version", "README.md"):
        shutil.copyfile(ROOT / name, installed / name)
    shutil.copytree(ROOT / "src", installed / "src", ignore=shutil.ignore_patterns("__pycache__"))
    launch = config["mcpServers"]["android-use"]
    parameters = StdioServerParameters(
        command=launch["command"],
        args=launch["args"],
        cwd=str(installed / launch["cwd"]),
        env={**os.environ, "PYTHONIOENCODING": "utf-8", "UV_LINK_MODE": "copy"},
    )
    async with stdio_client(parameters) as (reader, writer):
        async with ClientSession(
            reader, writer, read_timeout_seconds=timedelta(seconds=120)
        ) as session:
            await session.initialize()
            names = {tool.name for tool in (await session.list_tools()).tools}
            assert names == {
                "android_devices",
                "android_ready",
                "android_observe",
                "android_find",
                "android_tap",
                "android_swipe",
                "android_type_text",
                "android_press",
                "android_launch_app",
                "android_wait",
                "android_batch",
            }
            result = await session.call_tool("android_devices")
            assert result.isError is False
            assert json.loads(result.content[0].text)["ok"] is True
