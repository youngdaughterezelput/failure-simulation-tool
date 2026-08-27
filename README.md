# Failure Simulation Tool

‼️A local QA tool for injecting controlled failures between an HTTP client and a
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

The service is built with FastAPI and currently uses an in-memory rule store.
Rules define an exact HTTP method and path together with the status, headers,
body, and optional delay of the simulated response.

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
`UPSTREAM_TIMEOUT_SECONDS`.
