# ProjectWatcher

A lightweight, editor-agnostic, background time tracker for programming projects.

ProjectWatcher watches your project folders and measures how much time you actually
spend working on each one — based on **file modification activity**, not on which
IDE or editor process happens to be running. It lives in the macOS menu bar, keeps
its data in a local SQLite database, and automatically keeps a running total in each
project's `README.md`.

---

## Key Features

- **Editor-agnostic tracking** — driven by filesystem `mtime` and change events, not
  by watching specific applications or window titles.
- **Idle-aware sessions** — activity pauses automatically after a configurable idle
  threshold (default: 5 minutes of no file changes).
- **Automatic project detection** — noticing a new folder with recognized
  programming-language files (`.py`, `.ts`, `.rs`, `.swift`, etc.) and asking
  before tracking it.
- **Menu bar UI** — a native macOS SwiftUI menu bar app showing live totals, with a
  manual "add project" option and a confirmation dialog for auto-detected projects.
- **Self-updating README badge** — each tracked project's `README.md` gets an
  auto-maintained `⏱️ Total Time Spent` block, kept in sync every 10–15 minutes.
- **Portable core** — the tracking engine (Python) is fully independent of macOS, so
  the SwiftUI frontend can eventually be swapped for a Linux GTK/Qt tray app without
  touching the core logic.

---

## Documentation

| Document | Contents |
|---|---|
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | System design: components, data flow, concurrency model, database schema, IPC protocol, README sync algorithm |
| [`TECH_STACK.md`](./TECH_STACK.md) | Languages, libraries, and tools used, with rationale for each choice |

---

## Project Structure

```
ProjectWatcher/
├── .github/
│   └── workflows/          # CI pipeline definitions
├── backend/                 # Python core: watcher, DB layer, daemon, IPC server
│   ├── src/
│   ├── test/
│   ├── requirements.txt
│   └── pytest.ini
├── frontend/                 # Swift/SwiftUI macOS menu bar app
│   ├── src/
│   └── test/
├── README.md
├── ARCHITECTURE.md
└── TECH_STACK.md
```

---

## Getting Started (development)

**Backend (Python):**
```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

**Frontend (Swift):** built and run via Xcode; details added once Step 8 of the
roadmap begins.

---

## Development Workflow

- **Test-first per module.** Every module gets its own test-then-code loop: write
  test cases for that module, implement against them, then extend the tests for any
  edge case discovered while building — never a single upfront test-writing pass for
  the whole project.
- **Independent tests.** Each test case sets up its own isolated state, so one
  failing test never cascades into unrelated failures.
- **Regression tests for real bugs.** Any bug found after the fact gets its own
  permanent, independent test case, in addition to (not replacing) the existing
  suite.
- **CI-gated merges.** Every push and pull request runs the backend test suite via
  GitHub Actions; branch protection blocks merging to `main` until the suite passes.

---

## License

See [`LICENSE`](./LICENSE).
