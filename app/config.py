from dataclasses import dataclass
from os import environ


@dataclass(frozen=True, slots=True)
class Settings:
    target_api_url: str = "http://localhost:9000"
    upstream_timeout_seconds: float = 30.0
    database_path: str = "failure-simulator.db"

    @classmethod
    def from_environment(cls) -> "Settings":
        defaults = cls()
        return cls(
            target_api_url=environ.get("TARGET_API_URL", defaults.target_api_url),
            upstream_timeout_seconds=float(
                environ.get(
                    "UPSTREAM_TIMEOUT_SECONDS",
                    str(defaults.upstream_timeout_seconds),
                )
            ),
            database_path=environ.get("DATABASE_PATH", defaults.database_path),
        )
