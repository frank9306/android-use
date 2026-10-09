import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--plugin-root",
        default=None,
        help="Use an installed plugin's bundled MCP launcher in the real-device workflow",
    )
    parser.addoption(
        "--device-serial",
        default=None,
        help="Opt in to real-device tests: an ADB serial or 'auto' for one online device",
    )


@pytest.fixture(scope="session")
def device_serial(request):
    value = request.config.getoption("--device-serial")
    if value is None:
        pytest.skip("Pass --device-serial to explicitly enable the isolated real-device workflow")
    if value == "auto":
        from android_use.backend import SystemBackend

        devices = [
            record["serial"] for record in SystemBackend().devices() if record["state"] == "device"
        ]
        if len(devices) != 1:
            pytest.fail("Auto device selection requires exactly one authorized device")
        return devices[0]
    return value
