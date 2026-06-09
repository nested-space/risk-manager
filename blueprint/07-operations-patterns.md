# Operations Layer Patterns

## Overview

The operations layer contains all async business logic. Each entity has a
dedicated `<entity>_operations.py` file. Common patterns are extracted into
`base_operations.py` to eliminate duplication.

All operations functions are `async def` and open their own database sessions
via `get_db_session()`. They never share sessions across calls.

---

## Generic Base Operations (`base_operations.py`)

Four generic functions cover the most common patterns. Use these by default;
write specialized functions only when the generic approach is insufficient.

### `generic_get_by_id`

```python
async def generic_get_by_id(
    model_class: Type[T],
    entity_id: UUID,
    entity_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> Optional[T]:
    """Retrieve any entity by UUID primary key."""
    try:
        async with get_db_session(env, verbose) as session:
            results = await model_class.get_where(session, model_class.id == entity_id)
            return results[0] if results else None
    except Exception as e:
        print_error(f"Failed to get {entity_name} by ID: {e}")
        return None
```

**Use when:** Simple ID lookup with no joins or eager loading needed.

### `generic_check_exists`

```python
async def generic_check_exists(
    model_class: Type[T],
    entity_id: UUID,
    entity_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> bool:
    """Check if an entity exists by UUID."""
    try:
        async with get_db_session(env, verbose) as session:
            results = await model_class.get_where(session, model_class.id == entity_id)
            return len(results) > 0
    except Exception as e:
        print_error(f"Failed to check {entity_name} existence: {e}")
        return False
```

**Use when:** Validating a foreign key reference before creating a dependent entity.

**Do NOT use when:** Checking uniqueness by name, SMILES, or composite key.

### `generic_get_stats`

```python
async def generic_get_stats(
    model_class: Type[T],
    entity_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
    stats_calculator: Optional[Callable[[List[T]], Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Get entity statistics. Always returns dict with 'total' key."""
    try:
        async with get_db_session(env, verbose) as session:
            entities = await model_class.get_all(session)
            if stats_calculator:
                return stats_calculator(entities)
            return {"total": len(entities)}
    except Exception as e:
        print_error(f"Failed to get {entity_name} stats: {e}")
        return {"total": 0}
```

**Usage with custom calculator:**

```python
def calc_component_stats(components: list[Component]) -> dict:
    return {
        "total": len(components),
        "api_count": sum(1 for c in components if c.control_strategy_role == "API"),
        "isolated_count": sum(1 for c in components if c.is_isolated),
    }

stats = await generic_get_stats(Component, "component", stats_calculator=calc_component_stats)
```

### `generic_list_by_field`

```python
async def generic_list_by_field(
    model_class: Type[T],
    field_name: str,
    field_value: Any,
    entity_name: str,
    env: Environment = Environment.DEV,
    verbose: bool = False,
) -> List[T]:
    """List all entities where field_name == field_value (FK filtering)."""
    try:
        async with get_db_session(env, verbose) as session:
            field = getattr(model_class, field_name)
            return await model_class.get_where(session, field == field_value)
    except Exception as e:
        print_error(f"Failed to list {entity_name}s: {e}")
        return []
```

**Example:**

```python
stages = await generic_list_by_field(Stage, "process_id", process_uuid, "stage")
```

**Use when:** Simple FK filter with no eager loading or complex conditions.

---

## When to Use Generic vs Specialized

| Scenario | Approach |
|----------|---------|
| Get by UUID, no joins | `generic_get_by_id` |
| Check UUID existence | `generic_check_exists` |
| Count entities, simple stats | `generic_get_stats` |
| List by FK field | `generic_list_by_field` |
| Get by name or SMILES | Specialized function |
| Check uniqueness by name | Specialized function |
| Composite key check | Specialized function |
| Query with eager loading | Specialized function |
| Complex multi-condition filter | Specialized function |
| Requires special transaction flow | Specialized function |

---

## Session Management Pattern

