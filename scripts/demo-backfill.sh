#!/bin/bash
# Keep the SYNTHETIC demo data (index=teleport_demo) current without deleting anything.
#   scripts/demo-backfill.sh check   how fresh is demo-data/? (exit 1 if stale)
#   scripts/demo-backfill.sh run     add only the missing days (asks first)
# How: generates a fresh set (packs 1 and 2) into a temp folder, then copies in only
# the days NEWER than the latest day already in demo-data/. No overlap, so nothing is
# double-counted and nothing in Splunk has to be deleted. Old days simply age out of
# the dashboards' 15-day view. Days are UTC (the generators name files by UTC day).
# Also adds trigger-style events (<day>.triggers.log, cloned from real live-trigger
# events) for every complete day that lacks them, so demo and live data match in mix,
# size and shape. See scripts/gen_demo_events_triggers.py.
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"; DATA="${DEMO_DATA:-$HERE/demo-data}"
latest(){ ls "$DATA" 2>/dev/null | grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2}' | sort -u | tail -1; }
today=$(date -u +%F)
days_between(){ echo $(( ( $(date -j -u -f '%F' "$2" +%s) - $(date -j -u -f '%F' "$1" +%s) ) / 86400 )); }

last=$(latest)
no_triggers(){ for d in $(ls "$DATA" 2>/dev/null | grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2}' | sort -u); do
  [[ "$d" < "$today" ]] && [ ! -e "$DATA/$d.triggers.log" ] && echo "$d"; done; }
case "${1:-check}" in
  check)
    [ -z "$last" ] && { echo "No demo data in demo-data/. Generate it: python3 scripts/gen_demo_events.py"; exit 1; }
    behind=$(days_between "$last" "$today")
    nt=$(no_triggers | wc -l | tr -d ' ')
    if [ "$behind" -le 0 ] && [ "$nt" = 0 ]; then echo "Demo data is current (latest day $last UTC), trigger events on every day."
    elif [ "$behind" -le 0 ]; then echo "Demo data is current (latest day $last UTC), but $nt day(s) lack trigger events. Fix: scripts/demo-backfill.sh run"; exit 1
    else echo "Demo data is $behind day(s) behind (latest day $last, today $today UTC). Fix: scripts/demo-backfill.sh run"; exit 1; fi
    ;;
  run)
    [ -z "$last" ] && { echo "No demo data to extend. Generate it first: python3 scripts/gen_demo_events.py"; exit 1; }
    behind=$(days_between "$last" "$today")
    nt=$(no_triggers | wc -l | tr -d ' ')
    [ "$behind" -le 0 ] && [ "$nt" = 0 ] && { echo "Nothing to do: demo data reaches today ($today UTC) and every day has trigger events."; exit 0; }
    [ "$behind" -gt 0 ] && echo "Demo data ends $last; today is $today (UTC). This adds the $behind missing day(s) of packs 1 and 2."
    echo "It also adds trigger-style events to every complete day that lacks them (about 110 events per day)."
    printf 'Backfill now? [y/N] '; read -r a; case "$a" in y|Y) ;; *) echo "Skipped."; exit 0;; esac
    tmp=$(mktemp -d)
    python3 "$HERE/scripts/gen_demo_events.py" --days 15 --out "$tmp" >/dev/null || { echo "pack 1 generator failed"; exit 1; }
    python3 "$HERE/scripts/gen_demo_events_pack2.py" --days 15 --out "$tmp" >/dev/null || { echo "pack 2 generator failed"; exit 1; }
    n=0; ev=0
    [ "$behind" -gt 0 ] && for f in "$tmp"/*.log; do
      d=$(basename "$f" | cut -c1-10)
      if [[ "$d" > "$last" ]] && [ ! -e "$DATA/$(basename "$f")" ]; then
        cp "$f" "$DATA/" && n=$((n+1)) && ev=$((ev + $(wc -l < "$f")))
      fi
    done
    rm -rf "$tmp"
    [ "$behind" -gt 0 ] && echo "Added $n story file(s), $ev synthetic events (demo=true) for days after $last."
    python3 "$HERE/scripts/gen_demo_events_triggers.py" --out "$DATA" | tail -1
    echo "Splunk picks them up within a minute."
    [ "$behind" -gt 0 ] && echo "Note: $last only has events up to the moment it was generated; that partial day is left as it is."
    ;;
  *) sed -n '2,8p' "$0"; exit 1 ;;
esac
