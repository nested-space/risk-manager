"""The library screens: the tabbed landing page, the subsection lists, and the
per-entry detail page.

Three screens share one cohesive module because they operate on the same data and
flows:

* :class:`LibraryScreen` serves the ``library`` track. It renders either the
  tabbed landing page (``library_home``) or a navigable subsection table
  (``library_list``) depending on the active sub-mode, and owns the add/edit/
  delete/show flows for materials, NCRM entries, and counterions.
* :class:`LibraryDetailScreen` serves the ``library_detail`` track: the read-only
  detail page for a single entry, with inline edit (``^E``) and structure
  display (``^K``).

Shared row lookups, alias fetches, the edit form, and structure display live on
:class:`_LibraryMixin` so both screens reuse them without duplication. The three
subsections differ only in their operations/schemas/labels, which are captured in
the per-subsection :class:`~.library_subsections.LibraryDescriptor` registry, so
the add/edit/delete/list/alias flows are written once and keyed by sub-mode.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from ...operations.dmta_operations import ResolveResult, augment_name
from ...operations.material_operations import (
    display_name_is_unambiguous,
    existing_display_names,
)
from ...repl_engine import ListItem, ScreenSpec
from ...repl_engine.forms import FieldSpec, InfoSection, field_key
from ...service.structure_viewer import StructureResult, show_structure
from ...utils.name_simplifier import simplify_name
from ..form_fields import BOOL_OPTIONS, CONFIRM_OPTIONS, as_bool, default_text
from ..hotkeys import CTRL_A, CTRL_E, CTRL_F, CTRL_K, CTRL_L, CTRL_X
from ..renderers.library_home_renderer import (
    LIBRARY_HOME_TABS,
    OVERVIEW_CARDS,
    render_library_home,
)
from ..renderers.library_renderer import (
    library_targets,
    render_library_detail,
    render_library_screen,
)
from .base import AppScreen
from .library_subsections import LIBRARY_DESCRIPTORS, descriptor_for
from .specs import SCREEN_SPECS

if TYPE_CHECKING:
    from ..commands import CommandDispatcher


def _created_notice(entity: str, aliases: list[str]) -> str:
    """Build the success notice for a created entity, noting any added aliases."""
    if not aliases:
        return f"{entity} created."
    plural = "alias" if len(aliases) == 1 else "aliases"
    return f"{entity} created with {len(aliases)} {plural}."


def _library_item_matches(item: dict[str, Any], lowered: str) -> bool:
    """True if *lowered* matches the item's ``name`` or ``display_name``."""
    for key in ("name", "display_name"):
        value = item.get(key)
        if value and str(value).lower() == lowered:
            return True
    return False


