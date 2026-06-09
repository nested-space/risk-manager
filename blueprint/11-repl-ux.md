# REPL UX Specification

## Overview

This document defines the complete user experience for the interactive REPL shell.
It covers screens, navigation flows, input handling, visual layout, escape
behaviour, guided prompts, session persistence, and terminal management.

The application uses `blessed` for terminal control. The core design principle is:
**minimum friction for the most common workflow** (navigating into a project and
route to review and update risks and manufacturing steps).

---

## Screen Architecture

The terminal is divided into three permanent regions:

```
Row 0    ┌──────────────────────────────────────────────────────────────┐
         │  STATUS BAR  (1–2 rows)                                      │
Row 1    │  Breadcrumb + mode indicator                                 │
Row 2    ├──────────────────────────────────────────────────────────────┤
         │                                                              │
         │  OUTPUT PANE  (variable height)                              │
         │  Command results, tables, ASCII diagrams, dashboards         │
         │                                                              │
Row N-1  ├──────────────────────────────────────────────────────────────┤
Row N    │  INPUT LINE  (1 row)  >  /                                   │
         └──────────────────────────────────────────────────────────────┘
```

- `N` = `term.height - 1` (last row)
- The output pane occupies rows 2 through `N-2`
- On terminal resize (`SIGWINCH`), all three regions are fully redrawn

### Status Bar

The status bar is always visible and shows the current navigation context
as a breadcrumb:

```
[ Home ]
[ Project: Alpha ]
[ Project: Alpha ]  ›  [ Route: 1.1 ]
[ Project: Alpha ]  ›  [ Route: 1.1 ]  ›  [ Stage: Reaction ]
[ Library: Materials ]
[ Admin ]
```

The mode indicator on the second status row provides additional context:

```
MODE: route              — in Route View
MODE: risks (process)    — in Risk Mode for a process
MODE: focus (stage)      — in Stage Focus view
MODE: library            — in Library track
MODE: admin              — in Admin sub-mode
```

### Input Line

The input line shows the prompt `> ` followed by the user's current input buffer.

During list navigation (Home, Route Selection), the input line is suppressed and
replaced by navigation hint text:

```
  ↑↓ to navigate  ·  Enter to select  ·  /search <name> to filter
```

During a guided prompt (`/add`, `/edit`), the input line shows the current field
label as a prefix:

```
  Risk name: █
  Current risk level [1-10]: █
```

---

## Colour Conventions (using blessed + colorama)

| Element | Colour |
|---------|--------|
| Status bar background | Dark blue (`term.on_blue`) |
| Status bar text | White bold |
| Breadcrumb separator `›` | Cyan |
| Output: success | Green |
| Output: error | Red |
| Output: warning | Yellow |
| Output: info / dry-run | Cyan |
| Table header row | Cyan bold |
| Table separator | Dim white |
| Risk level critical (8–10) | Red bold |
| Risk level high (6–7) | Yellow bold |
| Risk level medium (4–5) | Yellow |
| Risk level low (1–3) | Green |
| List item (normal) | White |
| List item (highlighted/cursor) | Black on white (inverted) |
| Section header (Recents / All) | Cyan bold, underlined |
| Input prompt `> ` | Cyan |

---

## Screens

### Home Screen

**Trigger:** Application launch; `/home` from any screen.

**Layout:**

```
┌──────────────────────────────────────────────────────────────┐
│  [ Home ]                                                    │
│  MODE: home                                                  │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ── Recents ──────────────────────────────────────────────── │
│    ▶ Project Alpha                     (last used: today)    │
│      Project Beta                      (last used: 2d ago)   │
│      Project Gamma                     (last used: 1w ago)   │
│                                                              │
│  ── All Projects ─────────────────────────────────────────── │
│      Project Alpha                                           │
│      Project Beta                                            │
│      Project Delta                                           │
│      Project Gamma                                           │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  ↑↓ to navigate  ·  Enter to select  ·  /admin  /library    │
└──────────────────────────────────────────────────────────────┘
```

**Behaviour:**
- The `▶` arrow marks the cursor position (highlighted row)
- On launch, the cursor starts at the most recently used project in Recents
- If no Recents exist (first run or empty database), cursor starts at the first
  entry in All Projects
