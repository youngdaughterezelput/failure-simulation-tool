from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class RuleBehavior(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "probability": 0.3,
                    "skip_matches": 2,
                    "max_simulations": 5,
                    "seed": 42,
                }
            ]
        },
    )

    probability: float = Field(default=1.0, gt=0, le=1)
    skip_matches: int = Field(default=0, ge=0, le=1_000_000)
    max_simulations: int | None = Field(default=None, ge=1, le=1_000_000)
    seed: int | None = None


class RuleRuntimeState(BaseModel):
    model_config = ConfigDict(frozen=True)

    rule_id: UUID
    matched_count: int = Field(default=0, ge=0)
    simulated_count: int = Field(default=0, ge=0)
    last_triggered_at: datetime | None = None


class DecisionReason(StrEnum):
    ALWAYS = "always"
    PROBABILITY_HIT = "probability_hit"
    PROBABILITY_MISS = "probability_miss"
    SKIP_MATCH = "skip_match"
    COUNT_EXHAUSTED = "count_exhausted"
    NO_MATCHING_RULE = "no_matching_rule"
