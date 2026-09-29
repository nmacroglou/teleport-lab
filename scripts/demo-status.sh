#!/bin/bash
# Pre-flight check before a demo. Read-only: it only LOOKS, it changes nothing.
# Usage: scripts/demo-status.sh
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ok(){ echo "  [ OK ] $1"; }; bad(){ echo "  [FAIL] $1"; FAILED=1; }; FAILED=0
echo "Teleport demo pre-flight"
echo "1) Containers"
for c in teleport linux-server-1 whoami postgres splunk; do
  if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx "$c"; then ok "$c is running"; else bad "$c is NOT running (try: docker compose up -d $c)"; fi
done
echo "2) Splunk web"
code=$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8000/en-US/account/login 2>/dev/null)
[ "$code" = "200" ] && ok "Splunk answers on http://127.0.0.1:8000" || bad "Splunk did not answer (HTTP ${code:-none}); it can take ~1 minute after a restart"
echo "3) Teleport client and bot"
[ -x "$HERE/bin/tsh" ] && ok "tsh found ($("$HERE/bin/tsh" version 2>/dev/null | head -1))" || bad "bin/tsh missing"
if find "$HERE/tbot/out/identity" -type f -mmin -30 2>/dev/null | grep -q .; then ok "tbot identity was renewed in the last 30 minutes"; else bad "tbot identity looks stale (is tbot running? credentials live ~1h)"; fi
echo "4) Demo data"
n=$(ls "$HERE"/demo-data/*.log 2>/dev/null | wc -l | tr -d ' ')
[ "$n" -gt 0 ] && ok "$n demo-data files present" || bad "no demo-data (run: python3 scripts/gen_demo_events.py)"
echo
[ "$FAILED" = 0 ] && echo "All good. Break a leg." || echo "Fix the [FAIL] lines first. Nothing was changed by this check."