- `↑`/`↓` navigate through both lists; the cursor wraps from Recents to All
  seamlessly (no skipping the section header)
- `Enter` selects the highlighted project and navigates to the Project Screen
- Typing `/` immediately activates slash-command mode (input line appears)

**Available slash commands from home:**

```
/select <name>    — select a project by partial name match
/admin            — enter Admin sub-mode
/library          — switch to Library track
/help             — show help
/quit             — exit
```

---

### Project Screen

**Trigger:** After selecting a project from the Home Screen or via `/select <name>`.

**Layout:**

```
┌──────────────────────────────────────────────────────────────┐
│  [ Project: Alpha ]                                          │
│  MODE: project                                               │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Project Alpha                                               │
│  Material:       Aspirin (CC(=O)Oc1ccccc1C(=O)O)            │
│  Therapy Area:   Oncology                                    │
│  Routes:         3 routes / 5 processes                      │
│                                                              │
│  ── Risk Summary ────────────────────────────────────────── │
│  Level       Count    Highest Risk                           │
│  Critical    2        Explosion hazard (Stage 1, Route 1.1)  │
│  High        5        Solvent toxicity (Stage 2, Route 1.1)  │
│  Medium      8        —                                      │
│  Low         12       —                                      │
│                                                              │
│  ── Commands ────────────────────────────────────────────── │
│  /route   /risks   /library   /home   /help                  │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  > /                                                         │
└──────────────────────────────────────────────────────────────┘
```

**Available slash commands:**

```
/route [R.P]     — enter Route selection (or go direct to route R process P)
/risks           — enter project-level risk summary
/select <name>   — switch to a different project
/library         — switch to Library track
/home            — return to home
/help            — show help
```

---

### Route Selection Screen

**Trigger:** `/route` without a specific route number, when multiple routes exist.

**Layout:** Identical list style to Home Screen, but lists routes/processes.

```
┌──────────────────────────────────────────────────────────────┐
│  [ Project: Alpha ]  ›  [ Route ]                            │
│  MODE: route-select                                          │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  ── Recents ──────────────────────────────────────────────── │
│    ▶ Route 1.1  —  Project Alpha                             │
│      Route 2.1  —  Project Alpha                             │
│                                                              │
│  ── All Routes ────────────────────────────────────────────  │
│      Route 1.1  (route 1, process 1)                         │
│      Route 1.2  (route 1, process 2)                         │
│      Route 2.1  (route 2, process 1)                         │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  ↑↓ to navigate  ·  Enter to select  ·  /route <R.P>        │
└──────────────────────────────────────────────────────────────┘
```

**Behaviour:**
- Cursor starts at the most recently used route for this project
- `Enter` selects and navigates to Route View

---

### Route View

**Trigger:** After selecting a route; or via `/route R.P` directly.

**Layout:**

```
┌──────────────────────────────────────────────────────────────┐
│  [ Project: Alpha ]  ›  [ Route: 1.1 ]                       │
│  MODE: route                                                 │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Route 1.1  —  Synthesis of Aspirin                          │
│                                                              │
│  ┌──────────────┐   ┌───────────────┐   ┌───────────────┐   │
│  │   Stage 1    │──▶│    Stage 2    │──▶│   Stage 3     │   │
│  │  Nitration   │   │ Purification  │   │  Isolation    │   │
│  └──────────────┘   └───────────────┘   └───────────────┘   │
│                                                              │
│  ── Risk Dashboard ──────────────────────────────────────── │
│  [CRITICAL]  Explosion hazard   —  Stage 1: Nitration   (9) │
│  [CRITICAL]  Pressure build-up  —  Process level        (8) │
│  [HIGH]      Solvent toxicity   —  Stage 2: Purification(7) │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  > /                                                         │
└──────────────────────────────────────────────────────────────┘
```

**Risk Dashboard:**
- Shows the top N risks across all levels of this route, sorted by current level (descending)
- N defaults to the number of rows available in the output pane (adapts to terminal height)
- Risk level colour coding applied to `[CRITICAL]`/`[HIGH]`/`[MEDIUM]`/`[LOW]` labels

