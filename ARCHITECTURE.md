# Architecture

## 1. Goals

- Track project activity by **filesystem modification events**, independent of any
  specific editor or IDE.
- Never double-count overlapping activity across multiple files edited close
  together in time.
- Survive daemon restarts and crashes without losing accumulated time or confusing
  files with the same name.
- Keep the tracking **core** (Python) fully independent of macOS, so only the UI
  layer needs to change to support another OS later.

---

## 2. System Components

```
                         ┌─────────────────────────────┐
                         │   macOS Menu Bar UI         │
                         │   (Swift / SwiftUI)         │
                         │                             │
                         │  - shows live total time    │
                         │  - manual "add project"     │
                         │  - confirmation modal for   │
                         │    auto-detected projects   │
                         └──────────────┬──────────────┘
                                        │
                                 Unix Domain Socket
                           ~/.project_tracker/daemon.sock
                           (JSON messages, bidirectional)
                                        │
                         ┌──────────────┴───────────────────┐
                         │   Python Daemon (Core)           │
                         │                                  │
                         │  ┌────────────────────────────┐  │
                         │  │ Watcher Thread             │  │
                         │  │ (watchdog Observer)        │  │
                         │  └────────────┬───────────────┘  │
                         │               │ raw fs events    │
                         │               ▼                  │
                         │  ┌────────────────────────────┐  │
                         │  │ Aggregation Engine         │  │
                         │  │ (heartbeat/bucket logic,   │  │
                         │  │  idle/active state machine)│  │
                         │  └────────────┬───────────────┘  │
                         │               │ staged batches   │
                         │               ▼                  │
                         │  ┌────────────────────────────┐  │
                         │  │ Data Access Layer          │  │
                         │  │ (single writer thread)     │  │
                         │  └────────────┬───────────────┘  │
                         │               │                  │
                         │               ▼                  │
                         │  ┌────────────────────────────┐  │
                         │  │ IPC Server Thread          │  │
                         │  │ (socket server)            │  │
                         │  └────────────┬───────────────┘  │
                         │               │                  │
                         │               ▼                  │
                         │  ┌────────────────────────────┐  │
                         │  │ README Sync Scheduler      │  │
                         │  │ (periodic + on-shutdown)   │  │
                         │  └────────────────────────────┘  │
                         └───────────────┬──────────────────┘
                                         │
                                         ▼
                                ┌───────────────────┐
                                │  SQLite Database  │
                                │  (WAL mode)       │
                                └───────────────────┘
```

`launchd` sits outside this diagram entirely — it's the OS-level supervisor that
starts the daemon process, restarts it on crash, and starts it at login.

---

## 3. Concurrency Model

The daemon is **multi-threaded**, with each thread owning a single responsibility:

| Thread | Responsibility |
|---|---|
| Watcher thread | Runs the `watchdog` observer; converts raw OS filesystem events into normalized events and pushes them onto an internal thread-safe queue. |
| Aggregation engine | Consumes events from the queue, applies debounce/idle logic and the heartbeat-bucket algorithm, and produces *staged batches* of changes ready to persist. |
| Writer (data access) | The **only** thread that ever opens a write transaction against SQLite. All staged batches are handed to this thread and committed atomically. |
| IPC server thread | Accepts socket connections, handles inbound requests, and can push unsolicited messages (e.g. `new_project_detected`) to connected clients. |
| README sync scheduler | Wakes on a timer (10–15 min) and on shutdown, reads current totals, and rewrites the marker block in each tracked project's `README.md`. |

**Why a single writer thread even with WAL enabled:** SQLite's WAL mode allows many
concurrent *readers* alongside one *writer* without blocking, but it does not remove
the need for applicaton-level coordination of *what* gets written and *when* —
funnelling all writes through one thread avoids interleaved, partially-applied
batches without needing any explicit locks in application code.

Threads communicate through **thread-safe queues** (producer/consumer pattern) rather
than shared mutable state — the watcher thread never touches the database directly,
and the writer thread never touches the filesystem directly.

---

## 4. Data Flow (single edit, end to end)

```
file saved
   │
   ▼
watchdog fires event ──► Watcher Thread normalizes it ──► pushed to queue
   │
   ▼
Aggregation Engine consumes it
   │
   ├─ inside current 30s bucket for this project? ─── yes ──► no new project credit
   │                                                   no  ──► credit project +30s
   │
   ├─ file within debounce window? ── yes ──► collapse into current session
   │
   └─ idle timeout exceeded since last event? ── yes ──► close old session, start new one
   │
   ▼
Staged batch (project update + file update, grouped) ──► handed to Writer Thread
   │
   ▼
Writer Thread commits as ONE transaction
   │
   ▼
(every 10–15 min, or on shutdown)
README Sync Scheduler reads current totals ──► rewrites marker block in README.md
```

---

