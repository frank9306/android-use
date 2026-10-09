"""MCP stdio transport with typed tools and native image content."""

import argparse
import asyncio
import base64
import json
import sys
from contextlib import asynccontextmanager, redirect_stdout

from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, ImageContent, TextContent, ToolAnnotations

from android_use.controller import AndroidController
from android_use.errors import AndroidUseError
from android_use.hierarchy import Selector
from android_use.models import BatchStep


def create_server(controller: AndroidController | None = None) -> FastMCP:
    controller = controller or AndroidController()
    invoke_lock = asyncio.Lock()

    @asynccontextmanager
    async def lifespan(_server):
        try:
            yield {}
        finally:
            controller.close()

    server = FastMCP(
        "android-use",
        lifespan=lifespan,
        instructions=(
            "Observe before acting. Prefer selectors; ambiguous matches require refinement "
            "or an explicit index. "
            "Coordinate and node_id actions require a fresh observation_id from this session. "
            "A dispatched action needs a new observation or wait to confirm its result. "
            "Never blindly repeat action_uncertain. Passwords, unlock and CAPTCHA require the user."
        ),
    )
    read_only = ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=True)
    action = ToolAnnotations(readOnlyHint=False, idempotentHint=False, openWorldHint=True)

    async def invoke(operation, **kwargs) -> CallToolResult:
        def call():
            # Protect the MCP stdout channel from dependency installation/progress output.
            with redirect_stdout(sys.stderr):
                try:
                    data = operation(**kwargs)
                    image = data.pop("_image", None)
                    failed = data.get("ok") is False
                    payload = {"ok": not failed, "data": data}
                    if failed:
                        payload["error"] = data["error"]
                    return payload, image
                except AndroidUseError as error:
                    return {"ok": False, "error": error.as_dict()}, None

        async with invoke_lock:
            controller.reset_cancel()
            pending = asyncio.create_task(asyncio.to_thread(call))
            try:
                payload, image = await asyncio.shield(pending)
            except asyncio.CancelledError:
                controller.cancel()
                # Keep the lease and invocation lock until the worker has stopped.
                # A later request must not overlap a cancelled in-flight command.
                await asyncio.shield(pending)
                raise
        content = [TextContent(type="text", text=json.dumps(payload, ensure_ascii=False))]
        if image is not None:
            content.append(
                ImageContent(
                    type="image",
                    data=base64.b64encode(image).decode("ascii"),
                    mimeType="image/jpeg",
                )
            )
        return CallToolResult(content=content, structuredContent=payload, isError=not payload["ok"])

    @server.tool(annotations=read_only)
    async def android_devices() -> CallToolResult:
        """List all ADB devices, including unauthorized/offline states, without picking one."""
        return await invoke(controller.devices)

    @server.tool(annotations=read_only)
    async def android_ready() -> CallToolResult:
        """Check the selected device, UI service, display, hierarchy and screenshot access."""
        return await invoke(controller.ready)

    @server.tool(annotations=read_only)
    async def android_observe(
        screenshot: bool = True, max_nodes: int = 150, max_image_edge: int = 1280
    ) -> CallToolResult:
        """Read compact UI nodes and optionally a JPEG; return observation_id and pixel scales."""
        return await invoke(
            controller.observe,
            screenshot=screenshot,
            max_nodes=max_nodes,
            max_image_edge=max_image_edge,
        )

    @server.tool(annotations=read_only)
    async def android_find(selector: Selector, max_matches: int = 50) -> CallToolResult:
        """Find all matching current UI nodes. An index is only used when acting on a selector."""
        return await invoke(controller.find, selector=selector, max_matches=max_matches)

    @server.tool(annotations=action)
    async def android_tap(
        selector: Selector | None = None,
        x: float | None = None,
        y: float | None = None,
        observation_id: str | None = None,
        coordinate_space: str = "native",
        node_id: str | None = None,
    ) -> CallToolResult:
        """Tap a unique selector, observed node, or coordinates from a fresh observation."""
        return await invoke(
            controller.tap,
            selector=selector,
            x=x,
            y=y,
            observation_id=observation_id,
            coordinate_space=coordinate_space,
            node_id=node_id,
        )

    @server.tool(annotations=action)
    async def android_swipe(
        direction: str | None = None,
        sx: float | None = None,
        sy: float | None = None,
        ex: float | None = None,
        ey: float | None = None,
        duration: float = 0.3,
        observation_id: str | None = None,
        coordinate_space: str = "native",
        bounds: list[int] | None = None,
    ) -> CallToolResult:
        """Swipe direction in native space/bounds, or observed points in native/screenshot space."""
        return await invoke(
            controller.swipe,
            direction=direction,
            sx=sx,
            sy=sy,
            ex=ex,
            ey=ey,
            duration=duration,
            observation_id=observation_id,
            coordinate_space=coordinate_space,
            bounds=bounds,
        )

    @server.tool(annotations=action)
    async def android_type_text(
        text: str,
        selector: Selector | None = None,
        clear: bool = True,
        verify: bool = True,
        method: str = "accessibility",
    ) -> CallToolResult:
        """Replace/append Unicode text; read back and optionally use a restored IME."""
        return await invoke(
            controller.type_text,
            text=text,
            selector=selector,
            clear=clear,
            verify=verify,
            method=method,
        )

    @server.tool(annotations=action)
    async def android_press(key: str) -> CallToolResult:
        """Press an allowed key such as back, home, recent or enter; power/unlock are excluded."""
        return await invoke(controller.press, key=key)

    @server.tool(annotations=action)
    async def android_launch_app(
        package: str, activity: str | None = None, timeout: float = 10
    ) -> CallToolResult:
        """Launch a package/activity without clearing data; verify the active package."""
        return await invoke(
            controller.launch_app, package=package, activity=activity, timeout=timeout
        )

    @server.tool(annotations=read_only)
    async def android_wait(
        selector: Selector, timeout: float = 10, present: bool = True
    ) -> CallToolResult:
        """Wait up to 30 seconds for a selector to appear or disappear."""
        return await invoke(controller.wait, selector=selector, timeout=timeout, present=present)

    @server.tool(annotations=action)
    async def android_batch(steps: list[BatchStep]) -> CallToolResult:
        """Run up to 20 predetermined actions sequentially; stop and report the first failure."""
        return await invoke(controller.batch, steps=steps)

    return server


def main() -> None:
    parser = argparse.ArgumentParser(description="Android Use MCP stdio server")
    parser.add_argument(
        "--serial", help="ADB serial; defaults to ANDROID_SERIAL or one online device"
    )
    args = parser.parse_args()
    create_server(AndroidController(serial=args.serial)).run(transport="stdio")


if __name__ == "__main__":
    main()
