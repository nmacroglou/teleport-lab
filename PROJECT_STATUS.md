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

## Done: Splunk story

- [x] Synthetic demo data in a separate index (4,223 events over 15 days)
- [x] Classic dashboards and Command Center drill-down
- [x] Dashboard Studio edition: scorecard, identity layer, four scenes
- [x] Demo runbook

## To verify

- [ ] Live scene scripts (`demo-scene.sh`, `demo-status.sh`) end to end
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
