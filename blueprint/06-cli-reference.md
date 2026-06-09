# REPL Command Reference

## Launching the Application

```bash
rmgr
# or
riskmanager-cli
```

`rmgr` launches the interactive REPL shell directly. There are no one-shot
command-line arguments — all interaction happens within the running session.

---

## Screen Layout

```
┌──────────────────────────────────────────────────────────────┐
│  [Project: Alpha]  ›  [Route: 1.1]  ›  [Stage: Reaction]    │  ← status bar
│  MODE: route                                                 │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│   (output pane — command results, lists, dashboards)         │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  > /                                                         │  ← input line
└──────────────────────────────────────────────────────────────┘
```

- **Status bar** — breadcrumb showing current context; updates on navigation
- **Output pane** — command results; clears and redraws on each command
- **Input line** — slash-command input; `>` prompt; text accumulates as typed

---

## Navigation Model

### Tracks

The application has three top-level tracks:

| Track | Description | Entry |
|-------|-------------|-------|
| **Project** | Navigate projects, routes, stages, components, risks | Home screen (default) |
| **Library** | Browse and manage materials, NCRM, counterions | `/library` from anywhere |
| **Admin** | Bulk imports, database maintenance | `/admin` from home only |

### Navigation Hierarchy (Project Track)

```
Home
  └── Project (selected from list)
        ├── Route Mode → (route selected from list)
        │     ├── Stage Focus
        │     │     └── Component Focus
        │     └── Risk Mode (process-level)
        └── Risk Mode (project-level summary)
```

### Arrow Key Navigation

Arrow keys are active only on **list screens** (Home, Route selection):
- `↑` / `↓` — move cursor through list items
- `Enter` — confirm selection of highlighted item
- List screens show two sections: **Recents** (last used, top) and **All** (alphabetical, below)

Everywhere else, interaction is via slash commands.

---

## Escape Navigation

- **First `Esc`** — clears the current input buffer. Displays a message:
  `[ESC] Press Escape again to return to <parent screen>.`
  If a guided prompt (e.g. `/add`) is in progress, adds:
  `Warning: unsaved input will be lost.`
- **Second `Esc` within ~2 seconds** — navigates up one level in the context stack
- **Timeout** — if the second Esc is not pressed within ~2 seconds, the message
  clears and normal input resumes
- `/home` — jump directly to the home screen from any depth

---

## Global Commands (available in all modes)

| Command | Description |
|---------|-------------|
| `/home` | Return to the home screen |
| `/library [materials\|ncrm\|counterions]` | Switch to library track |
| `/help [command]` | Show help for all commands or a specific command |
| `/quit` | Exit the application (unsaved data guard applies) |

---

## Home Screen

Displays two lists: **Recents** (last 5 projects) and **All Projects**.

Use arrow keys to navigate, `Enter` to select. Or type:

```
/select <project name>    — select a project by name (partial match supported)
/admin                    — enter admin sub-mode
/library                  — switch to library track
/help                     — show all commands
/quit                     — exit
```

---

## Project Screen

Shown after selecting a project. Displays: project name, material, therapy area,
number of routes, and a risk summary table.

```
/route [R.P]              — enter route selection (or go direct to route R.P)
/risks                    — enter project-level risk summary
/select <project>         — switch to a different project
/library                  — switch to library track
```

---

## Route Selection Screen

Displays two lists: **Recents** (recently used routes in this project) and
**All Routes**. Use arrow keys to navigate, `Enter` to select.

```
/route <R.P>              — go directly to route R process P (e.g. /route 1.1)
```

---

## Route View (primary working mode)

Displays the ASCII process layout and a risk dashboard (top risks by level).

### Navigation
```
/risks                    — view manufacturing process-level risks
/focus stage <name>       — focus on a specific stage
/focus component <name>   — focus on a specific component
/focus process            — focus on process-level risks
```

### Listing
```
/list stages              — list all stages in this route
/list components          — list all components in this route
/list risks               — list all risks for this route (all levels)
/list ncrm                — list all NCRMs linked to stages in this route
```

### Creating
```
/add stage <name> --number N           — add a stage to this route
/add component <name>                  — add a component (guided prompt)
/add risk                              — add a risk (guided prompt, asks level)
/add risk stage <name>                 — add a risk to a specific stage
/add risk component <name>             — add a risk to a specific component
/add risk process                      — add a process-level risk
/add stage-component                   — link a stage and component (guided)
/add stage-ncrm                        — link a stage and NCRM (guided)
```

### Editing and Deleting
```
/edit                     — edit the current route (guided prompt)
/edit stage <name>        — edit a specific stage
/edit component <name>    — edit a specific component
/delete stage <name>      — delete a stage (with confirmation)
/delete component <name>  — delete a component (with confirmation)
```

### Searching
```
/search <query>           — search for stages or components by name
```

---

## Stage Focus View

Shown after `/focus stage <name>`. Displays stage details, linked components,
NCRMs, and risks table.

```
/add risk                 — add a risk to this stage (guided prompt)
/add ncrm <name>          — link an NCRM to this stage (guided prompt)
/add component <name>     — link a component to this stage
/list risks               — show risks for this stage
/list components          — show components linked to this stage
/list ncrm                — show NCRMs linked to this stage
/edit                     — edit this stage
/delete                   — delete this stage (with confirmation)
```

---

## Component Focus View

Shown after `/focus component <name>`. Displays component details, salt data,
and risks table.

