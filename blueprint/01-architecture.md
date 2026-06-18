# Architecture

## Overview

The application follows a **seven-layer architecture**. The top three layers
(REPL Loop, Screen Manager, Context Manager) replace the argparse-based CLI
from the original reference implementation. The bottom four layers
(Command Dispatcher, Operations, Database, Session State) handle business
logic and persistence.

Each layer communicates only with the layers immediately adjacent to it,
creating well-defined seams that make each layer independently testable
and replaceable.

---

## Engine / application split

The TUI is divided into two top-level packages joined by one explicit seam:

- **`repl_engine/`** — the application-agnostic terminal UI engine: the event
  loop (`loop.py`), screen drawing (`screen.py`), keystroke classification
  (`keys.py`), viewport scrolling (`viewport.py`, `sticky_window.py`), list
  navigation (`list_navigator.py`), the guided-prompt/picker forms engine
  (`forms.py`), and the layout primitives (`layout/`). It knows nothing about
  the risk-manager domain and imports no application code.
- **`repl/`** — the application: the command dispatcher (`commands.py`),
  navigation context (`context.py`), session state (`session_state.py`),
  bootstrap (`bootstrap.py`), and the domain screen renderers (`renderers/`).

**The seam is the `ReplController` protocol** (`repl_engine/controller.py`). The
engine's `start_repl(term, screen, controller)` drives any object implementing
that protocol; the application's `CommandDispatcher` is the concrete
implementation, supplying header text, screen capabilities, navigation, command
dispatch, and modal callbacks. Because the engine depends only on this
abstraction (dependency inversion), it could render a different application
unchanged.

The layer diagram below predates this split; treat `loop.py`, `screen.py`, and
the forms/viewport/layout machinery as living under `repl_engine/`, and the
dispatcher/context/renderers under `repl/`.

---

## Layer Diagram

```
┌──────────────────────────────────────────────────────────────┐
│  Entry Point  (__main__.py)                                  │
│  • Reads env vars (APP_ENV, APP_DB_PATH, RMGR_SESSION_PATH)  │
│  • Initialises SQLite DB on first run (create_all)           │
│  • Loads SessionState from ~/.rmgr/session.json              │
│  • Creates blessed Terminal instance                         │
│  • Launches REPL event loop                                  │
└───────────────────────┬──────────────────────────────────────┘
                        │ blessed.Terminal instance
┌───────────────────────▼──────────────────────────────────────┐
│  REPL Loop  (repl/loop.py)                                   │
│  • Main event loop via blessed terminal.inkey()              │
│  • Routes arrow keys → ListNavigator                         │
│  • Routes Enter → selection confirm or command submit        │
│  • Routes Escape → EscapeHandler (double-esc logic)          │
│  • Accumulates text input into slash-command buffer          │
│  • Dispatches complete /commands → CommandDispatcher         │
│  • Updates ContextManager on all navigation events           │
└───────────────────────┬──────────────────────────────────────┘
                        │ key events, command strings
         ┌──────────────┴──────────────────┐
         │                                 │
┌────────▼──────────────┐   ┌─────────────▼────────────────────┐
│  Screen Manager       │   │  Escape Handler                  │
│  (repl/screen.py)     │   │  (repl/escape_handler.py)        │
│  • Fixed regions:     │   │  • Double-esc timing (2s window) │
│    - Status bar (top) │   │  • First Esc: show warning +     │
│    - Output pane (mid)│   │    next destination              │
│    - Input line (bot) │   │  • Second Esc: navigate up       │
│  • draw_status_bar()  │   │  • Unsaved data guard            │
│  • draw_output()      │   └──────────────────────────────────┘
│  • draw_input()       │
│  • draw_list()        │
│  • Partial redraws:   │
│    status, output,    │
│    or full screen     │
└───────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  Context Manager  (repl/context.py)                          │
│  • Tracks current track: project | library | admin           │
│  • Navigation stack: [home, project, route, stage/component] │
│  • Holds selected entity IDs at each level                   │
│  • Provides current_breadcrumb() → status bar string         │
│  • Interfaces with SessionState for recents persistence      │
└───────────────────────┬──────────────────────────────────────┘
                        │ context + entity IDs
┌───────────────────────▼──────────────────────────────────────┐
│  Command Dispatcher  (repl/commands.py)                      │
│  • Parses slash command tokens: /cmd [sub] [args] [--flags]  │
│  • Routes to handler functions per command                   │
│  • Implements guided multi-step prompts for /add, /edit      │
│  • Returns RenderableContent → ScreenManager.draw_output()   │
│  • Implements /help (context-sensitive command listing)       │
└───────────────────────┬──────────────────────────────────────┘
                        │ typed Python values
┌───────────────────────▼──────────────────────────────────────┐
│  Operations Layer  (operations/*_operations.py)              │
│  • Async business logic functions (UNCHANGED from blueprint) │
│  • Open DB session via get_db_session()                      │
│  • Query and mutate models                                   │
│  • SMILES auto-detection, validation, canonicalization       │
│  • DMTA enrichment calls                                     │
│  • Bulk processing with skip-errors support                  │
└───────────────────────┬──────────────────────────────────────┘
                        │ SQLModel instances / None
┌───────────────────────▼──────────────────────────────────────┐
│  Database Layer  (database/, model/, schema/)                │
│  • SQLModel table definitions (model/tables.py)              │
│  • Pydantic create/update schemas (schema/)                  │
│  • Async session context manager (db_session.py)             │
│  • SQLite connection via aiosqlite                           │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────────────────────────────────────┐
│  Session State  (repl/session_state.py)           [sidecar]  │
│  • JSON file at ~/.rmgr/session.json                         │
│  • Persists: recent_projects, recent_routes, last context    │
│  • Loaded at startup; saved on context change + clean exit   │
│  • Corruption-safe: missing/invalid file → silent reset      │
└──────────────────────────────────────────────────────────────┘
```