## 5. Database Schema

### `projects`
| Column | Notes |
|---|---|
| `id` | Surrogate primary key |
| `name` | Display name |
| `root_path` | Absolute path, **unique** |
| `total_seconds` | Aggregate, kept in sync by the writer thread |
| `readme_path` | Resolved path to this project's `README.md` |
| `status` | `pending_confirmation` / `confirmed` / `declined` (drives the auto-detection flow) |
| `created_at` | Timestamp |

### `file_logs`
| Column | Notes |
|---|---|
| `id` | Surrogate primary key — **the stable identity of a tracked file**, independent of its name or path |
| `project_id` | Foreign key → `projects.id` |
| `relative_path` | Path relative to the project root |
| `total_seconds` | Aggregate for this file |
| `last_active_at` | Timestamp of the most recent credited activity |
| `deleted_at` | Nullable — set when the file is deleted; row is never physically removed |

**Why a surrogate `id`, not the path, is the identity of a file:** paths are not
stable. A file can be deleted and a *new, unrelated* file can later be created with
the exact same name in the exact same folder. If identity were keyed on path alone,
the new file would silently inherit the old file's accumulated time. Soft-deleting
(`deleted_at` timestamp, row retained) instead of hard-deleting means a recreated
file always gets a **new** row and a **new** `id`, and history of the old file is
preserved rather than lost.

---

## 6. Locking Strategy

SQLite is opened in **WAL (Write-Ahead Logging) mode**, which allows concurrent
readers alongside a single writer without either blocking the other for normal
operations. No application-level locking code is written; this is a connection-level
configuration decision, not a runtime concern. Combined with the single-writer-thread
rule above (§3), this gives correctness (no interleaved writes) without hand-rolled
locks.

---

## 7. Staged / Batched Writes

Whenever more than one table changes together as a result of the same real-world
event (e.g. a brand-new project's first file appears — this touches both `projects`
and `file_logs`), the changes are **staged** in memory as a single group first, then
committed as **one transaction**. This guarantees all-or-nothing application of
related changes and avoids the daemon ever landing in a state where, say, a file row
exists but its parent project row does not.

---

## 8. Heartbeat / Bucket Aggregation Algorithm

Time is divided into fixed windows (default: 30 seconds). Within a single window,
any number of edits — to any number of files in the same project — credit that
project **once** for that window. Each individual file also accumulates its own
per-window credit independently, so per-file totals and the project total can both
be derived without double-counting at either level. 

An **idle/active session state machine** sits on top of the bucket logic: activity
resuming after a gap longer than the idle threshold (default: 5 minutes) starts a
fresh session rather than crediting the gap itself.

---

## 9. IPC Protocol

- **Transport:** Unix Domain Socket at `~/.project_tracker/daemon.sock`.
- **Encoding:** JSON messages, one logical message per exchange.
- **Direction:** Bidirectional — the UI can *request* (e.g. `get_status`), and the
  daemon can *push* unsolicited messages (e.g. `new_project_detected`,
  `project_totals_updated`) to any connected client.
- **Why Unix Domain Sockets over TCP:** communication is strictly local
  (same machine, daemon and UI both running as the same user), so a UDS avoids
  network-stack overhead and exposes no network-facing port at all.

Full message schema (message `type` values, payload shapes) is defined during
Step 5 of the roadmap.

---

## 10. Daemon Lifecycle

The daemon is supervised by **launchd** via a `.plist` file in
`~/Library/LaunchAgents/`, configured to:
- start the daemon at login,
- restart it automatically if it crashes,
- redirect its stdout/stderr to a log file for debugging.

This is entirely a macOS-specific configuration layer — swapping to Linux later
means replacing this with an equivalent `systemd` user service, without touching any
of the Python core.

---

## 11. README Sync Algorithm

On each sync (scheduled, or triggered at shutdown):
1. Look for the marker pair `<!-- TIME_TRACKER:START -->` / `<!-- TIME_TRACKER:END -->`
   in the project's `README.md`.
2. If found, **replace only the content between the markers**, wherever in the file
   they currently are — preserving any manual repositioning the user has done.
3. If not found, **append** a fresh marker block to the end of the file.
4. All other content in the file is left completely untouched.

---

## 12. Portability Boundary

| Layer | Portable? |
|---|---|
| Watcher, aggregation engine, data access layer, IPC server, README sync | ✅ Pure Python, no macOS dependency |
| IPC protocol (JSON over Unix Domain Socket) | ✅ Works identically on Linux |
| Menu bar UI | ❌ macOS-specific (Swift/SwiftUI) — swappable for a GTK/Qt tray app |
| Process supervision | ❌ macOS-specific (`launchd`) — swappable for `systemd` |

This boundary is the explicit target for Step 9 of the roadmap: proving the core is
genuinely OS-agnostic, not just "probably fine."
