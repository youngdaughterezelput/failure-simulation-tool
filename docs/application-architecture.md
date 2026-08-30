# Application architecture and sequence diagrams

## System boundary

Failure Simulation Tool combines two planes in one FastAPI application:

- the **control plane** under `/_simulator/*` manages projects, rules,
  templates, counters, history, and the web UI;
- the **data plane** receives every other HTTP request, decides whether to
  simulate a response, and otherwise proxies the request to the configured
  upstream API.

```text
Browser / API client
        |
        +-- /_simulator/* --> control plane
        |
        +-- all other paths --> matcher --> decision engine
                                          |          |
                                          |          +--> upstream
                                          +--> simulated response
```

`app/main.py` is the composition root. It creates concrete repositories and
services, connects their dependencies, registers HTTP routes, and owns the
catch-all data-plane request flow.

## Directory structure and responsibilities

```text
failure-simulation-tool/
├── app/
│   ├── api/                    # thin control-plane HTTP adapters
│   ├── core/                   # matching, decisions, proxying, responses
│   ├── models/                 # validated domain and API models
│   ├── services/               # management use-case orchestration
│   ├── web/                    # browser dashboard
│   ├── main.py                 # composition root and data-plane entry point
│   ├── database.py             # SQLite schema, initialization, migrations
│   ├── repository.py           # rule repository interface + implementations
│   ├── project_repository.py   # project repository interface + implementations
│   ├── runtime_repository.py   # rule-counter repository + implementations
│   ├── history_repository.py   # history repository interface + implementations
│   ├── templates.py            # predefined failure catalogue
│   ├── config.py               # environment-backed runtime settings
│   └── constants.py            # shared routing constants
├── docs/                       # product and technical documentation
├── scripts/demo.py             # dependency-free management/data-plane demo
├── tests/                      # unit and integration tests
├── Dockerfile                  # production-like application image
└── docker-compose.yml          # simulator + disposable upstream demo
```

### `app/main.py`

This module wires the application together:

- reads `Settings`;
- creates SQLite repositories for normal startup or in-memory repositories
  when dependencies are injected by tests;
- creates `ProjectService`, `RuleService`, `RequestHistoryService`, and
  `RuleDecisionEngine`;
- mounts the UI and control-plane routers at `/_simulator`;
- processes all data-plane traffic in `simulate_or_proxy`;
- owns the reusable HTTPX client and converts upstream connection failures into
  a `502` response.

The created objects are kept in `application.state`. HTTP adapters retrieve
their service from that state instead of constructing dependencies themselves.

### `app/api/`

These modules are FastAPI adapters for the control plane:

- `projects.py` exposes project CRUD operations;
- `rules.py` exposes rule CRUD, enable/disable, runtime states, reset, and
  template-based creation;
- `templates.py` exposes the read-only predefined failure catalogue;
- `history.py` returns recent request decisions.

Routers validate transport input through Pydantic, call an application service
or catalogue, and translate results into HTTP status codes. Business decisions
do not belong in the routers.

### `app/services/`

Services implement management use cases:

- `ProjectService` prevents deletion of a project that still contains rules;
- `RuleService` validates project references, creates rules from templates,
  changes enabled state, deletes rules, lists counter states, and resets them;
- `RequestHistoryService` creates history entries and offers `record_safely`,
  ensuring a history-storage error does not break the proxied client request.

Services depend on repository protocols, not on SQLite classes. This keeps the
business layer testable and allows another storage implementation later.

### `app/core/`

The core modules handle data-plane behaviour:

- `matcher.py` selects the first enabled rule with an exact method and path;
- `decision.py` contains the OOP behaviour engine and its independent policies:
  `SkipMatchesPolicy`, `CountLimitPolicy`, and `ProbabilityPolicy`;
- `response.py` applies an optional delay and builds the configured simulated
  response;
- `proxy.py` builds the upstream URL, removes unsafe hop-by-hop headers,
  forwards method/query/body/headers, and maps the upstream response back to
  the client.

`RuleDecisionEngine` coordinates policies and persistent runtime state. The
policies decide *whether* a matched rule triggers; they do not know about
FastAPI, SQLite, or the upstream client.

### `app/models/`

Pydantic models define and validate the domain contract:

- `project.py`: `Project` and `ProjectCreate`;
- `rule.py`: exact request match, simulated response, rule create/update data,
  and stored failure rule;
- `behavior.py`: probability/count configuration, runtime counters, and
  decision-reason enum;
- `template.py`: predefined template and template-based rule request;
- `history.py`: request outcome and persisted history entry.

Validation is performed before invalid configuration can reach a repository.
This includes reserved control paths, HTTP status/delay limits, safe headers,
JSON-compatible body limits, and behaviour ranges.

### Repositories and `app/database.py`

Each storage concern has a protocol and two implementations:

| Concern | Protocol module | Production implementation | Test implementation |
| --- | --- | --- | --- |
| Rules | `repository.py` | `SQLiteRuleRepository` | `InMemoryRuleRepository` |
| Projects | `project_repository.py` | `SQLiteProjectRepository` | `InMemoryProjectRepository` |
| Counters | `runtime_repository.py` | `SQLiteRuleRuntimeRepository` | `InMemoryRuleRuntimeRepository` |
| History | `history_repository.py` | `SQLiteRequestHistoryRepository` | `InMemoryRequestHistoryRepository` |

`SQLiteDatabase` owns connection creation, transactions, schema initialization,
initial seed data, and compatible schema migrations. Project and rule
configuration is serialized as validated JSON. Runtime counters and request
history use dedicated columns for efficient updates and ordering.

