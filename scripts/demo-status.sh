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
# Check the certificate's real expiry: tbot keeps touching files even when renewal fails.
cert="$HERE/tbot/out/identity/tlscert"
end=$(openssl x509 -in "$cert" -noout -enddate 2>/dev/null | cut -d= -f2)
left=$(( $(date -j -f '%b %e %T %Y %Z' "$end" +%s 2>/dev/null || echo 0) - $(date +%s) ))
if [ "$left" -gt 600 ]; then ok "tbot certificate valid for another $((left/60)) min"
elif [ "$left" -gt 0 ]; then bad "tbot certificate expires in $((left/60)) min (is tbot renewing? check ~/Library/Logs/teleport-lab-tbot.log)"
else bad "tbot certificate EXPIRED (${end:-unreadable}). tbot cannot recover by itself: ask Claude to re-join the bot"; fi
echo "4) Demo data"
n=$(ls "$HERE"/demo-data/*.log 2>/dev/null | wc -l | tr -d ' ')
[ "$n" -gt 0 ] && ok "$n demo-data files present" || bad "no demo-data (run: python3 scripts/gen_demo_events.py)"
if [ "$n" -gt 0 ]; then
  fresh=$(bash "$HERE/scripts/demo-backfill.sh" check 2>&1)
  case "$fresh" in *current*) ok "$fresh" ;; *) bad "$fresh" ;; esac
fi
echo "5) Live demo traffic (informational)"
pidf="$HERE/.run/demo-traffic.pid"
if [ -f "$pidf" ] && kill -0 "$(cat "$pidf")" 2>/dev/null; then
  r=$(awk '/^rounds /{print $2}' "$HERE/.run/demo-traffic.stats" 2>/dev/null)
  echo "  [INFO] running (pid $(cat "$pidf")), ${r:-0} rounds so far. Stop: scripts/demo-traffic.sh stop"
else echo "  [INFO] not running. Start: scripts/demo-traffic.sh start"; fi
echo
[ "$FAILED" = 0 ] && echo "All good. Break a leg." || echo "Fix the [FAIL] lines first. Nothing was changed by this check."
