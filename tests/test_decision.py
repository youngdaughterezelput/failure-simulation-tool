from uuid import UUID

from app.core.decision import RuleDecisionEngine
from app.models import (
    DecisionReason,
    FailureRule,
    RequestMatch,
    RuleBehavior,
    SimulatedResponse,
)
from app.runtime_repository import InMemoryRuleRuntimeRepository


class SequenceProbabilitySource:
    def __init__(self, *values: float) -> None:
        self._values = iter(values)

    def sample(self, *, rule: FailureRule, matched_count: int) -> float:
        del rule, matched_count
        return next(self._values)


def make_rule(behavior: RuleBehavior) -> FailureRule:
    return FailureRule(
        id=UUID("00000000-0000-0000-0000-000000000042"),
        name="Decision test",
        match=RequestMatch(method="GET", path="/decision"),
        response=SimulatedResponse(status=503),
        behavior=behavior,
    )


def test_always_behavior_updates_runtime_state() -> None:
    repository = InMemoryRuleRuntimeRepository()
    engine = RuleDecisionEngine(repository)
    rule = make_rule(RuleBehavior())

    decision = engine.decide(rule)

    assert decision.simulate is True
    assert decision.reason is DecisionReason.ALWAYS
    assert decision.state.matched_count == 1
    assert decision.state.simulated_count == 1
    assert decision.state.last_triggered_at is not None


def test_skip_and_count_limit_are_applied_in_order() -> None:
    engine = RuleDecisionEngine(InMemoryRuleRuntimeRepository())
    rule = make_rule(RuleBehavior(skip_matches=2, max_simulations=2))

    decisions = [engine.decide(rule) for _ in range(5)]

    assert [decision.reason for decision in decisions] == [
        DecisionReason.SKIP_MATCH,
        DecisionReason.SKIP_MATCH,
        DecisionReason.ALWAYS,
        DecisionReason.ALWAYS,
        DecisionReason.COUNT_EXHAUSTED,
    ]
    assert decisions[-1].state.matched_count == 5
    assert decisions[-1].state.simulated_count == 2


def test_probability_hit_and_miss_use_injected_source() -> None:
    engine = RuleDecisionEngine(
        InMemoryRuleRuntimeRepository(),
        SequenceProbabilitySource(0.2, 0.8),
    )
    rule = make_rule(RuleBehavior(probability=0.5))

    hit = engine.decide(rule)
    miss = engine.decide(rule)

    assert hit.reason is DecisionReason.PROBABILITY_HIT
    assert hit.simulate is True
    assert miss.reason is DecisionReason.PROBABILITY_MISS
    assert miss.simulate is False
    assert miss.state.matched_count == 2
    assert miss.state.simulated_count == 1


def test_seed_produces_reproducible_decision_sequence() -> None:
    rule = make_rule(RuleBehavior(probability=0.5, seed=42))
    first_engine = RuleDecisionEngine(InMemoryRuleRuntimeRepository())
    second_engine = RuleDecisionEngine(InMemoryRuleRuntimeRepository())

    first = [first_engine.decide(rule).reason for _ in range(10)]
    second = [second_engine.decide(rule).reason for _ in range(10)]

    assert first == second