### `app/web/`

The UI is deliberately dependency-free:

- `index.html` defines the dashboard and forms;
- `static/app.js` contains `ApiClient` and `Dashboard` classes;
- `static/styles.css` owns presentation and responsive layout.

`ApiClient` distinguishes control-plane calls, which receive the
`/_simulator` prefix, from `send()`, which deliberately sends a raw data-plane
request to the rule path.

## Dependency direction

```mermaid
flowchart LR
    UI[Web UI] --> API[FastAPI routers]
    API --> Services[Application services]
    Services --> Models[Domain models]
    Services --> RepoProtocols[Repository protocols]
    Core[Matcher and decision engine] --> Models
    Core --> RepoProtocols
    SQLiteRepos[SQLite repositories] -. implement .-> RepoProtocols
    MemoryRepos[In-memory repositories] -. implement .-> RepoProtocols
    SQLiteRepos --> DB[SQLiteDatabase]
    Main[main.py composition root] --> API
    Main --> Services
    Main --> Core
    Main --> SQLiteRepos
```

The outer composition root chooses implementations. Core policies and services
work against abstractions, which is the main OOP boundary in the application.

## Sequence: simulated or proxied request

This diagram describes a request to any path outside `/_simulator/*`.

```mermaid
sequenceDiagram
    autonumber
    actor Client
    participant Main as FastAPI catch-all<br/>main.py
    participant Rules as RuleRepository
    participant Matcher
    participant Engine as RuleDecisionEngine
    participant Runtime as RuntimeRepository
    participant Builder as ResponseBuilder
    participant Proxy
    participant Upstream
    participant History as RequestHistoryService
    participant HistoryRepo as HistoryRepository

    Client->>Main: HTTP method + path + query + headers + body
    Main->>Rules: list()
    Rules-->>Main: ordered rules
    Main->>Matcher: find first enabled exact match

    alt Matching rule found
        Matcher-->>Main: FailureRule
        Main->>Engine: decide(rule)
        Engine->>Runtime: get(rule.id)
        Runtime-->>Engine: matched/simulated counters
        Note over Engine: Increment matched_count<br/>skip → count limit → probability
        Engine->>Runtime: save(updated state)
        Runtime-->>Engine: persisted state
        Engine-->>Main: simulate + decision reason

        alt Decision is simulated
            Main->>Builder: build_simulated_response(rule.response)
            Note over Builder: Apply delay_ms when configured
            Builder-->>Main: configured HTTP response
            Main->>History: record_safely(simulated, reason, rule_id)
            History->>HistoryRepo: create(entry)
            HistoryRepo-->>History: stored entry
            Main-->>Client: simulated response
        else Behaviour says proxy
            Main->>Proxy: proxy_request(request, target URL)
            Proxy->>Upstream: forwarded HTTP request
            Upstream-->>Proxy: real HTTP response
            Proxy-->>Main: filtered upstream response
            Main->>History: record_safely(proxied, reason, rule_id)
            History->>HistoryRepo: create(entry)
            HistoryRepo-->>History: stored entry
            Main-->>Client: upstream response
        end
    else No matching enabled rule
        Matcher-->>Main: none
        Main->>Proxy: proxy_request(request, target URL)
        Proxy->>Upstream: forwarded HTTP request
        Upstream-->>Proxy: real HTTP response
        Proxy-->>Main: filtered upstream response
        Main->>History: record_safely(proxied, no_matching_rule)
        History->>HistoryRepo: create(entry)
        HistoryRepo-->>History: stored entry
        Main-->>Client: upstream response
    end
```

If the upstream connection fails, `main.py` returns `502`, records the request
as `proxied`, and keeps the applicable decision reason.

## Sequence: create a rule from a template

This diagram follows the web UI action, but the same API can be called directly
with `curl` or another client.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant UI as Dashboard
    participant Client as ApiClient
    participant Router as Rules API router
    participant Service as RuleService
    participant Projects as ProjectRepository
    participant Catalog as FailureTemplateCatalog
    participant Rules as RuleRepository
    participant DB as SQLiteDatabase

    User->>UI: Submit rule form
    UI->>UI: Build match + behaviour payload
    UI->>Client: post(/api/rules/from-template/{id})
    Client->>Router: POST /_simulator/api/rules/from-template/{id}
    Router->>Service: create_from_template(id, data)
    Service->>Catalog: get(template_id)
    Catalog-->>Service: predefined response
    opt project_id was provided
        Service->>Projects: get(project_id)
        Projects->>DB: SELECT project
        DB-->>Projects: project row
        Projects-->>Service: Project
    end
    Service->>Rules: create(validated RuleCreate)
    Rules->>DB: INSERT rule JSON
    DB-->>Rules: committed
    Rules-->>Service: FailureRule with UUID
    Service-->>Router: created rule
    Router-->>Client: HTTP 201 + rule JSON
    Client-->>UI: parsed rule
    UI->>Client: refresh rules and states
    Client-->>UI: current dashboard data
    UI-->>User: Render rule card
```

## Current architectural constraints

- Matching is exact by method and path; query/body/header matching is not yet
  part of rule selection.
- The first enabled matching rule owns the decision. A probability miss does
  not fall through to another rule.
- One simulator instance has one global `TARGET_API_URL`; projects currently
  organize rules but do not select different upstreams.
- Counter updates are serialized inside one process. Multiple Uvicorn workers
  or replicas need a stronger cross-process atomic update mechanism.
- History persistence is best-effort so an observability failure does not
  replace the intended simulated or upstream response.
