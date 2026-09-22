import hashlib
import random
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import RLock
from typing import Protocol
from uuid import UUID

from app.models import (
    DecisionReason,
    FailureRule,
    RuleRuntimeState,
)
from app.runtime_repository import RuleRuntimeRepository


@dataclass(frozen=True, slots=True)
class RuleDecision:
    simulate: bool
    reason: DecisionReason
    rule_id: UUID
    state: RuleRuntimeState


@dataclass(frozen=True, slots=True)
class BehaviorContext:
    rule: FailureRule
    state: RuleRuntimeState


class ProbabilitySource(Protocol):
    def sample(self, *, rule: FailureRule, matched_count: int) -> float: ...


class ReproducibleProbabilitySource:
    def __init__(self, random_source: random.Random | None = None) -> None:
        self._random = random_source or random.Random()

    def sample(self, *, rule: FailureRule, matched_count: int) -> float:
        if rule.behavior.seed is None:
            return self._random.random()
        material = f"{rule.id}:{rule.behavior.seed}:{matched_count}".encode()
        digest = hashlib.sha256(material).digest()
        return int.from_bytes(digest[:8], "big") / 2**64


class BehaviorPolicy(Protocol):
    def evaluate(self, context: BehaviorContext) -> DecisionReason | None: ...


class SkipMatchesPolicy:
    def evaluate(self, context: BehaviorContext) -> DecisionReason | None:
        if context.state.matched_count <= context.rule.behavior.skip_matches:
            return DecisionReason.SKIP_MATCH
        return None


class CountLimitPolicy:
    def evaluate(self, context: BehaviorContext) -> DecisionReason | None:
        limit = context.rule.behavior.max_simulations
        if limit is not None and context.state.simulated_count >= limit:
            return DecisionReason.COUNT_EXHAUSTED
        return None


class ProbabilityPolicy:
    def __init__(self, source: ProbabilitySource) -> None:
        self._source = source

    def evaluate(self, context: BehaviorContext) -> DecisionReason | None:
        probability = context.rule.behavior.probability
        if probability == 1:
            return None
        sample = self._source.sample(
            rule=context.rule,
            matched_count=context.state.matched_count,
        )
        if sample >= probability:
            return DecisionReason.PROBABILITY_MISS
        return None


class CompositeBehaviorPolicy:
    def __init__(self, policies: tuple[BehaviorPolicy, ...]) -> None:
        self._policies = policies

    def evaluate(self, context: BehaviorContext) -> DecisionReason:
        for policy in self._policies:
            reason = policy.evaluate(context)
            if reason is not None:
                return reason
        if context.rule.behavior.probability < 1:
            return DecisionReason.PROBABILITY_HIT
        return DecisionReason.ALWAYS


class RuleDecisionEngine:
    def __init__(
        self,
        repository: RuleRuntimeRepository,
        probability_source: ProbabilitySource | None = None,
    ) -> None:
        self._repository = repository
        self._lock = RLock()
        self._policy = CompositeBehaviorPolicy(
            (
                SkipMatchesPolicy(),
                CountLimitPolicy(),
                ProbabilityPolicy(
                    probability_source or ReproducibleProbabilitySource()
                ),
            )
        )

    def decide(self, rule: FailureRule) -> RuleDecision:
        with self._lock:
            current = self._repository.get(rule.id)
            matched = current.model_copy(
                update={"matched_count": current.matched_count + 1}
            )
            reason = self._policy.evaluate(BehaviorContext(rule, matched))
            simulate = reason in {
                DecisionReason.ALWAYS,
                DecisionReason.PROBABILITY_HIT,
            }
            state = matched
            if simulate:
                state = matched.model_copy(
                    update={
                        "simulated_count": matched.simulated_count + 1,
                        "last_triggered_at": datetime.now(UTC),
                    }
                )
            self._repository.save(state)
            return RuleDecision(
                simulate=simulate,
                reason=reason,
                rule_id=rule.id,
                state=state,
            )
