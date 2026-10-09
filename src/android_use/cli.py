"""JSON command line and persistent JSON-lines session."""

import argparse
import inspect
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

from android_use.controller import AndroidController
from android_use.errors import AndroidUseError

ACTIONS = (
    "devices",
    "ready",
    "observe",
    "find",
    "tap",
    "swipe",
    "type_text",
    "press",
    "launch_app",
    "wait",
    "batch",
)


def execute(
    controller: AndroidController, action: str, params: dict, image_path: str | None = None
) -> dict:
    try:
        if not isinstance(action, str) or action not in ACTIONS or not isinstance(params, dict):
            raise AndroidUseError("invalid_argument", "Unknown action or non-object params")
        if image_path is not None and not isinstance(image_path, str):
            raise AndroidUseError("invalid_argument", "image_path must be a string")
        method = getattr(controller, action)
        try:
            inspect.signature(method).bind(**params)
        except TypeError as error:
            raise AndroidUseError("invalid_argument", "Invalid action arguments") from error
        with redirect_stdout(sys.stderr):
            data = method(**params)
        image = data.pop("_image", None)
        if image_path is not None:
            if image is None:
                raise AndroidUseError(
                    "screenshot_unavailable", "This call did not return a screenshot"
                )
            path = Path(image_path).resolve()
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("xb") as output:
                output.write(image)
            data["screenshot"]["path"] = str(path)
        payload = {"ok": data.get("ok") is not False, "data": data}
        if not payload["ok"]:
            payload["error"] = data["error"]
        return payload
    except AndroidUseError as error:
        return {"ok": False, "error": error.as_dict()}
    except (OSError, ValueError) as error:
        return {
            "ok": False,
            "error": {"code": "local_io_error", "message": str(error), "details": {}},
        }


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def session(controller: AndroidController) -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict) or set(request) - {"action", "params", "image_path"}:
                raise ValueError("Request requires action, params and optional image_path")
            emit(
                execute(
                    controller,
                    request["action"],
                    request.get("params", {}),
                    request.get("image_path"),
                )
            )
        except (ValueError, KeyError) as error:
            emit(
                {
                    "ok": False,
                    "error": {"code": "invalid_argument", "message": str(error), "details": {}},
                }
            )


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stdin.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--serial", help="ADB serial, or ANDROID_SERIAL")
    parser.add_argument("action", choices=(*ACTIONS, "session", "mcp"))
    params = parser.add_mutually_exclusive_group()
    params.add_argument("--params", default="{}", help="JSON object of tool arguments")
    params.add_argument("--params-file", type=Path, help="UTF-8 JSON argument file")
    parser.add_argument("--image", help="Save observe JPEG to a new file (never overwrite)")
    args = parser.parse_args()
    with AndroidController(serial=args.serial) as controller:
        if args.action == "mcp":
            from android_use.server import create_server

            create_server(controller).run(transport="stdio")
        elif args.action == "session":
            session(controller)
        else:
            try:
                arguments = json.loads(
                    args.params_file.read_text(encoding="utf-8")
                    if args.params_file
                    else args.params
                )
            except (OSError, ValueError) as error:
                emit(
                    {
                        "ok": False,
                        "error": {"code": "invalid_argument", "message": str(error), "details": {}},
                    }
                )
                raise SystemExit(1) from error
            result = execute(controller, args.action, arguments, args.image)
            emit(result)
            raise SystemExit(0 if result["ok"] else 1)


if __name__ == "__main__":
    main()
