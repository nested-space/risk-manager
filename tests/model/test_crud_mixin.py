"""Integration tests for the ``CRUDMixin`` query/update helpers.

These pin the behaviour of ``get_all``, ``get_where``, and ``update_fields``
(``model/tables.py``) — the three methods every operation in the codebase is
built on — directly against a real in-memory SQLite session.
"""

import pytest

from riskmanager_cli.model.tables import Counterion


@pytest.mark.integration
async def test_get_all_returns_empty_when_no_rows(db_session) -> None:
    """get_all returns an empty list when the table holds no rows."""
    assert await Counterion.get_all(db_session) == []


@pytest.mark.integration
async def test_get_all_returns_every_row(db_session) -> None:
    """get_all returns every persisted row of the model type."""
    for name in ("Chloride", "Sulfate", "Mesylate"):
        db_session.add(Counterion(name=name, display_name=name))
    await db_session.commit()

    names = sorted(c.name for c in await Counterion.get_all(db_session))
    assert names == ["Chloride", "Mesylate", "Sulfate"]


@pytest.mark.integration
async def test_get_where_filters_by_condition(db_session) -> None:
    """get_where returns only rows matching the SQLAlchemy condition."""
    db_session.add(Counterion(name="Chloride", display_name="Cl"))
    db_session.add(Counterion(name="Sulfate", display_name="SO4"))
    await db_session.commit()

    matches = await Counterion.get_where(db_session, Counterion.name == "Chloride")
    assert len(matches) == 1
    assert matches[0].display_name == "Cl"


@pytest.mark.integration
async def test_get_where_returns_empty_when_no_match(db_session) -> None:
    """get_where returns an empty list when nothing matches."""
    db_session.add(Counterion(name="Chloride", display_name="Cl"))
    await db_session.commit()

    assert await Counterion.get_where(db_session, Counterion.name == "Bromide") == []


@pytest.mark.integration
async def test_update_fields_persists_changes(db_session) -> None:
    """update_fields writes the given fields and commits them."""
    entity = Counterion(name="Chloride", display_name="Cl", interpret_chemically=False)
    db_session.add(entity)
    await db_session.commit()

    await entity.update_fields(db_session, display_name="Chloride ion", interpret_chemically=True)

    reloaded = await Counterion.get_where(db_session, Counterion.name == "Chloride")
    assert reloaded[0].display_name == "Chloride ion"
    assert reloaded[0].interpret_chemically is True


@pytest.mark.integration
async def test_update_fields_ignores_unknown_attributes(db_session) -> None:
    """update_fields silently skips keys that are not attributes of the model."""
    entity = Counterion(name="Chloride", display_name="Cl")
    db_session.add(entity)
    await db_session.commit()

    await entity.update_fields(db_session, not_a_real_field="x", display_name="Cl-")

    assert not hasattr(entity, "not_a_real_field")
    assert entity.display_name == "Cl-"
