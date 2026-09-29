# Teleport Home Lab - Instructions for Claude Code

## What we are building
We are building a small Teleport home lab for learning.

The lab will start on this Mac with Docker Desktop.
Later, we may move it to an Ubuntu home server or a small cloud server.

## Main rule
Go one small step at a time.
After each step, stop and show me whether it worked.

## Safety rules
- Do not delete files unless I clearly approve it.
- Do not run rm -rf.
- Do not run docker system prune.
- Do not run docker volume prune.
- Do not run terraform destroy.
- Do not run kubectl delete unless I clearly approve it.
- Do not print passwords, private keys, join tokens, or secret files into chat.
- Do not place secrets in Git.
- Do not expose SSH, PostgreSQL, Docker, or Kubernetes directly to the public internet.
- Start AI and machine access as read-only.

## How to explain things to me
- Use simple language.
- Explain one step at a time.
- Tell me exactly what command you want to run before you run it.
- If something fails, explain what the error means in plain English.
- Do not skip ahead.

## Build order
1. Check Docker Desktop.
2. Build Teleport locally.
3. Confirm the Teleport web page opens.
4. Create my first Teleport user.
5. Add one small Linux test server.
6. Test SSH through Teleport.
7. Add a test web app.
8. Add PostgreSQL.
9. Add audit logging.
10. Move to a trusted TLS setup before adding tbot and MCP.
11. Add Teleport Machine and Workload Identity with tbot.
12. Connect Claude Code to approved MCP tools through Teleport.
13. Add Splunk logging later.

## Definition of done for each step
A step is complete only when:
- the command succeeds,
- the service is healthy,
- and we run a simple test that proves it works.
