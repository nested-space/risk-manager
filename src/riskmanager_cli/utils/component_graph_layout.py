"""
Component-graph (DAG) layout engine for manufacturing route visualisation.

Renders a manufacturing process as a directed acyclic graph where **components**
are nodes and **stages** are the transformations connecting reactants to a
product. Columns are assigned by reverse-topological distance from the final
product; rows are computed bottom-up by composing subtrees with a minimum
vertical spacing (a "tidy tree" layout).

The render is a **strict grid**. The horizontal axis alternates *component
columns* and *connector bands*::

    [col 0][conn 0][col 1][conn 1] ... [col C]

Three invariants are enforced by construction:

1. **Column alignment by distance from the final product.** Every component the
   same number of steps from the final product lands in the same component
   column, so columns line up vertically.
2. **Uniform arrow sets.** *Every* connector band has the same width, with the
   convergence bus at the same offset inside each band, so reactant corners,
   vertical bus segments and the ``├─ Stage ──▶`` junction always align into one
   straight vertical line — no matter how many reactants converge.
3. **Centered component names.** Each component column is as wide as its widest
   label, and names are centered within it.

Unlike :mod:`.manufacturing_layout_engine` (which lays stages out as a flat
left-to-right strip of boxes), this engine understands that one component can be
the product of one stage *and* a reactant of the next, so the process forms a
graph that converges on a single final product.

Robustness:
    Processes are built incrementally, so the graph is frequently incomplete or
    invalid (no stages yet, several terminal products, a stage with two
    products, a cycle). Rather than raising assorted errors, every such case
    raises :class:`IncompleteProcessError`, which callers catch to fall back to
    the linear stage view.
"""

from __future__ import annotations

from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass


class IncompleteProcessError(Exception):
    """Raised when the component graph cannot be laid out as a single DAG.

    Covers: no stages/components, a stage without exactly one product, zero or
    more than one terminal (final) product, and cycles or disconnected pieces.
    """


# === Input data structures (built by the operations bridge or tests) ===


@dataclass(frozen=True)
class StageComponentInput:
    """One reactant/product link within a stage.

    Attributes:
        component_id: Identifier of the linked component.
        component_type: Either ``"reactant"`` or ``"product"``.
    """

    component_id: str
    component_type: str


@dataclass(frozen=True)
class StageInput:
    """A stage and its component links.

    Attributes:
        name: Display name of the stage.
        stage_components: Reactant/product links for this stage.
        number: Sequence number within the process (used by the linear stage
            list; ignored by the DAG layout).
    """

    name: str
    stage_components: list[StageComponentInput]
    number: int = 0


@dataclass(frozen=True)
class ComponentInput:
    """A process component (a material in process context).

    Attributes:
        id: Component identifier.
        display_name: Human-readable label (usually the material name).
        control_strategy_role: Optional role; ``"CRUDE"`` marks the RSM.
        is_isolated: Whether the component is physically isolated in this
            process. Non-isolated components render wrapped in ``[brackets]``.
    """

    id: str
    display_name: str
    control_strategy_role: str | None = None
    is_isolated: bool = True


# === Layout intermediate structures ===


@dataclass
class _GridPosition:
    row: int
    column: int


@dataclass
class _NodeLayout:
    """A laid-out subtree rooted at one component (tidy-tree composition)."""

    node_id: str
    anchor_row: int
    envelope: dict[int, tuple[int, int]]  # column -> (min_row, max_row)
    children: list[tuple[str, _NodeLayout, int]]  # (child_id, layout, shift)


