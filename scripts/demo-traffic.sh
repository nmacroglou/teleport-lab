#!/bin/bash
# Live traffic for the demo: fires real events through Teleport into Splunk
# (index=teleport) in a background loop until you stop it.
#   scripts/demo-traffic.sh start [seconds]   start (default: one round every 30 s)
#   scripts/demo-traffic.sh stop              stop and close the database tunnel
#   scripts/demo-traffic.sh status            running?, rounds, events fired, last line
# Each round, as the read-only bot (lab-bot, via tbot's certificates):
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

loop(){
  interval="$1"; round=0; tunnel=""
  trap '[ -n "$tunnel" ] && kill "$tunnel" 2>/dev/null; log "stopped"; exit 0' TERM INT
  READS=("select count(*) from servers" "select name, role from servers order by name" "select current_user" "select name from servers where role like '%ssh%'")
  WRITES=("create table hack (id int)" "delete from servers" "update servers set role = 'pwned'" "drop table servers")
  log "started: one round every ${interval}s"
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
    interval="${2:-30}"; : > "$STATS"; : > "$LOG"
    nohup bash "$0" _loop "$interval" >/dev/null 2>&1 & echo $! > "$PID"
    sleep 1; running && echo "Demo traffic started (pid $(cat "$PID")), one round every ${interval}s. Stop with: $0 stop" \
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
  *) sed -n '2,15p' "$0"; exit 1 ;;
esac
