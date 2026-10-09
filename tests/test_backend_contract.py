"""Check the pinned SDK boundary rather than inventing a separate RPC schema."""

import inspect
from importlib.metadata import version

import adbutils
import pytest
import uiautomator2.core as core
from uiautomator2.exceptions import HTTPError

from android_use.backend import AndroidDevice, SingleAttemptDevice


def test_pinned_sdk_rpc_contract_does_not_restart_and_replay_a_failed_key(monkeypatch):
    assert version("uiautomator2") == "3.7.0"
    assert list(inspect.signature(core._jsonrpc_call).parameters) == [
        "dev",
        "device_port",
        "method",
        "params",
        "timeout",
        "print_request",
    ]
    starts = []
    requests = []
    monkeypatch.setattr(
        core.BasicUiautomatorServer, "start_uiautomator", lambda _self: starts.append(True)
    )

    def lost_response(*args, **kwargs):
        requests.append(args[4])
        raise HTTPError("Transport failed after dispatch")

    monkeypatch.setattr(core, "_http_request", lost_response)
    device = SingleAttemptDevice(adbutils.adb.device(serial="contract-device"))
    with pytest.raises(HTTPError):
        device.jsonrpc.pressKey("back")
    assert len(starts) == 1
    assert len(requests) == 1
    assert requests[0]["method"] == "pressKey"
    assert requests[0]["params"] == ("back",)


def test_adapter_reports_a_rejected_click_even_when_sdk_click_discards_rpc_result(monkeypatch):
    monkeypatch.setattr(core.BasicUiautomatorServer, "start_uiautomator", lambda _self: None)
    monkeypatch.setattr(
        core,
        "_http_request",
        lambda *args, **kwargs: core.HTTPResponse(b'{"jsonrpc":"2.0","id":1,"result":false}'),
    )
    device = AndroidDevice("contract-device")
    with pytest.raises(RuntimeError, match="rejected click"):
        device.tap(100, 100)
