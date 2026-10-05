# Project status

## Done: Mac Docker lab

- [x] Docker Desktop, Teleport Community 18.11.2, web UI
- [x] Login with MFA
- [x] `linux-server-1` enrolled, SSH through Teleport
- [x] `whoami` web app
- [x] `lab-postgres` enrolled (certificate auth, read-only `labreader`)
- [x] Local trusted TLS for the proxy (mkcert)
- [x] Machine ID: `tbot` with a 1-hour identity and a read-only bot role
- [x] Claude Code reaches the lab database through an MCP server behind Teleport
- [x] Teleport audit events in Splunk (index `teleport`)

## Done: Phase 2, iPad on the home network

- [x] Teleport web port also published on the Mac's LAN IP (192.168.0.81), LAN only, no router forwarding
- [x] Certificate reissued with the LAN IP; mkcert CA trusted on the iPad
- [x] iPad login to Teleport works; failed logins visible in Splunk
- [x] Checked from the iPad: Splunk (8000), PostgreSQL (5432) and Teleport auth (3025) are not reachable
- [ ] Reserve 192.168.0.81 for the Mac in the router (DHCP reservation)
- [ ] Confirm tbot and the Claude workflow after the Teleport restart

## Done: Splunk story

- [x] Synthetic demo data in a separate index (4,223 events over 15 days)
- [x] Classic dashboards and Command Center drill-down
- [x] Dashboard Studio edition: scorecard, identity layer, four scenes
- [x] Demo runbook

## To verify

- [ ] Live scene scripts (`demo-scene.sh`, `demo-status.sh`) end to end
- [ ] Failure exercises F4 to F7 in docs/LAB_RUN_GUIDE.md
- [ ] Studio dashboards on a projector (fixed canvas)
- [ ] One allowed and one denied AI action, captured as a screenshot for the runbook

## Next: Ubuntu home server

- [ ] Ubuntu 24.04 with a stable home-network IP
- [ ] SSH from the Mac
- [ ] Docker, then a second Teleport lab (keep the Mac lab as rollback)
- [ ] Linux resource, web app, PostgreSQL

## Later

- [ ] Real DNS name and public TLS certificate, proxy on 443
- [ ] `tbot` and MCP against the trusted cluster
- [ ] Kubernetes resource
- [ ] Alerts in Splunk for denials and bot join failures

Do not delete the Mac lab: it is the rollback copy.
