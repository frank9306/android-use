"""Validate native Codex install, skill discovery and MCP without model requests.

Uses a disposable Codex home; existing client settings and credentials are untouched.
Optionally run the existing real-device acceptance suite through the installed launcher.
"""

import argparse
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class AppServer:
    def __init__(self, codex: str, environment: dict, cwd: Path, log):
        self.process = subprocess.Popen(
            [codex, "app-server"],
            cwd=cwd,
            env=environment,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=log,
            text=True,
            encoding="utf-8",
        )
        self.messages = queue.Queue()
        self.counter = 0

        def read():
            for line in self.process.stdout:
                self.messages.put(json.loads(line))
            self.messages.put(None)

        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()

    def send(self, message):
        self.process.stdin.write(json.dumps(message) + "\n")
        self.process.stdin.flush()

    def request(self, method, params):
        self.counter += 1
        request_id = self.counter
        self.send({"id": request_id, "method": method, "params": params})
        deadline = time.monotonic() + 150
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"Codex app-server did not respond to {method} within 150s")
            message = self.messages.get(timeout=remaining)
            if message is None:
                raise RuntimeError("Codex app-server exited before responding")
            if message.get("id") == request_id:
                if "error" in message:
                    raise RuntimeError(f"{method}: {message['error']}")
                return message["result"]

    def close(self):
        self.process.stdin.close()
        try:
            self.process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            self.process.wait(timeout=15)
        self.reader.join(timeout=5)
        self.process.stdout.close()


def check(device_serial: str | None = None, marketplace_source: str | None = None) -> dict:
    codex = shutil.which("codex")
    if not codex:
        raise RuntimeError("Install Codex CLI and make codex available on PATH")
    with tempfile.TemporaryDirectory(prefix="android-use-plugin-check-") as work:
        base = Path(work)
        stage, home = base / "marketplace", base / "isolated-codex"
        stage.mkdir()
        home.mkdir()
        for name in ("README.md", "pyproject.toml", "uv.lock", ".python-version", ".mcp.json"):
            shutil.copyfile(ROOT / name, stage / name)
        for name in ("src", "skills", ".codex-plugin", ".agents"):
            shutil.copytree(ROOT / name, stage / name, ignore=shutil.ignore_patterns("__pycache__"))
        environment = {**os.environ, "CODEX_HOME": str(home), "UV_LINK_MODE": "copy"}

        def cli(*arguments):
            result = subprocess.run(
                [codex, "plugin", *arguments, "--json"],
                cwd=base,
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
                check=True,
            )
            return json.loads(result.stdout)

        cli("marketplace", "add", marketplace_source or str(stage))
        installed = cli("add", "android-use@android-use")
        listing = cli("list", "--marketplace", "android-use")
        assert any(
            item["pluginId"] == "android-use@android-use" and item["enabled"]
            for item in listing["installed"]
        ), listing
        installed_root = Path(installed["installedPath"])
        assert installed_root.is_relative_to(home)
        with (base / "app-server.log").open("w", encoding="utf-8") as log:
            server = AppServer(codex, environment, base, log)
            try:
                server.request(
                    "initialize",
                    {
                        "clientInfo": {"name": "android-use-check", "version": "0.1.0"},
                        "capabilities": {"experimentalApi": True},
                    },
                )
                server.send({"method": "initialized"})
                skills = server.request("skills/list", {"cwds": [str(base)], "forceReload": True})
                names = {
                    skill["name"]
                    for entry in skills["data"]
                    for skill in entry["skills"]
                    if Path(skill["path"]).is_relative_to(installed_root)
                }
                assert names == {"android-use:android-setup", "android-use:android-control"}, names
                inventory = server.request("mcpServerStatus/list", {"detail": "toolsAndAuthOnly"})
                tools = {
                    tool["name"]
                    for item in inventory["data"]
                    if "android-use" in item["name"]
                    for tool in item["tools"].values()
                }
            finally:
                server.close()
        expected_tools = {
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
        assert tools == expected_tools, (
            inventory,
            (base / "app-server.log").read_text(encoding="utf-8")[-4000:],
        )
        assert (installed_root / ".venv" / "pyvenv.cfg").is_file(), (
            "The native MCP launcher did not create its own installed runtime"
        )
        if device_serial:
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "-c",
                    str(ROOT / "pyproject.toml"),
                    str(ROOT / "tests"),
                    "--device-serial",
                    device_serial,
                    "--plugin-root",
                    str(installed_root),
                    "-q",
                ],
                cwd=ROOT,
                check=True,
                timeout=300,
            )
        return {
            "plugin": installed["pluginId"],
            "version": installed["version"],
            "skills": sorted(names),
            "mcp_tools": sorted(tools),
            "real_device_tests": "passed" if device_serial else "not requested",
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-serial", help="Opt in: serial or auto; install the fixture first")
    parser.add_argument(
        "--marketplace-source", help="Optional Git marketplace to verify after push"
    )
    arguments = parser.parse_args()
    print(
        json.dumps(
            check(arguments.device_serial, arguments.marketplace_source),
            ensure_ascii=False,
            indent=2,
        )
    )
