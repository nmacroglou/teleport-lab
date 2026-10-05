# Demo Runbook: "Claude decides. Teleport decides what Claude is allowed to do. Splunk records what happened."

Length: about 20 minutes plus Q&A. Audience: Teleport technical interview / exec.
Data: dashboards default to **Demo data** (synthetic, clearly labeled). Switch **Data source** to **Live lab data** for the live scenes.

## Before you start (10 minutes ahead)
- [ ] Easiest path: `scripts/demo-menu.sh` (pre-flight, every scene trigger, and `r` to reset demo users, locks and invites afterwards)
- [ ] `scripts/demo-status.sh` shows no `[FAIL]` lines
- [ ] Splunk open at http://127.0.0.1:8000 -> Teleport Lab app
- [ ] Claude Code open in this project (MCP tool `teleport-databases` connected)
- [ ] Browser tab ready at https://localhost:3080 (Teleport web UI), logged in
- [ ] Terminal ready in the project folder
- [ ] Fallback: if anything live breaks, stay on **Demo data**. Nothing depends on the live lab.

## Run of show
| Min | Screen | Say | Do |
|---|---|---|---|
| 0-3 | **0 Trust Scorecard** (Demo) | "Three questions: are credentials short-lived, is every action tied to an identity, and what did policy block?" | Point at: short-lived %, long-lived (0), blocked count. Read the PPI FS box: before = manual certs and fragmented access; after = SSO, audited sessions, access as code. |
| 3-7 | **1 Day-One Onboarding** | "PPI's engineers log in once and get the access their role allows." | Show the journey table (account -> MFA -> login -> cert -> access) and the minutes figure. Then live: `scripts/demo-scene.sh 1`, finish the invite in the browser, switch to Live data. |
| 7-11 | **2 Auditor Evidence** | "An auditor asks: who touched the database?" | Heatmap -> "Who accessed" table -> query log. Click into one row, show the event `uid`. Filter Identity to one person. Mention Export. |
| 11-16 | **3 AI Agent Governance** | "Claude decides. Teleport decides. Splunk records." | Run `scripts/demo-scene.sh 3` for the prompts. Type A and B (allowed), then C and D (writes). Switch to Live data: click the agent's session -> Session replay. Show the red "Blocked at Teleport" rows in Demo data. The AI Agent page is now a 4-step story: (1) the narrow job and 1-hour credential, (2) click the worst day ("Went off-script, stopped every time"), (3) walk the step-by-step table (3 admin-user attempts refused by Teleport, 3 writes refused by the database, 2 SSH attempts refused), (4) click a step to show the raw audit event. |
| 16-20 | **4 Security Watch** | "Something looks wrong: where do I look?" | Live: `scripts/demo-scene.sh 4`. Show failed logins, brute-force burst, bot denial. In Demo data show off-hours access and the unusual source IP. |
| 20-25 | **5 Remote engineer (iPad)** | "This iPad is a laptop in a hotel. No VPN, no SSH key, no database password." | Before: `scripts/demo-scene.sh 5 setup` (sends nothing to screen; invite in `secrets/ipad-invite.txt`). On the iPad: log in with password + OTP, open a browser terminal to `linux-server-1`, show Splunk/5432 do not load. Then on the Mac: `scripts/demo-scene.sh 5 lock` and watch the iPad session drop. See "Scene 5" below. |
| 25+ | Whiteboard / Q&A | Architecture | See cheat sheet below. |

## Honest details to say out loud (this builds trust)
- Demo data is synthetic and tagged `demo=true`, in a separate index (`teleport_demo`).
- A write attempt shown as "allowed" in Teleport means the query was forwarded and logged. The read-only database user (`labreader`) is what refuses the change.
- "Supports C5 / KRITIS / DORA evidence" is not "certified". PPI FS's C5 result is their result, from their customer story.

## Architecture cheat sheet
- **Short-lived certificates:** users and bots get certificates that expire in hours (bot ~1h). No long-lived keys to steal or forget.
- **Reverse tunnel:** resources (agents) dial OUT to the proxy, so no inbound holes in the firewall to servers.
- **RBAC:** roles decide what an identity can reach (`bot-lab-readonly` = read-only database only).
- **Machine ID (tbot):** the bot gets its own identity, renews it automatically, never uses a human admin login.
- **MCP:** Claude Code reaches the database through Teleport's MCP database server, so the AI inherits the bot's limits.
- **Audit:** every login, cert, session and query is an event; Splunk indexes the JSON files.
- **Access as code:** roles and users managed by code (Terraform / Kubernetes operator). Demo data shows a `bot-terraform` identity making the changes.
- Check edition details (Community vs Enterprise) before claiming a feature in Q&A.

## Likely questions
1. *Why short-lived certs instead of API keys?* Stolen credentials expire on their own; nothing to rotate or revoke by hand.
2. *What stops the AI doing damage?* Its identity and role, not its good behavior.
3. *What if the agent asks for a database user it should not have?* Teleport denies at connection time (red "Blocked at Teleport").
4. *How do you prove what happened?* Immutable audit events with unique IDs, indexed in Splunk.
5. *How would this scale?* Kubernetes-native deployment and Terraform, as PPI FS did.

