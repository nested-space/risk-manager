"""
Deterministic compound display-name simplification.

Produces a concise display label for a chemical compound name by running an
ordered set of rule passes (noise-word removal, substituent-symbol
substitution, locant removal, fragment compression) and stopping as soon as the
result is within a soft length cap. A hard truncation is applied only as a last
resort. The result is fully auditable: it records which passes ran, whether a
collision was resolved, and whether manual review is recommended.

Why this exists:
    Library entries carry full IUPAC / semi-systematic names that are far too
    long for table cells, route diagrams and focus-screen titles. A short
    ``display_name`` is wanted, but it should be *suggested* (and overridable),
    deterministic, and testable — never an opaque or network-dependent guess.
    The rules are intentionally heuristic: they favour chemical intelligibility
    and never claim to be a complete IUPAC parser.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass

#: Unicode subscript digits. Each already occupies a single terminal cell, so
#: :func:`visual_length` counts them like any other character; the set documents
#: the "subscripts = one char" contract and the digits baked into Pass 2.
_SUBSCRIPT_DIGITS: frozenset[str] = frozenset("₀₁₂₃₄₅₆₇₈₉")

#: Pass 1 — words removed wholesale; they add no value when a structure is shown.
#: ``free`` is included so "free base" collapses to "base".
_NOISE_WORDS: tuple[str, ...] = (
    "intermediate",
    "derivative",
    "compound",
    "product",
    "free",
    "salt",
)

#: Pass 1 — salt/hydrate normalisations as ``(pattern, replacement)`` applied in
#: order (longest first so "dihydrochloride" wins over "hydrochloride"). An
#: optional leading separator is consumed so the result reads "Aspirin·HCl".
_SALT_NORMALISATIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"[\s·.-]*\bdihydrochloride\b", re.IGNORECASE), "·2HCl"),
    (re.compile(r"[\s·.-]*\bhydrochloride\b", re.IGNORECASE), "·HCl"),
    (re.compile(r"[\s·.-]*\b(?:mono|di|tri|tetra)?hydrate\b", re.IGNORECASE), ""),
)

#: Pass 2 — substituent → symbol, ordered longest/most-specific first so a longer
#: token (e.g. ``trifluoromethyl``) is never partially shadowed by a shorter one
#: (``methyl``). Replacements carry a trailing hyphen; doubled separators are
#: tidied afterwards.
_SUBSTITUENTS: tuple[tuple[str, str], ...] = (
    ("trifluoromethyl", "CF₃-"),
    ("dimethylamino", "NMe₂-"),
    ("trimethyl", "triMe-"),
    ("dimethyl", "diMe-"),
    ("trifluoro", "F₃-"),
    ("methoxy", "MeO-"),
    ("ethoxy", "EtO-"),
    ("hydroxy", "HO-"),
    ("chloro", "Cl-"),
    ("fluoro", "F-"),
    ("bromo", "Br-"),
    ("iodo", "I-"),
    ("nitro", "NO₂-"),
    ("amino", "NH₂-"),
    ("acetyl", "Ac-"),
)

#: Pass 3 — numeric / heteroatom locants stripped together with their trailing
#: hyphen so the surrounding single separators survive (``4-Fluoro-2-`` →
#: ``Fluoro-``). Handles plain, primed, and comma-grouped N-locants.
_LOCANT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bN(?:,N)*['′]?-", re.IGNORECASE),
    re.compile(r"\b\d+['′]?-"),
)

#: Pass 4 — multi-token fragments compressed to recognised abbreviations. Regex
#: based so an interior locant removed by Pass 3 (``oxirane-2-carboxylate`` →
#: ``oxirane-carboxylate``) still matches.
_FRAGMENTS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bethylenediamine\b", re.IGNORECASE), "EDA"),
    (re.compile(r"\boxirane-?\d*-?carboxylate\b", re.IGNORECASE), "glycidic ester"),
    (re.compile(r"carboxylate\b", re.IGNORECASE), "-COOH"),
    (re.compile(r"carboxylic acid\b", re.IGNORECASE), "-COOH"),
)

#: Names of the passes, indexed by their spec number, for the audit trail.
_PASS_NAMES: dict[int, str] = {
    1: "pass1-noise",
    2: "pass2-substituents",
    3: "pass3-locants",
    4: "pass4-fragments",
    6: "pass6-truncate",
}


@dataclass(frozen=True)
class SimplifyResult:
    """Outcome of a deterministic display-name simplification run.

    Attributes:
        display_name: The simplified name, with Unicode subscripts already
            applied. Never longer than the hard cap passed to
            :func:`simplify_name`.
        char_count: Visual length of ``display_name`` (each Unicode subscript
            counts as a single character).
        passes_applied: Names of the passes that changed the string, ordered by
            their spec pass number.
        collision: ``True`` when the candidate matched an existing name and was
            disambiguated.
        flagged_for_review: ``True`` when hard truncation fired or a collision
            could only be resolved with a disambiguating suffix.
        notes: Ordered, human-readable diagnostics for review surfaces.
    """

    display_name: str
    char_count: int
    passes_applied: tuple[str, ...]
    collision: bool
    flagged_for_review: bool
    notes: tuple[str, ...]


def visual_length(text: str) -> int:
    """Return the display width of *text*, counting each subscript as one char.

    Unicode subscript digits occupy a single terminal cell, so they are counted
    like any other character. This helper exists to make that invariant explicit
    and to provide a single place to revisit should superscripts or combining
    marks be added later.

    Args:
        text: The string to measure.

    Returns:
        The number of characters, treating each subscript digit as one.
    """
    return len(text)


def _tidy(text: str) -> str:
    """Collapse whitespace and duplicated/edge hyphens left by substitutions.

    Args:
        text: A partially transformed name.

    Returns:
        The name with runs of spaces and hyphens collapsed and leading/trailing
        hyphens removed.
    """
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"-{2,}", "-", text)
    text = re.sub(r"^-+|-+$", "", text)
    return text.strip()


def _pass1_remove_noise(name: str) -> str:
    """Pass 1: drop noise words and normalise salt/hydrate suffixes.

    Args:
        name: The current working name.

    Returns:
        The name with salt forms normalised (e.g. ``hydrochloride`` → ``·HCl``)
        and noise words (``product``, ``intermediate`` …) removed.
    """
    for pattern, replacement in _SALT_NORMALISATIONS:
        name = pattern.sub(replacement, name)
    for word in _NOISE_WORDS:
        name = re.sub(rf"\b{word}\b", "", name, flags=re.IGNORECASE)
    return _tidy(name)


def _pass2_substituents(name: str) -> str:
    """Pass 2: replace spelled-out substituents with symbols.

    Args:
        name: The current working name.

    Returns:
        The name with substituent words (``chloro``, ``nitro``, ``methoxy`` …)
        replaced by their symbols (``Cl-``, ``NO₂-``, ``MeO-`` …).
    """
    for word, symbol in _SUBSTITUENTS:
        name = re.sub(re.escape(word), symbol, name, flags=re.IGNORECASE)
    return _tidy(name)


def _pass3_remove_locants(name: str) -> tuple[str, list[str]]:
    """Pass 3: strip numeric and heteroatom locants.

    Args:
        name: The current working name.

    Returns:
        A ``(name, dropped)`` pair where ``dropped`` lists the locant tokens
        removed (most-informative re-add fodder for collision resolution),
        in the order they appeared.
    """
    dropped: list[str] = []
    for pattern in _LOCANT_PATTERNS:
        dropped.extend(match.group(0) for match in pattern.finditer(name))
        name = pattern.sub("", name)
    return _tidy(name), dropped


def _pass4_compress_fragments(name: str) -> str:
    """Pass 4: compress recognised multi-token fragments to abbreviations.

    Args:
        name: The current working name.

    Returns:
        The name with fragments such as ``ethylenediamine`` → ``EDA`` compressed.
    """
    for pattern, replacement in _FRAGMENTS:
        name = pattern.sub(replacement, name)
    return _tidy(name)


def _pass6_truncate(name: str, hard_cap: int) -> str:
    """Pass 6: last-resort truncation to fit *hard_cap*.

    Drops whole tokens from the left first, then hard-cuts on the right with an
    ellipsis. Never splits inside a token unless a single token already exceeds
    the cap.

    Args:
        name: The current working name (already over the hard cap).
        hard_cap: Maximum permitted visual length.

    Returns:
        A name of at most ``hard_cap`` characters.
    """
    tokens = name.split(" ")
    while len(tokens) > 1 and visual_length(" ".join(tokens)) > hard_cap:
        tokens.pop(0)
    candidate = " ".join(tokens)
    if visual_length(candidate) <= hard_cap:
        return candidate
    return candidate[: max(1, hard_cap - 1)].rstrip() + "…"


def _run_passes(name: str, max_length: int) -> tuple[str, set[int], list[str]]:
    """Run passes 1, 3, 2, 4 in that order, stopping under *max_length*.

    Locant removal (Pass 3) runs before substituent substitution (Pass 2) so the
    flagship multi-substituent names tidy cleanly; fragment compression (Pass 4)
    runs last as it is the most specific.

    Args:
        name: The normalised input name.
        max_length: Soft cap; passes stop once the working name is within it.

    Returns:
        A ``(name, applied, dropped_locants)`` tuple. ``applied`` holds the spec
        numbers of passes that changed the string.
    """
    applied: set[int] = set()
    dropped: list[str] = []
    working = name
    if visual_length(working) <= max_length:
        return working, applied, dropped

    def step(number: int, candidate: str) -> bool:
        """Adopt *candidate* for pass *number*; return True once under the cap."""
        nonlocal working
        if candidate != working:
            applied.add(number)
            working = candidate
        return visual_length(working) <= max_length

    if step(1, _pass1_remove_noise(working)):
        return working, applied, dropped
    delocanted, dropped = _pass3_remove_locants(working)
    if step(3, delocanted):
        return working, applied, dropped
    if step(2, _pass2_substituents(working)):
        return working, applied, dropped
    step(4, _pass4_compress_fragments(working))
    return working, applied, dropped


def _resolve_collision(
    name: str, existing: set[str], dropped_locants: list[str]
) -> tuple[str, bool]:
    """Disambiguate *name* against an existing name set.

    First re-adds the most recently dropped locant as a prefix; if that still
    collides (or none was dropped), appends ``(A)``, ``(B)`` … as a last resort.

    Args:
        name: The candidate display name.
        existing: Case-folded names already in use.
        dropped_locants: Locant tokens removed by Pass 3, in order.

    Returns:
        A ``(name, flagged)`` pair. ``flagged`` is ``True`` only when a suffix
        had to be appended (manual review recommended).
    """
    if name.casefold() not in existing:
        return name, False
    if dropped_locants:
        candidate = f"{dropped_locants[-1]}{name}"
        if candidate.casefold() not in existing:
            return candidate, False
    for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
        candidate = f"{name} ({letter})"
        if candidate.casefold() not in existing:
            return candidate, True
    return name, True


def simplify_name(
    name: str,
    *,
    existing_names: Iterable[str] | None = None,
    max_length: int = 25,
    hard_cap: int = 30,
) -> SimplifyResult:
    """Deterministically shorten a chemical *name* for display.

    Runs ordered rule passes, stopping as soon as the visual length is within
    *max_length*. Names already within the soft cap are returned unchanged. After
    the passes, the candidate is checked against *existing_names* and, if still
    over *hard_cap*, truncated as a last resort.

    Args:
        name: The full compound name to shorten.
        existing_names: Other display names / aliases already in the set, used to
            detect and resolve collisions. ``None`` disables collision checks.
        max_length: Soft cap (characters); passes stop once it is met.
        hard_cap: Hard cap (characters); truncation fires above it.

    Returns:
        A :class:`SimplifyResult` describing the outcome and how it was reached.
    """
    working = _tidy(name)
    working, applied, dropped = _run_passes(working, max_length)

    notes: list[str] = []
    existing = {item.casefold() for item in existing_names} if existing_names else set()
    collision = False
    flagged = False
    if existing:
        before = working
        working, flagged = _resolve_collision(working, existing, dropped)
        collision = flagged or working != before

    if visual_length(working) > hard_cap:
        working = _pass6_truncate(working, hard_cap)
        applied.add(6)
        flagged = True
        notes.append("Name truncated to fit the display cap — review recommended.")

    passes = tuple(_PASS_NAMES[num] for num in sorted(applied))
    return SimplifyResult(
        display_name=working,
        char_count=visual_length(working),
        passes_applied=passes,
        collision=collision,
        flagged_for_review=flagged,
        notes=tuple(notes),
    )