# Light box-drawing glyphs for the convergence bus, keyed by which sides of the
# cell connect: (up, down, left, right).
_BOX: dict[tuple[bool, bool, bool, bool], str] = {
    (False, True, True, False): "┐",  # top reactant lead onto the bus
    (True, False, True, False): "┘",  # bottom reactant lead onto the bus
    (True, True, True, False): "┤",  # intermediate reactant join
    (False, True, False, True): "┌",  # product junction at the top of the bus
    (True, False, False, True): "└",  # product junction at the bottom of the bus
    (True, True, False, True): "├",  # product junction inside the bus
    (True, True, False, False): "│",  # plain vertical bus segment
    (False, True, True, True): "┬",  # reactant + product share the top row
    (True, False, True, True): "┴",  # reactant + product share the bottom row
    (True, True, True, True): "┼",  # reactant + product share an inner row
    (False, False, True, True): "─",  # single reactant straight into the arrow
    (False, False, True, False): "─",  # degenerate lone reactant
    (False, False, False, True): "─",  # degenerate lone product
}

_LEAD = 3  # number of "─" between a reactant and the bus
_ARROW = "▶"
_MAX_NAME_LEN = 12
_MAX_STAGE_LEN = 24
_DEFAULT_MIN_SPACING = 2  # gives each product its own row between two reactants


def _identity(text: str) -> str:
    return text


