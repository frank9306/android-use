from copy import deepcopy
from xml.etree import ElementTree as ET

import pytest
from PIL import Image
from test_hierarchy import XML

from android_use.controller import AndroidController
from android_use.errors import AndroidUseError


class DeviceDouble:
    """Fault injection at the real uiautomator2 adapter boundary, not an emulator."""

    def __init__(self):
        self.xml = XML
        self.rotation = 0
        self.calls = []

    def info(self):
        return {
            "width": 1080,
            "height": 2400,
            "rotation": self.rotation,
            "screen_on": True,
            "package": "com.androiduse.fixture",
            "activity": None,
        }

    def hierarchy(self):
        return self.xml.replace('rotation="0"', f'rotation="{self.rotation}"')

    def screenshot(self):
        return Image.new("RGB", (1080, 2400), "white")

    def tap(self, x, y):
        self.calls.append(("tap", x, y))

    def press(self, key):
        self.calls.append(("press", key))

    def swipe(self, sx, sy, ex, ey, duration):
        self.calls.append(("swipe", sx, sy, ex, ey, duration))

    def type_text(self, node, text, method):
        self.calls.append(("type_text", text, method))
        root = ET.fromstring(self.xml)
        for element in root.iter("node"):
            if element.get("resource-id") == node.resource_id:
                element.set("text", text)
        self.xml = ET.tostring(root, encoding="unicode")
        return {"input_method_restored": True}


class BackendDouble:
    def __init__(self, records=None):
        self.device = DeviceDouble()
        self.records = (
            records if records is not None else [{"serial": "test-device", "state": "device"}]
        )

    def devices(self):
        return deepcopy(self.records)

    def connect(self, serial):
        return self.device


@pytest.fixture
def controller(tmp_path):
    backend = BackendDouble()
    with AndroidController(serial="test-device", backend=backend, lock_dir=tmp_path) as control:
        yield control, backend.device


def test_screenshot_coordinates_map_to_native_pixels_and_rotation_stops_dispatch(controller):
    control, device = controller
    observation = control.observe(screenshot=True, max_image_edge=1200)
    assert observation["screenshot"]["width"] == 540
    assert observation["screenshot"]["height"] == 1200
    control.tap(
        x=250, y=150, coordinate_space="screenshot", observation_id=observation["observation_id"]
    )
    assert device.calls == [("tap", 500, 300)]
    observation = control.observe(screenshot=False)
    device.rotation = 1
    with pytest.raises(AndroidUseError) as failure:
        control.tap(x=500, y=300, observation_id=observation["observation_id"])
    assert failure.value.code == "stale_observation"
    assert device.calls == [("tap", 500, 300)]


def test_batch_stops_at_ambiguous_selector_without_running_later_steps(controller):
    control, device = controller
    result = control.batch(
        [
            {"action": "press", "params": {"key": "back"}},
            {"action": "tap", "params": {"selector": {"text": "Duplicate"}}},
            {"action": "press", "params": {"key": "home"}},
        ]
    )
    assert result["ok"] is False
    assert result["failed_index"] == 1
    assert len(result["completed"]) == 1
    assert result["error"]["code"] == "ambiguous_selector"
    assert device.calls == [("press", "back")]


def test_cancelled_batch_does_not_dispatch_the_next_step(controller):
    control, device = controller

    def first_step(key):
        device.calls.append(("press", key))
        control.cancel()

    device.press = first_step
    result = control.batch(
        [
            {"action": "press", "params": {"key": "back"}},
            {"action": "press", "params": {"key": "home"}},
        ]
    )
    assert result["ok"] is False
    assert result["error"]["code"] == "cancelled"
    assert device.calls == [("press", "back")]


def test_timed_out_action_is_dispatched_once_and_reported_uncertain(controller):
    control, device = controller

    def timed_out(x, y):
        device.calls.append(("tap", x, y))
        raise TimeoutError("A response was lost after the click")

    device.tap = timed_out
    with pytest.raises(AndroidUseError) as failure:
        control.tap(selector={"resource_id": "com.androiduse.fixture:id/input"})
    assert failure.value.code == "action_uncertain"
    assert len(device.calls) == 1


def test_chinese_input_is_read_back_after_replacement_and_append(controller):
    control, device = controller
    selector = {"resource_id": "com.androiduse.fixture:id/input"}
    result = control.type_text("你好，安卓", selector=selector)
    assert result["verified"] is True
    assert result["input_method_restored"] is True
    result = control.type_text("！", selector=selector, clear=False)
    assert result["verified"] is True
    assert device.calls[-1] == ("type_text", "你好，安卓！", "accessibility")


