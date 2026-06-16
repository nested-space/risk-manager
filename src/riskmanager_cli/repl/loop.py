"""Synchronous blessed event loop bridging into async operations."""

from __future__ import annotations

import asyncio
import signal
from collections.abc import Coroutine
from types import FrameType
from typing import Any, TypeVar

import blessed

from ..config.settings import Environment
from .commands import CommandDispatcher
from .context import ContextManager
from .screen import ScreenManager
from .session_state import SessionState
from .viewport import follow, max_offset, parse, selected_line

T = TypeVar("T")


def run_async(coro: Coroutine[Any, Any, T]) -> T:
    """Bridge from the synchronous blessed event loop to async operations.

    Creates a fresh event loop per call because terminal input handling remains
    synchronous for the lifetime of the REPL.

    Args:
        coro: Coroutine to execute.

    Returns:
        The coroutine's result.
    """
    return asyncio.run(coro)


async def _async_bridge(coro: Coroutine[Any, Any, T]) -> T:
    """Await and return *coro*.

    Args:
        coro: Coroutine to await.

    Returns:
        The awaited result.
    """
    return await coro


def start_repl(  # pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches,too-many-statements  # blessed event loop; all deps injected, cannot reduce
    term: blessed.Terminal,
    ctx: ContextManager,
    session: SessionState,
    screen: ScreenManager,
    dispatcher: CommandDispatcher,
    env: Environment,
) -> None:
    """Start the main REPL event loop.

    Args:
        term: Active terminal instance.
        ctx: Navigation context stack.
        session: Persistent session state.
        screen: Screen renderer.
        dispatcher: Slash-command dispatcher.
        env: Active database environment.
    """
    del env  # The environment is already captured by *dispatcher*.

    input_buffer = ""
    last_field_key: tuple[int, int] | None = None
    notice = ""
    mode = "view"  # "view" (hotkeys) | "search" ("/" filter) | "command" (":" line)
    view = parse(_coerce_lines(run_async(dispatcher.render_current())))
    current_output_lines = view.lines
    scroll_offset = 0
    resize_pending = False

    def reflow(lines: list[str]) -> None:
        """Re-parse the output buffer in place, preserving the scroll position.

        Used for same-screen re-renders (list navigation, resize) where the
        caller manages ``scroll_offset`` itself.
        """
        nonlocal current_output_lines, view
        view = parse(lines)
        current_output_lines = view.lines

    def set_output(lines: list[str]) -> None:
        """Replace the output pane content, resetting the scroll to the top.

        Every content change other than a same-screen list re-render goes through
        here so the new screen starts unscrolled.
        """
        nonlocal scroll_offset
        reflow(lines)
        scroll_offset = 0

    def _max_scroll() -> int:
        return max_offset(view, screen.output_height)

    def consume_notice() -> None:
        """Refresh the status notice from any just-completed dispatcher action.

        Submitting an action either sets a fresh notice or clears the previous
        one; plain typing and navigation leave the notice untouched.
        """
        nonlocal notice
        pending = dispatcher.take_notice()
        notice = screen.style_notice(*pending) if pending else ""

    def view_hint() -> str:
        """Build the input-row reminder for the current view-mode screen."""
        parts = []
        if _in_list_mode(ctx):
            parts.append("↑↓ navigate · Enter select")
        if dispatcher.supports_search():
            parts.append("/ search")
        parts.extend([": command", "? help"])
        return "  ·  ".join(parts)

    def sync_prompt_prefill() -> None:
        """Seed the input buffer with the active prompt field's current value.

        Edit forms supply each field's existing value as its ``default``. The
        first time a text/numeric field becomes active we copy that into the
        live buffer so it shows and can be edited; subsequent keystrokes on the
        same field leave the buffer alone. Select fields and completed/absent
        prompts contribute nothing (``prompt_prefill`` returns ``""``).
        """
        nonlocal input_buffer, last_field_key
        state = dispatcher.prompt_state
        if state is None or state.is_complete():
            last_field_key = None
            return
        key = (id(state), state.current_index)
        if key != last_field_key:
            last_field_key = key
            input_buffer = dispatcher.prompt_prefill()

    def redraw() -> None:
        nonlocal scroll_offset
        sync_prompt_prefill()
        scroll_offset = max(0, min(scroll_offset, _max_scroll()))
        screen.draw_status_bar()
        screen.draw_output(view, scroll_offset)
        if dispatcher.picker_state is not None:
            screen.draw_input_line(prompt="filter: ", text=input_buffer)
        elif dispatcher.prompt_state is not None:
            if dispatcher.prompt_state.is_select_field:
                screen.draw_nav_hint("↑↓ to move · Enter to select · Esc/Ctrl-C to cancel")
            else:
                prompt = f"{dispatcher.prompt_state.current_field.label}: "
                screen.draw_input_line(prompt=prompt, text=input_buffer)
        elif mode == "command":
            screen.draw_input_line(prompt=":", text=input_buffer)
        elif mode == "search":
            screen.draw_input_line(prompt="/", text=input_buffer)
        else:
            hint = view_hint()
            indicator = screen.scroll_indicator(
                scroll_offset,
                len(view.lines) - view.sticky_count,
                height=screen.output_height - view.sticky_count,
            )
            if indicator:
                hint = f"{hint}  ·  {indicator}"
            screen.draw_nav_hint(hint, notice=notice)
        screen.draw_info_line(dispatcher.command_hints())

    def reset_to_view() -> None:
        nonlocal input_buffer, notice, mode
        input_buffer = ""
        notice = ""
        mode = "view"

    def handle_back(*, quit_at_home: bool) -> bool:
        """Leave the innermost context: cancel a modal, exit the "/" or ":" line,
        or pop a navigation level.

        Args:
            quit_at_home: When ``True`` (Ctrl-C), signal quit if there is nothing
                left to leave; when ``False`` (Esc), the home screen stays put.

        Returns:
            ``True`` only when *quit_at_home* and already at the home screen.
        """
        nonlocal input_buffer, notice, mode
        cancelled = False
        if dispatcher.picker_state is not None:
            set_output(_coerce_lines(run_async(dispatcher.cancel_picker())))
            cancelled = True
        elif dispatcher.prompt_state is not None:
            set_output(_coerce_lines(run_async(dispatcher.cancel_prompt())))
            cancelled = True
        elif mode in {"command", "search"}:
            set_output(_coerce_lines(run_async(dispatcher.render_current())))
        elif ctx.pop() is None:
            return quit_at_home
        else:
            set_output(_coerce_lines(run_async(dispatcher.render_current())))
            _sync_session_context(session, ctx)
        reset_to_view()
        if cancelled:
            consume_notice()
        return False

    def handle_resize(_signum: int, _frame: FrameType | None) -> None:
        """Flag a pending resize; the reflow happens in the main loop.

        The handler must stay trivial: re-rendering calls ``asyncio.run`` (via
        ``run_async``), which cannot be re-entered, and SIGWINCH can fire while
        the loop is mid-render. Setting a flag defers the work to a safe point.
        """
        nonlocal resize_pending
        resize_pending = True

    def apply_resize() -> None:
        """Reflow the current screen to the new terminal size, then repaint.

        View screens are rebuilt at the new width so tables refit and the home
        banner re-centres; modal states are only repainted, since ``redraw``
        draws the live prompt/picker itself.
        """
        nonlocal resize_pending
        resize_pending = False
        screen.clear_screen()
        idle = mode == "view" and dispatcher.prompt_state is None
        if idle and dispatcher.picker_state is None:
            reflow(_coerce_lines(run_async(dispatcher.render_current())))
        redraw()

    previous_handler = signal.getsignal(signal.SIGWINCH)
    signal.signal(signal.SIGWINCH, handle_resize)
    redraw()

    def request_quit() -> None:
        """Open the home-screen quit confirmation in place of an immediate exit."""
        set_output(_coerce_lines(dispatcher.start_quit_confirm()))

    try:  # pylint: disable=too-many-nested-blocks  # blessed inkey loop; prompt/picker/list branches require deep nesting
        while True:
            if resize_pending:
                apply_resize()
            if dispatcher.quit_requested:
                break
            try:
                # A timeout lets the loop notice a pending resize (flagged by the
                # SIGWINCH handler) without waiting for the next keystroke.
                key = term.inkey(timeout=0.25)
            except KeyboardInterrupt:
                if handle_back(quit_at_home=True):
                    request_quit()
                redraw()
                continue
            if not key:
                continue
            key_name = key.name or str(key)
            key_text = str(key)

            if key_text == "\x04":
                break
            if key_text == "\x03":
                if handle_back(quit_at_home=True):
                    request_quit()
                redraw()
                continue
            if key_name == "KEY_ESCAPE":
                handle_back(quit_at_home=False)
                redraw()
                continue

            if dispatcher.prompt_state is not None:
                if dispatcher.prompt_state.is_select_field:
                    if _is_enter(key_name, key_text):
                        set_output(_coerce_lines(run_async(dispatcher.submit_prompt_selection())))
                        input_buffer = ""
                        consume_notice()
                    elif key_name in {"KEY_UP", "KEY_DOWN"}:
                        direction = "up" if key_name == "KEY_UP" else "down"
                        set_output(dispatcher.prompt_move(direction))
                    redraw()
                    continue
                if _is_enter(key_name, key_text):
                    set_output(_coerce_lines(run_async(dispatcher.advance_prompt(input_buffer))))
                    input_buffer = ""
                    consume_notice()
                elif _is_backspace(key_name, key_text):
                    input_buffer = input_buffer[:-1]
                elif _is_text_input(key):
                    input_buffer += key_text
                redraw()
                continue

            if dispatcher.picker_state is not None:
                if _is_enter(key_name, key_text):
                    set_output(_coerce_lines(run_async(dispatcher.picker_select())))
                    input_buffer = ""
                    consume_notice()
                elif key_name in {"KEY_UP", "KEY_DOWN"}:
                    direction = "up" if key_name == "KEY_UP" else "down"
                    set_output(dispatcher.picker_move(direction))
                elif _is_backspace(key_name, key_text):
                    input_buffer = input_buffer[:-1]
                    set_output(dispatcher.update_picker_query(input_buffer))
                elif _is_text_input(key):
                    input_buffer += key_text
                    set_output(dispatcher.update_picker_query(input_buffer))
                redraw()
                continue

            if mode == "command":
                if _is_enter(key_name, key_text):
                    result = run_async(dispatcher.dispatch(input_buffer))
                    if result == "__QUIT__":
                        break
                    set_output(_coerce_lines(result))
                    reset_to_view()
                    _sync_session_context(session, ctx)
                    consume_notice()
                elif _is_backspace(key_name, key_text):
                    input_buffer = input_buffer[:-1]
                elif _is_text_input(key):
                    input_buffer += key_text
                redraw()
                continue

            if mode == "search":
                if _is_enter(key_name, key_text):
                    mode = "view"
                    input_buffer = ""
                elif _is_backspace(key_name, key_text):
                    input_buffer = input_buffer[:-1]
                    set_output(_coerce_lines(run_async(dispatcher.search(input_buffer))))
                elif _is_text_input(key):
                    input_buffer += key_text
                    set_output(_coerce_lines(run_async(dispatcher.search(input_buffer))))
                redraw()
                continue

            # View-mode content scrolling, available on every screen.
            if _is_scroll_key(key_name, key_text):
                is_page = key_name in {"KEY_PGUP", "KEY_PGDOWN"}
                if is_page and _in_list_mode(ctx) and dispatcher.list_navigator is not None:
                    # In a list, PgUp/PgDn move the selection by a screenful of
                    # items (clamped to the ends) while holding the caret at its
                    # current vertical position; the viewport follows it.
                    selected_before = selected_line(view)
                    caret_row = None if selected_before is None else selected_before - scroll_offset
                    step = screen.output_height
                    dispatcher.list_navigator.move(step if key_name == "KEY_PGDOWN" else -step)
                    reflow(_coerce_lines(run_async(dispatcher.render_current())))
                    selected_after = selected_line(view)
                    if selected_after is not None and caret_row is not None:
                        scroll_offset = follow(
                            view, selected_after - caret_row, screen.output_height
                        )
                    redraw()
                    continue
                page = max(screen.output_height - 1, 1)  # keep one line of overlap
                if key_name == "KEY_PGUP":
                    scroll_offset -= page
                elif key_name == "KEY_PGDOWN":
                    scroll_offset += page
                elif key_name == "KEY_CTRL_UP" or key_text == "\x1b[1;5A":
                    scroll_offset -= 1
                else:  # KEY_CTRL_DOWN / "\x1b[1;5B"
                    scroll_offset += 1
                redraw()  # redraw() clamps scroll_offset
                continue

            # View mode: arrow/Enter list navigation, then "/", ":", "?", and hotkeys.
            if _in_list_mode(ctx) and dispatcher.list_navigator is not None:
                selected = dispatcher.list_navigator.handle_key(key_name)
                if selected is not None:
                    set_output(
                        _coerce_lines(run_async(dispatcher.activate_list_selection(selected)))
                    )
                    _sync_session_context(session, ctx)
                    consume_notice()
                    redraw()
                    continue
                if key_name in {"KEY_UP", "KEY_DOWN", "KEY_LEFT", "KEY_RIGHT"} or key_text in {
                    "j",
                    "k",
                }:
                    # Same-screen re-render: preserve scroll and keep the selection visible.
                    reflow(_coerce_lines(run_async(dispatcher.render_current())))
                    scroll_offset = follow(view, scroll_offset, screen.output_height)
                    redraw()
                    continue

            # Non-list screens: plain Up/Down scroll one line.
            if key_name in {"KEY_UP", "KEY_DOWN"}:
                scroll_offset += -1 if key_name == "KEY_UP" else 1
                redraw()
                continue

            if key_text == "/" and dispatcher.supports_search():
                mode = "search"
                input_buffer = ""
                set_output(_coerce_lines(run_async(dispatcher.search(""))))
            elif key_text == ":":
                mode = "command"
                input_buffer = ""
            elif key_text == "?":
                set_output(dispatcher.help_legend())
            elif _is_hotkey(key, key_text):
                hotkey_result = run_async(dispatcher.handle_hotkey(key_text))
                if hotkey_result == "__QUIT__":
                    break
                if hotkey_result is not None:
                    set_output(_coerce_lines(hotkey_result))
                    _sync_session_context(session, ctx)
                    consume_notice()
            redraw()
    finally:
        signal.signal(signal.SIGWINCH, previous_handler)


