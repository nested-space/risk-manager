"""Unit tests for the risk add/edit guided-prompt field builders."""

from types import SimpleNamespace

import pytest

from riskmanager_cli.model.enums import RiskType
from riskmanager_cli.repl.risk_forms import risk_edit_fields, risk_fields


def _field(fields: list, label: str):
    """Return the field spec with *label* from *fields*."""
    return next(field for field in fields if field.label == label)


@pytest.mark.unit
def test_risk_fields_risk_type_is_threat_opportunity_select() -> None:
    """The add form offers risk_type as a Threat/Opportunity select."""
    risk_type = _field(risk_fields(), "risk_type")
    assert risk_type.field_type == "select"
    assert [value for _label, value in risk_type.options] == [
        RiskType.THREAT.value,
        RiskType.OPPORTUNITY.value,
    ]


@pytest.mark.unit
def test_risk_edit_fields_preselects_known_value() -> None:
    """Editing a Threat/Opportunity risk pre-selects the stored value."""
    risk = SimpleNamespace(
        risk_type="Opportunity",
        name="Yield uplift",
        description=None,
        current_level=3,
        proposed_mitigation="Optimise charge",
        mitigated_level=1,
    )
    risk_type = _field(risk_edit_fields(risk), "risk_type")
    assert risk_type.field_type == "select"
    assert risk_type.default == "Opportunity"


@pytest.mark.unit
def test_risk_edit_fields_tolerates_legacy_value() -> None:
    """A legacy free-text value is carried as the default without erroring."""
    risk = SimpleNamespace(
        risk_type="Safety",
        name="Exotherm",
        description="Runaway",
        current_level=5,
        proposed_mitigation="Add cooling",
        mitigated_level=2,
    )
    risk_type = _field(risk_edit_fields(risk), "risk_type")
    # The select still builds; the unmatched default simply won't pre-select.
    assert risk_type.field_type == "select"
    assert risk_type.default == "Safety"
