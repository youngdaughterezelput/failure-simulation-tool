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

## Delivery plan

Implementation progress and planned iterations are tracked in the separate
[Roadmap](roadmap.md).

## Explicit non-goals for the first version

- Kubernetes or service-mesh traffic management;
- TCP-level failures such as a true connection reset;
- multi-user authentication and permissions;
- a visual scenario builder;
- production-scale observability or distributed storage.

These are useful future directions, but they do not need to be solved before
the core fault-injection proxy is proven.

## Future direction: product and Kubernetes integration

The long-term direction is to let a product team connect a test environment,
import its service configuration, and manage prepared failure scenarios through
the UI.

The simulator should not modify application code or inject invalid checks into
running services. It should remain a controlled traffic intermediary: a
matching request receives a simulated response, while an unmatched request is
sent to the real service.

```text
                        Management UI
                              |
                     projects / rules / runs
                              |
                    Management API
                              |
           +------------------+------------------+
           |                                     |
     Local proxy mode                     Kubernetes mode
           |                                     |
     Target API URL                    Agent inside cluster
                                                 |
                                   services / ingress / routes
```

### Product-oriented workflow

A user creates or imports a product environment:

```text
Project: Payments
Environment: QA
Connection: payments-qa
Namespace: payments-qa
```

The UI then presents the configured or discovered services:

```text
payment-api
order-api
billing-api
notification-api
```

The user selects a service and activates a prepared scenario:

```text
Service: payment-api
Endpoint: POST /api/payments
Scenario: 503 Service Unavailable
Duration: 15 minutes
```

The client must then send test traffic through a simulator address or through a
temporary test-only route. The exact routing mechanism depends on the selected
deployment mode.

### Kubernetes connection modes

Entering a cluster IP, username, and password is not the preferred connection
model. Kubernetes access should use its native authentication and authorization
mechanisms.

#### Simulator deployed inside a cluster

The initial Kubernetes version should be installed into a QA cluster with
Helm. It receives a dedicated Kubernetes ServiceAccount and narrowly scoped
RBAC permissions.

```text
Helm release
├── Management API
├── Web UI
├── Simulator proxy
└── Cluster integration component
```

Running inside the cluster provides access to internal service DNS names and
does not require exposing the Kubernetes API or private backend services to an
external system.

The first permission set should be read-only and limited to selected
namespaces. Automatic traffic changes require a separate, explicitly enabled
permission set.

#### Central control plane with a cluster agent

When several products or clusters need one UI, a small agent can run in each
cluster and establish an outbound authenticated connection to a central
management service.

```text
Central UI and Management API
              |
        secure agent channel
              |
      +-------+-------+
      |               |
 QA cluster A    QA cluster B
      |               |
    agent           agent
```

This avoids storing broad cluster credentials in the central application and
does not require opening the Kubernetes API to incoming internet traffic.

Uploading a kubeconfig can be supported as a local development convenience,
but it should not be the primary production deployment model.

### Product configuration

Each product should be able to keep a declarative configuration in its source
repository. The same configuration can be imported through the UI, applied by
a CLI, or delivered with a Helm release.

An initial format could look like this:

```yaml
apiVersion: failure-simulator.io/v1
kind: SimulationProject
metadata:
  name: payments
spec:
  environment: qa
  namespace: payments-qa

  services:
    - name: payment-api
      target: http://payment-api:8080
      endpoints:
        - method: POST
          path: /api/payments
        - method: GET
          path: /api/payments/{id}

  scenarios:
    - name: payment-service-unavailable
      enabled: false
      match:
        service: payment-api
        method: POST
        path: /api/payments
      response:
        status: 503
        body:
          error: service unavailable
```

This configuration gives the UI a product-specific catalogue of services,
endpoints, and prepared scenarios without requiring a QA engineer to recreate
them manually. Keeping it in Git also provides review, version history, and a
path toward GitOps synchronization.

