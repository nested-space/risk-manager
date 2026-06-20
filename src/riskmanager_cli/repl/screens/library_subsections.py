"""Per-subsection descriptors for the library screens.

The library handles three entity types — materials, NCRM library entries, and
counterions — through identical add/edit/delete/list/alias flows that differ only
in *which* operation functions, schemas, labels, and titles they use. Capturing
those differences in one :class:`LibraryDescriptor` per subsection lets
:mod:`.library` drive all three from a single set of descriptor-keyed methods
instead of parallel ``if/elif`` chains and triplicated handlers.

Adding a fourth library type is then a matter of adding one enum member and one
descriptor here, with no edits to the screen logic.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from typing import Any
from uuid import UUID

from ...config.settings import Environment
from ...operations.counterion_operations import (
    add_counterion_alias,
    counterion_alias_counts,
    create_counterion,
    delete_counterion,
    list_counterion_aliases,
    list_counterions,
    update_counterion,
)
from ...operations.material_operations import (
    add_material_alias,
    create_material,
    delete_material,
    list_material_aliases,
    list_materials,
    material_alias_counts,
    update_material,
)
from ...operations.ncrm_library_operations import (
    add_ncrm_alias,
    create_ncrm_library_entry,
    delete_ncrm_library_entry,
    list_ncrm_aliases,
    list_ncrm_library,
    ncrm_alias_counts,
    update_ncrm_library_entry,
)
from ...schema.create import (
    CounterionAliasCreate,
    CounterionCreate,
    MaterialAliasCreate,
    MaterialCreate,
    NcrmLibraryAliasCreate,
    NcrmLibraryCreate,
)
from ...schema.update import (
    CounterionUpdate,
    MaterialUpdate,
    NcrmLibraryUpdate,
)


class LibrarySubsection(str, Enum):
    """The three library entity types, keyed by their context ``library_sub`` value."""

    MATERIALS = "materials"
    NCRM = "ncrm"
    COUNTERIONS = "counterions"


@dataclass(frozen=True)
class LibraryDescriptor:  # pylint: disable=too-many-instance-attributes  # value object
    """The per-subsection operations, schemas, and labels the library screen needs.

    Attributes:
        list_fn: Return all entities for the subsection.
        alias_counts_fn: Return a ``{entity_id: alias_count}`` mapping.
        alias_list_fn: Return one entity's aliases.
        create_fn: Persist a new entity from a create schema.
        alias_add_fn: Persist one alias from an alias-create schema.
        update_fn: Apply an update schema to an entity by id.
        delete_fn: Delete an entity by id.
        create_schema: The ``*Create`` schema class (kwargs: name, display_name,
            interpret_chemically, smiles).
        update_schema: The ``*Update`` schema class (same kwargs, all optional).
        alias_factory: Build an alias-create schema from ``(entity_id, alias)``.
        add_title: Title for the add form (e.g. ``"Add material"``).
        edit_title: Title for the edit form (e.g. ``"Edit material"``).
        created_label: Subject of the post-create notice (e.g. ``"Material"``).
        create_fail_notice: Notice shown when creation fails.
        update_ok_notice: Notice shown after a successful update.
        update_fail_notice: Notice shown when an update fails.
    """

    list_fn: Callable[[Environment], Awaitable[list[Any]]]
    alias_counts_fn: Callable[[Environment], Awaitable[dict[str, int]]]
    alias_list_fn: Callable[[UUID, Environment], Awaitable[list[str]]]
    create_fn: Callable[[Any, Environment], Awaitable[Any]]
    alias_add_fn: Callable[[Any, Environment], Awaitable[Any]]
    update_fn: Callable[[UUID, Any, Environment], Awaitable[Any]]
    delete_fn: Callable[[UUID, Environment], Awaitable[bool]]
    create_schema: type[Any]
    update_schema: type[Any]
    alias_factory: Callable[[UUID, str], Any]
    add_title: str
    edit_title: str
    created_label: str
    create_fail_notice: str
    update_ok_notice: str
    update_fail_notice: str


LIBRARY_DESCRIPTORS: dict[LibrarySubsection, LibraryDescriptor] = {
    LibrarySubsection.MATERIALS: LibraryDescriptor(
        list_fn=list_materials,
        alias_counts_fn=material_alias_counts,
        alias_list_fn=list_material_aliases,
        create_fn=create_material,
        alias_add_fn=add_material_alias,
        update_fn=update_material,
        delete_fn=delete_material,
        create_schema=MaterialCreate,
        update_schema=MaterialUpdate,
        alias_factory=lambda entity_id, alias: MaterialAliasCreate(
            material_id=entity_id, alias=alias
        ),
        add_title="Add material",
        edit_title="Edit material",
        created_label="Material",
        create_fail_notice="Failed to create material.",
        update_ok_notice="Material updated.",
        update_fail_notice="Failed to update material.",
    ),
    LibrarySubsection.NCRM: LibraryDescriptor(
        list_fn=list_ncrm_library,
        alias_counts_fn=ncrm_alias_counts,
        alias_list_fn=list_ncrm_aliases,
        create_fn=create_ncrm_library_entry,
        alias_add_fn=add_ncrm_alias,
        update_fn=update_ncrm_library_entry,
        delete_fn=delete_ncrm_library_entry,
        create_schema=NcrmLibraryCreate,
        update_schema=NcrmLibraryUpdate,
        alias_factory=lambda entity_id, alias: NcrmLibraryAliasCreate(
            ncrm_library_id=entity_id, alias=alias
        ),
        add_title="Add NCRM",
        edit_title="Edit NCRM",
        created_label="NCRM entry",
        create_fail_notice="Failed to create NCRM entry.",
        update_ok_notice="NCRM updated.",
        update_fail_notice="Failed to update NCRM.",
    ),
    LibrarySubsection.COUNTERIONS: LibraryDescriptor(
        list_fn=list_counterions,
        alias_counts_fn=counterion_alias_counts,
        alias_list_fn=list_counterion_aliases,
        create_fn=create_counterion,
        alias_add_fn=add_counterion_alias,
        update_fn=update_counterion,
        delete_fn=delete_counterion,
        create_schema=CounterionCreate,
        update_schema=CounterionUpdate,
        alias_factory=lambda entity_id, alias: CounterionAliasCreate(
            counterion_id=entity_id, alias=alias
        ),
        add_title="Add counterion",
        edit_title="Edit counterion",
        created_label="Counterion",
        create_fail_notice="Failed to create counterion.",
        update_ok_notice="Counterion updated.",
        update_fail_notice="Failed to update counterion.",
    ),
}


def descriptor_for(sub_mode: str) -> LibraryDescriptor | None:
    """Return the descriptor for *sub_mode*, or ``None`` when it is not a subsection.

    ``sub_mode`` is the context's ``library_sub`` value; the landing page uses
    ``"select"`` (and anything unrecognised), for which there is no descriptor.
    """
    try:
        return LIBRARY_DESCRIPTORS[LibrarySubsection(sub_mode)]
    except ValueError:
        return None