---

## Layer Responsibilities

### Layer 1: Entry Point (`__main__.py`)

**Responsibilities:**
- Read `APP_ENV`, `APP_DB_PATH`, `RMGR_SESSION_PATH` from environment
- Build `Environment` enum and DB URL
- Run `init_db()` to create missing tables (idempotent)
- Load `SessionState` from disk
- Instantiate `blessed.Terminal`
- Call `start_repl(terminal, session_state, env)`

**Does NOT:**
- Contain navigation logic
- Access the database directly beyond initialization
- Format any console output

```python
def cli_main():
    env = Environment(os.getenv("APP_ENV", "dev"))
    asyncio.run(init_db(build_db_url(env)))
    session_state = SessionState.load(get_session_path())
    term = blessed.Terminal()
    start_repl(term, session_state, env)
```

---

### Layer 2: REPL Loop (`repl/loop.py`)

**Responsibilities:**
- Own the main `while True` event loop using `term.inkey(timeout=...)`
- Route key events to the correct handler:
  - Arrow keys → `ListNavigator` (project/route selection screens)
  - `Enter` → submit current selection or slash-command buffer
  - `Escape` → `EscapeHandler`
  - Printable characters → append to input buffer
  - `Backspace`/`Delete` → remove from input buffer
- Dispatch complete slash commands to `CommandDispatcher`
- Update `ContextManager` on navigation events
- Trigger `ScreenManager` partial redraws as needed

**Async bridge:**
`inkey()` is blocking. Async operations (DB calls) are dispatched via
`asyncio.get_event_loop().run_until_complete()` or a dedicated thread
using `asyncio.run()` for each operation call. The REPL loop itself
runs synchronously to ensure clean terminal control.

**Does NOT:**
- Render anything directly (delegates to `ScreenManager`)
- Contain business logic
- Open database sessions

---

### Layer 3: Screen Manager (`repl/screen.py`)

**Responsibilities:**
- Manage `blessed` terminal regions using absolute cursor positioning
- Divide the terminal into three fixed regions:
  - **Status bar** (top 1–2 rows): breadcrumb context + mode indicator
  - **Output pane** (middle): command results, lists, dashboards
  - **Input line** (bottom 1 row): prompt character + input buffer + hint text
- Expose drawing methods:
  - `draw_status_bar(breadcrumb: str)` — overwrites status bar only
  - `draw_output(content: RenderableContent)` — clears and redraws output pane
  - `draw_input(buffer: str, hint: str = "")` — overwrites input line
  - `draw_list(items: list, cursor: int)` — renders navigable list in output pane
  - `draw_full()` — redraws all three regions
- Handle terminal resize (`SIGWINCH`) by redrawing all regions

**Partial redraws:**
- Context navigation → `draw_status_bar()` + `draw_input()` only
- Data command output → `draw_output()` only
- List navigation (arrow keys) → `draw_list()` only (cursor position update)

---

### Layer 4: Context Manager (`repl/context.py`)

**Responsibilities:**
- Track the **current track**: `"project"`, `"library"`, or `"admin"`
- Maintain a **navigation stack** of `ContextFrame` objects:
  ```
  [home] → [project: Alpha] → [route: 1.1] → [stage: Reaction]
  ```
- Store **selected entity IDs** at each level (project UUID, process UUID, stage UUID, etc.)
- Provide `current_breadcrumb() -> str` for the status bar
- Record navigation events into `SessionState` for recents tracking
- Expose `pop()` to navigate up one level (used by `EscapeHandler`)

---

### Layer 5: Command Dispatcher (`repl/commands.py`)

**Responsibilities:**
- Parse slash command strings into `(command, subcommand, args, flags)`
- Route to handler functions:

