# Control plane and proxy routing

## Decision

The simulator owns one reserved URL namespace: `/_simulator` and everything
below `/_simulator/*`. Management endpoints, the web UI, health checks, static
assets, and generated API documentation all live there.

Every other path is data-plane traffic. It can match a failure rule or be
proxied to the configured upstream API.

```text
incoming request
       |
       +-- /_simulator/* --> management API, UI, health, docs, assets
       |
       +-- every other path
               |
               +-- matching enabled rule triggers --> simulated response
               |
               +-- no trigger ----------------------> upstream response
```

Examples:

| Request | Destination |
| --- | --- |
| `GET /_simulator/api/rules` | simulator management API |
| `GET /_simulator` | simulator web UI |
| `GET /_simulator/health` | simulator health endpoint |
| `GET /api/rules` | rule engine, then upstream if not simulated |
| `PUT /api/rules/123` | rule engine, then upstream if not simulated |
| `GET /` | rule engine, then upstream if not simulated |

## Why the namespace is necessary

Previously, management routes occupied common application paths such as
`/api/rules`. A real upstream API using the same path could never receive that
traffic: FastAPI resolved the simulator's management route first. Reserving a
single explicit namespace removes the ambiguity and makes routing predictable.

This is a breaking API change for management clients. Calls such as
`GET /api/rules` must become `GET /_simulator/api/rules`. It is intentionally
not kept as a compatibility alias: an alias would recreate the collision and
prevent `/api/rules` from being used by the upstream.

## Route ownership

The current control-plane endpoints are:

- `/_simulator/api/projects`
- `/_simulator/api/rules`
- `/_simulator/api/templates`
- `/_simulator/api/history`
- `/_simulator/health`
- `/_simulator/docs`, `/_simulator/redoc`, and
  `/_simulator/openapi.json`
- `/_simulator`, `/_simulator/ui`, and `/_simulator/static/*`

A rule whose exact path begins with `/_simulator` is rejected by validation.
The restriction applies only to the path namespace; method differences do not
make a control-plane path safe because present or future management routes may
use any HTTP method.

## Deployment consequence

Clients under test must use the simulator's base URL in place of the upstream
base URL. The path and query string remain the application's own values. For
example, if the real request is `https://api.example.test/api/orders?limit=10`,
the local test request is
`http://localhost:8080/api/orders?limit=10`—not a URL below `/_simulator`.

The browser dashboard is therefore available at
`http://localhost:8080/_simulator`; the root path `/` is deliberately available
to the upstream application.
