from collections.abc import Sequence
from uuid import UUID

from app.models import FailureRule, RequestMatch, RuleCreate, SimulatedResponse


class InMemoryRuleRepository:
    def __init__(self, rules: Sequence[FailureRule] = ()) -> None:
        self._rules = list(rules)

    def list(self) -> tuple[FailureRule, ...]:
        return tuple(self._rules)

    def get(self, rule_id: UUID) -> FailureRule | None:
        return next((rule for rule in self._rules if rule.id == rule_id), None)

    def create(self, data: RuleCreate) -> FailureRule:
        rule = FailureRule(**data.model_dump())
        self._rules.append(rule)
        return rule

    def update(self, rule_id: UUID, data: RuleCreate) -> FailureRule | None:
        index = self._find_index(rule_id)
        if index is None:
            return None

        rule = FailureRule(id=rule_id, **data.model_dump())
        self._rules[index] = rule
        return rule

    def set_enabled(self, rule_id: UUID, *, enabled: bool) -> FailureRule | None:
        index = self._find_index(rule_id)
        if index is None:
            return None

        rule = self._rules[index].model_copy(update={"enabled": enabled})
        self._rules[index] = rule
        return rule

    def delete(self, rule_id: UUID) -> bool:
        index = self._find_index(rule_id)
        if index is None:
            return False

        del self._rules[index]
        return True

    def _find_index(self, rule_id: UUID) -> int | None:
        return next(
            (index for index, rule in enumerate(self._rules) if rule.id == rule_id),
            None,
        )


def seed_rules() -> tuple[FailureRule, ...]:
    return (
        FailureRule(
            name="Users service unavailable",
            match=RequestMatch(method="GET", path="/api/users"),
            response=SimulatedResponse(
                status=503,
                headers={"content-type": "application/json"},
                body={"error": "service unavailable"},
            ),
        ),
    )
