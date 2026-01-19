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

## 10. Roadmap

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