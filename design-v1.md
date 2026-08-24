# Failure Simulation Tool: Design v1

A local QA tool that sits between a client and a real HTTP API, then injects
controlled failures into selected requests. Requests that do not match an
active rule are forwarded to the target API unchanged.

```text
Client -> Failure Simulation Tool -> Target API
                     |
                     +-> simulated response when a rule matches
```

## Problem

Testing unhappy paths often requires changing a backend, waiting for a test
environment to enter a specific state, or maintaining one-off mocks. This tool
is intended to let a QA engineer reproduce those conditions on demand without
changing either the client or the target service.

Examples include:

- returning `500`, `429`, or another HTTP error;
- adding a fixed response delay;
- returning a custom body with a chosen status and headers;
- applying a failure only to a selected method and path;
- temporarily disabling a rule and falling back to the real API.

## First MVP

The first version proves one complete workflow:

1. Configure one target API URL.
2. Define a rule using an HTTP method and an exact path.
3. Choose either a predefined HTTP error or a custom HTTP response.
4. Enable or disable the rule.
5. Send traffic through the simulator.
6. Return the simulated response when the rule matches.
7. Proxy every other request to the target API.

The first release is successful when this can be demonstrated from the command
line. A web UI and persistent storage are not required to validate the core.

### Initial scenario model

```json
{
  "name": "Users service unavailable",
  "enabled": true,
  "match": {
    "method": "GET",
    "path": "/api/users"
  },
  "response": {
    "status": 503,
    "headers": {
      "content-type": "application/json"
    },
    "body": {
      "error": "service unavailable"
    },
    "delay_ms": 0
  }
}
```

For the MVP, matching is deliberately limited to an exact method and path.
Query parameters, headers, body matching, probabilities, and request counters
can be added after the basic proxy path is reliable.

## Suggested architecture

```text
app/
├── api/                 # management API for rules and configuration
├── core/
│   ├── matcher.py       # selects an active rule
│   ├── proxy.py         # forwards unmatched HTTP requests
│   └── response.py      # builds simulated responses
├── models/              # validated configuration models
└── main.py              # application and proxy entry point
```

Suggested initial stack:

- Python 3.12+
- FastAPI and Pydantic
- HTTPX for async proxy requests
- pytest for matcher and integration tests
- in-memory configuration for the first vertical slice

## Implementation order

### Iteration 1: headless vertical slice

- application skeleton and health endpoint;
- target URL configuration through an environment variable;
- in-memory rule repository with one seed rule;
- exact method/path matcher;
- simulated response builder;
- transparent forwarding of method, path, query, body, and safe headers;
- integration tests using a disposable upstream API.

### Iteration 2: management API

- create, list, update, enable, disable, and delete rules;
- validation for statuses, headers, body, and delay;
- predefined HTTP failure templates;
- OpenAPI examples and a small demo script.

### Iteration 3: usable product shell

- persistent storage (SQLite is sufficient initially);
- request history marked as `simulated` or `proxied`;
- minimal web UI for projects and rules;
- Docker image and Docker Compose demo.

### Later, only after usage validates the need

- probability and request-count behaviours;
- malformed or mutated upstream responses;
- advanced request matching;
- multiple projects and target APIs;
- export/import of configurations;
- Kubernetes deployment or cluster integrations.

## Explicit non-goals for the first version

- Kubernetes or service-mesh traffic management;
- TCP-level failures such as a true connection reset;
- multi-user authentication and permissions;
- a visual scenario builder;
- production-scale observability or distributed storage.

These are useful future directions, but they do not need to be solved before
the core fault-injection proxy is proven.

## First development task

Build an executable FastAPI service with one hard-coded rule:

```text
GET /api/users -> 503 simulated response
all other requests -> target API
```

Cover both branches with integration tests. This establishes the central
abstraction of the project and provides a stable base for the management API
and UI.
