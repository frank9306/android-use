import pytest
from pydantic import ValidationError

from android_use.errors import AndroidUseError
from android_use.hierarchy import Hierarchy, Selector

# Android UI Automator dump schema, with synthetic app/text values.
# Contract: openatx/android-uiautomator-server-jar AccessibilityNodeInfoDumper.
XML = """<hierarchy rotation="0">
<node text="" resource-id="" class="android.widget.FrameLayout"
 package="com.androiduse.fixture" bounds="[0,0][1080,2400]" enabled="true">
 <node text="安卓测试" resource-id="com.androiduse.fixture:id/input"
  class="android.widget.EditText" content-desc="Search input"
  package="com.androiduse.fixture" bounds="[20,100][1060,200]"
  clickable="true" enabled="true" focused="true" password="false" />
 <node text="Duplicate" resource-id="com.androiduse.fixture:id/first"
  class="android.widget.Button" bounds="[20,220][500,300]"
  clickable="true" enabled="true" />
 <node text="Duplicate" resource-id="com.androiduse.fixture:id/second"
  class="android.widget.Button" bounds="[520,220][1060,300]"
  clickable="true" enabled="true" />
 <node text="secret" resource-id="com.androiduse.fixture:id/password"
  class="android.widget.EditText" bounds="[20,320][1060,400]"
  enabled="true" password="true" />
</node></hierarchy>"""


def test_observation_compacts_android_xml_and_masks_password_text():
    hierarchy = Hierarchy.parse(XML)
    nodes, truncated = hierarchy.compact(10)
    assert truncated is False
    assert len(nodes) == 4
    assert nodes[0]["text"] == "安卓测试"
    assert nodes[0]["bounds"] == [20, 100, 1060, 200]
    assert nodes[0]["focused"] is True
    assert nodes[-1]["text"] == "[redacted]"
    assert hierarchy.rotation == 0


def test_selector_requires_explicit_disambiguation_and_rejects_broad_selection():
    hierarchy = Hierarchy.parse(XML)
    with pytest.raises(AndroidUseError, match="matched 2"):
        hierarchy.resolve(Selector(text="Duplicate"))
    assert hierarchy.resolve(Selector(text="Duplicate", index=1)).resource_id.endswith("/second")
    with pytest.raises(ValidationError):
        Selector()
    with pytest.raises(ValidationError):
        Selector(text="Duplicate", unexpected="ignored")


@pytest.mark.parametrize(
    "xml",
    [
        '<!DOCTYPE hierarchy [<!ENTITY entity "injected">]><hierarchy>&entity;</hierarchy>',
        '<hierarchy rotation="9"/>',
        '<hierarchy><node bounds="broken"/></hierarchy>',
        "<unrelated/>",
    ],
)
def test_malformed_or_unsafe_hierarchy_is_a_contract_failure(xml):
    with pytest.raises(AndroidUseError) as failure:
        Hierarchy.parse(xml)
    assert failure.value.code == "invalid_hierarchy"
