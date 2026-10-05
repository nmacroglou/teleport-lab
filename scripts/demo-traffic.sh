#!/bin/bash
# Live traffic for the demo: fires real events through Teleport into Splunk
# (index=teleport) in a background loop until you stop it.
#   scripts/demo-traffic.sh start             realistic: follows the demo data's daily curve
#                                             (same volume and shape as index=teleport_demo)
#   scripts/demo-traffic.sh start fast [s]    on stage: every action every [s] seconds (default 30)
#   scripts/demo-traffic.sh stop              stop and close the database tunnel
#   scripts/demo-traffic.sh status            running?, rounds, events fired, last line
# Realistic mode fires ONE action at a time, picked with the same mix as the synthetic
# trigger events (scripts/gen_demo_events_triggers.py), spaced so each hour gets about
# as many events as the same hour in the demo data. Fast mode, each round:
#   - 1-2 allowed reads (labreader)            -> db.session.query, allowed
#   - 1 write the read-only user cannot do     -> forwarded, then refused by the database
#   every 2nd round: bot SSH to linux-server-1 -> denied (no SSH logins in its role)
#   every 3rd round: bot asks for admin user   -> denied by Teleport
#   every 4th round: 3 failed logins, made-up user -> user.login failures
# Never prints secrets, never changes data (all writes are refused), no psql needed
# on the Mac (queries run with the postgres container's psql through a local tunnel).
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
RUN="$HERE/.run"; PID="$RUN/demo-traffic.pid"; LOG="$RUN/demo-traffic.log"; STATS="$RUN/demo-traffic.stats"
TSH="$HERE/bin/tsh"; PROXY="localhost:3080"; ID="$HERE/tbot/out/identity/identity"; DBID="$HERE/tbot/out/db/identity"
PORT=15432
mkdir -p "$RUN"

running(){ [ -f "$PID" ] && kill -0 "$(cat "$PID")" 2>/dev/null; }
log(){ echo "$(date '+%H:%M:%S') $*" >> "$LOG"; }
bump(){ c=$(grep -E "^$1 " "$STATS" 2>/dev/null | awk '{print $2}'); c=$(( ${c:-0} + ${2:-1} ))
        grep -vE "^$1 " "$STATS" 2>/dev/null > "$STATS.tmp"; echo "$1 $c" >> "$STATS.tmp"; mv "$STATS.tmp" "$STATS"; }
cert_ok(){ end=$(openssl x509 -in "$HERE/tbot/out/identity/tlscert" -noout -enddate 2>/dev/null | cut -d= -f2)
           [ $(( $(date -j -f '%b %e %T %Y %Z' "$end" +%s 2>/dev/null || echo 0) - $(date +%s) )) -gt 60 ]; }
psql_as(){ docker exec postgres psql "host=host.docker.internal port=$PORT user=$1 dbname=labdb sslmode=disable connect_timeout=10" -tAc "$2" 2>&1 | head -1; }

READS=("select count(*) from servers" "select name, role from servers order by name" "select current_user" "select name from servers where role like '%ssh%'")
WRITES=("create table hack (id int)" "delete from servers" "update servers set role = 'pwned'" "drop table servers")
tunnel_up(){ "$TSH" -i "$DBID" --proxy "$PROXY" proxy db --tunnel --port "$PORT" --db-user labreader --db-name labdb lab-postgres >/dev/null 2>&1 & tunnel=$!
             for i in 1 2 3 4 5 6 7 8 9 10; do nc -z 127.0.0.1 "$PORT" 2>/dev/null && break; sleep 1; done; }
tunnel_down(){ [ -n "${tunnel:-}" ] && { kill "$tunnel" 2>/dev/null; wait "$tunnel" 2>/dev/null; }; tunnel=""; }
act(){  # one action; prints how many events it should produce
  case "$1" in
    read)  tunnel_up; r=$(psql_as labreader "${READS[$((RANDOM % 4))]};"); tunnel_down; bump allowed_reads; log "read  -> ${r:0:60}"; echo 3 ;;
    write) tunnel_up; w="${WRITES[$((RANDOM % 4))]}"; r=$(psql_as labreader "$w;"); tunnel_down; bump refused_writes; log "write '$w' -> ${r:0:60}"; echo 3 ;;
    admin) tunnel_up; r=$(psql_as postgres "select 1;" | sed -E 's/.*failed: //'); tunnel_down; bump denied_admin; log "admin user -> ${r:0:60}"; echo 1 ;;
    ssh)   r=$(perl -e 'alarm 30; exec @ARGV' "$TSH" -i "$ID" --proxy "$PROXY" ssh labuser@linux-server-1 true 2>&1 | grep -oE 'access denied[^.]*' | head -1)
           bump denied_ssh; log "bot ssh -> ${r:-no answer}"; echo 1 ;;
    login) u=$( [ $((RANDOM % 2)) = 0 ] && echo ben.okafor || echo temp.contractor ); k=$((RANDOM % 3 + 1))
           for i in $(seq 1 $k); do curl -sk -o /dev/null -X POST -H 'Content-Type: application/json' \
             -d "{\"user\":\"$u\",\"pass\":\"not-the-password\"}" "https://$PROXY/v1/webapi/mfa/login/begin"; done
           bump failed_logins "$k"; log "$k failed login(s) for made-up user $u"; echo "$k" ;;
  esac; }
