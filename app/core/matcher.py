from collections.abc import Iterable

from app.models import FailureRule


def find_matching_rule(
    rules: Iterable[FailureRule], *, method: str, path: str,) -> FailureRule | None:
    normalized_method = method.upper()
    return next(
        (
            rule
            for rule in rules
            if rule.enabled
            and rule.match.method == normalized_method
            and rule.match.path == path
        ),
        None,
    )