class ComponentGraphLayoutEngine:  # pylint: disable=too-few-public-methods  # render() is the only entry point
    """Lay out a component DAG and render it on a fixed grid.

    The engine is pure: construct it with the process's stages and components,
    then call :meth:`render` to obtain display lines. Any structural problem
    raises :class:`IncompleteProcessError`.
    """

    def __init__(
        self,
        stages: list[StageInput],
        components: list[ComponentInput],
    ) -> None:
        self._components: dict[str, ComponentInput] = {c.id: c for c in components}
        self._stages = stages
        self._forward: dict[str, list[str]] = defaultdict(list)  # reactant -> [products]
        self._reverse: dict[str, list[str]] = defaultdict(list)  # product -> [reactants]
        self._connected_ids: set[str] = set()

    # ----- graph construction -----

    def _build_graph(self) -> None:
        """Populate forward/reverse adjacency from the stages.

        Raises:
            IncompleteProcessError: If a stage does not have exactly one product
                whose reactants and product are all known components.
        """
        for stage in self._stages:
            reactants, products = self._stage_links(stage)
            if len(products) != 1:
                raise IncompleteProcessError(
                    f"Stage '{stage.name}' must have exactly one product (found {len(products)})."
                )
            product_id = products[0]
            self._connected_ids.add(product_id)
            for reactant_id in reactants:
                self._connected_ids.add(reactant_id)
                self._forward[reactant_id].append(product_id)
                self._reverse[product_id].append(reactant_id)

        if not self._connected_ids:
            raise IncompleteProcessError("No connected components to lay out.")

    def _stage_links(self, stage: StageInput) -> tuple[list[str], list[str]]:
        """Return ``(reactant_ids, product_ids)`` for known components of *stage*."""
        reactants: list[str] = []
        products: list[str] = []
        for link in stage.stage_components:
            if link.component_id not in self._components:
                continue
            if link.component_type == "reactant":
                reactants.append(link.component_id)
            elif link.component_type == "product":
                products.append(link.component_id)
        return reactants, products

    def _find_final_product(self) -> str:
        """Return the single connected component with no downstream product.

        Raises:
            IncompleteProcessError: If there is not exactly one terminal product.
        """
        terminals = [comp_id for comp_id in self._connected_ids if not self._forward.get(comp_id)]
        if len(terminals) != 1:
            raise IncompleteProcessError(
                f"Expected exactly one final product, found {len(terminals)}."
            )
        return terminals[0]

    def _depths(self, final_product_id: str) -> dict[str, int]:
        """Return steps-from-final-product for every connected component.

        Raises:
            IncompleteProcessError: If some connected component is unreachable
                from the final product (a cycle or a disconnected piece).
        """
        depths: dict[str, int] = {}
        queue: deque[tuple[str, int]] = deque([(final_product_id, 0)])
        while queue:
            current_id, depth = queue.popleft()
            if current_id in depths:
                continue
            depths[current_id] = depth
            for reactant_id in self._reverse.get(current_id, []):
                if reactant_id not in depths:
                    queue.append((reactant_id, depth + 1))
        if set(depths) != self._connected_ids:
            raise IncompleteProcessError(
                "Process graph is not a single connected tree (cycle or split)."
            )
        return depths

    @staticmethod
    def _column(component_id: str, depths: dict[str, int]) -> int:
        max_depth = max(depths.values()) if depths else 0
        return max_depth - depths[component_id]

    # ----- tidy-tree row assignment -----

    def _compose(
        self,
        node_id: str,
        depths: dict[str, int],
        min_spacing: int,
        memo: dict[str, _NodeLayout],
    ) -> _NodeLayout:
        if node_id in memo:
            return memo[node_id]

        col = self._column(node_id, depths)
        children_ids = sorted(self._reverse.get(node_id, []))

        if not children_ids:
            layout = _NodeLayout(node_id, anchor_row=0, envelope={col: (0, 0)}, children=[])
            memo[node_id] = layout
            return layout

        child_layouts = [
            (cid, self._compose(cid, depths, min_spacing, memo), 0) for cid in children_ids
        ]
        merged = _stack_children(child_layouts, min_spacing)

        anchors = sorted(cl.anchor_row + sh for (_cid, cl, sh) in child_layouts)
        parent_row = _median_int(anchors)

        if col in merged:
            lo, hi = merged[col]
            merged[col] = (min(lo, parent_row), max(hi, parent_row))
        else:
            merged[col] = (parent_row, parent_row)

        layout = _NodeLayout(node_id, parent_row, merged, child_layouts)
        memo[node_id] = layout
        return layout

    def _place(
        self,
        layout: _NodeLayout,
        depths: dict[str, int],
        base_shift: int,
        positions: dict[str, _GridPosition],
    ) -> None:
        positions[layout.node_id] = _GridPosition(
            row=base_shift + layout.anchor_row,
            column=self._column(layout.node_id, depths),
        )
        for _cid, child_layout, child_shift in layout.children:
            self._place(child_layout, depths, base_shift + child_shift, positions)

    # ----- rendering -----

    def render(
        self,
        dim: Callable[[str], str] = _identity,
        min_spacing: int = _DEFAULT_MIN_SPACING,
    ) -> list[str]:
        """Return the rendered DAG as a list of display lines.

        Args:
            dim: Optional styling function applied to stage-label spans only
                (visible width unchanged). Defaults to a no-op so the plain grid
                can be asserted directly.
            min_spacing: Minimum vertical gap between sibling subtrees.

        Raises:
            IncompleteProcessError: If the graph cannot be laid out as a DAG.
        """
        positions = self._positions(min_spacing)
        labels = {cid: self._label(cid) for cid in positions}
        return _render_grid(positions, labels, self._stage_specs(positions), dim)

    def final_product_name(self) -> str:
        """Return the display label of the graph's single final product.

        Raises:
            IncompleteProcessError: If the graph cannot be laid out as a DAG.
        """
        self._build_graph()
        return self._label(self._find_final_product())

    def _positions(self, min_spacing: int) -> dict[str, _GridPosition]:
        """Build the graph and assign a normalised ``(row, column)`` to each node."""
        self._build_graph()
        final_product_id = self._find_final_product()
        depths = self._depths(final_product_id)

        memo: dict[str, _NodeLayout] = {}
        root = self._compose(final_product_id, depths, min_spacing, memo)
        positions: dict[str, _GridPosition] = {}
        self._place(root, depths, base_shift=-root.anchor_row, positions=positions)

        min_row = min(pos.row for pos in positions.values())
        for pos in positions.values():
            pos.row -= min_row
        return positions

    def _label(self, component_id: str) -> str:
        """Return the display label, bracketing non-isolated components."""
        component = self._components.get(component_id)
        if component is None:
            return _truncate(component_id, _MAX_NAME_LEN)
        name = _truncate(component.display_name, _MAX_NAME_LEN)
        return name if component.is_isolated else f"[{name}]"

    def _stage_specs(self, positions: dict[str, _GridPosition]) -> list[_StageSpec]:
        """Build one drawable spec per stage whose reactants are placed adjacently.

        A spec is emitted only when the stage has its single product placed and
        at least one reactant exactly one column to its left, so the connector
        can be drawn as a clean convergence bus.
        """
        specs: list[_StageSpec] = []
        for stage in self._stages:
            _reactants, products = self._stage_links(stage)
            if len(products) != 1 or products[0] not in positions:
                continue
            band = positions[products[0]].column - 1
            adjacent = [
                rid for rid in _reactants if rid in positions and positions[rid].column == band
            ]
            if band < 0 or not adjacent:
                continue
            specs.append(_StageSpec(_truncate(stage.name, _MAX_STAGE_LEN), adjacent, products[0]))
        return specs


