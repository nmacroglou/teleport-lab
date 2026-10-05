#!/bin/bash
# One menu for the whole demo: pre-flight, every scene trigger, and a reset.
# Rules: never prints secrets (invite links go to secrets/ and open in TextEdit),
#        asks before anything that creates, locks or removes, never touches
#        real users (only the demo users listed in DEMO_USERS).
# Usage: scripts/demo-menu.sh
set -u
HERE="$(cd "$(dirname "$0")/.." && pwd)"
SCENE="$HERE/scripts/demo-scene.sh"
DEMO_USERS="${DEMO_USERS:-lena.demo ipad.demo}"
INVITES="onboard-invite.txt ipad-invite.txt rehearsal-invite.txt"
LAN="${DEMO_LAN_IP:-192.168.0.81}"
cd "$HERE"

tctl(){ docker exec teleport tctl "$@"; }
ask(){ printf '%s [y/N] ' "$1"; read -r a; [ "$a" = y ] || [ "$a" = Y ]; }
pause(){ printf '\nPress Enter to return to the menu. '; read -r _; }
user_exists(){ tctl get "user/$1" >/dev/null 2>&1; }
locks_for(){ tctl get locks --format=json 2>/dev/null | python3 -c 'import json,sys; u=sys.argv[1]; print(" ".join(l["metadata"]["name"] for l in json.load(sys.stdin) or [] if (l["spec"].get("target") or {}).get("user")==u))' "$1"; }

status(){
  echo "Demo users:"
  for u in $DEMO_USERS; do
    if user_exists "$u"; then l=$(locks_for "$u"); echo "  $u: exists${l:+, LOCKED}"; else echo "  $u: not created"; fi
  done
  echo "Invite files in secrets/:"
  n=0; for f in $INVITES; do [ -e "secrets/$f" ] && { echo "  $f"; n=1; }; done; [ $n = 0 ] && echo "  none"
  echo "Splunk: $(docker inspect -f '{{.State.Status}} {{if .State.Health}}({{.State.Health.Status}}){{end}}' splunk 2>/dev/null || echo 'not found')"
  echo "Demo data: $(bash scripts/demo-backfill.sh check 2>&1)"
  echo "Live traffic: $(bash scripts/demo-traffic.sh status | head -1)"
  echo "Claude MCP: reconnect it (/mcp -> teleport-databases -> Reconnect) right before scene 3."
}

onboard(){
  name="${1:-lena.demo}"
  echo "SCENE 1 - Day-one onboarding: creates '$name' (role access, SSH login labuser)."
  echo "The invite link is saved to secrets/onboard-invite.txt and opened in TextEdit, NOT shown here."
  user_exists "$name" && { echo "'$name' already exists. Use Reset first."; return; }
  ask "Create the user?" || { echo "Skipped."; return; }
  umask 077; mkdir -p secrets
  tctl users add "$name" --roles=access --logins=labuser | grep -oE 'https://[^ ]+' | head -1 > secrets/onboard-invite.txt
  if [ -s secrets/onboard-invite.txt ]; then
    open -e secrets/onboard-invite.txt
    echo "Invite opened in TextEdit (valid 1 hour). Open it in the browser on the Mac, or on the iPad"
    echo "after replacing localhost:3080 with $LAN:3080. In Splunk: '1 Day-One Onboarding', New hire = $name."
  else echo "No invite link captured."; fi
}

reset(){
  echo "RESET - removes demo users ($DEMO_USERS), their locks, and the invite files."
  echo "Real users (nsuave, bot-lab-bot) and all audit data are left alone."
  status; echo
  ask "Reset now?" || { echo "Skipped."; return; }
  for u in $DEMO_USERS; do
    for l in $(locks_for "$u"); do tctl rm "lock/$l" >/dev/null && echo "  removed lock on $u"; done
    if user_exists "$u"; then tctl users rm "$u" >/dev/null && echo "  removed user $u"; fi
  done
  for f in $INVITES; do [ -e "secrets/$f" ] && rm "secrets/$f" && echo "  deleted secrets/$f"; done
  echo "Done. (Teleport's user list can take a few seconds to catch up.)"
}

menu(){
  clear 2>/dev/null
  cat <<MENU
 Teleport lab demo menu                          $(date '+%H:%M')
 ------------------------------------------------------------
  Before           p) Pre-flight check     s) Status
                   u) Start Splunk         d) Stop Splunk
  Scenes           1) Onboard new hire (invite -> TextEdit)
                   3) AI agent prompts (run them in Claude Code)
                   4) Failed logins + denied bot
                   5) iPad: set up user   l) Lock (kill switch)   k) Unlock
  All triggers     a) Run every automatic trigger once (scene 4)
                   t) START live traffic   x) STOP live traffic   w) Traffic status
  Demo data        b) Backfill missing days (synthetic data, nothing deleted)
  After            r) Reset the demo (demo users, locks, invites; stops traffic)
                   q) Quit
MENU
  printf ' Choose: '
}

while true; do
  menu; read -r c || exit 0
  echo
  case "$c" in
    p) bash scripts/demo-status.sh ;;
    s) status ;;
    u) docker compose start splunk && echo "Splunk starting: ready in about 2-3 minutes. Run p) to check." ;;
    d) ask "Stop Splunk (frees CPU; data is kept)?" && docker compose stop splunk ;;
    1) printf 'Name [lena.demo]: '; read -r n; onboard "${n:-lena.demo}" ;;
    3) bash "$SCENE" 3 ;;
    4|a) bash "$SCENE" 4 ;;
    5) bash "$SCENE" 5 setup ipad.demo && open -e secrets/ipad-invite.txt 2>/dev/null ;;
    l) bash "$SCENE" 5 lock ipad.demo ;;
    k) bash "$SCENE" 5 unlock ipad.demo ;;
    t) printf 'Seconds between rounds [30]: '; read -r n; bash scripts/demo-traffic.sh start "${n:-30}" ;;
    x) bash scripts/demo-traffic.sh stop ;;
    w) bash scripts/demo-traffic.sh status ;;
    b) bash scripts/demo-backfill.sh run ;;
    r) bash scripts/demo-traffic.sh stop >/dev/null 2>&1; reset ;;
    q) exit 0 ;;
    *) echo "Unknown choice: $c" ;;
  esac
  pause
done
