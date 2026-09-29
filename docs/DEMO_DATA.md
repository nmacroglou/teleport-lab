# Demo data

The lab produces only a handful of real audit events, so the dashboards are filled with **synthetic** events that tell a realistic story. They are clearly separate from real data.

## Rules

- Stored in index **`teleport_demo`**, never in `index=teleport`.
- Every event carries `demo=true`.
- Files live in `demo-data/` (git-ignored) and are mounted read-only into Splunk at `/teleport-demo`.
- Generators are deterministic (fixed seeds) and **refuse to overwrite** existing files.

## Generators

| Script | Adds | Events |
|---|---|---|
| `scripts/gen_demo_events.py` | Pack 1: baseline traffic, logins, certificates, sessions, database queries, a few incidents | 2,466 |
| `scripts/gen_demo_events_pack2.py` | Pack 2: more people and bots, contractor incidents, onboarding of a new hire, Kubernetes activity | 1,757 |

```bash
python3 scripts/gen_demo_events.py --days 15
python3 scripts/gen_demo_events_pack2.py
```

Options include `--days`, `--out` and `--force`. Splunk picks up new files through the `[monitor:///teleport-demo/*.log]` input.

## The cast (fictional)

Humans such as anna.becker, dev.singh, ben.okafor (contractor with failed logins), lena.vogel (new hire), and bots such as `bot-monitoring`, `bot-ci-deploy`, `bot-claude-agent`, `bot-copilot-support`, `bot-terraform`. Any resemblance to real people is coincidental.

## Live scene helpers

| Script | What it does |
|---|---|
| `scripts/demo-status.sh` | Read-only pre-flight check before a demo |
| `scripts/demo-scene.sh 1` | Creates a real Teleport user (asks to confirm) |
| `scripts/demo-scene.sh 3` | Prints the Claude Code prompts for the AI-agent scene |
| `scripts/demo-scene.sh 4` | Sends a few failed logins for a made-up user, plus a bot SSH attempt |

These have been syntax-checked but are **not yet tested end to end**. Set `DEMO_INSECURE=1` only for local self-signed certificates.
