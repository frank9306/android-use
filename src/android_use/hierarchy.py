"""Bounded parsing of the Android UI Automator hierarchy contract."""

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from xml.etree import ElementTree as ET

from pydantic import BaseModel, ConfigDict, Field, model_validator

from android_use.errors import AndroidUseError


class Selector(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    resource_id: str | None = Field(default=None, min_length=1, max_length=1024)
    text: str | None = Field(default=None, max_length=4096)
    text_contains: str | None = Field(default=None, min_length=1, max_length=4096)
    description: str | None = Field(default=None, max_length=4096)
    class_name: str | None = Field(default=None, min_length=1, max_length=1024)
    package_name: str | None = Field(default=None, min_length=1, max_length=1024)
    clickable: bool | None = None
    enabled: bool | None = None
    focused: bool | None = None
    scrollable: bool | None = None
    index: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def require_filter(self) -> "Selector":
        if not any(value is not None for key, value in self.model_dump().items() if key != "index"):
            raise ValueError("At least one selector filter is required")
        return self


@dataclass(frozen=True)
class Node:
    id: str
    text: str
    resource_id: str
    description: str
    class_name: str
    package_name: str
    bounds: list[int]
    clickable: bool
    long_clickable: bool
    enabled: bool
    focused: bool
    scrollable: bool
    password: bool

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class Hierarchy:
    nodes: list[Node]
    rotation: int
    fingerprint: str

    @classmethod
    def parse(cls, xml: str) -> "Hierarchy":
        if len(xml) > 4_000_000 or "<!DOCTYPE" in xml.upper() or "<!ENTITY" in xml.upper():
            raise AndroidUseError("invalid_hierarchy", "Oversized XML or DTD is unsupported")
        try:
            root = ET.fromstring(xml)
            rotation = int(root.get("rotation", "0"))
            if root.tag != "hierarchy" or rotation not in range(4):
                raise ValueError("Unsupported hierarchy root or rotation")
            nodes = []
            for index, element in enumerate(root.iter("node")):
                if index >= 20_000:
                    raise ValueError("Too many hierarchy nodes")
                values = element.attrib
                match = re.fullmatch(
                    r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]", values.get("bounds", "")
                )
                if not match:
                    raise ValueError("Invalid node bounds")
                password = values.get("password") == "true"
                nodes.append(
                    Node(
                        id=f"n{index}",
                        text="[redacted]" if password else values.get("text", ""),
                        resource_id=values.get("resource-id", ""),
                        description="[redacted]" if password else values.get("content-desc", ""),
                        class_name=values.get("class", ""),
                        package_name=values.get("package", ""),
                        bounds=[int(value) for value in match.groups()],
                        clickable=values.get("clickable") == "true",
                        long_clickable=values.get("long-clickable") == "true",
                        enabled=values.get("enabled", "true") == "true",
                        focused=values.get("focused") == "true",
                        scrollable=values.get("scrollable") == "true",
                        password=password,
                    )
                )
        except (ET.ParseError, ValueError) as error:
            raise AndroidUseError(
                "invalid_hierarchy", "UI hierarchy violates the Android XML contract"
            ) from error
        records = []
        passive_status_ids = {
            "clock",
            "speed_text",
            "speed_unit",
            "network_speed",
            "network_speed_text",
            "battery_level",
            "mfv_battery_level_outside",
        }
        for node in nodes:
            record = node.as_dict()
            if (
                node.package_name == "com.android.systemui"
                and not node.clickable
                and not node.long_clickable
                and not node.focused
                and node.resource_id.rsplit("/", 1)[-1] in passive_status_ids
            ):
                # Status telemetry changes continuously without changing a target.
                # Keep its geometry and every interactive/app node in the signature.
                record["text"] = record["description"] = ""
            records.append(record)
        semantic = json.dumps(
            [rotation, records], ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return cls(nodes, rotation, hashlib.sha256(semantic.encode("utf-8")).hexdigest())

    def compact(self, max_nodes: int) -> tuple[list[dict], bool]:
        relevant = [
            node
            for node in self.nodes
            if node.text
            or node.resource_id
            or node.description
            or node.clickable
            or node.scrollable
            or node.focused
        ]
        return [node.as_dict() for node in relevant[:max_nodes]], len(relevant) > max_nodes

    def find(self, selector: Selector) -> list[Node]:
        filters = selector.model_dump(exclude_none=True, exclude={"index"})
        result = []
        for node in self.nodes:
            if all(
                value in node.text if key == "text_contains" else getattr(node, key) == value
                for key, value in filters.items()
            ):
                result.append(node)
        return result

    def resolve(self, selector: Selector) -> Node:
        nodes = self.find(selector)
        if not nodes:
            raise AndroidUseError("not_found", "Selector matched no elements")
        if selector.index is not None:
            if selector.index >= len(nodes):
                raise AndroidUseError(
                    "not_found", "Selector index exceeds match count", match_count=len(nodes)
                )
            return nodes[selector.index]
        if len(nodes) != 1:
            raise AndroidUseError(
                "ambiguous_selector",
                f"Selector matched {len(nodes)} elements; refine it or specify index",
                match_count=len(nodes),
                matches=[node.as_dict() for node in nodes[:20]],
            )
        return nodes[0]