Always use `get_db_session()` as an async context manager. Never pass sessions
between functions — each operation opens and closes its own session.

```python
from ..database.db_session import get_db_session
from ..config.settings import Environment

async def create_material(name: str, smiles: Optional[str], env: Environment, verbose: bool) -> Optional[Material]:
    try:
        async with get_db_session(env, verbose) as session:
            material = Material(name=name, smiles=smiles)
            session.add(material)
            await session.commit()
            await session.refresh(material)
            return material
    except Exception as e:
        print_error(f"Failed to create material: {e}")
        return None
```

**Session lifecycle:**
1. Engine created from connection URL
2. Session opened
3. Exception → automatic rollback
4. `finally` → session closed, engine disposed

---

## SMILES Auto-Detection Pattern

Used when searching materials by ID, SMILES, or name without the user specifying
the search type. Applied in `material_operations.py` and `update_material_by_search()`.

```python
def detect_search_type(search_value: str) -> str:
    """Detect whether a search value is a UUID, SMILES, or name.

    Returns:
        'id', 'smiles', or 'name'
    """
    try:
        UUID(search_value)
        return "id"
    except ValueError:
        pass

    # SMILES contain chemical characters without spaces
    chemical_chars = set("()[]=#@+-")
    if any(c in search_value for c in chemical_chars) and " " not in search_value:
        return "smiles"

    return "name"
```

**Usage in update operations:**

```python
search_type = detect_search_type(search_value)
if search_type == "id":
    condition = Material.id == UUID(search_value)
elif search_type == "smiles":
    condition = Material.smiles == search_value
else:
    condition = Material.name == search_value
```

---

## Dry-Run Pattern

Dry-run is checked in the **Command Dispatcher** (`repl/commands.py`), not in
operations. Operations are not called at all in dry-run mode. The `--dry-run`
flag is passed as part of the slash command:

```
/add risk --dry-run
/admin import materials compounds.csv --dry-run
```

The dispatcher checks for the flag before calling any operation:

```python
# In repl/commands.py
def handle_add_risk(args: CommandArgs, context: ContextManager, env: Environment) -> RenderableContent:
    if args.dry_run:
        return RenderableContent.info(f"[DRY RUN] Would create risk: '{args.name}' (level {args.current_level})")
    result = run_async(create_risk(args.risk_type, args.name, ..., env=env))
    if result:
        return RenderableContent.success(f"Risk created: '{result.name}'")
    return RenderableContent.error("Failed to create risk.")
```

---

## Bulk CSV Operation Pattern

```python
async def bulk_create_materials(
    csv_file: str,
    skip_errors: bool,
    dry_run: bool,
    env: Environment,
    verbose: bool,
) -> None:
    # 1. Parse entire file first
    rows = await parse_csv_file(csv_file, verbose=verbose)
    total = len(rows)
    print_info(f"Parsed {total} rows from {csv_file}")

    if dry_run:
        print_info(f"[DRY RUN] Would process {total} materials")
        return

    # 2. Process each row
    success_count = 0
    error_count = 0

    for i, row in enumerate(rows, 1):
        print_progress(f"Creating material", i, total)
        try:
            result = await create_material(
                name=row["name"],
                smiles=row.get("smiles"),
                aliases=row.get("aliases", []),
                env=env,
                verbose=verbose,
            )
            if result:
                success_count += 1
            else:
                error_count += 1
                if not skip_errors:
                    print_error(f"Stopping at row {i}. Use --skip-errors to continue.")
                    break
        except Exception as e:
            error_count += 1
            print_error(f"Row {i} ({row.get('name', '?')}): {e}")
            if not skip_errors:
                print_error("Stopping. Use --skip-errors to continue.")
                break

    # 3. Summary
    print_success(f"Completed: {success_count}/{total} created, {error_count} errors")
```

---

## CSV Parsing Pattern

CSV files support both comma and semicolon delimiters (auto-detected). Alias
fields within a cell are split on `;;`, `||`, `;`, or `, ` (in that order of preference).

