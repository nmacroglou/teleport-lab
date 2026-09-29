# Setup notes (Mac lab)

The repository holds configuration only. You must create the secrets locally; they are git-ignored.

## Prerequisites

- Docker Desktop
- mkcert (local trusted certificate authority) for the proxy certificate
- The pinned `tsh` client under `bin/` (downloaded and checksum-verified; git-ignored)

## Local files you create (never committed)

| Path | Purpose |
|---|---|
| `secrets/tls/` | Proxy certificate and key from mkcert, plus the public mkcert root CA |
| `secrets/node-join-token` | One-time token for `linux-server-1` to join |
| `secrets/postgres-superuser-password` | PostgreSQL superuser password |
| `secrets/splunk.env` | `SPLUNK_PASSWORD=...` for the Splunk admin user |
| `data/` | Teleport state (created by Teleport) |
| `tbot/out/`, `tbot/data/` | tbot identity and short-lived output certificates |

## Start and check

```bash
docker compose up -d
docker compose ps
docker compose logs teleport --tail 100
```

Do not delete Docker volumes to "fix" a problem. Ask first.

## Bot and MCP

1. A role `bot-lab-readonly` (`config/roles/bot-lab-readonly.yaml`) grants read-only database access.
2. `tbot/tbot.yaml` joins with a one-time token and writes a 1-hour identity to `tbot/out/`.
3. `.mcp.json` starts `tsh mcp db start` for `lab-postgres` using that identity file. Claude Code then reaches the database only through Teleport.

## Splunk

The `teleport_lab` app is mounted read-only from `splunk/apps/teleport_lab`. Build dashboards and demo data as described in [SPLUNK_DASHBOARDS.md](SPLUNK_DASHBOARDS.md) and [DEMO_DATA.md](DEMO_DATA.md).
