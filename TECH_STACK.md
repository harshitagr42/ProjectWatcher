# Tech Stack

## Backend Core (Python)

| Tech | Purpose | Why |
|---|---|---|
| **Python 3.13** | Core daemon language | Portable across macOS/Linux, rich stdlib, fast to iterate in |
| **`watchdog`** | Filesystem event monitoring | Cross-platform wrapper over native OS file-event APIs (FSEvents on macOS, inotify on Linux) — matches the portability goal directly |
| **`sqlite3`** (stdlib) | Database driver | No external DB server needed; single-file, zero-config, supports WAL mode natively |
| **`threading` + `queue`** (stdlib) | Concurrency | Thread-safe producer/consumer communication between the watcher, aggregation, and writer threads |
| **`socket`** (stdlib, `AF_UNIX`) | IPC transport | Native Unix Domain Socket support, no external dependency needed |
| **`json`** (stdlib) | IPC message encoding | Human-readable, trivially consumable from both Python and Swift |
| **`re`** (stdlib) | README marker detection/replacement | Sufficient for anchor-based text block matching without a templating engine |
| **`pytest`** | Backend test framework | Fixture system (`tmp_path`, etc.) is a natural fit for simulating isolated fake project directories per test |
| **`pytest`'s `tmp_path` fixture** | Test isolation | Gives every test its own disposable temp directory — no shared state between tests |

## Frontend (macOS Menu Bar UI)

| Tech | Purpose | Why |
|---|---|---|
| **Swift** | UI language | Native macOS language, required for a proper menu bar app |
| **SwiftUI** | UI framework | Declarative UI, `MenuBarExtra` gives a modern, low-boilerplate menu bar scene |
| **`Network.framework`** (or POSIX socket interop) | IPC client | Connects to the daemon's Unix Domain Socket; exact API choice decided in Step 8, based on `AF_UNIX` support at the target macOS version |
| **XCTest** | Frontend test framework | Standard Swift testing framework, kept as an entirely separate suite from the backend's pytest suite |

## Data Layer

| Tech | Purpose | Why |
|---|---|---|
| **SQLite (WAL mode)** | Source of truth for all persisted data | Single embedded file, concurrent-reader-friendly in WAL mode, no server process to manage |

## Inter-Process Communication

| Tech | Purpose | Why |
|---|---|---|
| **Unix Domain Socket** (`~/.project_tracker/daemon.sock`) | Transport between daemon and UI | Purely local communication — no network exposure, lower overhead than TCP |
| **JSON** | Message format | Simple, bidirectional, human-debuggable, natively supported on both sides |

## Process Supervision

| Tech | Purpose | Why |
|---|---|---|
| **`launchd`** (macOS) | Keeps the daemon running | Native macOS service manager — starts at login, restarts on crash |
| *(future)* **`systemd`** (Linux) | Equivalent supervisor on Linux | Swappable replacement when the portable core gets a Linux frontend |

## CI / CD & Tooling

| Tech | Purpose | Why |
|---|---|---|
| **Git / GitHub** | Version control & hosting | — |
| **GitHub Actions** | CI pipeline | Runs the backend test suite on every push/PR; a separate frontend (XCTest) job is added once Step 8 begins |
| **GitHub Branch Protection (Rulesets)** | Merge gating | Blocks merging into `main` until required status checks pass |

## Explicitly *not* used (and why)

| Considered | Why not (for now) |
|---|---|
| A full client-server database (Postgres/MySQL) | Massive overkill for a single-user local app; SQLite's WAL mode already gives sufficient concurrency |
| A message broker (e.g. Redis pub/sub) for IPC | A local Unix Domain Socket is simpler, has fewer moving parts, and needs no separate running service |
| An ORM (e.g. SQLAlchemy) | The schema is small and stable enough that direct `sqlite3` + a thin data-access layer stays easier to reason about than an ORM's abstraction overhead — worth revisiting only if the schema grows significantly |