---

### Stage Focus View

**Trigger:** `/focus stage <name>` from Route View.

```
┌──────────────────────────────────────────────────────────────┐
│  [ Project: Alpha ]  ›  [ Route: 1.1 ]  ›  [ Stage: Nitration ] │
│  MODE: focus (stage)                                         │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Stage: Nitration  (Step 1)                                  │
│                                                              │
│  ── Components ──────────────────────────────────────────── │
│  Aspirin (API, reactant)                                     │
│  Acetic anhydride (reagent, not isolated)                    │
│                                                              │
│  ── NCRMs ───────────────────────────────────────────────── │
│  Sulfuric acid  [catalyst]                                   │
│  Dichloromethane  [solvent]                                  │
│                                                              │
│  ── Risks ───────────────────────────────────────────────── │
│  [CRITICAL]  Explosion hazard  (Safety, current: 9)          │
│  [MEDIUM]    Purity concern    (Quality, current: 5)         │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  > /                                                         │
└──────────────────────────────────────────────────────────────┘
```

---

### Component Focus View

**Trigger:** `/focus component <name>` from Route View or Stage Focus.

```
┌──────────────────────────────────────────────────────────────┐
│  [ Project: Alpha ]  ›  [ Route: 1.1 ]  ›  [ Component: Aspirin ] │
│  MODE: focus (component)                                     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Component: Aspirin                                          │
│  Role:       API                                             │
│  Isolated:   Yes                                             │
│  SMILES:     CC(=O)Oc1ccccc1C(=O)O                          │
│                                                              │
│  ── Salt Formation ─────────────────────────────────────── │
│  Counterion:    Sodium  ([Na+])                              │
│  Stoichiometry: 1.0                                          │
│  Fully defined: Yes                                          │
│                                                              │
│  ── Risks ───────────────────────────────────────────────── │
│  [HIGH]   Degradation   (Quality, current: 7 → mitigated: 3) │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  > /                                                         │
└──────────────────────────────────────────────────────────────┘
```

---

### Risk Mode

**Trigger:** `/risks` from project, route, stage, or component context.

The output pane shows a full filterable risk table. The status bar appends
the risk scope:

```
[ Project: Alpha ]  ›  [ Route: 1.1 ]  ›  [ Risks ]
MODE: risks (process)
```

**Table format:**

```
#   Type       Name                  Level  Mitigated  Scope
──  ─────────  ────────────────────  ─────  ─────────  ────────────────────
1   Safety     Explosion hazard      9      3          Stage 1: Nitration
2   Safety     Pressure build-up     8      —          Process level
3   Quality    Purity concern        5      —          Stage 1: Nitration
4   Environment  Solvent disposal    4      2          Stage 2: Purification
```

---

### Library Track

**Trigger:** `/library [materials|ncrm|counterions]` from any screen.

```
┌──────────────────────────────────────────────────────────────┐
│  [ Library: Materials ]                                      │
│  MODE: library                                               │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  (material list or search results)                           │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  > /                                                         │
└──────────────────────────────────────────────────────────────┘
```

The default sub-mode is determined by context: if the user entered from a
material-related operation, `/library materials` is shown by default.
Otherwise, a sub-mode selector is shown:

```
Select library:  materials  /  ncrm  /  counterions
```

---

### Admin Sub-mode

**Trigger:** `/admin` from the **Home Screen only**. If `/admin` is typed from
any other screen, the output pane shows:

```
⚠  Admin is only accessible from the home screen.
   Type /home first, then /admin.
```

**Layout:**

```
┌──────────────────────────────────────────────────────────────┐
│  [ Admin ]                                                   │
│  MODE: admin                                                 │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  Admin sub-mode                                              │
│                                                              │
│  ── Bulk Import ─────────────────────────────────────────── │
│  /admin import materials <file.csv>                          │
│  /admin import ncrm <file.csv>                               │
│  /admin import counterions <file.csv>                        │
│  /admin import projects <file.csv>                           │
│  /admin import stages <file.csv>                             │
│  /admin import components <file.csv>                         │
│  /admin import stage-components <file.csv>                   │
│  /admin import stage-ncrm <file.csv>                         │
│  /admin import component-salts <file.csv>                    │
│                                                              │
│  ── Database ────────────────────────────────────────────── │
│  /admin db analyze [--ncrm]                                  │
│  /admin db canonicalize [--dry-run] [--ncrm]                 │
│                                                              │
│  Options: --dry-run  --skip-errors                           │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  > /                                                         │
└──────────────────────────────────────────────────────────────┘
```

