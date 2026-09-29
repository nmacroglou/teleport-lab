# Splunk dashboards

Splunk Enterprise 10.4.3 runs in Docker on the Mac (`http://127.0.0.1:8000`). The app `teleport_lab` holds everything Splunk needs.

## Data model

| Item | Value |
|---|---|
| Real events | index `teleport`, sourcetype `teleport:audit` |
| Synthetic demo events | index `teleport_demo`, sourcetype `teleport:audit`, field `demo=true` |
| Parsing | JSON (`KV_MODE=json`), timestamp from `"time"`, join-token names masked before indexing |

Every dashboard starts from one shared base search (in `scripts/build_dashboards.py`, `PRELUDE`) that derives:

| Field | Meaning |
|---|---|
| `actor` | Who did it (user, identity or bot name) |
| `actor_type` | `human`, `machine` or `system` |
| `actor_class` | `human`, `ai_agent` (bot names starting `bot-claude`, `bot-copilot`, `bot-lab`), `workload` or `system` |
| `outcome` | `denied` if `success=false` or the event code ends in `W`, else `allowed` |
| `resource`, `src_ip`, `hour_utc`, `ttl_h`, `is_write` | Target, source address, hour, certificate lifetime in hours, write-attempt flag |
| `deny_reason`, `control`, `meaning` | Plain-English reason a request was refused, and which control refused it |

## Two editions

**Dashboard Studio** (recommended for the demo): dark canvas, sparkline tiles, Sankey, click-through drill-downs. Fixed 1920 px canvas that auto-scales.

| Menu name | File | Purpose |
|---|---|---|
| Trust Scorecard (Studio) | `tp_studio_scorecard` | Short-lived credentials, attribution, what policy blocked, customer before/after |
| Unified Identity Layer (Studio) | `tp_studio_identity` | Humans, machines, AI agents; Sankey; four-level "why refused" drill-down; operating model |
| Demo scenes (Studio): Onboarding, Auditor, AI Agent, Security | `tp_studio_onboarding`, `tp_studio_auditor`, `tp_studio_agent`, `tp_studio_security` | The four demo scenes |

**Classic (Simple XML)**: the fallback, with the same content: `tp_scorecard`, `tp_identity`, `tp_onboarding`, `tp_auditor`, `tp_agent`, `tp_security`, and the **Command Center** (`teleport_overview`).

## The drill-down ("Why was the AI agent refused?")

| Level | Shows |
|---|---|
| 1 | Reason for denial and the control that refused (for example role-based access control) |
| 2 | Which identities were denied for that reason |
| 3 | The exact events |
| 4 | The raw audit event (evidence card) |

The filters (identity class, reason, who, event, time, data source) stay applied at every level. In the classic Command Center they are also in the URL, so a drill can be bookmarked.

## Build and reload

Dashboards are generated from Python so they stay consistent and reviewable:

```bash
python3 scripts/build_dashboards.py          # classic views + navigation
python3 scripts/dash_studio_identity.py      # Studio: Unified Identity Layer
python3 scripts/dash_studio_scorecard.py     # Studio: Trust Scorecard
python3 scripts/dash_studio_scenes.py        # Studio: four scenes
```

Then reload Splunk views. Both steps are needed:

1. Open `/en-US/splunkd/__raw/servicesNS/nobody/teleport_lab/data/ui/views/_reload`
2. Open `/en-US/debug/refresh` and click **Refresh**

## Things to know (lessons learned)

- Post-process searches only see fields named in the base search, so the base ends with an explicit `| fields` list.
- In Simple XML, `$$` means a literal `$`.
- HTML panels must be well-formed and placed directly in the tag, not inside CDATA.
- In Dashboard Studio, `splunk.text` does not exist here; text uses `splunk.markdown`.
- A `db.session.query` marked *allowed* means Teleport forwarded and logged it. The read-only database user is what refuses writes.
- Kubernetes denial codes in the synthetic data are approximate.
- Hardware-backed keys (HSM/TPM) are not modelled in this lab.
