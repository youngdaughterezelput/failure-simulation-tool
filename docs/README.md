# Documentation

All design and product documentation for Failure Simulation Tool lives in this
directory.

- [Design v1](design-v1.md) describes the original problem, MVP, architecture,
  and longer-term product direction.
- [Application architecture and sequence diagrams](application-architecture.md)
  explains every layer, dependency boundaries, and the runtime request flows.
- [Control plane and proxy routing](control-plane-routing.md) defines the
  `/_simulator/*` namespace and explains how requests are classified.
- [Rule behaviours](rule-behaviors.md) defines probability and request-count
  behaviour, persistent runtime state, decision reasons, and reset semantics.
- [Roadmap](roadmap.md) tracks completed and planned iterations.

The running application also publishes generated OpenAPI documentation at
`/_simulator/docs` and its schema at `/_simulator/openapi.json`.
