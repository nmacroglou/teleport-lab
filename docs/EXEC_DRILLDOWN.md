# Unified Identity Layer: executive drill-down

One story, three levels. Every page carries the time range and data source forward.

```
L0  tp_identity            Unified Identity Layer (the hub: one picture, every tile is a link)
 |
 +-- L1  id_ai_agents      AI agents: behavior watch        (non-deterministic actors, main event)
 +-- L1  id_humans         Humans: who, how they log in, standing privilege
 +-- L1  id_workloads      Workloads / machines: renewal rhythm, credential lifetime
 +-- L1  id_refusals       Identity security: what policy refused, by class
 +-- L1  id_governance     Access and governance: roles as code vs. changed by people
 +-- L1  id_estate         Software estate: k8s, apps, databases, servers, client addresses
 +-- L1  id_trust          Hardware root-of-trust: MFA share, credential lifetimes
        |
        +-- L2  id_actor   One identity: profile, behavior, timeline, raw events
```

Exec workflow: hub (is anything on fire?) -> L1 (which actor class?) -> click a row -> L2 (what exactly did it do?).

## KPI dictionary (behavior of non-deterministic actors)

| KPI | Meaning | Why it matters |
|---|---|---|
| Refusal % | Share of an actor's actions Teleport refused | Off-script intent; the boundary held |
| Write attempts | Tries to change data (DB writes, admin users) | Read-only agents should not try |
| New behavior % | Actions never seen before for that identity (first-seen signature) | Drift from baseline |
| Retry after a no | Same actor tries again within 10 minutes of a refusal | Persistence, not accident |
| Action entropy | Shannon entropy of the action mix | Deterministic bots are low; agents are high |
| Renewal rhythm | Coefficient of variation of gaps between credential renewals: Clockwork / Mostly regular / Erratic | Machines that behave like humans (or the reverse) |
| Off-hours, external IPs | Activity outside working hours; non-RFC1918, non-loopback sources | Context anomalies |
| MFA % | Successful logins with a registered MFA device | Human assurance |
| Standing privilege | Credentials with TTL over 24 h | Zero standing credentials goal |
| As-code share | Roles defined as code vs. changed by people | Governance drift |
| Watch level | Investigate (refusal >= 10% or new behavior >= 50%), Watch, Normal | One-word triage |

Some Teleport codes used: TDB00W (admin DB user refused), TDB03W (DB write rejected; event shape approximated, verify on a live event), T3007W (SSH principal denied), T1000W (bad credentials).

## Rebuild

```
python3 scripts/dash_identity_drilldowns.py
```
Idempotent. Then reload views: `/en-US/splunkd/__raw/servicesNS/nobody/teleport_lab/data/ui/views/_reload` and `.../nav/_reload`.
