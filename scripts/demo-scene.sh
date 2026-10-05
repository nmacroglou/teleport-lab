#!/bin/bash
# Live demo scenes for the Teleport home lab (run on the Mac).
# Rules: never deletes data, never prints secrets, asks before it acts,
#        only does harmless things (create a test user, fail a login, get denied).
#
#   scripts/demo-scene.sh 1 [new-user-name]   Scene 1: day-one onboarding
#   scripts/demo-scene.sh 3                   Scene 3: prompts for the Claude Code agent
#   scripts/demo-scene.sh 4                   Scene 4: failed logins + a denied bot
#   scripts/demo-scene.sh 5 setup  [name]     Scene 5: remote engineer on the iPad (user + invite)
#   scripts/demo-scene.sh 5 lock   [name]     Scene 5: kill switch, lock the user for 10 minutes
#   scripts/demo-scene.sh 5 unlock [name]     Scene 5: lift the lock again
set -eu
HERE="$(cd "$(dirname "$0")/.." && pwd)"
TSH="$HERE/bin/tsh"; PROXY="localhost:3080"; ID="$HERE/tbot/out/identity/identity"
INSECURE=""; [ "${DEMO_INSECURE:-0}" = 1 ] && INSECURE="--insecure"
confirm(){ printf '%s [y/N] ' "$1"; read -r a; case "$a" in y|Y) ;; *) echo "Skipped."; exit 0;; esac; }

case "${1:-}" in
1)
  name="${2:-lena.demo}"
  echo "SCENE 1 - Day-one onboarding"
  echo "This creates ONE test user '$name' with the built-in 'access' role."
  echo "  command: docker exec teleport tctl users add $name --roles=access"
  confirm "Create the user?"
  docker exec teleport tctl users add "$name" --roles=access
  cat <<TXT

Next (do this in the browser, it is the part the audience watches):
  1. Open the invite link above (one-time link: do not paste it anywhere).
  2. Choose a password, register an MFA device, log in.
  3. Open the 'whoami' app or click into a resource.
In Splunk: '1 Day-One Onboarding', Data source = Live lab data, New hire = $name.
(Cleanup is NOT automated on purpose. Ask Claude before removing the test user.)
TXT
  ;;
3)
  cat <<'TXT'
SCENE 3 - The AI agent (live, through Teleport's MCP database server)
Open Claude Code in this project. Type these prompts one at a time:

  A (allowed):  "Using the teleport-databases tool, list the tables in labdb."
  B (allowed):  "How many rows are in the servers table? Show name and role."
  C (denied):   "Create a table called hack with one integer column."
  D (denied):   "Delete every row from the servers table."

Say out loud: Claude decided to try C and D. Teleport gave it a read-only identity
(role bot-lab-readonly, credential about 1 hour). The database refuses the write.
Splunk recorded every attempt.

Then open Splunk: '3 AI Agent Governance', Data source = Live lab data.
Honest detail: the audit line for C and D shows the query was forwarded; the
read-only database user (labreader) is what refuses it.
TXT
  ;;
4)
  echo "SCENE 4 - Something looks wrong"
  echo "Part A: 8 failed logins for a made-up user 'ben.okafor' against https://$PROXY (bad password on purpose)."
  echo "Part B: the bot tries SSH to linux-server-1, which its role does not allow."
  confirm "Run both parts?"
  i=1
  while [ "$i" -le 8 ]; do
    code=$(curl -sk -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
      -d '{"user":"ben.okafor","pass":"not-the-password"}' "https://$PROXY/v1/webapi/mfa/login/begin" || true)
    echo "  attempt $i -> HTTP $code (a 4xx means Teleport refused it, as intended)"; i=$((i+1)); sleep 1
  done
  if [ -f "$ID" ]; then
    echo "  bot SSH attempt..."
    "$TSH" -i "$ID" --proxy "$PROXY" $INSECURE ssh labuser@linux-server-1 true || echo "  -> denied, as expected"
  else
    echo "  (bot identity file not found at tbot/out/identity/identity: skipping part B)"
  fi
  echo "In Splunk: '4 Security Watch', Data source = Live lab data (give it ~10 seconds)."
  echo "If the HTTP code is 404 or the bot step complains about certificates, tell Claude what it printed."
  ;;
5)
  name="${3:-ipad.demo}"; LAN="${DEMO_LAN_IP:-192.168.0.81}"
  case "${2:-}" in
  setup)
    echo "SCENE 5 - Remote engineer on an unmanaged device (the iPad)"
    echo "This creates ONE test user '$name' with role 'access' and SSH login 'labuser'."
    echo "The invite link is saved to secrets/ipad-invite.txt with localhost replaced by $LAN."
    echo "It is NOT printed: open the file on the Mac and send the link to the iPad privately (AirDrop/Notes)."
    confirm "Create the user?"
    umask 077; mkdir -p "$HERE/secrets"; out="$HERE/secrets/ipad-invite.txt"
    docker exec teleport tctl users add "$name" --roles=access --logins=labuser \
      | grep -oE 'https://[^ ]+' | head -1 | sed "s#https://localhost:3080#https://$LAN:3080#" > "$out"
    [ -s "$out" ] && echo "  invite saved: secrets/ipad-invite.txt (valid 1 hour)" || { echo "  no invite link captured"; exit 1; }
    cat <<TXT

On the iPad (the audience watches):
  1. Safari: aA menu -> Request Mobile Website (so Splunk logs say iPad, not Mac).
  2. Open the invite link, choose a password, add an authenticator (OTP), log in.
     Type the username in lowercase: '$name'.
  3. Resources -> linux-server-1 -> Connect as labuser. Run: hostname; whoami
  4. Try http://$LAN:8000 (Splunk) and port 5432: they do not load. Only Teleport is reachable.
Then the kill switch on the Mac: scripts/demo-scene.sh 5 lock $name
In Splunk: '4 Security Watch' or search: index=teleport user_agent="*iPad*" OR event=lock.created
TXT
    ;;
  lock)
    echo "SCENE 5 - Kill switch: lock '$name' for 10 minutes (open sessions are cut, new logins refused)."
    echo "  command: docker exec teleport tctl lock --user=$name --ttl=10m"
    confirm "Lock the user?"
    docker exec teleport tctl lock --user="$name" --ttl=10m --message="Demo: remote access revoked"
    echo "Watch the iPad terminal drop. Undo with: scripts/demo-scene.sh 5 unlock $name"
    ;;
  unlock)
    locks=$(docker exec teleport tctl get locks --format=json \
      | python3 -c 'import json,sys; u=sys.argv[1]; print(" ".join(l["metadata"]["name"] for l in json.load(sys.stdin) or [] if (l["spec"].get("target") or {}).get("user")==u))' "$name")
    [ -z "$locks" ] && { echo "No lock found for '$name'."; exit 0; }
    echo "Locks for '$name': $locks"
    confirm "Remove them?"
    for l in $locks; do docker exec teleport tctl rm "lock/$l"; done
    ;;
  *) sed -n '2,11p' "$0"; exit 1;;
  esac
  echo "(Cleanup of the test user is NOT automated on purpose. Ask Claude before removing '$name'.)"
  ;;
*)
  sed -n '2,11p' "$0"; exit 1;;
esac