def _in_list_mode(ctx: ContextManager) -> bool:
    return ctx.current.track in {
        "home",
        "project_select",
        "project",
        "route_select",
        "stage_focus",
        "component_focus",
        "library",
    }


def _is_scroll_key(key_name: str, key_text: str) -> bool:
    """Return ``True`` for a content-scroll key.

    PgUp/PgDown page the view; Ctrl+Up/Ctrl+Down nudge it one line. blessed
    resolves the Ctrl+arrow combos to ``KEY_CTRL_UP``/``KEY_CTRL_DOWN`` on most
    terminals; the raw xterm sequences are matched as a fallback.
    """
    return key_name in {"KEY_PGUP", "KEY_PGDOWN", "KEY_CTRL_UP", "KEY_CTRL_DOWN"} or key_text in {
        "\x1b[1;5A",
        "\x1b[1;5B",
    }


def _is_enter(key_name: str, key_text: str) -> bool:
    return key_name == "KEY_ENTER" or key_text in {"\n", "\r"}


def _is_backspace(key_name: str, key_text: str) -> bool:
    return key_name in {"KEY_BACKSPACE", "KEY_DELETE"} or key_text in {"\b", "\x7f"}


def _is_text_input(key: blessed.keyboard.Keystroke) -> bool:
    text = str(key)
    return bool(text) and not key.is_sequence and text.isprintable()


def _is_hotkey(key: blessed.keyboard.Keystroke, key_text: str) -> bool:
    """Return ``True`` for a Ctrl-<letter> hotkey keystroke.

    Control characters arrive as a single byte below ``0x20`` and are not part
    of an escape sequence (arrow keys are). Ctrl-C/D, Enter, Tab, and Backspace
    are handled earlier, so they never reach this check.
    """
    return not key.is_sequence and len(key_text) == 1 and ord(key_text) < 0x20


def _sync_session_context(session: SessionState, ctx: ContextManager) -> None:
    current = ctx.current
    session.update_context(
        track=current.track,
        project_id=current.project_id,
        process_id=current.process_id,
        stage_id=current.stage_id,
        component_id=current.component_id,
    )


def _coerce_lines(result: list[str] | str) -> list[str]:
    return result if isinstance(result, list) else [result]
