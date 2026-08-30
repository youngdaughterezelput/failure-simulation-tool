# Failure Simulation Tool

A local QA tool for injecting controlled failures between an HTTP client and a
real backend API. Matching requests receive a simulated response; unmatched
requests are transparently forwarded to the configured target.

```text
Client -> Failure Simulation Tool -> Target API
                     |
                     +-> simulated response when a rule matches
```

This makes unhappy-path testing reproducible without changing the client,
modifying the backend, or waiting for a shared environment to enter a specific
state.

The service is built with FastAPI and stores projects, rules, and request
history in SQLite.
Rules define an exact HTTP method and path together with the status, headers,
body, and optional delay of the simulated response.

The management API supports both custom responses and predefined failure
templates. Response configuration is validated before a rule is stored:

- statuses must be integers from `200` through `599`;
- header names and values must be safe for HTTP, and transport-managed headers
  such as `content-length` cannot be overridden;
- bodies must be JSON-compatible and no larger than 1 MiB;
- `204`, `205`, and `304` responses cannot have a body;
- delay must be an integer from `0` through `60000` milliseconds.

## Documentation

- [Design v1](design-v1.md) — product context, scope, and architecture.
- [Roadmap](roadmap.md) — implementation progress and planned iterations.
- Interactive API documentation — `/docs` on a running instance.

## Local development

Python 3.12 or newer is required.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/pytest
```

Start the service and point it at a running HTTP API:

```bash
TARGET_API_URL=http://localhost:9000 \
  .venv/bin/uvicorn app.main:app --reload --port 8080
```

The target defaults to `http://localhost:9000` and the upstream timeout defaults
to 30 seconds. They can be changed with `TARGET_API_URL` and
`UPSTREAM_TIMEOUT_SECONDS`. SQLite data is written to `failure-simulator.db` by
default; set `DATABASE_PATH` to use another location.

Open `http://localhost:8080/` for the web UI. It provides project creation,
template-based rule creation, enable/disable/delete actions, and recent request
history. Configuration and history survive application restarts.

Projects are organizational groups in the current single-target mode. All
enabled rules participate in matching; `TARGET_API_URL` remains global for the
running simulator instance.

Paths used by the management API and UI (`/api/rules`, `/api/projects`,
`/api/templates`, `/api/history`, `/health`, `/docs`, and `/static`) are local
and cannot be used as rule match paths. The UI's `Send` action sends one test
request to a rule's exact path and refreshes request history.

## Management API

The main endpoints are:

```text
GET    /api/projects
POST   /api/projects
PUT    /api/projects/{project_id}
DELETE /api/projects/{project_id}

GET    /api/rules
POST   /api/rules
PUT    /api/rules/{rule_id}
POST   /api/rules/{rule_id}/enable
POST   /api/rules/{rule_id}/disable
DELETE /api/rules/{rule_id}

GET    /api/templates
GET    /api/templates/{template_id}
POST   /api/rules/from-template/{template_id}

GET    /api/history?limit=100
```

For example, create a disabled `503 Service Unavailable` rule from a template:

```bash
curl -X POST http://localhost:8080/api/rules/from-template/service-unavailable \
  -H 'content-type: application/json' \
  -d '{
    "name": "Checkout unavailable",
    "enabled": false,
    "match": {"method": "POST", "path": "/api/checkout"}
  }'
```

Request and response schemas, including examples for custom and template-based
rules, are available at `/docs` and `/openapi.json`.

## Demo

With the service running on port 8080, the dependency-free demo lists the
templates, creates a rule, triggers its simulated response, disables it, and
then removes it:

```bash
python3 scripts/demo.py
```

Use `--url` if the simulator is running elsewhere.

## Docker Compose demo

Build and start the simulator together with a disposable upstream HTTP server:

```bash
docker compose up --build
```

Then open `http://localhost:8080/` or run `python3 scripts/demo.py`. Requests
without a matching rule are proxied to the `upstream` service. Simulator data
is retained in the named `simulator-data` volume.

Stop the services with `docker compose down`. Add `--volumes` only when you
also want to remove the persisted simulator database.
