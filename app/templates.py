from collections.abc import Sequence

from app.models import FailureTemplate, SimulatedResponse


class FailureTemplateCatalog:
    """Read-only catalogue of reusable HTTP failure responses."""

    def __init__(self, templates: Sequence[FailureTemplate]) -> None:
        self._templates = tuple(templates)
        self._by_id = {template.id: template for template in templates}
        if len(self._by_id) != len(self._templates):
            raise ValueError("failure template ids must be unique")

    def list(self) -> tuple[FailureTemplate, ...]:
        return self._templates

    def get(self, template_id: str) -> FailureTemplate | None:
        return self._by_id.get(template_id)

    @classmethod
    def predefined(cls) -> "FailureTemplateCatalog":
        return cls(
            (
                FailureTemplate(
                    id="bad-request",
                    name="Bad Request",
                    description="Reject the request as invalid.",
                    response=SimulatedResponse(
                        status=400,
                        headers={"content-type": "application/json"},
                        body={"error": "bad request"},
                    ),
                ),
                FailureTemplate(
                    id="unauthorized",
                    name="Unauthorized",
                    description="Require valid client authentication.",
                    response=SimulatedResponse(
                        status=401,
                        headers={
                            "content-type": "application/json",
                            "www-authenticate": "Bearer",
                        },
                        body={"error": "unauthorized"},
                    ),
                ),
                FailureTemplate(
                    id="not-found",
                    name="Not Found",
                    description="Report that the requested resource does not exist.",
                    response=SimulatedResponse(
                        status=404,
                        headers={"content-type": "application/json"},
                        body={"error": "not found"},
                    ),
                ),
                FailureTemplate(
                    id="too-many-requests",
                    name="Too Many Requests",
                    description="Apply a temporary client rate limit.",
                    response=SimulatedResponse(
                        status=429,
                        headers={
                            "content-type": "application/json",
                            "retry-after": "30",
                        },
                        body={"error": "too many requests"},
                    ),
                ),
                FailureTemplate(
                    id="internal-server-error",
                    name="Internal Server Error",
                    description="Simulate an unexpected server failure.",
                    response=SimulatedResponse(
                        status=500,
                        headers={"content-type": "application/json"},
                        body={"error": "internal server error"},
                    ),
                ),
                FailureTemplate(
                    id="bad-gateway",
                    name="Bad Gateway",
                    description="Simulate an invalid response from a dependency.",
                    response=SimulatedResponse(
                        status=502,
                        headers={"content-type": "application/json"},
                        body={"error": "bad gateway"},
                    ),
                ),
                FailureTemplate(
                    id="service-unavailable",
                    name="Service Unavailable",
                    description="Make the service temporarily unavailable.",
                    response=SimulatedResponse(
                        status=503,
                        headers={
                            "content-type": "application/json",
                            "retry-after": "30",
                        },
                        body={"error": "service unavailable"},
                    ),
                ),
                FailureTemplate(
                    id="gateway-timeout",
                    name="Gateway Timeout",
                    description="Simulate a dependency timeout at a gateway.",
                    response=SimulatedResponse(
                        status=504,
                        headers={"content-type": "application/json"},
                        body={"error": "gateway timeout"},
                    ),
                ),
            )
        )