def test_directional_swipe_uses_current_screen_and_wait_has_a_finite_timeout(controller):
    control, device = controller
    result = control.swipe(direction="up")
    assert result["dispatched"] is True
    assert device.calls == [("swipe", 540, 1920, 540, 480, 0.3)]
    assert control.wait({"text": "Duplicate"}, timeout=0)["matched"] is True
    with pytest.raises(AndroidUseError) as failure:
        control.wait({"text": "Absent"}, timeout=0)
    assert failure.value.code == "wait_timeout"


def test_device_disconnect_does_not_switch_to_another_online_device(tmp_path):
    backend = BackendDouble()
    with AndroidController(serial="test-device", backend=backend, lock_dir=tmp_path) as control:
        control.observe(screenshot=False)
        backend.records = [{"serial": "other-device", "state": "device"}]
        with pytest.raises(AndroidUseError) as failure:
            control.press("home")
        assert failure.value.code == "device_unavailable"
        assert backend.device.calls == []


def test_device_lease_blocks_another_controller_until_owner_closes(tmp_path):
    first = AndroidController(serial="test-device", backend=BackendDouble(), lock_dir=tmp_path)
    second = AndroidController(serial="test-device", backend=BackendDouble(), lock_dir=tmp_path)
    try:
        first.observe(screenshot=False)
        with pytest.raises(AndroidUseError) as failure:
            second.observe(screenshot=False)
        assert failure.value.code == "device_busy"
        first.close()
        assert second.observe(screenshot=False)["screen"]["width"] == 1080
    finally:
        first.close()
        second.close()


def test_changed_content_expired_observations_and_out_of_bounds_coordinates_stop(controller):
    control, device = controller
    observed = control.observe(screenshot=False)
    device.xml = device.xml.replace("安卓测试", "Changed")
    with pytest.raises(AndroidUseError) as failure:
        control.tap(x=1, y=1, observation_id=observed["observation_id"])
    assert failure.value.code == "stale_observation"
    observed = control.observe(screenshot=False)
    with pytest.raises(AndroidUseError) as failure:
        control.tap(x=1080, y=1, observation_id=observed["observation_id"])
    assert failure.value.code == "invalid_argument"
    observed = control.observe(screenshot=False)
    control.observation_ttl = -1
    with pytest.raises(AndroidUseError) as failure:
        control.tap(x=1, y=1, observation_id=observed["observation_id"])
    assert failure.value.code == "stale_observation"
    assert device.calls == []


def test_invalid_batch_shape_is_rejected_before_dispatch(controller):
    control, device = controller
    with pytest.raises(AndroidUseError) as failure:
        control.batch(
            [
                {"action": "press", "params": {"key": "home"}},
                {"action": "press", "params": {"invalid": "argument"}},
            ]
        )
    assert failure.value.code == "invalid_argument"
    assert device.calls == []


def test_incidental_xml_formatting_does_not_invalidate_unchanged_visible_controls(controller):
    control, device = controller
    observed = control.observe(screenshot=False)
    device.xml = device.xml.replace(
        'class="android.widget.Button"', 'drawing-order="7" class="android.widget.Button"'
    )
    result = control.tap(x=500, y=300, observation_id=observed["observation_id"])
    assert result["dispatched"] is True
    assert device.calls == [("tap", 500, 300)]


def test_passive_system_status_numbers_do_not_invalidate_app_coordinates(controller):
    control, device = controller
    status = (
        '<node text="0.5" resource-id="com.android.systemui:id/speed_text" '
        'class="android.widget.TextView" package="com.android.systemui" '
        'bounds="[10,0][50,30]" clickable="false" enabled="true" />'
    )
    device.xml = device.xml.replace("</hierarchy>", status + "</hierarchy>")
    observed = control.observe(screenshot=False)
    device.xml = device.xml.replace('text="0.5"', 'text="99.8"')
    result = control.tap(x=500, y=300, observation_id=observed["observation_id"])
    assert result["dispatched"] is True
    assert device.calls == [("tap", 500, 300)]


def test_screenshot_failure_preserves_hierarchy_and_disallows_image_coordinates(controller):
    control, device = controller

    def unavailable():
        raise RuntimeError("Protected or unavailable screenshot")

    device.screenshot = unavailable
    observed = control.observe()
    assert observed["nodes"]
    assert observed["screenshot"] is None
    assert observed["screenshot_error"]["code"] == "screenshot_unavailable"
    with pytest.raises(AndroidUseError) as failure:
        control.tap(
            x=20, y=20, coordinate_space="screenshot", observation_id=observed["observation_id"]
        )
    assert failure.value.code == "invalid_argument"
    assert device.calls == []


def test_observe_retries_reads_when_the_ui_changes_during_screenshot_capture(controller):
    control, device = controller
    attempts = []

    def screenshot_during_transition():
        attempts.append(True)
        device.xml = device.xml.replace("安卓测试", "Settled")
        return Image.new("RGB", (1080, 2400), "white")

    device.screenshot = screenshot_during_transition
    observed = control.observe()
    assert observed["nodes"][0]["text"] == "Settled"
    assert len(attempts) == 2
