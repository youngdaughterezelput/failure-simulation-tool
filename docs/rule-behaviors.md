# Rule behaviours: probability and request counts

## Purpose

A matching rule no longer has to fail every request forever. Its `behavior`
controls when a simulated response is returned:

```json
{
  "probability": 0.3,
  "skip_matches": 2,
  "max_simulations": 5,
  "seed": 42
}
```

| Field | Meaning | Default | Valid values |
| --- | --- | --- | --- |
| `probability` | chance that an eligible match is simulated | `1.0` | greater than `0`, at most `1` |
| `skip_matches` | matching requests to proxy before the rule can trigger | `0` | `0` to `1,000,000` |
| `max_simulations` | successful simulations allowed before the rule is exhausted | `null` (unlimited) | `1` to `1,000,000`, or `null` |
| `seed` | makes the probability sequence reproducible for this rule | `null` (random) | any integer, or `null` |

To simulate no traffic, disable the rule. A probability of zero is rejected so
that the enabled/disabled state remains the single explicit off switch.

## Decision order

For the first enabled rule whose method and path match exactly, the engine:

1. increments `matched_count`;
2. proxies with `skip_match` while `matched_count <= skip_matches`;
3. proxies with `count_exhausted` if `simulated_count` has reached
   `max_simulations`;
4. evaluates probability and proxies with `probability_miss` on a miss;
5. otherwise returns the configured simulated response and increments
   `simulated_count`.

```text
exact match
    |
    +-- within initial skip window? -- yes --> proxy (skip_match)
    |
    +-- simulation limit reached? --- yes --> proxy (count_exhausted)
    |
    +-- probability miss? ----------- yes --> proxy (probability_miss)
    |
    +---------------------------------------> simulate
```

`max_simulations` counts only responses that were actually simulated.
Probability misses do not consume the limit, but every exact match increments
`matched_count`.

Example with `skip_matches=2`, `max_simulations=2`, and `probability=1`:

| Match number | Result | Reason | Counters after request |
| --- | --- | --- | --- |
| 1 | proxied | `skip_match` | matched 1, simulated 0 |
| 2 | proxied | `skip_match` | matched 2, simulated 0 |
| 3 | simulated | `always` | matched 3, simulated 1 |
| 4 | simulated | `always` | matched 4, simulated 2 |
| 5+ | proxied | `count_exhausted` | matched continues, simulated 2 |

## Probability and seed

Without `seed`, each eligible request uses a random sample. With a seed, the
sample is derived from the rule ID, seed, and current `matched_count`. Resetting
the counters therefore replays the same probability sequence for that rule.
Two different rules with the same seed still have different sequences because
their IDs differ.

Probability is evaluated per request, not as an exact batch quota. A `0.3`
probability does not guarantee exactly three simulations in ten requests.

## Persistent runtime state

Runtime state is stored separately from immutable rule configuration:

```json
{
  "rule_id": "3cfc5514-b4fc-41bf-971d-ffdb294a3847",
  "matched_count": 7,
  "simulated_count": 3,
  "last_triggered_at": "2026-08-30T18:10:00Z"
}
```

List all states with:

```bash
curl http://localhost:8080/_simulator/api/rules/states
```

Reset one rule with:

```bash
curl -X POST \
  http://localhost:8080/_simulator/api/rules/3cfc5514-b4fc-41bf-971d-ffdb294a3847/reset
```

Updating, disabling, or enabling a rule does not reset its counters. Reset is
an explicit action in both the API and web UI. Deleting a rule also deletes its
runtime state. SQLite persistence keeps rule state across application and
container restarts.

## Request history

Every data-plane request records an `outcome` and a `decision_reason`:

| Outcome | Decision reason | Meaning |
| --- | --- | --- |
| `simulated` | `always` | eligible rule with probability `1` triggered |
| `simulated` | `probability_hit` | probability sample triggered the rule |
| `proxied` | `skip_match` | request was inside the initial skip window |
| `proxied` | `probability_miss` | eligible probability sample did not trigger |
| `proxied` | `count_exhausted` | maximum simulations had already been reached |
| `proxied` | `no_matching_rule` | no enabled exact method/path rule matched |

A behavioural miss does not try a second matching rule; it proxies upstream.
Rule ordering therefore remains deterministic and a request has one decision.

## Implementation shape and current boundary

The implementation separates configuration models, runtime repositories,
decision policies, and the orchestration engine. SQLite and in-memory runtime
repositories implement the same interface, while skip, count-limit, and
probability checks are independent policies composed in a fixed order.

The decision engine serializes updates within one application process. The
current Docker and local examples run one Uvicorn worker. Strictly atomic
counters across multiple worker processes or replicas require a transactional
compare-and-update operation or an external shared counter store and are a
future scaling concern.
