from app.core.matcher import find_matching_rule
from app.models import FailureRule, RequestMatch, SimulatedResponse


def make_rule(*, enabled: bool = True) -> FailureRule:
    return FailureRule(
        name="test rule",
        enabled=enabled,
        match=RequestMatch(method="get", path="/api/users"),
        response=SimulatedResponse(status=503),
    )


def test_matches_enabled_rule_by_exact_method_and_path() -> None:
    rule = make_rule()

    assert (
        find_matching_rule([rule], method="GET", path="/api/users") is rule
    )


def test_does_not_match_a_different_method_or_path() -> None:
    rule = make_rule()

    assert find_matching_rule([rule], method="POST", path="/api/users") is None
    assert find_matching_rule([rule], method="GET", path="/api/users/1") is None


def test_does_not_match_a_disabled_rule() -> None:
    assert (
        find_matching_rule(
            [make_rule(enabled=False)],
            method="GET",
            path="/api/users",
        )
        is None
    )

