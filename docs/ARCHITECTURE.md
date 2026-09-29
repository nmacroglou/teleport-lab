# Architecture

## Today: the Mac lab

Everything runs in Docker Desktop on one Mac. Only Teleport and Splunk publish ports, and only on `127.0.0.1`.

```mermaid
flowchart TB
  subgraph Mac["Mac (Docker Desktop)"]
    direction TB
    subgraph tele["Teleport 18.11.2 (auth + proxy)"]
      W[Web UI + API :3080]
      R[Reverse tunnel :3024]
    end
    LS[linux-server-1<br/>SSH node]
    WH[whoami<br/>web app]
    PG[(lab-postgres<br/>PostgreSQL 17)]
    SP[Splunk 10.4.3<br/>:8000]
    TB[tbot<br/>Machine ID, on the host]
    CC[Claude Code]
  end
  LS -->|reverse tunnel| R
  WH -->|app service| R
  PG -->|database service| R
  CC -->|MCP: tsh mcp db start| TB
  TB -->|1h certificate| W
  tele -->|audit log files, read-only mount| SP
```

Key points:

- **Resources dial out.** The Linux server, app and database connect to Teleport over a reverse tunnel. They publish no ports, so there is nothing to attack from the network.
- **Certificates, not passwords.** PostgreSQL trusts Teleport-issued client certificates. The `labreader` database user has no password and is read-only.
- **Local TLS.** The proxy certificate comes from a local mkcert CA. That is fine for a lab, but the final demo needs a real DNS name and a public certificate (see the roadmap).
- **Splunk reads files, not the network.** It mounts the Teleport audit log folder read-only. Session recordings and keys are not mounted.

## The AI identity path

```mermaid
sequenceDiagram
  participant N as Niko
  participant C as Claude Code
  participant B as tbot (lab-bot)
  participant T as Teleport
  participant D as lab-postgres
  participant S as Splunk
  N->>C: ask a question
  B->>T: join with one-time token, get identity (1h)
  C->>T: MCP database request as lab-bot
  T->>T: check role bot-lab-readonly
  alt allowed (labdb as labreader)
    T->>D: read-only query
    D-->>C: rows
  else not allowed (other database or user)
    T-->>C: access denied
  end
  T-->>S: audit event (allowed or denied)
```

The bot role `bot-lab-readonly` allows only database `labdb` as user `labreader`, on databases labelled `env: lab`. It has no SSH, app, Kubernetes or admin rules.

## Observability path

| Stage | What happens |
|---|---|
| Teleport | Writes JSON audit events (logins, certificates, sessions, queries, denials) |
| Splunk input | Monitors the audit folder; index `teleport`, sourcetype `teleport:audit` |
| Parsing | JSON fields extracted at search time; join tokens masked before indexing |
| Dashboards | Classic and Dashboard Studio views in the `teleport_lab` app |
| Demo data | Synthetic events go to a **separate** index, `teleport_demo` |

## Roadmap architecture: Ubuntu home server

```mermaid
flowchart LR
  M[Mac<br/>browser, tsh, Claude Code] -->|home network| U
  subgraph U[Ubuntu 24.04 home server]
    D[Docker] --> T[Teleport on 443<br/>real DNS name + TLS]
    D --> R1[Linux resource]
    D --> R2[Web app]
    D --> R3[(PostgreSQL)]
  end
```

The Mac lab stays as the rollback copy until the Ubuntu lab is fully working.

## Why this design matters

| Design choice | Why it matters |
|---|---|
| Reverse tunnels | No inbound ports on resources |
| Short-lived certificates | A stolen credential expires in hours |
| Separate bot identity | AI activity is attributable and revocable on its own |
| Deterministic RBAC | The agent is non-deterministic; the policy is not |
| Audit events to Splunk | Every allow and deny can be searched, alerted on and explained |