# === Grid rendering (pure, operates on placed positions and stage specs) ===


@dataclass(frozen=True)
class _StageSpec:
    """A stage ready to draw: its label, adjacent reactants and single product."""

    label: str
    reactant_ids: list[str]
    product_id: str


@dataclass(frozen=True)
class _Grid:
    """Geometry of the fixed render grid (column widths and x-offsets)."""

    rows: int
    cols: int
    col_width: dict[int, int]
    x_col: dict[int, int]
    right_width: int
    total_width: int


def _render_grid(
    positions: dict[str, _GridPosition],
    labels: dict[str, str],
    specs: list[_StageSpec],
    dim: Callable[[str], str],
) -> list[str]:
    """Paint components and connectors onto a fixed grid and stringify it."""
    geo = _grid_geometry(positions, labels, specs)
    canvas = [[" "] * geo.total_width for _ in range(geo.rows)]
    dim_spans: dict[int, list[tuple[int, int]]] = defaultdict(list)
    _paint_components(canvas, positions, labels, geo)
    for spec in specs:
        _paint_stage(canvas, dim_spans, spec, positions, geo)
    return _stringify(canvas, dim_spans, dim)


def _grid_geometry(
    positions: dict[str, _GridPosition],
    labels: dict[str, str],
    specs: list[_StageSpec],
) -> _Grid:
    """Compute column widths and x-offsets; every connector band shares one width."""
    rows = max(pos.row for pos in positions.values()) + 1
    cols = max(pos.column for pos in positions.values()) + 1

    max_label = max((len(spec.label) for spec in specs), default=1)
    right_width = max_label + 6  # "─ <label> ──▶" with room for the arrowhead
    conn_width = _LEAD + 1 + right_width

    # One space of padding each side keeps names off the connectors.
    col_width = {col: 1 for col in range(cols)}
    for cid, pos in positions.items():
        col_width[pos.column] = max(col_width[pos.column], len(labels[cid]) + 2)

    x_col: dict[int, int] = {}
    cursor = 0
    for col in range(cols):
        x_col[col] = cursor
        cursor += col_width[col] + (conn_width if col < cols - 1 else 0)
    return _Grid(rows, cols, col_width, x_col, right_width, cursor)


def _paint_components(
    canvas: list[list[str]],
    positions: dict[str, _GridPosition],
    labels: dict[str, str],
    geo: _Grid,
) -> None:
    """Write each component's centered label into its column cell."""
    for cid, pos in positions.items():
        cell = labels[cid].center(geo.col_width[pos.column])
        canvas[pos.row][geo.x_col[pos.column] : geo.x_col[pos.column] + len(cell)] = list(cell)


