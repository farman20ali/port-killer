# kport – Advanced Port & Process Management CLI

## 1. Overview

**kport** is a cross-platform, developer-focused CLI tool for inspecting, explaining, and safely managing ports, processes, Docker containers, and (future) Kubernetes networking.

It is designed for:

* Backend developers
* DevOps engineers
* Platform & SRE roles
* Anyone debugging port conflicts locally or in containers

> Core philosophy: **Explain first, act safely, automate cleanly**.

---

## 2. Problems kport Solves

### 2.1 Classic Port Conflicts

* “Port 8080 is already in use”
* Unknown background processes
* Zombie services after crashes

### 2.2 Docker & Container Confusion

* Port appears busy, but no host process exists
* Process runs inside a container namespace
* Developers don’t know *what* owns the port

### 2.3 Unsafe Killing

* Accidental `kill -9`
* Killing multiple unrelated processes
* No dry-run or explanation

### 2.4 Automation Gaps

* Tools that don’t support JSON
* No exit codes for CI/CD
* Hard to script safely

---

## 3. Key Design Principles

1. **Docker-aware by default**
2. **Safe by default (dry-run, confirmations)**
3. **Explainability over mystery**
4. **Automation-ready (JSON + exit codes)**
5. **Cross-platform (Linux, macOS, Windows)**

---

## 4. Supported Platforms

| Platform | Backend                                   |
| -------- | ----------------------------------------- |
| Linux    | lsof, ss, docker                          |
| macOS    | lsof, docker                              |
| Windows  | PowerShell (Get-NetTCPConnection), docker |

---

## 5. CLI Command Structure

```bash
kport <command> [options]
```

### Global Options

| Option    | Description                    |
| --------- | ------------------------------ |
| --json    | Output machine-readable JSON   |
| --dry-run | Show actions without executing |
| -y, --yes | Skip confirmation prompts      |
| --debug   | Verbose internal logs          |

---

## 6. Feature Set & Examples

---

## 6.1 Inspect a Port

### Command

```bash
kport inspect 8080
```

### Possible Outputs

#### Case 1: Local Process

```
Port: 8080
Type: Local Process
PID: 34521
Process: node
Command: node server.js
State: LISTENING
```

#### Case 2: Docker Container

```
Port: 8080
Type: Docker Container
Container: web-app
Image: nginx:latest
Host Port: 8080
Container Port: 80
Status: Running
```

#### Case 3: Port Free

```
Port 8080 is free
```

---

## 6.2 Explain Why a Port Is Blocked

### Command

```bash
kport explain 8080
```

### Output

```
Port 8080 is unavailable because:
- It is mapped to Docker container "web-app"
- Docker maps host port 8080 → container port 80
- The process runs inside an isolated network namespace
```

---

## 6.3 Kill / Free a Port Safely

### Command

```bash
kport kill 8080
```

### Behavior

#### If Local Process

```
Port 8080 is used by:
- PID: 34521
- Process: node

Action plan:
1. Send SIGTERM
2. Wait up to 5 seconds
3. Escalate to SIGKILL if needed

Proceed? (y/N)
```

#### If Docker Container

```
Port 8080 belongs to Docker container: web-app

Choose action:
1) Stop container
2) Restart container
3) Remove container
4) Cancel
```

---

## 6.4 Dry Run Mode

### Command

```bash
kport kill 8080 --dry-run
```

### Output

```
Dry run enabled.
Would stop Docker container: web-app
No action taken.
```

---

## 6.5 Kill by Process Name

### Command

```bash
kport kill-process node --exact
```

### Output

```
Matched processes:
PID     NAME    COMMAND
34521   node    node server.js

Proceed to terminate? (y/N)
```

---

## 6.6 List All Active Ports

### Command

```bash
kport list
```

### Output

```
PORT   TYPE        OWNER
3000   local       node
5432   docker      postgres-db
8080   docker      web-app
```

---

## 6.7 Docker-specific Commands

### List Docker Ports

```bash
kport docker
```

Output:

```
PORT   CONTAINER      IMAGE          STATUS
8080   web-app        nginx:latest   running
5432   postgres-db    postgres:15    running
```

---

## 6.8 Detect Port Conflicts

### Command

```bash
kport conflicts
```

### Output

```
WARNING: Port conflict detected

Port: 5432
- Docker container: postgres-db
- Local process: pgAdmin
```

---

## 6.9 JSON Output (Automation)

### Command

```bash
kport inspect 8080 --json
```

### Output

```json
{
  "port": 8080,
  "type": "docker",
  "container": "web-app",
  "image": "nginx:latest",
  "host_port": 8080,
  "container_port": 80,
  "status": "running"
}
```

---

## 7. Exit Codes

| Code | Meaning             |
| ---- | ------------------- |
| 0    | Success             |
| 1    | General error       |
| 2    | Invalid input       |
| 3    | Permission denied   |
| 4    | Port used by Docker |
| 5    | Port free           |

---

## 8. Internal Architecture

```
kport/
 ├─ core/
 │   ├─ inspector.py
 │   ├─ killer.py
 │   ├─ docker.py
 │   ├─ explainer.py
 ├─ adapters/
 │   ├─ linux.py
 │   ├─ windows.py
 │   └─ macos.py
 ├─ output/
 │   ├─ text.py
 │   └─ json.py
 ├─ cli.py
 └─ main.py
```

---

## 9. Security & Safety Guarantees