```
/add risk                 — add a risk to this component (guided prompt)
/add salt                 — add salt formation data (guided prompt)
/list risks               — show risks for this component
/edit                     — edit this component
/delete                   — delete this component (with confirmation)
```

---

## Risk Mode

Entered via `/risks` from the project, route, stage, or component context.
Displays a filterable risk table.

```
/add risk                 — add a new risk (guided prompt)
/edit --id <N>            — edit risk by ID shown in table
/delete --id <N>          — delete risk by ID (with confirmation)
/filter type <TYPE>       — filter by risk type (Safety, Quality, Environment)
/filter level <N>         — show only risks at level N or above
/sort level               — sort risks by current level (descending)
```

---

## Library Track

Entered via `/library` from any screen.

```
/library materials        — browse materials
/library ncrm             — browse NCRM library
/library counterions      — browse counterions
```

### Within library sub-modes

```
/list                     — list all entries (with optional --limit N)
/search <query>           — search by name
/add                      — add an entry (guided prompt)
/edit <name>              — edit an entry (guided prompt)
/delete <name>            — delete an entry (with confirmation)
/show <name>              — show full details for an entry
/filter has-smiles        — show only entries with SMILES
/filter no-smiles         — show only entries without SMILES
```

**Material-specific:**
```
/add material <name> [--smiles SMILES] [--alias ALIAS] [--enable-dmta]
/edit material <name> [--set-name NAME] [--set-smiles SMILES] [--add-alias ALIAS]
```

**NCRM-specific:**
```
/add ncrm --display-name NAME --common-name NAME [--alias ALIAS] [--smiles SMILES]
```

**Counterion-specific:**
```
/add counterion <name> [--smiles SMILES] [--alias ALIAS]
```

---

## Admin Sub-mode

Entered via `/admin` from the **home screen only**.

### Bulk Import

All import commands support `--skip-errors` and `--dry-run` flags.

```
/admin import materials <file.csv>       — bulk import materials
/admin import ncrm <file.csv>            — bulk import NCRM library entries
/admin import counterions <file.csv>     — bulk import counterions
/admin import projects <file.csv>        — bulk import projects
/admin import stages <file.csv>          — bulk import stages
/admin import components <file.csv>      — bulk import components
/admin import stage-components <file.csv>
/admin import stage-ncrm <file.csv>
/admin import component-salts <file.csv>
```

**Options:**

| Flag | Description |
|------|-------------|
| `--dry-run` | Preview import without writing to database |
| `--skip-errors` | Continue processing remaining rows on individual row failure |

### Database Maintenance

```
/admin db analyze           — check SMILES canonicality across all materials and NCRM
/admin db analyze --ncrm    — include NCRM library in analysis
/admin db canonicalize      — auto-canonicalize non-canonical SMILES using RDKit
/admin db canonicalize --dry-run  — preview canonicalization without writing
```

---

## CSV Formats for Bulk Import

### Materials

```csv
name,smiles,aliases
Aspirin,CC(=O)Oc1ccccc1C(=O)O,Acetylsalicylic Acid;ASA
Ibuprofen,CC(C)Cc1ccc(C(C)C(=O)O)cc1,Advil;Motrin
```

### Projects

```csv
name,therapy_area,material_name
Project Alpha,Oncology,Aspirin
Project Beta,CVRM,Ibuprofen
```

### Manufacturing Processes

```csv
project_name,route_number,process_number
Project Alpha,1,1
Project Alpha,1,2
```

### Stages

```csv
project_name,route_number,process_number,stage_name,stage_number
Project Alpha,1,1,Reaction,1
Project Alpha,1,1,Purification,2
```

### NCRM Library

```csv
display_name,common_name,aliases,interpret_chemically,smiles
Sodium bicarbonate,NaHCO3,Baking soda;Bicarb,false,
Palladium on carbon,Pd/C,,true,
```

### Counterions

```csv
name,smiles,aliases
Chloride,[Cl-],Cl-;chloride anion
Sodium,[Na+],Na+
```

---

## Guided Prompts

Commands like `/add risk` enter a **guided prompt mode** where the REPL asks for
each required field one at a time. The output pane shows the form in progress;
the input line collects each answer.

Example `/add risk` flow:

```
> /add risk

  Adding risk to: Route 1.1

  Risk type [Safety / Quality / Environment]: Safety
  Risk name: Explosion hazard
  Description (optional): Pressure build-up during nitration step
  Current risk level [1-10]: 8
  Proposed mitigation (optional): Install pressure relief valve
  Mitigated risk level [1-10]: 3

  [DRY RUN / PREVIEW]
  ─────────────────────────────────────
  Type    : Safety
  Name    : Explosion hazard
  Level   : 8 → 3 (mitigated)
  ─────────────────────────────────────
  Confirm? [y/n]: y

  ✓ Risk created.
```

Press `Esc` twice during a guided prompt to abort without saving.

---

## Therapy Areas (valid values)

```
Oncology
CVRM
Respiratory and Immunology
Vaccines and Immune Therapies
Rare Diseases
```

---

## NCRM Roles (valid values)

```
reagent
catalyst
solvent
additive
internal_standard
```

---

## Exit

```
/quit            — clean exit (saves session state, prompts if unsaved changes)
Ctrl+C           — interrupt exit (session state saved)
Ctrl+D           — EOF exit (session state saved)
```