def _paint_stage(
    canvas: list[list[str]],
    dim_spans: dict[int, list[tuple[int, int]]],
    spec: _StageSpec,
    positions: dict[str, _GridPosition],
    geo: _Grid,
) -> None:
    """Draw one stage's convergence bus and labelled arrow into the connector band."""
    product_pos = positions[spec.product_id]
    band_left = geo.x_col[product_pos.column - 1] + geo.col_width[product_pos.column - 1]
    bus_x = band_left + _LEAD
    reactant_rows = {positions[rid].row for rid in spec.reactant_ids}
    span = sorted(reactant_rows | {product_pos.row})
    for row in range(span[0], span[-1] + 1):
        left, right = row in reactant_rows, row == product_pos.row
        canvas[row][bus_x] = _BOX[(row > span[0], row < span[-1], left, right)]
        if left:
            canvas[row][band_left:bus_x] = list("─" * _LEAD)
        if right:
            # "─ <label> ──▶" from the bus to the product column edge.
            filled = f"─ {spec.label} ".ljust(geo.right_width - 1, "─") + _ARROW
            canvas[row][bus_x + 1 : bus_x + 1 + len(filled)] = list(filled)
            label_start = bus_x + 3  # after the bus glyph and the leading "─ "
            dim_spans[row].append((label_start, label_start + len(spec.label)))


def _stringify(
    canvas: list[list[str]],
    dim_spans: dict[int, list[tuple[int, int]]],
    dim: Callable[[str], str],
) -> list[str]:
    """Join the grid into lines, dimming recorded label spans (right-to-left)."""
    lines: list[str] = []
    for row, chars in enumerate(canvas):
        text = "".join(chars)
        for start, end in sorted(dim_spans[row], reverse=True):
            text = text[:start] + dim(text[start:end]) + text[end:]
        lines.append(text.rstrip())
    return lines


def render_component_graph(
    stages: list[StageInput],
    components: list[ComponentInput],
    dim: Callable[[str], str] = _identity,
) -> list[str]:
    """Render a component DAG to display lines.

    Convenience wrapper over :class:`ComponentGraphLayoutEngine`.

    Args:
        stages: Stages with their reactant/product links.
        components: Process components.
        dim: Optional styling function for stage-label spans.

    Returns:
        Rendered grid lines.

    Raises:
        IncompleteProcessError: If the graph cannot be laid out as a DAG.
    """
    return ComponentGraphLayoutEngine(stages, components).render(dim)


def split_for_width(
    stages: list[StageInput],
    components: list[ComponentInput],
    max_width: int,
    dim: Callable[[str], str] = _identity,
) -> list[tuple[str | None, list[str]]]:
    """Render the graph, splitting it into stacked sub-graphs when too wide.

    When the full graph fits within *max_width*, a single ``(None, lines)``
    section is returned (no header). Otherwise stages are packed greedily, in
    order, into consecutive groups that each fit; every group becomes a
    ``("Route To <final product>:", lines)`` section, and the intermediate
    component at each split re-appears as a leaf reactant seeding the next group.

    Args:
        stages: Stages in chronological order (as listed for the process).
        components: All process components.
        max_width: Maximum line width to fit within (terminal width).
        dim: Optional styling function for stage-label spans.

    Returns:
        Ordered ``(title, lines)`` sections; ``title`` is ``None`` for the
        single-section (fits) case.

    Raises:
        IncompleteProcessError: If the full graph cannot be laid out as a DAG.
    """
    full = ComponentGraphLayoutEngine(stages, components).render()
    if _visible_width(full) <= max_width:
        return [(None, ComponentGraphLayoutEngine(stages, components).render(dim))]

    groups = _group_stages(stages, components, max_width)
    sections = _render_groups(groups, components, dim)
    if sections is None:
        # A group could not stand alone (e.g. a branch whose merge is elsewhere);
        # fall back to the un-split graph rather than crash.
        return [(None, ComponentGraphLayoutEngine(stages, components).render(dim))]
    return sections