* No blind `kill -9`
* Confirmation required by default
* Exact-match process killing
* Docker-aware actions
* Dry-run support

---

## 10. kport Pro (Paid Local Edition)

kport Pro builds on the open-source core and targets **professional developers, DevOps engineers, consultants, and small teams** who want safety, automation, and deeper visibility.

### 10.1 kport Pro Feature List

#### 🔐 Advanced Safety & Control

* Graceful shutdown policies (SIGTERM → wait → SIGKILL)
* Configurable timeouts per process type
* Protected ports (cannot kill without override)
* Policy-based rules (e.g., never kill database ports)

#### 🧠 Intelligent Conflict Detection

* Detect local ↔ Docker ↔ systemd conflicts
* Identify reverse proxies (nginx, traefik)
* Explain *why* a conflict exists, not just that it exists

#### 🕵️ Port History & Audit (Local)

* Track which process/container used a port
* Timestamped usage history
* Useful for debugging intermittent issues

#### 🔁 Watch Mode

```bash
kport watch 8080
```

* Live monitoring of port ownership
* Alerts on port change or process restart

#### 📄 Automation & CI Enhancements

* SARIF output (for security tooling)
* Stable JSON schemas
* Deterministic exit codes
* Machine-readable explanations

#### 🧩 Deep Docker Awareness

* Docker Compose service names
* Multiple containers mapping same port
* Container restart reason analysis

---

### 10.2 kport Pro Paywall Architecture

**Open-Core Model**

| Layer                | Access |
| -------------------- | ------ |
| Core inspect / kill  | Free   |
| Explain mode (basic) | Free   |
| Advanced safety      | Pro    |
| Conflict engine      | Pro    |
| Watch mode           | Pro    |
| Port history         | Pro    |

#### Enforcement Mechanism

* License key (local, offline-first)
* Feature flags checked at runtime
* No cloud dependency for Pro

#### Pricing (Indicative)

* $5–10 / month (individual)
* $49–79 / year

---

## 11. kport Cloud (Agent + Backend SaaS)

kport Cloud turns kport from a **local tool** into an **organization-wide visibility platform**.

---

### 11.1 Problem kport Cloud Solves

* Who opened this port in production?
* Why did this service become unreachable?
* Is any sensitive port exposed accidentally?
* Are teams following port usage policies?

These questions are **high-value** and companies pay for answers.

---

### 11.2 High-Level Architecture

```
[ Server / VM / Node ]
        |
     kport-agent
        |
  Secure HTTPS / mTLS
        |
[ kport Cloud API ]
        |
[ Event Store + Analytics ]
        |
[ Web Dashboard + Alerts ]
```

---

### 11.3 kport Agent (Installed on Hosts)

Responsibilities:

* Periodic port scanning
* Docker & systemd inspection
* Detect changes (diff-based)
* Enforce local policies (optional)

Key Properties:

* Lightweight (low CPU/memory)
* Read-only by default
* No shell access

---

### 11.4 Backend Components

#### API Layer

* Receives agent reports
* Authenticates via API key / mTLS

#### Event Store

* Port open/close events
* Ownership changes
* Conflict events

#### Analytics Engine

* Exposure duration
* High-risk ports
* Trend analysis

#### Alerting Engine

* Slack / Email / Webhooks
* Threshold-based alerts

---

### 11.5 Dashboard Capabilities

* Real-time port map per host
* Docker & Kubernetes views
* Timeline ("who used port 6379 last week")
* Compliance status

---

### 11.6 Example SaaS Use Case

```
⚠️ Alert: Port 6379 exposed

Host: prod-node-3
Reason: Docker container started without firewall rule
Owner: team-backend
Duration: 12 minutes
```

---

### 11.7 Pricing Model (B2B SaaS)

| Tier       | Price              |
| ---------- | ------------------ |
| Starter    | $29 / node / month |
| Team       | $99 / node / month |
| Enterprise | Custom             |

---

## 12. Security & Trust Model

* Read-only agents by default
* Encrypted communication
* Least-privilege design
* Full audit trails

---

## 13. Updated Roadmap

### Phase 1 – Open Core

* Local + Docker awareness
* Explain mode

### Phase 2 – Pro

* Conflict engine
* Watch mode
* Safety policies

### Phase 3 – Cloud

* Agent + SaaS backend
* Alerts & dashboards

### Phase 4 – Enterprise

* Kubernetes
* Compliance exports
* RBAC & SSO

---

## 14. Strategic Positioning

kport evolves from:

CLI Tool → Pro Developer Utility → Infrastructure Visibility Platform

This positioning supports:

* Open-source adoption
* Sustainable revenue
* Enterprise credibility

### Phase 1 (Core – This Document)

* Docker detection
* Safe kill
* JSON output
* Explain mode

### Phase 2 (Professional)

* Windows PowerShell backend
* Conflict detection
* Config file support

### Phase 3 (Elite)

* Kubernetes (NodePort, port-forward)
* Remote host inspection
* Rust rewrite for performance

---

## 11. Positioning

**kport** is not just a port killer.

It is a:

* Developer productivity tool
* DevOps debugging utility
* Foundation for enterprise-grade diagnostics

---

## 12. Final Note

This design intentionally aligns with:

* Real developer pain
* Modern containerized workflows
* Automation & CI/CD standards

It is suitable for:

* Open-source release
* Technical blogging
* Portfolio for Big Tech & startups