**Implementation in `utils/parsing.py`:**

```python
import csv
import io

def detect_delimiter(first_line: str) -> str:
    """Auto-detect CSV delimiter from the header row."""
    semicolons = first_line.count(";")
    commas = first_line.count(",")
    return ";" if semicolons > commas else ","


def parse_aliases(value: str) -> list[str]:
    """Parse alias field supporting multiple delimiter strategies.

    Precedence: ';;' or '||' > ';' > ', ' (comma+space)
    This preserves chemical names like 'N,N-dimethylacetamide'.
    """
    if not value or not value.strip():
        return []
    if ";;" in value:
        return [a.strip() for a in value.split(";;") if a.strip()]
    if "||" in value:
        return [a.strip() for a in value.split("||") if a.strip()]
    if ";" in value:
        return [a.strip() for a in value.split(";") if a.strip()]
    if ", " in value:
        return [a.strip() for a in value.split(", ") if a.strip()]
    return [value.strip()] if value.strip() else []
```

---

## Error Handling Pattern

Operations layer:
1. Wrap in `try/except Exception`
2. Call `print_error()` with context
3. Return `None` or `[]` or `False` (not re-raise) — the caller handles absence

```python
async def get_material_by_name(name: str, env: Environment, verbose: bool) -> Optional[Material]:
    try:
        async with get_db_session(env, verbose) as session:
            results = await Material.get_where(session, Material.name == name)
            if not results:
                print_warning(f"No material found with name: '{name}'")
                return None
            return results[0]
    except Exception as e:
        print_error(f"Failed to get material by name: {e}")
        return None
```

Connectivity errors are identified separately for user-friendly messaging:

```python
from ..database.exceptions import is_connectivity_error

async def execute_safe(fn, *args, **kwargs):
    try:
        return await fn(*args, **kwargs)
    except Exception as exc:
        if is_connectivity_error(exc):
            print("Temporary database connectivity issue. Please retry shortly.")
        raise
```

---

## SMILES Validation and Canonicalization

```python
from rdkit import Chem

def is_smiles_canonical(smiles: Optional[str]) -> bool:
    """Return True if SMILES is canonical or None (trivially valid)."""
    if not smiles:
        return True
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return False
        return smiles == Chem.MolToSmiles(mol, canonical=True)
    except Exception:
        return False


def canonicalize_smiles(smiles: str) -> Optional[str]:
    """Return the canonical form of a SMILES string, or None if invalid."""
    try:
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            return None
        return Chem.MolToSmiles(mol, canonical=True)
    except Exception:
        return None
```

---

## DMTA Enrichment Pattern

```python
from ..service.DmtaService import DmtaService
import os

async def enrich_material_with_dmta(material: Material, env: Environment) -> None:
    """Attempt DMTA enrichment; skip silently if service is unavailable."""
    api_url = os.getenv("DMTA_API_URL")
    api_key = os.getenv("DMTA_API_KEY")

    if not api_url:
        print_warning("DMTA_API_URL not set; skipping enrichment")
        return

    try:
        service = DmtaService(api_url=api_url, api_key=api_key)
        result = await service.search_by_name(material.name)
        if result and result.smiles and not material.smiles:
            # Only enrich if material has no SMILES yet
            material.smiles = result.smiles
    except Exception as e:
        print_warning(f"DMTA enrichment failed (non-fatal): {e}")
        # Enrichment failure does NOT abort the primary operation
```

---

## Connectivity Error Detection

```python
# In database/exceptions.py
import socket
import aiosqlite

def is_connectivity_error(exc: BaseException) -> bool:
    """Check if an exception represents a database connectivity issue."""
    return isinstance(exc, (
        aiosqlite.OperationalError,  # DB locked, file not found
        OSError,
        socket.gaierror,
        TimeoutError,
    ))
```

Note: For SQLite, the most common connectivity-like errors are:
- `OperationalError: database is locked` (concurrent write attempt)
- `OperationalError: unable to open database file` (path not found)