class _LibraryMixin(AppScreen):
    """Shared library data lookups, edit form, and structure display.

    Both :class:`LibraryScreen` and :class:`LibraryDetailScreen` inherit these so
    row resolution, alias fetches, the per-subsection edit form, and SMILES
    visualisation are defined once.
    """

    @property
    def _current_sub(self) -> str:
        """Return the active library subsection (defaulting to ``select``)."""
        return self.app.ctx.current.library_sub or "select"

    async def _library_items(self, sub_mode: str) -> list[dict[str, Any]]:
        """Return library rows as dicts, alphabetised by name with alias counts.

        Each dict carries ``id``, ``name``, ``display_name``,
        ``interpret_chemically``, ``smiles`` and ``alias_count``. Rows are sorted
        case-insensitively by name so the rendered table reads alphabetically.
        """
        descriptor = descriptor_for(sub_mode)
        if descriptor is None:
            return []
        entities = await descriptor.list_fn(self.app.env)
        counts = await descriptor.alias_counts_fn(self.app.env)
        items = [
            {
                "id": entity.id,
                "name": entity.name,
                "display_name": entity.display_name,
                "interpret_chemically": entity.interpret_chemically,
                "smiles": entity.smiles,
                "alias_count": counts.get(str(entity.id), 0),
            }
            for entity in entities
        ]
        items.sort(key=lambda item: str(item["name"]).casefold())
        return items

    async def _find_library_item_by_id(self, sub_mode: str, item_id: str) -> dict[str, Any] | None:
        """Return the library row whose id matches *item_id*, or ``None``."""
        for item in await self._library_items(sub_mode):
            if str(item.get("id")) == item_id:
                return item
        return None

    async def _library_item_aliases(self, sub_mode: str, item_id: str) -> list[str]:
        """Return the aliases of one library entry for its subsection."""
        descriptor = descriptor_for(sub_mode)
        if descriptor is None:
            return []
        return await descriptor.alias_list_fn(UUID(item_id), self.app.env)

    async def _render_library_detail(self, sub_mode: str, item_id: str) -> list[str]:
        """Render the detail (show) page for one library entry, with its aliases.

        The detail page is not a list screen, so the navigator is cleared (arrow
        keys scroll the page rather than walking a caret).
        """
        self.app.navigator = None
        item = await self._find_library_item_by_id(sub_mode, item_id)
        if item is None:
            return await self.app.refresh_with_notice("Item not found.", "error")
        aliases = await self._library_item_aliases(sub_mode, item_id)
        return render_library_detail(item, aliases, width=self.app.screen.width)

    async def _show_structure_for_item(self, item: dict[str, Any]) -> list[str]:
        """Render *item*'s SMILES to an image and open it, returning a notice.

        Maps each :class:`StructureResult` to a status notice so every failure
        path (missing SMILES, render failure, no viewer, launch failure) is
        reported on the input row.
        """
        name = str(item.get("name") or item.get("display_name") or "item")
        smiles = item.get("smiles")
        if not smiles:
            return await self.app.refresh_with_notice(
                f"No SMILES available for '{name}'.", "warning"
            )
        match show_structure(str(smiles)):
            case StructureResult.OK:
                return await self.app.refresh_with_notice(f"Opened structure for '{name}'.")
            case StructureResult.RENDER_FAILED:
                return await self.app.refresh_with_notice(
                    "Could not render structure (invalid SMILES).", "error"
                )
            case StructureResult.NO_VIEWER:
                return await self.app.refresh_with_notice(
                    "No image viewer found (install feh).", "error"
                )
            case _:
                return await self.app.refresh_with_notice("Failed to open image viewer.", "error")

    def _library_edit_form(self, sub_mode: str, item: dict[str, Any]) -> list[str]:
        """Start the edit form for an already-resolved library *item*."""
        descriptor = descriptor_for(sub_mode)
        if descriptor is None:
            return ["Choose a library subsection first."]
        return self.app.modal.start_prompt(
            [
                FieldSpec("name", default=str(item["name"])),
                FieldSpec(
                    "display_name",
                    default=default_text(item.get("display_name")),
                    max_length=30,
                ),
                FieldSpec(
                    "interpret_chemically",
                    field_type="select",
                    options=BOOL_OPTIONS,
                    default="true" if bool(item.get("interpret_chemically")) else "false",
                ),
                FieldSpec("smiles", required=False, default=default_text(item.get("smiles"))),
            ],
            lambda **payload: self._update_library_entry(sub_mode, str(item["id"]), payload),
            title=descriptor.edit_title,
        )

    async def _update_library_entry(
        self, sub_mode: str, item_id: str, payload: dict[str, str | None]
    ) -> list[str]:
        """Apply an edit form's *payload* to the entry with *item_id*."""
        descriptor = descriptor_for(sub_mode)
        if descriptor is None:
            return await self.app.refresh_with_notice("Item not found.", "error")
        updated = await descriptor.update_fn(
            UUID(item_id),
            descriptor.update_schema(
                name=payload.get("name"),
                display_name=payload.get("display_name") or None,
                interpret_chemically=as_bool(payload.get("interpret_chemically")),
                smiles=payload.get("smiles") or None,
            ),
            self.app.env,
        )
        if updated is None:
            return await self.app.refresh_with_notice(descriptor.update_fail_notice, "error")
        return await self.app.refresh_with_notice(descriptor.update_ok_notice)