curve(){  # events per UTC hour in the demo data (story + trigger events), averaged over complete days
  python3 - "$HERE/demo-data" <<'PY'
import glob, json, os, sys, collections
from datetime import datetime, timezone
today = datetime.now(timezone.utc).strftime('%Y-%m-%d'); h = collections.Counter(); days = set()
for p in glob.glob(os.path.join(sys.argv[1], '*.log')):
    d = os.path.basename(p)[:10]
    if d >= today: continue
    days.add(d)
    for line in open(p, errors='replace'):
        try: h[int(json.loads(line)['time'][11:13])] += 1
        except Exception: pass
n = max(len(days), 1); print(' '.join(str(max(round(h[i] / n, 1), 1)) for i in range(24)))
PY
}
realistic(){
  trap 'tunnel_down; log "stopped"; exit 0' TERM INT
  C=($(curve)); total=0; for v in "${C[@]}"; do total=$(python3 -c "print(round($total+$v))"); done
  log "started (realistic): about $total events/day, following the demo data's hourly curve"
  while true; do
    h=$((10#$(date -u +%H))); per_hour=${C[$h]}
    if cert_ok; then r=$((RANDOM % 100))
      if   [ $r -lt 55 ]; then k=read; elif [ $r -lt 65 ]; then k=write; elif [ $r -lt 70 ]; then k=admin
      elif [ $r -lt 80 ]; then k=ssh; else k=login; fi
    else k=login; log "bot certificate expired or missing: only failed logins (run scripts/demo-status.sh)"; fi
    cost=$(act "$k"); bump events "$cost"
    wait_s=$(python3 -c "import random; print(int(min(3600, max(15, $cost*3600/$per_hour*random.uniform(.5,1.5)))))")
    sleep "$wait_s" & wait $!
  done
}

loop(){
  interval="$1"; round=0; tunnel=""
  trap '[ -n "$tunnel" ] && kill "$tunnel" 2>/dev/null; log "stopped"; exit 0' TERM INT
  log "started (fast): every action every ${interval}s"
  while true; do
    round=$((round+1)); bump rounds
    if ! cert_ok; then log "round $round: bot certificate expired or missing, skipping bot actions (run scripts/demo-status.sh)"; bump skipped
    else
      # fresh tunnel each round, so it always uses tbot's newest certificate
      "$TSH" -i "$DBID" --proxy "$PROXY" proxy db --tunnel --port "$PORT" --db-user labreader --db-name labdb lab-postgres >/dev/null 2>&1 & tunnel=$!
      for i in 1 2 3 4 5 6 7 8 9 10; do nc -z 127.0.0.1 "$PORT" 2>/dev/null && break; sleep 1; done
      for q in "${READS[$((RANDOM % 4))]}" "${READS[$((RANDOM % 4))]}"; do
        r=$(psql_as labreader "$q;"); bump allowed_reads; log "round $round: read  -> ${r:0:60}"
      done
      w="${WRITES[$((RANDOM % 4))]}"; r=$(psql_as labreader "$w;"); bump refused_writes; log "round $round: write '$w' -> ${r:0:70}"
      if [ $((round % 3)) = 0 ]; then r=$(psql_as postgres "select 1;" | sed -E 's/.*failed: //'); bump denied_admin; log "round $round: admin user -> ${r:0:70}"; fi
      kill "$tunnel" 2>/dev/null; wait "$tunnel" 2>/dev/null; tunnel=""
      if [ $((round % 2)) = 0 ]; then
        r=$(perl -e 'alarm 30; exec @ARGV' "$TSH" -i "$ID" --proxy "$PROXY" ssh labuser@linux-server-1 true 2>&1 | grep -oE 'access denied[^.]*' | head -1)
        bump denied_ssh; log "round $round: bot ssh -> ${r:-no answer}"
      fi
    fi
    if [ $((round % 4)) = 0 ]; then
      u=$( [ $((RANDOM % 2)) = 0 ] && echo ben.okafor || echo temp.contractor )
      for i in 1 2 3; do curl -sk -o /dev/null -X POST -H 'Content-Type: application/json' \
        -d "{\"user\":\"$u\",\"pass\":\"not-the-password\"}" "https://$PROXY/v1/webapi/mfa/login/begin"; done
      bump failed_logins 3; log "round $round: 3 failed logins for made-up user $u"
    fi
    sleep "$interval" & wait $!
  done
}

case "${1:-}" in
  start)
    running && { echo "Already running (pid $(cat "$PID")). Use: $0 status"; exit 0; }
    : > "$STATS"; : > "$LOG"
    if [ "${2:-}" = fast ]; then interval="${3:-30}"; nohup bash "$0" _loop "$interval" >/dev/null 2>&1 & echo $! > "$PID"; how="fast: every action every ${interval}s"
    else nohup bash "$0" _realistic >/dev/null 2>&1 & echo $! > "$PID"; how="realistic: follows the demo data's daily curve"; fi
    sleep 2; running && echo "Demo traffic started (pid $(cat "$PID")), $how. Stop with: $0 stop" \
                    || { echo "Failed to start; see $LOG"; exit 1; }
    cert_ok || echo "Warning: the bot certificate is expired or missing, so only failed logins will be sent."
    ;;
  stop)
    if running; then kill "$(cat "$PID")"; sleep 1; rm -f "$PID"; echo "Demo traffic stopped."; else rm -f "$PID"; echo "Not running."; fi
    pkill -f "proxy db --tunnel --port $PORT" 2>/dev/null || true
    ;;
  status)
    running && echo "Running (pid $(cat "$PID"))." || echo "Not running."
    [ -s "$STATS" ] && { echo "Fired so far:"; sed 's/^/  /' "$STATS"; }
    [ -s "$LOG" ] && { echo "Last activity:"; tail -3 "$LOG" | sed 's/^/  /'; }
    ;;
  _loop) loop "${2:-30}" ;;
  _realistic) realistic ;;
  *) sed -n '2,18p' "$0"; exit 1 ;;
esac
