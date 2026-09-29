# Troubleshooting

For any error: understand it first, check three safe things, and change nothing until the cause is clear. Never delete Docker volumes to fix a problem.

## Teleport container is not running

```bash
docker compose ps
docker compose logs teleport --tail 100
```

## Browser cannot open Teleport

```bash
curl -k https://localhost:3080/webapi/ping
docker compose ps
```

If the certificate is rejected, confirm the mkcert root CA is trusted on the Mac.

## Claude Code cannot reach the database

1. Is `tbot` running and is `tbot/out/identity/identity` recent (it renews every 20 minutes)?
2. Does the bot role allow the database and user in `.mcp.json`?
3. Check Teleport's audit log for a denial with a reason.

## Splunk shows no data

```bash
docker compose logs splunk --tail 100
docker exec splunk ls /teleport-audit /teleport-demo
```

Then search `index=teleport OR index=teleport_demo | stats count by index`. Widen the time range (demo data covers 15 days).

## Splunk restarts in a loop on an existing install

Splunk ships Intel images and runs under Rosetta on Apple Silicon. The compose file clears the image's first-run marker at startup for existing installs; see the comments in `docker-compose.yml`.

## Dashboard changes do not appear

Reload views (`_reload` URL, then **Refresh** on `/en-US/debug/refresh`), then hard-refresh the browser.

## A dashboard panel is empty or says "malformed"

- Empty panel after a post-process search: the field is missing from the base `| fields` list.
- "EvalCommand: expression is malformed": look for stray text inside the base search string.
- Dashboard Studio panel says a visualization type is not defined: use a supported type (`splunk.markdown` for text).

## Claude ignores CLAUDE.md

Start Claude Code from the project folder, where `CLAUDE.md` lives.
