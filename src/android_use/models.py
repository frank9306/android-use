from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class BatchStep(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    action: Literal["tap", "swipe", "type_text", "press", "launch_app", "wait"]
    params: dict[str, Any] = Field(default_factory=dict)
