#!/bin/bash
# Keep the SYNTHETIC demo data (index=teleport_demo) current without deleting anything.
#   scripts/demo-backfill.sh check   how fresh is demo-data/? (exit 1 if stale)
#   scripts/demo-backfill.sh run     add only the missing days (asks first)
# How: generates a fresh set (packs 1 and 2) into a temp folder, then copies in only
# the days NEWER than the latest day already in demo-data/. No overlap, so nothing is
# double-counted and nothing in Splunk has to be deleted. Old days simply age out of
# the dashboards' 15-day view. Days are UTC (the generators name files by UTC day).
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"; DATA="${DEMO_DATA:-$HERE/demo-data}"
latest(){ ls "$DATA" 2>/dev/null | grep -oE '^[0-9]{4}-[0-9]{2}-[0-9]{2}' | sort -u | tail -1; }
today=$(date -u +%F)
days_between(){ echo $(( ( $(date -j -u -f '%F' "$2" +%s) - $(date -j -u -f '%F' "$1" +%s) ) / 86400 )); }

last=$(latest)
case "${1:-check}" in
  check)
    [ -z "$last" ] && { echo "No demo data in demo-data/. Generate it: python3 scripts/gen_demo_events.py"; exit 1; }
    behind=$(days_between "$last" "$today")
    if [ "$behind" -le 0 ]; then echo "Demo data is current (latest day $last UTC)."
    else echo "Demo data is $behind day(s) behind (latest day $last, today $today UTC). Fix: scripts/demo-backfill.sh run"; exit 1; fi
    ;;
  run)
    [ -z "$last" ] && { echo "No demo data to extend. Generate it first: python3 scripts/gen_demo_events.py"; exit 1; }
    behind=$(days_between "$last" "$today")
    [ "$behind" -le 0 ] && { echo "Nothing to do: demo data already reaches today ($today UTC)."; exit 0; }
    echo "Demo data ends $last; today is $today (UTC). This adds the $behind missing day(s) of packs 1 and 2."
    printf 'Backfill now? [y/N] '; read -r a; case "$a" in y|Y) ;; *) echo "Skipped."; exit 0;; esac
    tmp=$(mktemp -d)
    python3 "$HERE/scripts/gen_demo_events.py" --days 15 --out "$tmp" >/dev/null || { echo "pack 1 generator failed"; exit 1; }
    python3 "$HERE/scripts/gen_demo_events_pack2.py" --days 15 --out "$tmp" >/dev/null || { echo "pack 2 generator failed"; exit 1; }
    n=0; ev=0
    for f in "$tmp"/*.log; do
      d=$(basename "$f" | cut -c1-10)
      if [[ "$d" > "$last" ]] && [ ! -e "$DATA/$(basename "$f")" ]; then
        cp "$f" "$DATA/" && n=$((n+1)) && ev=$((ev + $(wc -l < "$f")))
      fi
    done
    rm -rf "$tmp"
    echo "Added $n file(s), $ev synthetic events (demo=true) for days after $last."
    echo "Splunk picks them up within a minute. Note: the last day before the gap ($last) only has events up"
    echo "to the moment it was generated; that partial day is left as it is."
    ;;
  *) sed -n '2,8p' "$0"; exit 1 ;;
esac