## After the demo
- Test users from scene 1 stay until you decide what to do with them (cleanup is intentionally manual).
- To rebuild dashboards: `python3 scripts/build_dashboards.py`
- To rebuild demo data (only after clearing `index=teleport_demo`): `python3 scripts/gen_demo_events.py --force`

## Demo data packs
- Pack 1 (`demo-data/<day>.log`): the core story, 2,466 events.
- Pack 2 (`demo-data/<day>.pack2.log`): bigger company, Kubernetes, more databases, 1,757 events. Extra incidents to point at in **4 Security Watch**: impossible travel (9 days ago), a role change made by a person outside Terraform (5 days ago), a bot join with a bad token (3 days ago), a bulk read at night (6 days ago), and a developer probing production Kubernetes (yesterday). Kubernetes denial codes in the synthetic data are approximated.

## Bonus scene: "Why was the AI agent refused?" (Unified Identity Layer + Command Center drill-down)

Use this after the AI Agent scene, or as the closer. About 3 minutes.

1. Open **★ Unified Identity Layer**. Say: "One identity layer for humans, machines and AI agents." Point at the tiles (humans, AI agents, workloads, denied %, MFA %). Click the **AI agents** tile.
2. You land in the **Command Center** with *Identity class = ai_agent* already set. Say: "Claude decides what to try. Teleport decides what is allowed."
3. Click the **Denied / failed: click to drill** tile, then walk the levels:
   - Level 1: *why* (e.g. "Database access refused by role") and which control refused it.
   - Level 2: *who* (e.g. bot-claude-agent).
   - Level 3: *which events*, plus allowed-vs-denied over time for that identity.
   - Level 4: the raw audit event (evidence card). Link to Auditor Evidence for the full story.
4. Point out: the filters (class, why, who, time, source) stay set at every level and live in the URL, so the drill can be bookmarked or shared.

Honest notes: demo data is synthetic (`teleport_demo`, `demo=true`). A "db.session.query success" means Teleport forwarded it; the read-only DB user refuses writes. Kubernetes denial codes in demo data are approximate. If Level 3 shows nothing, clear the *Who* box.
Known quirk: the Unified Identity Layer page may appear in a light theme in some browsers.

## Studio edition: the recommended demo path

The Dashboard Studio pages tell one story. Classic Simple XML pages stay available as a fallback (menu: "Demo scenes (classic)").

| Order | Page (menu name) | Say |
|---|---|---|
| 0 | Trust Scorecard (Studio) | "Can we prove who did what, with credentials that expire?" |
| 1 | Unified Identity Layer (Studio) | "Humans, machines and AI agents on one layer. Why was the agent refused? Click through 4 levels." |
| 2 | Demo scenes (Studio): 1 · Day-One Onboarding | New engineer, no ticket queue, short-lived certificate |
| 3 | 2 · Auditor Evidence | Who touched the database, and what they ran |
| 4 | 3 · AI Agent Governance | Claude decides, Teleport decides, Splunk proves. Click a session to replay it |
| 5 | 4 · Security Watch | Something looks wrong: where do you look? |
| 6 | Command Center | Raw evidence and free drill-down |

Build: `python3 scripts/build_dashboards.py`, then `dash_studio_identity.py`, `dash_studio_scorecard.py`, `dash_studio_scenes.py`. Reload Splunk views (`_reload` URL, then Refresh on /debug/refresh) so the menu updates.
Studio pages are a fixed 1920 px canvas that auto-scales: check them on the projector before the demo.

## Scene 5: remote engineer on an unmanaged device (the iPad)

The iPad stands in for a remote site: it reaches the Mac over the home network at `https://192.168.0.81:3080`, and only Teleport's web port is published there.

**Before the demo**
- `scripts/demo-scene.sh 5 setup` creates `ipad.demo` (role `access`, SSH login `labuser`) and saves the invite with `localhost` already replaced by the Mac's LAN IP. Send it to the iPad privately; never show it on the projector.
- On the iPad, Safari aA menu -> **Request Mobile Website**, so Splunk logs the device as an iPad (by default iPad Safari reports itself as a Mac).
- The mkcert CA must be trusted on the iPad (profile installed, then enabled under Certificate Trust Settings).

**Live**
1. Log in on the iPad (username in lowercase; the iPad keyboard capitalizes it), password + authenticator code.
2. Resources -> `linux-server-1` -> Connect as `labuser`: `hostname`, `whoami`. Every keystroke is recorded; replay it on the Mac under Session Recordings.
3. On the iPad, try `http://192.168.0.81:8000` (Splunk) and port 5432: nothing loads. Only Teleport is reachable.
4. Kill switch on the Mac: `scripts/demo-scene.sh 5 lock`. Teleport cuts the open session within about 2 seconds and refuses new logins (`client.disconnect`: "lock targeting User ... is in force").
5. Splunk: `index=teleport (user_agent="*iPad*" OR event=lock.created OR event=client.disconnect)`.
6. Afterwards: `scripts/demo-scene.sh 5 unlock`. Removing the test user is manual on purpose.

**Honest details**
- Splunk shows the source address as Docker Desktop's gateway (`192.168.65.1`), not the iPad's IP; on a Linux server the real client IP appears.
- The `whoami` app does not work from the iPad: it is addressed as `whoami.localhost`.
- Tested 2026-10-05 with a throwaway user: SSH as `labuser` worked; a lock cut the open session in 2 s and refused new connections.
