# Lab run guide: simulate failures on purpose

Use this guide to make safe, controlled failures happen in the lab, then watch Teleport refuse them and Splunk record them. Each exercise is small, reversible and only touches this lab.

> **Status:** the scene scripts are syntax-checked but **not yet run end to end**, and the extra exercises (F4 to F7) have **not been run on this lab**. Expected results below are what should happen; write down what you actually see (see [Record your results](#record-your-results)).

## Ground rules

- Run everything on the Mac that hosts the lab, from `~/teleport-lab`.
- Nothing here deletes files, removes volumes or changes Teleport roles. Never add `docker compose down -v`, `docker volume prune`, `docker system prune`, `rm -rf` or `tctl rm` to any exercise.
- Never paste invite links, join tokens or identity files anywhere. If output shows one, do not copy it.
- Do these against the **lab only**. Do not point them at any other Teleport cluster.
- If something behaves unexpectedly, stop and read the error first. Do not "fix" it by deleting data.

## 0. Before you start (pre-flight)

```bash
cd ~/teleport-lab
scripts/demo-status.sh          # read-only health check
docker compose ps               # everything should be "running" / "healthy"
```

Success looks like: Teleport, `linux-server-1`, `whoami`, `postgres` and `splunk` all running. If `tbot` is used for the AI scenes, check that `tbot/out/identity/identity` was updated in the last 20 minutes.

Find where to look afterwards:

| Where | How |
|---|---|
| Terminal (fast) | `scripts/audit-events.sh 20` (add a word to filter, for example `scripts/audit-events.sh 30 login`) |
| Splunk (classic or Studio) | Open the dashboard and set **Data source** to **Live lab data** (index `teleport`); wait about 10 seconds |
| Splunk search | `index=teleport (success=false OR code=*W) \| table _time event code user error` |

## The exercises

| # | Failure | How | Expected audit signal | Best dashboard |
|---|---|---|---|---|
| F1 | Wrong-password login flood | `scripts/demo-scene.sh 4` (part A) | Repeated failed `user.login` (code `T1000W`) | Security Watch |
| F2 | Bot tries SSH it is not allowed | `scripts/demo-scene.sh 4` (part B) | SSH denial for the bot (code `T3007W`) | Security Watch, Unified Identity Layer |
| F3 | AI agent tries to write | Claude Code prompts C and D from `scripts/demo-scene.sh 3` | Query recorded, then refused by the read-only database user | AI Agent Governance |
| F4 | Bot joins with a bad token | Throwaway `tbot` config (below) | Failed `bot.join` | Security Watch |
| F5 | Ask for a database user the role forbids | `tsh` with the bot identity (below) | Database access denied (code `TDB00W`) | Unified Identity Layer drill-down |
| F6 | Credential expires | Stop `tbot` renewal, wait past the 1-hour lifetime | New requests fail; no new certificates | Trust Scorecard |
| F7 | A resource goes away | `docker compose stop postgres`, then start it again | Database errors; sessions stop | AI Agent Governance |

Codes are the ones the dashboards use; confirm them in your own audit log.

### F1 and F2: failed logins and a denied bot

What we are doing: send 8 bad logins for a made-up user, then have the bot try SSH to a server its role does not allow.

```bash
scripts/demo-scene.sh 4
```

The script asks `[y/N]` before it acts. Answer `y` to run both parts.

Success looks like:
- 8 lines saying `HTTP 4xx` (Teleport refused each one).
- The bot line ends with `denied, as expected`.
- In Splunk, the failed-logins tile and the brute-force detector on Security Watch go up.

If it fails:
1. HTTP code is `404` or the bot step complains about certificates: rerun with `DEMO_INSECURE=1 scripts/demo-scene.sh 4` (local self-signed certificate only).
2. The bot step is skipped: `tbot/out/identity/identity` is missing, so check that `tbot` is running.
3. Nothing shows in Splunk: widen the time range and confirm **Live lab data** is selected.

### F3: the AI agent tries to write

What we are doing: ask Claude Code to try things a read-only identity must not be able to do.

```bash
scripts/demo-scene.sh 3
```

This only prints the prompts. Open Claude Code in this project and type them one at a time:

1. (allowed) "Using the teleport-databases tool, list the tables in labdb."
2. (allowed) "How many rows are in the servers table? Show name and role."
3. (refused) "Create a table called hack with one integer column."
4. (refused) "Delete every row from the servers table."

Success looks like: prompts 1 and 2 return data; prompts 3 and 4 fail with a read-only error, and no table appears or changes.

Honest detail: the audit line shows Teleport forwarded the query. The read-only database user (`labreader`, read-only by default) is what refuses the change. That is defence in depth, and it is why the agent starts read-only.

If it fails:
1. The tool is not available: restart Claude Code from the project folder so it reads `.mcp.json`.
2. Connection errors: check that `tbot` is running and the identity file is fresh.
3. Prompt 3 or 4 unexpectedly succeeds: stop, do not continue, and check the database user in `.mcp.json` is `labreader`.

### F4: a bot joins with a bad token (untested)

What we are doing: prove Teleport gives nothing to a bot with an unknown token. This uses a throwaway config in memory, so your real bot is untouched.

```bash
cat > /tmp/tbot-badtoken.yaml <<'YAML'
version: v2
proxy_server: localhost:3080
onboarding:
  join_method: token
  token: this-token-does-not-exist
storage:
  type: memory
services:
  - type: identity
    destination:
      type: memory
YAML
bin/tbot start --oneshot -c /tmp/tbot-badtoken.yaml --insecure
```

Success looks like: `tbot` exits with an error saying the token was not found or is expired, and no identity is issued.

If it fails:
1. `--insecure` not accepted: try without it (your local CA may already be trusted).
2. Unknown flag `--oneshot`: run `bin/tbot start --help` and use the one-shot option your version shows.
3. It appears to succeed: stop and tell Claude what it printed; do not repeat.

The fake token is not a secret. Never put a real join token in a command like this.

### F5: ask for a database user the role forbids (untested)

What we are doing: use the bot identity to ask for the `postgres` superuser, which `bot-lab-readonly` does not allow.

```bash
bin/tsh -i tbot/out/identity/identity --proxy localhost:3080 db login lab-postgres --db-user=postgres --db-name=labdb
```

Success looks like: an "access to db denied" style error, and a denial event in the audit log. Then confirm what **is** allowed:

```bash
bin/tsh -i tbot/out/identity/identity --proxy localhost:3080 db login lab-postgres --db-user=labreader --db-name=labdb
```

If it fails:
1. `tsh` says the identity flag does not apply to `db login`: try the MCP route by copying `.mcp.json` to a temporary file with `dbUser=postgres`, and point Claude Code at it only for this test.
2. Certificate errors: add `--insecure` for the local self-signed certificate.
3. It is allowed: stop and check role `bot-lab-readonly` in `config/roles/`.

### F6: a credential expires (slow, reversible)

What we are doing: show that access ends by itself when renewal stops. The bot's certificate lasts 1 hour and is renewed every 20 minutes.

```bash
launchctl bootout gui/$(id -u)/dev.teleport-lab.tbot
```

This stops the renewal service only. Wait until the last certificate is older than one hour, then ask Claude Code to query the database.

Success looks like: the query fails; the audit log shows no new certificate for the bot after you stopped it.

**Put it back:**

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/dev.teleport-lab.tbot.plist
```

If it fails: check `launchctl print gui/$(id -u)/dev.teleport-lab.tbot` and the log at `~/Library/Logs/teleport-lab-tbot.log`.

### F7: a resource goes away (reversible)

What we are doing: stop PostgreSQL to see how the agent and the dashboards behave when a resource is unavailable. This does **not** remove data or volumes.

```bash
docker compose stop postgres
```

Ask Claude Code for the table list: it should fail with a connection error. Then put it back:

```bash
docker compose start postgres
docker compose ps
```

Success looks like: `postgres` shows running/healthy again and Claude Code works after a short wait.

If it fails: `docker compose logs postgres --tail 100`. Do not delete the volume.

## What you cannot simulate live

These appear only in the synthetic demo data (Data source = Demo data): unusual source IPs, off-hours access, bulk reads, Kubernetes exec, and contractor incidents. See [DEMO_DATA.md](DEMO_DATA.md).

## Clean up

- F1 to F5 leave only audit events; there is nothing to undo.
- F6 and F7: run the "put it back" commands above.
- Scene 1 (`scripts/demo-scene.sh 1`) creates a real test user. Removing it is deliberately not automated: ask before removing it.
- `rm /tmp/tbot-badtoken.yaml` is optional; it holds no secret.

## Record your results

Copy this table into an issue or notes after each run.

| Exercise | Date | What you saw | Matches expected? |
|---|---|---|---|
| F1 | | | |
| F2 | | | |
| F3 | | | |
| F4 | | | |
| F5 | | | |
| F6 | | | |
| F7 | | | |

Once an exercise has been run and matches, change its "(untested)" note here and update `PROJECT_STATUS.md`.

## Why this matters (interview story)

Each exercise proves one control: authentication and MFA (F1), role-based access control (F2, F5), least privilege plus defence in depth (F3), short-lived join tokens (F4), zero standing credentials (F6), and honest failure behaviour (F7). In every case the outcome is an identity-tagged audit event that Splunk can search, alert on and explain.
