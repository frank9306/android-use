import json
import subprocess
import sys

import pytest
from test_controller import BackendDouble

from android_use.cli import execute
from android_use.controller import AndroidController


def test_cli_saves_images_without_overwriting_existing_files(tmp_path):
    with AndroidController(
        serial="test-device", backend=BackendDouble(), lock_dir=tmp_path
    ) as controller:
        image_path = tmp_path / "screen.jpg"
        observed = execute(controller, "observe", {}, str(image_path))
        assert observed["ok"] is True
        assert image_path.read_bytes().startswith(b"\xff\xd8")
        original = image_path.read_bytes()
        repeated = execute(controller, "observe", {}, str(image_path))
        assert repeated["ok"] is False
        assert image_path.read_bytes() == original
        assert (
            execute(controller, "tap", {"unexpected": "parameter"})["error"]["code"]
            == "invalid_argument"
        )


def test_persistent_cli_accepts_json_lines_and_returns_errors_without_crashing():
    result = subprocess.run(
        [sys.executable, "-m", "android_use", "session"],
        input='not json\n{"action":"unknown","params":{}}\n',
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=15,
    )
    assert result.returncode == 0
    responses = [json.loads(line) for line in result.stdout.splitlines()]
    assert len(responses) == 2
    assert all(item["error"]["code"] == "invalid_argument" for item in responses)


@pytest.mark.parametrize(
    "action, params",
    [
        ("press", {"key": []}),
        ("swipe", {"direction": []}),
        ("type_text", {"text": "safe", "method": []}),
    ],
)
def test_invalid_cli_argument_types_return_json_errors(action, params, tmp_path):
    with AndroidController(
        serial="test-device", backend=BackendDouble(), lock_dir=tmp_path
    ) as controller:
        result = execute(controller, action, params)
        assert result["ok"] is False
        assert result["error"]["code"] == "invalid_argument"
