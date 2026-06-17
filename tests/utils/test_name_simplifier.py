"""Unit tests for riskmanager_cli.utils.name_simplifier."""

import pytest

from riskmanager_cli.utils.name_simplifier import (
    _pass1_remove_noise,
    _pass2_substituents,
    _pass3_remove_locants,
    _pass4_compress_fragments,
    simplify_name,
    visual_length,
)


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("CF₃-", 4),
        ("NO₂-aniline", 11),
        ("plain", 5),
        ("", 0),
    ],
)
def test_visual_length_counts_subscripts_as_one(text: str, expected: int) -> None:
    """Each Unicode subscript digit counts as a single character."""
    assert visual_length(text) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("mesylate salt", "mesylate"),  # standalone "salt" dropped
        ("nitro-SNAr product", "nitro-SNAr"),
        ("Osimertinib free base", "Osimertinib base"),
        ("Aspirin hydrochloride", "Aspirin·HCl"),
        ("Drug dihydrochloride", "Drug·2HCl"),  # longest salt wins
        ("Drug monohydrate", "Drug"),
    ],
)
def test_pass1_remove_noise(text: str, expected: str) -> None:
    """Pass 1 strips noise words and normalises salt/hydrate suffixes."""
    assert _pass1_remove_noise(text) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("chloroaniline", "Cl-aniline"),
        ("nitroaniline", "NO₂-aniline"),
        ("methoxyaniline", "MeO-aniline"),
        ("aminophenol", "NH₂-phenol"),
        # Ordering hazards: longer tokens must win over their substrings.
        ("trifluoromethylbenzene", "CF₃-benzene"),
        ("dimethylaminopyridine", "NMe₂-pyridine"),
    ],
)
def test_pass2_substituents(text: str, expected: str) -> None:
    """Pass 2 replaces spelled-out substituents with symbols, longest first."""
    assert _pass2_substituents(text) == expected


@pytest.mark.unit
def test_pass3_remove_locants_reports_dropped_tokens() -> None:
    """Pass 3 removes numeric locants and reports them for collision re-add."""
    cleaned, dropped = _pass3_remove_locants("4-Fluoro-2-methoxy-5-nitroaniline")
    assert cleaned == "Fluoro-methoxy-nitroaniline"
    assert dropped == ["4-", "2-", "5-"]


@pytest.mark.unit
def test_pass3_removes_grouped_n_locants() -> None:
    """Comma-grouped, primed N-locant prefixes are stripped wholesale."""
    cleaned, _ = _pass3_remove_locants("N,N,N′-Trimethylethylenediamine")
    assert cleaned == "Trimethylethylenediamine"


@pytest.mark.unit
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("ethylenediamine", "EDA"),
        ("oxirane-2-carboxylate", "glycidic ester"),
        ("propanecarboxylate", "propane-COOH"),
    ],
)
def test_pass4_compress_fragments(text: str, expected: str) -> None:
    """Pass 4 compresses recognised fragments to abbreviations."""
    assert _pass4_compress_fragments(text) == expected


@pytest.mark.unit
@pytest.mark.parametrize(
    ("name", "display_name", "char_count", "passes", "flagged"),
    [
        (
            "4-Fluoro-2-methoxy-5-nitroaniline",
            "F-MeO-NO₂-aniline",
            17,
            ("pass2-substituents", "pass3-locants"),
            False,
        ),
        (
            "AZD9291 nitro-SNAr product",
            "AZD9291 nitro-SNAr",
            18,
            ("pass1-noise",),
            False,
        ),
        (
            "Osimertinib mesylate monohydrate",
            "Osimertinib mesylate",
            20,
            ("pass1-noise",),
            False,
        ),
        (
            "trifluoromethylbenzenesulfonamide",
            "CF₃-benzenesulfonamide",
            22,
            ("pass2-substituents",),
            False,
        ),
        # Already within the soft cap — returned untouched, no passes.
        ("chloropyrimidine", "chloropyrimidine", 16, (), False),
    ],
)
def test_simplify_name_spec_cases(
    name: str,
    display_name: str,
    char_count: int,
    passes: tuple[str, ...],
    flagged: bool,
) -> None:
    """Documented worked examples produce the expected audited result."""
    result = simplify_name(name)
    assert result.display_name == display_name
    assert result.char_count == char_count
    assert result.passes_applied == passes
    assert result.flagged_for_review is flagged
    assert result.collision is False


@pytest.mark.unit
def test_simplify_name_truncates_and_flags_when_irreducible() -> None:
    """A long name with no applicable rules is truncated and flagged."""
    result = simplify_name("verylongchemicalnamewithoutanyrecognisedtokensatall")
    assert result.char_count <= 30
    assert result.display_name.endswith("…")
    assert result.flagged_for_review is True
    assert "pass6-truncate" in result.passes_applied


@pytest.mark.unit
def test_simplify_name_resolves_collision_by_readding_locant() -> None:
    """A clash with an existing name re-adds the most recent dropped locant."""
    result = simplify_name(
        "4-Fluoro-2-methoxy-5-nitroaniline",
        existing_names=["F-MeO-NO₂-aniline"],
    )
    assert result.collision is True
    assert result.display_name == "5-F-MeO-NO₂-aniline"
    assert result.flagged_for_review is False


@pytest.mark.unit
def test_simplify_name_appends_suffix_when_locant_readd_insufficient() -> None:
    """When re-adding a locant still collides, a disambiguating suffix is added."""
    result = simplify_name(
        "4-Fluoro-2-methoxy-5-nitroaniline",
        existing_names=["F-MeO-NO₂-aniline", "5-F-MeO-NO₂-aniline"],
    )
    assert result.collision is True
    assert result.flagged_for_review is True
    assert result.display_name.endswith("(A)")


@pytest.mark.unit
def test_simplify_name_is_idempotent_and_side_effect_free() -> None:
    """Calling twice yields identical results; the input is never mutated."""
    name = "4-Fluoro-2-methoxy-5-nitroaniline"
    first = simplify_name(name)
    second = simplify_name(name)
    assert first == second
    assert name == "4-Fluoro-2-methoxy-5-nitroaniline"
