# Failure Simulation Tool: Roadmap

This document tracks delivery progress. Product decisions and architectural
context are documented separately in [Design v1](design-v1.md).

## Iteration 1: headless vertical slice — completed

- [x] Application skeleton and health endpoint.
- [x] Target URL configuration through an environment variable.
- [x] In-memory rule repository with one seed rule.
- [x] Exact method and path matcher.
- [x] Simulated response builder.
- [x] Forwarding of method, path, query, body, and safe headers.
- [x] Integration tests using a disposable upstream API.

The initial vertical slice proves the central behaviour:

```text
GET /api/users -> 503 simulated response
all other requests -> target API
```

## Iteration 2: management API — in progress

- [x] Create, list, update, enable, disable, and delete rules.
- [ ] Extend validation for statuses, headers, body, and delay.
- [ ] Add predefined HTTP failure templates.
- [ ] Add OpenAPI examples and a small demo script.

## Iteration 3: usable product shell — planned

- [ ] Add persistent storage; SQLite is sufficient initially.
- [ ] Record request history with `simulated` or `proxied` outcomes.
- [ ] Build a minimal web UI for projects and rules.
- [ ] Provide a Docker image and Docker Compose demo.

## Later

- [ ] Probability and request-count behaviours.
- [ ] Malformed or mutated upstream responses.
- [ ] Advanced request matching.
- [ ] Multiple projects and target APIs.
- [ ] Configuration export and import.
- [ ] Kubernetes deployment or cluster integrations.
