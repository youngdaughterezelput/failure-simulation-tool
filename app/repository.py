from collections.abc import Sequence

from app.models import FailureRule, RequestMatch, SimulatedResponse


class InMemoryRuleRepository:
    def __init__(self, rules: Sequence[FailureRule] = ()) -> None:
        self._rules = list(rules)

    def list(self) -> tuple[FailureRule, ...]:
        return tuple(self._rules)


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