---

## Input Handling

### Normal Mode

Characters accumulate in an input buffer displayed on the input line.
Input begins with `/` for slash commands.

| Key | Action |
|-----|--------|
| Printable chars | Append to input buffer |
| `Backspace` | Remove last character from buffer |
| `Delete` | Clear entire buffer |
| `Enter` | Submit buffer as slash command |
| `↑` / `↓` | Active only on list screens; navigate cursor |
| `Esc` | First Esc press (see Escape Handling) |
| `Ctrl+C` | Clean exit (saves session state) |
| `Ctrl+D` | EOF exit (saves session state) |

### List Navigation Mode

Active on Home Screen and Route Selection Screen. Arrow keys move the cursor.

| Key | Action |
|-----|--------|
| `↑` | Move cursor up; wraps from top to bottom |
| `↓` | Move cursor down; wraps from bottom to top |
| `Enter` | Confirm selection of highlighted item |
| Any `/` | Exit list mode; enter slash-command mode |
| `Esc` | First Esc press (see Escape Handling) |

### Guided Prompt Mode

Active during multi-step `/add` and `/edit` flows.

| Key | Action |
|-----|--------|
| Printable chars | Input for current field |
| `Backspace` | Remove last character |
| `Enter` | Confirm current field value; advance to next field |
| `Enter` (empty) | Use default value if available; skip optional fields |
| `Esc` | First Esc press — warns about data loss |
| `Esc` × 2 | Abort the guided prompt; return to previous screen |

---

## Escape Navigation

### State Machine

```
  Normal input          First Esc pressed
  (buffer may be empty) ─────────────────▶  WARNING STATE
                                             │
                        Second Esc < 2s      │  Timeout (2s)
                        ─────────────────────▼  ──────────▶  Back to normal
                        Navigate up one level
```

### Warning Message

First Esc press clears the input buffer and displays in the output pane:

```
  [ESC] Press Escape again within 2 seconds to return to: [ Project: Alpha ]

```

If a guided prompt is in progress:

```
  [ESC] Unsaved input will be lost.
        Press Escape again within 2 seconds to cancel and return to: [ Route: 1.1 ]
```

### Navigation Target

The navigation target is determined by the current context stack:

| Current Screen | Double-Esc Goes To |
|---------------|--------------------|
| Project Screen | Home Screen |
| Route Selection | Project Screen |
| Route View | Project Screen |
| Stage Focus | Route View |
| Component Focus | Route View |
| Risk Mode (process) | Route View |
| Risk Mode (project) | Project Screen |
| Library | Home Screen |
| Admin | Home Screen |

### Home Screen Escape

From the Home Screen, the first Esc shows:

```
  [ESC] Press Escape again within 2 seconds to quit.
```

The second Esc exits the application (equivalent to `/quit`).

---

## Session State

### File Location

Default: `~/.rmgr/session.json`
Override: `RMGR_SESSION_PATH` environment variable

### Schema

```json
{
  "recent_projects": [
    "uuid-project-1",
    "uuid-project-2",
    "uuid-project-3"
  ],
  "recent_routes": {
    "uuid-project-1": ["uuid-process-1", "uuid-process-3"],
    "uuid-project-2": ["uuid-process-5"]
  },
  "last_context": {
    "track": "project",
    "project_id": "uuid-project-1",
    "process_id": "uuid-process-1",
    "stage_id": null,
    "component_id": null
  },
  "version": 1
}
```

### Behaviour

