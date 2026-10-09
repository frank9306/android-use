import json

from mcp.shared.memory import create_connected_server_and_client_session
from mcp.types import ImageContent
from test_controller import BackendDouble

from android_use.controller import AndroidController
from android_use.server import create_server


async def test_mcp_lists_typed_tools_and_returns_images_and_action_errors(tmp_path):
    with AndroidController(backend=BackendDouble(), lock_dir=tmp_path) as controller:
        server = create_server(controller)
        async with create_connected_server_and_client_session(server._mcp_server) as session:
            tools = (await session.list_tools()).tools
            assert {tool.name for tool in tools} >= {
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
            observed = await session.call_tool("android_observe", {"max_image_edge": 1200})
            assert observed.isError is False
            assert any(isinstance(content, ImageContent) for content in observed.content)
            data = json.loads(observed.content[0].text)
            assert data["data"]["screen"]["width"] == 1080
            assert "_image" not in data["data"]
            typed = await session.call_tool(
                "android_type_text",
                {
                    "text": "中文输入",
                    "selector": {"resource_id": "com.androiduse.fixture:id/input"},
                },
            )
            assert typed.isError is False
            assert json.loads(typed.content[0].text)["data"]["verified"] is True
            ambiguous = await session.call_tool("android_tap", {"selector": {"text": "Duplicate"}})
            assert ambiguous.isError is True
            assert json.loads(ambiguous.content[0].text)["error"]["code"] == "ambiguous_selector"
