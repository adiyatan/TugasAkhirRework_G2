from __future__ import annotations

from pydantic import BaseModel, Field


class AiModelSwitchRequest(BaseModel):
    model: str = Field(..., min_length=2, max_length=120)
    usd_to_idr_rate: float | None = Field(default=None, gt=0)


class AiEvaluateRequest(BaseModel):
    candidate_model: str = Field(..., min_length=2, max_length=120)
    sample_size: int = Field(default=4, ge=1, le=7)
    compare_baseline: bool = True