def _group_stages(
    stages: list[StageInput],
    components: list[ComponentInput],
    max_width: int,
) -> list[list[StageInput]]:
    """Greedily pack stages, in order, into consecutive groups that each fit."""
    groups: list[list[StageInput]] = []
    current: list[StageInput] = []
    for stage in stages:
        if not current:
            current = [stage]
            continue
        trial = current + [stage]
        if _chunk_fits(trial, components, max_width):
            current = trial
        else:
            groups.append(current)
            current = [stage]
    if current:
        groups.append(current)
    return groups


def _chunk_fits(
    chunk: list[StageInput],
    components: list[ComponentInput],
    max_width: int,
) -> bool:
    """True if *chunk* renders as a valid DAG within *max_width*."""
    try:
        lines = ComponentGraphLayoutEngine(chunk, _referenced(chunk, components)).render()
    except IncompleteProcessError:
        return False
    return _visible_width(lines) <= max_width


def _render_groups(
    groups: list[list[StageInput]],
    components: list[ComponentInput],
    dim: Callable[[str], str],
) -> list[tuple[str | None, list[str]]] | None:
    """Render each group with its ``Route To <final>:`` title, or ``None`` on failure."""
    sections: list[tuple[str | None, list[str]]] = []
    for chunk in groups:
        engine = ComponentGraphLayoutEngine(chunk, _referenced(chunk, components))
        try:
            title = f"Route To {engine.final_product_name()}:"
            lines = ComponentGraphLayoutEngine(chunk, _referenced(chunk, components)).render(dim)
        except IncompleteProcessError:
            return None
        sections.append((title, lines))
    return sections


def _referenced(
    stages: list[StageInput],
    components: list[ComponentInput],
) -> list[ComponentInput]:
    """Return the components referenced by *stages* (preserving order)."""
    ids = {link.component_id for stage in stages for link in stage.stage_components}
    return [c for c in components if c.id in ids]


def _visible_width(lines: list[str]) -> int:
    return max((len(line) for line in lines), default=0)


def _stack_children(
    child_layouts: list[tuple[str, _NodeLayout, int]],
    min_spacing: int,
) -> dict[int, tuple[int, int]]:
    """Shift each child down so subtrees never overlap; return the merged envelope.

    Mutates *child_layouts* in place, replacing each entry's shift with the value
    needed to keep that child at least *min_spacing* below everything already
    placed. Returns the combined column -> (min_row, max_row) envelope.
    """
    merged: dict[int, tuple[int, int]] = {}
    for i, (cid, child, shift) in enumerate(child_layouts):
        shift += _required_push(child.envelope, shift, merged, min_spacing)
        child_layouts[i] = (cid, child, shift)
        for column, (mn, mx) in child.envelope.items():
            lo, hi = mn + shift, mx + shift
            if column in merged:
                e_lo, e_hi = merged[column]
                merged[column] = (min(e_lo, lo), max(e_hi, hi))
            else:
                merged[column] = (lo, hi)
    return merged


def _required_push(
    envelope: dict[int, tuple[int, int]],
    shift: int,
    merged: dict[int, tuple[int, int]],
    min_spacing: int,
) -> int:
    """Return the extra downward shift needed to clear *merged* by *min_spacing*."""
    push = 0
    for column, (mn, _mx) in envelope.items():
        if column in merged:
            _e_lo, e_hi = merged[column]
            push = max(push, (e_hi + min_spacing) - (mn + shift))
    return max(0, push)


def _median_int(values: list[int]) -> int:
    """Return the integer midpoint of a sorted list (rounded for even counts)."""
    if not values:
        return 0
    mid = len(values) // 2
    if len(values) % 2 == 1:
        return values[mid]
    return round((values[mid - 1] + values[mid]) / 2)


def _truncate(text: str, max_len: int) -> str:
    """Truncate *text* to *max_len*, adding ``…`` when shortened."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"
