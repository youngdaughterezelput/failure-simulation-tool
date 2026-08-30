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
body, optional delay, and triggering behaviour of the simulated response.

The management API supports both custom responses and predefined failure
templates. Response configuration is validated before a rule is stored:

- statuses must be integers from `200` through `599`;
- header names and values must be safe for HTTP, and transport-managed headers
  such as `content-length` cannot be overridden;
- bodies must be JSON-compatible and no larger than 1 MiB;
- `204`, `205`, and `304` responses cannot have a body;
- delay must be an integer from `0` through `60000` milliseconds.

## Documentation

- [Documentation index](docs/README.md) — all project documents.
- [Design v1](docs/design-v1.md) — product context, scope, and architecture.
- [Application architecture and sequence diagrams](docs/application-architecture.md)
  — module responsibilities and request flows.
- [Control plane and proxy routing](docs/control-plane-routing.md) — why the
  simulator owns only `/_simulator/*`.
- [Rule behaviours](docs/rule-behaviors.md) — probability, counters, state,
  reset, and decision order.
- [Roadmap](docs/roadmap.md) — implementation progress and planned iterations.
- Interactive API documentation — `/_simulator/docs` on a running instance.

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

Open `http://localhost:8080/_simulator` for the web UI. It provides project
creation, template-based rule creation, probability and request-count settings,
enable/disable/reset/delete actions, a one-request `Send` action, and recent
request history. Configuration, counters, and history survive application
restarts.

Projects are organizational groups in the current single-target mode. All
enabled rules participate in matching; `TARGET_API_URL` remains global for the
running simulator instance.

Only `/_simulator` and `/_simulator/*` are reserved for the control plane. All
other paths belong to the data plane and may be matched or proxied. This means
an upstream endpoint such as `/api/rules` no longer conflicts with the
simulator's management API. The UI's `Send` action sends one test request to a
rule's exact path and refreshes its counters and request history.

## Management API

The main endpoints are:

```text
GET    /_simulator/api/projects
POST   /_simulator/api/projects
PUT    /_simulator/api/projects/{project_id}
DELETE /_simulator/api/projects/{project_id}

GET    /_simulator/api/rules
POST   /_simulator/api/rules
PUT    /_simulator/api/rules/{rule_id}
GET    /_simulator/api/rules/states
POST   /_simulator/api/rules/{rule_id}/enable
POST   /_simulator/api/rules/{rule_id}/disable
POST   /_simulator/api/rules/{rule_id}/reset
DELETE /_simulator/api/rules/{rule_id}

GET    /_simulator/api/templates
GET    /_simulator/api/templates/{template_id}
POST   /_simulator/api/rules/from-template/{template_id}

GET    /_simulator/api/history?limit=100
```

For example, create a disabled `503 Service Unavailable` rule from a template:

```bash
curl -X POST http://localhost:8080/_simulator/api/rules/from-template/service-unavailable \
  -H 'content-type: application/json' \
  -d '{
    "name": "Checkout unavailable",
    "enabled": false,
    "match": {"method": "POST", "path": "/api/checkout"},
    "behavior": {
      "probability": 0.3,
      "skip_matches": 2,
      "max_simulations": 5,
      "seed": 42
    }
  }'
```

Request and response schemas, including examples for custom and template-based
rules, are available at `/_simulator/docs` and
`/_simulator/openapi.json`. Behaviour defaults preserve the original mode:
every matching request is simulated with no count limit.

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

Then open `http://localhost:8080/_simulator` or run
`python3 scripts/demo.py`. Requests without a matching rule, and requests
skipped by a rule's behaviour, are proxied to the `upstream` service. Simulator
data is retained in the named `simulator-data` volume.

Stop the services with `docker compose down`. Add `--volumes` only when you
also want to remove the persisted simulator database.
