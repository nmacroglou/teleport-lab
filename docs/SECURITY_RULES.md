# Security rules

These rules apply to every change in this project, by people and by Claude Code.

## Never put these in Git

Passwords, Teleport join tokens, private keys, TLS private keys, bot identity files, API keys, database passwords, Splunk tokens.

Local secrets live outside the repository or in git-ignored folders (`secrets/`, `data/`, `tbot/out/`). `.gitignore` covers them; check `git status` before every commit.

## Never expose directly to the public internet

SSH on protected machines, PostgreSQL (5432), the Docker socket, the Kubernetes API, and the local Teleport port 3080. All published ports here are bound to `127.0.0.1`.

## Claude Code safety

- Claude Code **never** uses a human Teleport admin identity.
- It gets its **own machine identity** (`lab-bot`, via `tbot`), with short-lived certificates (1 hour, renewed every 20 minutes).
- It starts **read-only**: role `bot-lab-readonly` allows `labdb` as `labreader` only.
- No permanent SSH key, no database admin password.
- Big changes start with a plan and human approval.

## Destructive commands need clear approval

`rm -rf`, `docker system prune`, `docker volume prune`, `docker compose down -v`, `terraform destroy`, `kubectl delete namespace`, `tctl rm`. Never delete Docker volumes without approval.

## Demo data rules

Synthetic events are labelled `demo=true`, live in index `teleport_demo`, and are never written into `index=teleport`. The generators refuse to overwrite existing files.

## Before the final demo

Require a real DNS name and a valid TLS certificate before using `tbot` and MCP against a non-local cluster.

## Known housekeeping

Some tracked config files contain absolute paths under a local user directory. They are not secrets, but review them before making the repository public.
