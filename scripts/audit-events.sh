#!/bin/sh
# Show recent Teleport audit events as a readable table (read-only).
#
# Usage: scripts/audit-events.sh [COUNT] [EVENT-FILTER]
#   scripts/audit-events.sh            last 20 events
#   scripts/audit-events.sh 50 login   last 50 events whose name contains "login"
#
# Only selected fields are printed, so secrets (e.g. join token names) never show.

COUNT="${1:-20}"
FILTER="${2:-}"
LOG_DIR="$(cd "$(dirname "$0")/.." && pwd)/data/log"

# -type f skips events.log, a symlink to a path that only exists in the container.
find "$LOG_DIR" -mindepth 2 -maxdepth 2 -type f -name '*.log' -print0 |
  xargs -0 cat |
  python3 -c '
import json, sys

count, flt = int(sys.argv[1]), sys.argv[2]
events = []
for line in sys.stdin:
    try:
        e = json.loads(line)
    except ValueError:
        continue
    if flt in e.get("event", ""):
        events.append(e)
events.sort(key=lambda e: e.get("time", ""))

def target(e):
    if e.get("server_hostname"):
        return "ssh %s@%s" % (e.get("login", "?"), e["server_hostname"])
    if e.get("app_name"):
        return "app " + e["app_name"]
    if e.get("db_service") or e.get("db_user"):
        q = (e.get("db_query") or "").replace("\n", " ")
        q = (" | " + q[:40]) if q else ""
        return "db %s@%s%s" % (e.get("db_user", "?"), e.get("db_name", "?"), q)
    if e.get("method"):
        return "method " + e["method"]
    return ""

def result(e):
    if "success" not in e:
        return ""
    if e["success"]:
        return "ok"
    return "FAILED " + (e.get("error") or "")[:40]

print("%-19s  %-22s  %-10s  %-8s  %s" % ("TIME (UTC)", "EVENT", "USER", "RESULT", "TARGET"))
for e in events[-count:]:
    print("%-19s  %-22s  %-10s  %-8s  %s" % (
        e.get("time", "")[:19], e.get("event", ""),
        (e.get("user") or (e.get("identity") or {}).get("user") or "")[:10],
        result(e), target(e)))
' "$COUNT" "$FILTER"
