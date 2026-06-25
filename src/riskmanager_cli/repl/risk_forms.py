"""Guided-prompt field builders for risk add/edit forms.

Stage, process, and component risks share the same editable columns, so these two
builders serve every scope. They are stateless: the level fields are number-selects
on the 1-5 severity scale, pre-selected to the risk's stored level on edit.
"""

from __future__ import annotations

from typing import Any

from ..model.enums import RiskType
from ..model.severity import LEVEL_OPTIONS
from ..repl_engine.forms import FieldSpec
from .form_fields import default_text, enum_options


def risk_fields() -> list[FieldSpec]:
    """Return the blank field set for adding a risk."""
    return [
        FieldSpec("risk_type", field_type="select", options=enum_options(RiskType)),
        FieldSpec("name"),
        FieldSpec("description", required=False),
        FieldSpec("current_level", field_type="select", options=LEVEL_OPTIONS),
        FieldSpec("proposed_mitigation"),
        FieldSpec("mitigated_level", field_type="select", options=LEVEL_OPTIONS),
    ]


def risk_edit_fields(risk: Any) -> list[FieldSpec]:
    """Return the risk fields pre-filled from *risk* for an edit form.

    The level fields are number-selects on the 1-5 severity scale, pre-selected
    to the risk's stored level.
    """
    return [
        FieldSpec(
            "risk_type",
            field_type="select",
            options=enum_options(RiskType),
            default=risk.risk_type,
        ),
        FieldSpec("name", default=risk.name),
        FieldSpec("description", required=False, default=risk.description),
        FieldSpec(
            "current_level",
            field_type="select",
            options=LEVEL_OPTIONS,
            default=default_text(risk.current_level),
        ),
        FieldSpec("proposed_mitigation", default=risk.proposed_mitigation),
        FieldSpec(
            "mitigated_level",
            field_type="select",
            options=LEVEL_OPTIONS,
            default=default_text(risk.mitigated_level),
        ),
    ]