| Command | Handler |
|---------|---------|
| `/select` | `handle_select(name, context, env)` |
| `/route` | `handle_route(route_spec, context, env)` |
| `/risks` | `handle_risks(context, env)` |
| `/focus` | `handle_focus(entity_type, name, context, env)` |
| `/add` | `handle_add(entity_type, args, context, env)` |
| `/edit` | `handle_edit(args, context, env)` |
| `/delete` | `handle_delete(args, context, env)` |
| `/list` | `handle_list(entity_type, filters, context, env)` |
| `/search` | `handle_search(query, context, env)` |
| `/filter` | `handle_filter(field, value, context, env)` |
| `/library` | `handle_library(sub, context, env)` |
| `/admin` | `handle_admin(sub, args, context, env)` |
| `/home` | `handle_home(context)` |
| `/help` | `handle_help(command, context)` |
| `/quit` | `handle_quit(session_state)` |

- For `/add` and `/edit`: orchestrate **guided multi-step prompts** (a lightweight
  prompt state machine that temporarily replaces the slash-command input with field-by-field questions)
- Return `RenderableContent` objects that `ScreenManager` renders in the output pane

**Does NOT:**
- Open database sessions directly (delegates to operations functions)
- Handle key events (that is the REPL loop's responsibility)

---

### Layer 6: Operations Layer (`operations/*_operations.py`)

**Responsibilities:**
- All async business logic (identical to the blueprint specification)
- Open and manage database sessions via `get_db_session()`
- Implement search, create, update, delete, and bulk operations
- SMILES auto-detection, validation, canonicalization
- DMTA enrichment
- Bulk CSV import with `skip_errors` support

See `AGENTS.md` §5 (Async Patterns / Error Handling) and the
`src/riskmanager_cli/operations/` modules for the operation pattern.

---

### Layer 7: Database Layer (`database/`, `model/`, `schema/`)

See `02-data-model.md` for the schema, and `src/riskmanager_cli/database/`
for the engine/session implementation.

---

## Seams and Boundaries

| Seam | Interface | What crosses it |
|------|-----------|-----------------|
| Entry Point → REPL Loop | Function call | `Terminal`, `SessionState`, `Environment` |
| REPL Loop → Screen Manager | Method calls | `RenderableContent`, cursor position |
| REPL Loop → Escape Handler | Method calls | Key event, context stack |
| REPL Loop → Context Manager | Method calls | Navigation events, entity selections |
| REPL Loop → Command Dispatcher | Slash command string | Parsed command + args |
| Command Dispatcher → Operations | Function calls with typed args | Python primitives, UUIDs, enums |
| Operations → Database | `get_db_session()` context manager | `AsyncSession` |
| Operations → External | `DmtaService` HTTP client | JSON payloads |
| Context Manager → Session State | Method calls | Recent entity IDs, context snapshot |

---

## Async Execution Model

The REPL loop runs **synchronously** (blocking `term.inkey()` for precise
terminal control). Async database operations are invoked from within the
synchronous loop using a helper:

```python
def run_async(coro):
    """Run an async coroutine from the synchronous REPL loop."""
    return asyncio.get_event_loop().run_until_complete(coro)
```

This is safe because:
- There is exactly one event loop created at startup
- The REPL loop never nests async calls
- Each DB operation opens and closes its own session

```
cli_main() [sync]                   ← entry point
    └── start_repl() [sync]         ← REPL event loop (blocking inkey)
            └── dispatch_command()  ← parse + route slash command
                    └── run_async(operation_fn(...))  ← async bridge
                            └── get_db_session()      ← async context manager
                                    └── SQLAlchemy async session
```

---

## Screen Layout

```
┌────────────────────────────────────────────────────────────┐  ← row 0
│  [Project: Alpha]  >  [Route: 1.1]  >  [Stage: Reaction]  │  ← status bar
│  MODE: route                                               │
├────────────────────────────────────────────────────────────┤  ← row 2
│                                                            │
│   Route 1.1: Synthesis of Aspirin                          │
│   ┌─────────────┐    ┌──────────────┐    ┌─────────────┐  │
│   │  Stage 1    │───▶│   Stage 2    │───▶│   Stage 3   │  │
│   │  Reaction   │    │ Purification │    │  Isolation  │  │
│   └─────────────┘    └──────────────┘    └─────────────┘  │
│                                                            │
│   ⚠ Risk Dashboard                                         │
│   [CRITICAL] Explosion hazard — Stage 1: Reaction          │
│   [HIGH]     Solvent toxicity  — Stage 2: Purification     │
│                                                            │
├────────────────────────────────────────────────────────────┤  ← penultimate row
│  > /                                                       │  ← input line
└────────────────────────────────────────────────────────────┘  ← last row
```

---

## Error Propagation

```
Database exception
    → operations layer: print_error(), return None/[]
    → command dispatcher: check return, produce error RenderableContent
    → screen manager: draw_output(error content)
    → REPL loop: continues; user can retry
```

Unlike the argparse CLI, errors in the REPL do **not** exit the process.
They are displayed in the output pane and the loop continues. The application
only exits on `/quit`, `Ctrl+C`, or `Ctrl+D`.
