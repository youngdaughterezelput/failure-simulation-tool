import json
import re
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.constants import CONTROL_PREFIX
from app.models.behavior import RuleBehavior


HTTP_TOKEN_PATTERN = re.compile(r"^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$")
FORBIDDEN_RESPONSE_HEADERS = {
    "connection",
    "content-length",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
}
BODYLESS_STATUSES = {204, 205, 304}
MAX_DELAY_MS = 60_000
MAX_BODY_BYTES = 1_048_576
MAX_HEADER_COUNT = 100
MAX_HEADER_BYTES = 16_384
RESERVED_PATH_PREFIXES = (CONTROL_PREFIX,)


def is_reserved_path(path: str) -> bool:
    return any(
        path == prefix or path.startswith(f"{prefix}/")
        for prefix in RESERVED_PATH_PREFIXES
    )


class HttpResponseValidator:
    """Validates response values before Starlette writes them to the wire."""

    @classmethod
    def validate_headers(cls, headers: dict[str, str]) -> dict[str, str]:
        if len(headers) > MAX_HEADER_COUNT:
            raise ValueError(f"at most {MAX_HEADER_COUNT} headers are allowed")

        normalized: dict[str, str] = {}
        total_bytes = 0
        for name, value in headers.items():
            lower_name = name.lower()
            if not HTTP_TOKEN_PATTERN.fullmatch(name):
                raise ValueError(f"invalid HTTP header name: {name!r}")
            if lower_name in normalized:
                raise ValueError(f"duplicate HTTP header name: {name!r}")
            if lower_name in FORBIDDEN_RESPONSE_HEADERS:
                raise ValueError(
                    f"header {name!r} is managed by the HTTP server"
                )
            if "\r" in value or "\n" in value or "\x00" in value:
                raise ValueError(f"invalid HTTP header value for {name!r}")
            try:
                value.encode("latin-1")
            except UnicodeEncodeError as error:
                raise ValueError(
                    f"header value for {name!r} must contain only latin-1 characters"
                ) from error
            total_bytes += len(name.encode("ascii")) + len(
                value.encode("latin-1")
            )
            if total_bytes > MAX_HEADER_BYTES:
                raise ValueError(
                    f"headers must not exceed {MAX_HEADER_BYTES} bytes"
                )
            normalized[lower_name] = value
        return normalized

    @classmethod
    def validate_body(cls, body: JsonValue) -> JsonValue:
        try:
            encoded = json.dumps(
                body,
                ensure_ascii=False,
                allow_nan=False,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise ValueError("body must be valid JSON") from error
        if len(encoded) > MAX_BODY_BYTES:
            raise ValueError(
                f"body must not exceed {MAX_BODY_BYTES} bytes when JSON encoded"
            )
        return body


class RequestMatch(BaseModel):
    model_config = ConfigDict(frozen=True)
    method: str
    path: str

    @field_validator("method")
    @classmethod
    def normalize_method(cls, value: str) -> str:
        return value.upper()

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str, info: ValidationInfo) -> str:
        if not value.startswith("/"):
            raise ValueError("path must start with '/'")
        allow_reserved = bool(
            info.context and info.context.get("allow_reserved_paths")
        )
        if is_reserved_path(value) and not allow_reserved:
            raise ValueError(
                "path is reserved by the simulator control plane"
            )
        return value


class SimulatedResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    status: int = Field(strict=True, ge=200, le=599)
    headers: dict[str, str] = Field(default_factory=dict)
    body: JsonValue = None
    delay_ms: int = Field(default=0, strict=True, ge=0, le=MAX_DELAY_MS)

    @field_validator("headers")
    @classmethod
    def validate_headers(cls, value: dict[str, str]) -> dict[str, str]:
        return HttpResponseValidator.validate_headers(value)

    @field_validator("body")
    @classmethod
    def validate_body(cls, value: JsonValue) -> JsonValue:
        return HttpResponseValidator.validate_body(value)

    @model_validator(mode="after")
    def validate_status_body_combination(self) -> "SimulatedResponse":
        if self.status in BODYLESS_STATUSES and self.body is not None:
            raise ValueError(f"status {self.status} cannot have a response body")
        return self


class RuleCreate(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        json_schema_extra={
            "examples": [
                {
                    "name": "Payments rate limited",
                    "enabled": True,
                    "project_id": "00000000-0000-0000-0000-000000000001",
                    "match": {"method": "POST", "path": "/api/payments"},
                    "response": {
                        "status": 429,
                        "headers": {
                            "content-type": "application/json",
                            "retry-after": "30",
                        },
                        "body": {"error": "too many requests"},
                        "delay_ms": 250,
                    },
                    "behavior": {
                        "probability": 0.3,
                        "max_simulations": 5,
                        "seed": 42,
                    },
                }
            ]
        },
    )
    name: str = Field(min_length=1)
    enabled: bool = True
    project_id: UUID | None = None
    match: RequestMatch
    response: SimulatedResponse
    behavior: RuleBehavior = Field(default_factory=RuleBehavior)


class FailureRule(RuleCreate):
    id: UUID = Field(default_factory=uuid4)