- `recent_projects`: capped at 5 entries; most recent first
- `recent_routes`: per-project list; capped at 3 entries per project; most recent first
- `last_context`: snapshot of the last active context before exit
- On startup: `recent_projects` populates the Recents section on Home Screen
- On project select: project UUID is pushed to front of `recent_projects`
- On route select: route UUID is pushed to front of `recent_routes[project_id]`
- On clean exit (`/quit`, `Ctrl+C`, `Ctrl+D`): session state is written to disk
- If file is missing or JSON is malformed: silently reset to empty state; no error

---

## Guided Prompt Design

Guided prompts are used for `/add` and `/edit` commands. They replace the
slash-command input with a field-by-field form rendered in the output pane.

### Prompt Flow

1. Command dispatcher enters `PromptMode` with a list of `FieldSpec` objects
2. REPL loop routes `Enter` to `PromptMode.submit_field()` instead of command dispatch
3. Each `FieldSpec` defines: `label`, `type`, `required`, `default`, `choices`
4. After all fields are collected, a preview is shown in the output pane
5. A final `Confirm? [y/n]` prompt completes or aborts the operation

### Example: `/add risk`

```
Field sequence:
  1. Risk type       [Safety / Quality / Environment]  required, choices
  2. Risk name       free text                         required
  3. Description     free text                         optional
  4. Current level   integer 1–10                      required
  5. Proposed mitigation  free text                    optional
  6. Mitigated level integer 1–10                      optional (default: none)
  7. Confirm?        y/n                               required
```

### Example: `/add stage`

```
Field sequence:
  1. Stage name      free text                         required
  2. Stage number    integer                           required
  3. Confirm?        y/n                               required
```

### Validation During Prompts

- Choices: if user input is not in the choices list, re-prompt with error
- Integer fields: if non-integer entered, re-prompt with error
- Required fields: if empty and no default, re-prompt with `(required)` message
- Optional fields: empty input accepted; treated as `None`

---

## Terminal Resize Handling

The application listens for `SIGWINCH` (terminal resize signal). On resize:

1. Re-query `term.height` and `term.width`
2. Call `ScreenManager.draw_full()` to repaint all three regions
3. If in list mode, restore cursor position (clamped to new list bounds)

---

## First-Run Experience

If the database contains no projects:

**Home Screen shows:**

```
  ── All Projects ───────────────────────────────────────────
  (no projects yet)

  To get started:
    /library materials      — add materials to the library
    /admin import projects  — bulk import from CSV
```

If the NCRM library and counterions are also empty, Admin sub-mode is recommended
as the first step.

---

## `/help` Command

`/help` is context-sensitive: it shows only the commands available in the current
mode. `/help <command>` shows detailed usage for a specific command.

### Example output for `/help` in Route View

```
  Commands available in Route View:

  Navigation
    /home                 Return to home screen
    /risks                View process-level risks
    /focus stage <name>   Focus on a stage
    /focus component <name>  Focus on a component
    /focus process        Focus on process-level risks
    /library              Switch to library track
    Esc × 2              Return to project screen

  Listing
    /list stages          List all stages
    /list components      List all components
    /list risks           List all risks for this route

  Creating
    /add stage <name>     Add a stage
    /add component <name> Add a component
    /add risk             Add a risk (guided prompt)

  Editing / Deleting
    /edit stage <name>    Edit a stage
    /delete stage <name>  Delete a stage

  Other
    /search <query>       Search stages and components
    /help [command]       Show this help
    /quit                 Exit
```

---

## Exit Behaviour

### Clean Exit (`/quit`)

1. If a guided prompt is in progress: warn the user and require confirmation
2. Write session state to disk
3. Restore terminal to normal mode (via `blessed` cleanup)
4. Exit with code `0`

### Interrupt Exit (`Ctrl+C`, `Ctrl+D`)

1. Session state is written to disk (best-effort; errors are suppressed)
2. Terminal restored to normal mode
3. Exit with code `0` for `Ctrl+D`; `130` for `Ctrl+C` (SIGINT convention)

### Crash Exit (unhandled exception)

1. Terminal restored to normal mode (via `atexit` handler registered at startup)
2. Full traceback printed to `stderr`
3. Exit with code `1`

The `atexit` handler ensures the terminal is always restored even on crash,
preventing the terminal from being left in raw/noecho mode.