class LibraryScreen(_LibraryMixin):
    """The library track: the tabbed landing page and the subsection tables.

    The single ``library`` navigation track maps to two screen keys: ``select``
    sub-mode is the tabbed landing page (``library_home``); any other sub-mode is
    a navigable subsection table (``library_list``). Reporting the key as a
    property lets the engine derive the right capability spec, tab state, and
    legend for whichever view is showing.
    """

    def __init__(self, app: CommandDispatcher) -> None:
        """Bind the screen and reset the transient display-name suggestion inputs."""
        super().__init__(app)
        # Transient inputs for the next display-name suggestion, gathered in the
        # async augment step and consumed by the (sync) finish form. Reset on use.
        self._suggestion_inputs: tuple[list[str] | None, bool] = (None, False)

    @property
    def key(self) -> str:  # type: ignore[override]  # dynamic: home vs list view
        """Return ``library_home`` on the landing page, else ``library_list``."""
        return "library_home" if self._current_sub == "select" else "library_list"

    @property
    def spec(self) -> ScreenSpec:  # type: ignore[override]  # dynamic per active sub-mode
        """Return the capability spec for the active library view."""
        return SCREEN_SPECS[self.key]

    def is_navigable(self) -> bool:
        """Return whether caret navigation applies.

        The Library home's navigation belongs to its ``Libraries`` tab only; the
        ``Information`` tab has no cards, so it reports as non-navigable.
        """
        if self.key == "library_home" and self.app.active_tab() != 0:
            return False
        return self.spec.navigable

    def tab_count(self) -> int:
        """Return the screen's tab count (only the library home is tabbed)."""
        return len(LIBRARY_HOME_TABS) if self.key == "library_home" else 0

    async def render(self) -> list[str]:
        """Render the landing page or the active subsection table."""
        sub_mode = self._current_sub
        if sub_mode == "select":
            return await self._render_library_home()
        return await self._render_library(sub_mode)

    async def run_command(  # pylint: disable=too-many-return-statements  # one return per command verb
        self, verb: str, args: list[str]
    ) -> list[str] | str | None:
        """Dispatch a library command (list/search/filter/show/add/edit/delete)."""
        sub_mode = self._current_sub
        if verb == "/list":
            return await self._render_library(sub_mode)
        if verb == "/search" and args:
            return await self._render_library(sub_mode, query=" ".join(args))
        if verb == "/filter" and args:
            return await self._render_library(sub_mode, filter_mode=args[0].lower())
        if verb == "/show" and args:
            return await self._show_library_item(sub_mode, " ".join(args))
        if verb == "/add":
            return self._start_library_add_prompt(sub_mode)
        if verb == "/edit" and args:
            return await self._start_library_edit_prompt(sub_mode, " ".join(args))
        if verb == "/delete" and args:
            return await self._delete_library_item(sub_mode, " ".join(args))
        return [f"Unknown command: {verb}. Type /help for commands."]

    async def run_hotkey(  # pylint: disable=too-many-return-statements  # one return per hotkey
        self, key_text: str
    ) -> list[str] | str | None:
        """Service the subsection hotkeys; the landing menu has none."""
        sub_mode = self._current_sub
        if sub_mode == "select":
            # The library landing page is a menu, not a list: add/filter/edit/delete
            # have nothing to act on, so leave their keys inert (only ↑↓/Enter apply).
            return None
        if key_text == CTRL_A:
            return self._start_library_add_prompt(sub_mode)
        if key_text == CTRL_F:
            return self._start_library_filter_chooser(sub_mode)
        if key_text == CTRL_L:
            return await self._render_library(sub_mode)
        if key_text == CTRL_K:
            return await self._visualize_library_structure(sub_mode)
        if key_text in {CTRL_E, CTRL_X}:
            return await self._library_selection_action(sub_mode, key_text)
        return None

    async def activate(self, item: ListItem) -> list[str]:
        """Open a subsection from the landing page, or a row's detail page."""
        if self._current_sub == "select":
            return await self.app.enter_library(item.item_id)
        return await self._activate_library_row(item.item_id)

    async def search(self, query: str) -> list[str]:
        """Re-render the active subsection filtered by *query*."""
        return await self._render_library(self._current_sub, query=query.strip() or None)

    async def _library_counts(self) -> dict[str, int]:
        """Return live record counts for each library subsection.

        Keyed by subsection (``ncrm``/``materials``/``counterions``) to match
        :data:`~..renderers.library_home_renderer.OVERVIEW_CARDS`.
        """
        return {
            subsection.value: len(await descriptor.list_fn(self.app.env))
            for subsection, descriptor in LIBRARY_DESCRIPTORS.items()
        }

    async def _render_library_home(self) -> list[str]:
        """Render the Library landing page: a tabbed overview/information pane.

        On the ``Libraries`` tab the three overview cards are backed by a fixed
        navigator (matching
        :data:`~..renderers.library_home_renderer.OVERVIEW_CARDS`) so arrow keys
        and Enter pick a subsection exactly like any other list screen. The
        ``Information`` tab has no cards, so its navigator is cleared.
        """
        counts = await self._library_counts()
        active = self.app.active_tab()
        if active == 0:
            items = [ListItem(label=title, item_id=key) for key, title in OVERVIEW_CARDS]
            navigator = self.app.rebuild_navigator([], items)
            selected_index = navigator.selected_index
        else:
            self.app.navigator = None
            selected_index = -1
        return render_library_home(
            counts,
            selected_index,
            active_tab=active,
            width=self.app.screen.width,
            bold=self.app.screen.bold,
        )

    async def _render_library(
        self,
        sub_mode: str,
        query: str | None = None,
        filter_mode: str | None = None,
    ) -> list[str]:
        """Render a subsection table, optionally filtered by *query*/*filter_mode*."""
        if sub_mode == "select":
            return await self._render_library_home()
        items = await self._library_items(sub_mode)
        if query:
            lowered = query.lower()
            items = [
                item
                for item in items
                if lowered in str(item.get("name") or item.get("display_name") or "").lower()
            ]
        if filter_mode == "has-smiles":
            items = [item for item in items if item.get("smiles")]
        if filter_mode == "no-smiles":
            items = [item for item in items if not item.get("smiles")]
        navigator = self.app.rebuild_navigator([], library_targets(items))
        selected_id = navigator.selected.item_id if navigator.selected is not None else None
        return await render_library_screen(
            sub_mode, items, width=self.app.screen.width, selected_id=selected_id
        )

    async def _show_library_item(self, sub_mode: str, name: str) -> list[str]:
        """Open the detail page for the first row matching *name* exactly."""
        items = await self._library_items(sub_mode)
        lowered = name.lower()
        for item in items:
            if _library_item_matches(item, lowered):
                aliases = await self._library_item_aliases(sub_mode, str(item["id"]))
                return render_library_detail(item, aliases, width=self.app.screen.width)
        return [f"No {sub_mode} item matched '{name}'."]

    async def _activate_library_row(self, item_id: str) -> list[str]:
        """Open the detail (show) screen for the caret-selected library row.

        The library screen's navigator carries the entry id; Enter opens its
        detail page on a new ``library_detail`` frame so ``^C`` returns to the
        list. (``^E`` still edits the highlighted row directly.)
        """
        sub_mode = self._current_sub
        item = await self._find_library_item_by_id(sub_mode, item_id)
        if item is None:
            return await self.app.refresh_with_notice("Item not found.", "error")
        self.app.push_library_detail(sub_mode, item_id)
        return await self._render_library_detail(sub_mode, item_id)

    async def _library_selection_action(self, sub_mode: str, key: str) -> list[str]:
        """Run edit/delete against the caret-selected library row.

        Edit (``^E``) and delete (``^X``) act on the row the navigator currently
        highlights, so no chooser is needed. (Enter opens the detail/show screen
        via :meth:`_activate_library_row`.)
        """
        selected = self.list_navigator.selected if self.list_navigator else None
        if selected is None:
            return await self.app.refresh_with_notice("No item selected.", "warning")
        item = await self._find_library_item_by_id(sub_mode, selected.item_id)
        if item is None:
            return await self.app.refresh_with_notice("Item not found.", "error")
        if key == CTRL_E:
            return self._library_edit_form(sub_mode, item)
        label = str(item.get("name") or item.get("display_name") or "item")
        return self.app.start_confirm(
            f"Delete '{label}'",
            lambda: self._delete_library_entry(sub_mode, item),
        )

    async def _visualize_library_structure(self, sub_mode: str) -> list[str]:
        """Display the molecular structure of the caret-selected library row."""
        selected = self.list_navigator.selected if self.list_navigator else None
        if selected is None:
            return await self.app.refresh_with_notice("No item selected.", "warning")
        item = await self._find_library_item_by_id(sub_mode, selected.item_id)
        if item is None:
            return await self.app.refresh_with_notice("Item not found.", "error")
        return await self._show_structure_for_item(item)

    def _start_library_filter_chooser(self, sub_mode: str) -> list[str]:
        """Open the SMILES-presence filter chooser for the subsection."""
        return self.app.modal.start_prompt(
            [
                FieldSpec(
                    "filter",
                    field_type="select",
                    options=[
                        ("all", ""),
                        ("has SMILES", "has-smiles"),
                        ("no SMILES", "no-smiles"),
                    ],
                )
            ],
            lambda **payload: self._render_library(sub_mode, filter_mode=payload["filter"] or None),
        )

    def _start_library_add_prompt(self, sub_mode: str) -> list[str]:
        """Begin the add flow for *sub_mode* (collect the lead name first)."""
        # Each add flow is a three-step chain: collect the lead name, offer to
        # auto-resolve SMILES/aliases, then collect the remaining fields. On a
        # successful resolve the retrieved values are shown read-only and only the
        # remaining fields stay editable (see _offer_augment /
        # _finish_library_add_augmented); otherwise SMILES is entered manually.
        descriptor = descriptor_for(sub_mode)
        if descriptor is None:
            return ["Choose a library subsection first."]
        return self.app.modal.start_prompt(
            [FieldSpec("name")],
            lambda **payload: self._offer_augment(sub_mode, payload.get("name") or ""),
            title=descriptor.add_title,
        )

    def _offer_augment(self, sub_mode: str, name: str) -> list[str]:
        """Ask whether to auto-resolve SMILES/aliases for *name* before finishing.

        Args:
            sub_mode: Library subsection (``materials``/``ncrm``/``counterions``).
            name: The lead chemical name to resolve.

        Returns:
            Prompt lines for the Yes/No augment question, or the finish form when
            *name* is empty.
        """
        if not name:
            return self._finish_library_add(sub_mode, name, None, [])
        label = f"Augment '{name}' with SMILES & aliases?"
        return self.app.modal.start_prompt(
            [FieldSpec(label, field_type="select", options=CONFIRM_OPTIONS, default="no")],
            lambda **payload: self._resolve_augment(sub_mode, name, payload[field_key(label)]),
        )

    async def _resolve_augment(self, sub_mode: str, name: str, answer: str | None) -> list[str]:
        """Run augmentation when confirmed, then open the finish form.

        On a successful resolve, the retrieved SMILES and aliases are shown in a
        read-only "Retrieved values" section on the finish form (and carried
        through to be persisted on completion); only the remaining fields stay
        editable. On a miss (or "No"), the form opens for manual SMILES entry.
        """
        if answer != "yes":
            self._suggestion_inputs = await self._collision_inputs(sub_mode, name, None)
            return self._finish_library_add(sub_mode, name, None, [])
        result = await augment_name(name)
        if result.resolved:
            self._suggestion_inputs = await self._collision_inputs(sub_mode, name, result.smiles)
            return self._finish_library_add_augmented(sub_mode, name, result)
        self.app.set_notice(f"Could not resolve '{name}'. Enter SMILES manually.", "warning")
        self._suggestion_inputs = await self._collision_inputs(sub_mode, name, None)
        return self._finish_library_add(sub_mode, name, None, [])

    async def _collision_inputs(
        self, sub_mode: str, name: str, smiles: str | None
    ) -> tuple[list[str] | None, bool]:
        """Gather the collision set and PubChem-ambiguity flag for a suggestion.

        Only materials currently expose a collision/ambiguity source; the other
        subsections receive rules-only suggestions.

        Args:
            sub_mode: Library subsection.
            name: The lead chemical name collected earlier.
            smiles: The resolved SMILES to validate the suggestion against, if any.

        Returns:
            A ``(existing_names, ambiguous)`` pair. ``existing_names`` is ``None``
            for subsections without a collision source.
        """
        if sub_mode != "materials":
            return None, False
        existing = await existing_display_names(env=self.app.env)
        candidate = simplify_name(name, existing_names=existing).display_name
        ambiguous = (await display_name_is_unambiguous(candidate, smiles)) is False
        return existing, ambiguous

    def _finish_library_add(
        self,
        sub_mode: str,
        name: str,
        smiles: str | None,
        aliases: list[str],
    ) -> list[str]:
        """Open the final add form for the manual (non-augmented) path.

        Used when the user declined augmentation or it missed: SMILES is an
        editable field. See :meth:`_finish_library_add_augmented` for the form
        shown after a successful resolve.

        Args:
            sub_mode: Library subsection.
            name: The lead chemical name collected earlier.
            smiles: Pre-filled SMILES, or ``None`` for manual entry.
            aliases: Aliases to persist once the entity is created.

        Returns:
            Prompt-render lines for the finish form.
        """
        descriptor = descriptor_for(sub_mode)
        if descriptor is None:
            return ["Choose a library subsection first."]
        display_field, note = self._suggested_display_name_field(name)
        info = InfoSection(title="Suggested display name", rows=[("note", note)]) if note else None
        return self.app.modal.start_prompt(
            [
                display_field,
                FieldSpec(
                    "interpret_chemically",
                    field_type="select",
                    options=BOOL_OPTIONS,
                    default="false",
                ),
                FieldSpec("smiles", required=False, default=smiles),
            ],
            lambda **payload: self._create_library_entry_from_prompt(
                sub_mode, name, payload, aliases
            ),
            title=descriptor.add_title,
            info_section=info,
        )

    def _suggested_display_name_field(self, name: str) -> tuple[FieldSpec, str | None]:
        """Build a ``display_name`` field pre-filled with a simplified suggestion.

        The suggestion is a deterministic shortening of *name* (see
        :func:`~..utils.name_simplifier.simplify_name`); the user can accept it
        with Enter or type over it. Typing is capped at the hard length limit.
        Collision inputs gathered by the async augment step (stored in
        ``self._suggestion_inputs``) are consumed and reset here.

        Args:
            name: The lead chemical name collected earlier.

        Returns:
            A ``(field, note)`` pair. ``note`` is a short review message when the
            suggestion was truncated, disambiguated, or ambiguous, else ``None``.
        """
        existing_names, ambiguous = self._suggestion_inputs
        self._suggestion_inputs = (None, False)
        suggestion = simplify_name(name, existing_names=existing_names)
        spec = FieldSpec(
            "display_name",
            required=False,
            default=suggestion.display_name,
            max_length=30,
        )
        note = suggestion.notes[0] if suggestion.notes else None
        if ambiguous and note is None:
            note = "Suggestion matches another compound on PubChem — review recommended."
        return spec, note

    def _finish_library_add_augmented(
        self,
        sub_mode: str,
        name: str,
        result: ResolveResult,
    ) -> list[str]:
        """Open the finish form with augmentation *result* shown read-only.

        Builds the "Retrieved values" section from the resolved name/SMILES/aliases
        and leaves ``display_name`` and ``interpret_chemically`` editable for all
        three library subsections. The resolved SMILES is carried through to be
        persisted on completion.

        Args:
            sub_mode: Library subsection.
            name: The lead chemical name collected earlier.
            result: The successful resolution carrying SMILES, aliases and source.

        Returns:
            Prompt-render lines for the finish form.
        """
        descriptor = descriptor_for(sub_mode)
        if descriptor is None:
            return ["Choose a library subsection first."]
        display_field, note = self._suggested_display_name_field(name)
        rows: list[tuple[str, str]] = [("name", name)]
        if result.smiles:
            rows.append(("smiles", result.smiles))
        if result.aliases:
            rows.append(("aliases", ", ".join(result.aliases)))
        if note:
            rows.append(("display-name note", note))
        info = InfoSection(title=f"Retrieved values (source: {result.source})", rows=rows)

        return self.app.modal.start_prompt(
            [
                display_field,
                FieldSpec(
                    "interpret_chemically",
                    field_type="select",
                    options=BOOL_OPTIONS,
                    default="false",
                ),
            ],
            lambda **payload: self._create_library_entry_from_prompt(
                sub_mode, name, {**payload, "smiles": result.smiles}, result.aliases
            ),
            title=descriptor.add_title,
            info_section=info,
        )

    async def _start_library_edit_prompt(self, sub_mode: str, name: str) -> list[str]:
        """Resolve *name* in the subsection and open its edit form."""
        item = await self._find_library_item(sub_mode, name)
        if item is None:
            return [f"No {sub_mode} item matched '{name}'."]
        return self._library_edit_form(sub_mode, item)

    async def _find_library_item(self, sub_mode: str, name: str) -> dict[str, Any] | None:
        """Return the first row whose name/display_name matches *name* exactly."""
        lowered = name.lower()
        for item in await self._library_items(sub_mode):
            if _library_item_matches(item, lowered):
                return item
        return None

    async def _delete_library_item(self, sub_mode: str, name: str) -> list[str]:
        """Resolve *name* and delete the matching subsection entry."""
        item = await self._find_library_item(sub_mode, name)
        if item is None:
            return [f"No {sub_mode} item matched '{name}'."]
        return await self._delete_library_entry(sub_mode, item)

    async def _delete_library_entry(self, sub_mode: str, item: dict[str, Any]) -> list[str]:
        """Delete an already-resolved library *item* and refresh the screen."""
        descriptor = descriptor_for(sub_mode)
        if descriptor is None:
            return await self.app.refresh_with_notice("Delete failed.", "error")
        success = await descriptor.delete_fn(UUID(str(item["id"])), self.app.env)
        if not success:
            return await self.app.refresh_with_notice("Delete failed.", "error")
        return await self.app.refresh_with_notice("Deleted.")

    async def _create_library_entry_from_prompt(
        self, sub_mode: str, name: str, payload: dict[str, str | None], aliases: list[str]
    ) -> list[str]:
        """Create a library entry from the finish form, then persist any *aliases*."""
        descriptor = descriptor_for(sub_mode)
        if descriptor is None:
            return ["Choose a library subsection first."]
        created = await descriptor.create_fn(
            descriptor.create_schema(
                name=name or "",
                display_name=payload.get("display_name") or None,
                interpret_chemically=as_bool(payload.get("interpret_chemically")),
                smiles=payload.get("smiles") or None,
            ),
            self.app.env,
        )
        if created is None:
            return await self.app.refresh_with_notice(descriptor.create_fail_notice, "error")
        for alias in aliases:
            await descriptor.alias_add_fn(
                descriptor.alias_factory(UUID(str(created.id)), alias), self.app.env
            )
        return await self.app.refresh_with_notice(
            _created_notice(descriptor.created_label, aliases)
        )


class LibraryDetailScreen(_LibraryMixin):
    """The read-only detail page for a single library entry.

    Shows the entry's fields and aliases. ``^E`` opens its edit form and ``^K``
    displays its molecular structure; ``^C`` (back to the list) is handled
    generically by the REPL loop.
    """

    key = "library_detail"
    spec = SCREEN_SPECS["library_detail"]

    async def render(self) -> list[str]:
        """Render the detail page for the entry on the current frame."""
        return await self._render_library_detail(
            self._current_sub, self.app.ctx.current.library_detail_id or ""
        )

    async def run_hotkey(self, key_text: str) -> list[str] | str | None:
        """Open the edit form (``^E``) or the structure (``^K``) for the entry."""
        if key_text not in {CTRL_E, CTRL_K}:
            return None
        sub_mode = self._current_sub
        item_id = self.app.ctx.current.library_detail_id or ""
        item = await self._find_library_item_by_id(sub_mode, item_id)
        if item is None:
            return await self.app.refresh_with_notice("Item not found.", "error")
        if key_text == CTRL_K:
            return await self._show_structure_for_item(item)
        return self._library_edit_form(sub_mode, item)
