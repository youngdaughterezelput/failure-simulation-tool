#!/usr/bin/env python3
"""Demonstrate the management API against a running simulator."""

import argparse
import json
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


@dataclass(frozen=True)
class ApiResponse:
    status: int
    body: Any


class FailureSimulatorClient:
    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def request(self, method: str,path: str, payload: dict[str, Any] | None = None,) -> ApiResponse:
        data = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            f"{self._base_url}{path}",
            data=data,
            method=method,
            headers={"content-type": "application/json"},
        )
        try:
            with urlopen(request) as response:  # noqa: S310 - URL is user supplied.
                return self._read_response(response.status, response.read())
        except HTTPError as error:
            return self._read_response(error.code, error.read())

    @staticmethod
    def _read_response(status: int, content: bytes) -> ApiResponse:
        if not content:
            return ApiResponse(status=status, body=None)
        try:
            body = json.loads(content)
        except json.JSONDecodeError:
            body = content.decode(errors="replace")
        return ApiResponse(status=status, body=body)


class ManagementApiDemo:
    def __init__(self, client: FailureSimulatorClient) -> None:
        self._client = client

    def run(self) -> None:
        projects = self._client.request("GET", "/api/projects")
        self._show("Available projects", projects)
        if projects.status != 200 or not projects.body:
            raise RuntimeError("no project is available for the demo rule")

        templates = self._client.request("GET", "/api/templates")
        self._show("Available templates", templates)

        created = self._client.request(
            "POST",
            "/api/rules/from-template/service-unavailable",
            {
                "name": "Demo outage",
                "project_id": projects.body[0]["id"],
                "match": {"method": "GET", "path": "/demo/failure"},
            },
        )
        self._show("Created rule", created)
        if created.status != 201 or not isinstance(created.body, dict):
            raise RuntimeError("could not create the demo rule")

        rule_id = created.body["id"]
        try:
            simulated = self._client.request("GET", "/demo/failure")
            self._show("Simulated request", simulated)

            disabled = self._client.request(
                "POST", f"/api/rules/{rule_id}/disable"
            )
            self._show("Disabled rule", disabled)
        finally:
            deleted = self._client.request("DELETE", f"/api/rules/{rule_id}")
            self._show("Deleted rule", deleted)

    @staticmethod
    def _show(label: str, response: ApiResponse) -> None:
        print(f"\n{label} (HTTP {response.status})")
        print(json.dumps(response.body, indent=2, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--url",
        default="http://localhost:8080",
        help="simulator base URL (default: %(default)s)",
    )
    args = parser.parse_args()
    ManagementApiDemo(FailureSimulatorClient(args.url)).run()


if __name__ == "__main__":
    main()