Automatic discovery from Kubernetes Services, Ingress resources, or OpenAPI
documents may complement this manifest later. Discovery should not replace an
explicit product configuration because infrastructure metadata rarely contains
all expected endpoints and QA scenarios.

### Traffic routing strategies

There are three possible levels of integration. They should be implemented in
increasing order of operational risk.

#### Explicit simulator URL

The client uses a different base URL during a test run:

```text
Normal: frontend -> payment-api
Test:   frontend -> failure simulator -> payment-api
```

This is the safest initial Kubernetes mode. The normal Kubernetes Service is
not modified, and only clients intentionally configured for the test are
affected.

#### Dedicated proxy Service

The platform exposes a stable test-only service for each target, for example:

```text
payment-api.simulator.qa
```

Test workloads use this address while ordinary workloads continue using the
original `payment-api` Service.

#### Transparent traffic interception

The platform temporarily changes an Ingress, Service, sidecar, or service-mesh
route so that existing traffic passes through the simulator.

This provides the most convenient UX, but it also introduces the greatest
operational risk. It requires reliable rollback, compatibility with the chosen
Ingress or service mesh, strict environment controls, audit logging, and an
automatic expiration time. It should only be considered after explicit proxy
modes have been validated in real QA environments.

### Future domain model

The current in-memory `Rule` model will eventually need product and environment
context:

```text
Project
└── Environment
    ├── Cluster connection
    ├── Target services
    ├── Endpoints
    ├── Rules
    └── Simulation runs
```

A target could be represented independently of the failure rule:

```json
{
  "project": "payments",
  "environment": "qa",
  "target": {
    "type": "kubernetes_service",
    "cluster": "qa-cluster",
    "namespace": "payments",
    "service": "payment-api",
    "port": 8080
  }
}
```

An enabled flag alone is insufficient once scenarios affect shared test
environments. Activation should become a time-bounded `SimulationRun`:

```text
Scenario: Payment API unavailable
Environment: payments-qa
Started by: qa@example.com
Status: active
Expires after: 15 minutes
```

The run records who activated a scenario, its exact configuration, the target
environment, its start and expiration times, and whether it stopped normally or
was cancelled.

### UI responsibilities

The future UI should let a user:

- create projects and environments;
- connect or select a cluster integration;
- import and validate a product manifest;
- browse configured or discovered services and endpoints;
- create rules from templates or custom responses;
- start a time-bounded simulation run;
- see which simulations are active and which traffic they affect;
- stop one run or use an emergency stop for the environment;
- inspect an audit history of simulated and proxied requests.

The UI should always make the selected environment, affected service, routing
mode, and expiration time visible before activation.

### Safety requirements

Cluster integration must be designed around limited blast radius:

- production environments are denied by default;
- allowed clusters and namespaces are explicitly configured;
- agents and in-cluster components use least-privilege ServiceAccounts;
- read-only discovery and traffic mutation use separate permissions;
- every simulation has a maximum duration and automatic rollback;
- all activations, changes, and cancellations are audited;
- the UI exposes a prominent environment-wide emergency stop;
- startup reconciliation disables or repairs stale routes after a restart;
- product manifests are validated before any cluster change is applied.

### Recommended delivery sequence

This direction should be delivered incrementally:

1. Complete the local management API and rule validation.
2. Add projects, environments, and multiple target APIs.
3. Build the UI around explicit proxy URLs.
4. Add import and export of product manifests.
5. Publish a Docker image and Helm chart for in-cluster deployment.
6. Add read-only discovery of namespaces, Services, and Ingress resources.
7. Introduce an agent for centrally managed multi-cluster installations.
8. Add time-bounded simulation runs, audit history, and emergency stop.
9. Only then evaluate automatic Ingress, Service, or service-mesh routing.

The first useful product-level Kubernetes release therefore remains modest: a
team installs the simulator into a QA cluster, imports its product manifest,
and receives a UI with prepared services, endpoints, and scenarios. Clients use
an explicit simulator URL, so the platform delivers immediate value without
becoming a service mesh or silently changing shared traffic.
