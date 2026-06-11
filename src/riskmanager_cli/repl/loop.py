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
    notice = ""
    mode = "view"  # "view" (hotkeys) | "search" ("/" filter) | "command" (":" line)
    current_output_lines = _coerce_lines(run_async(dispatcher.render_current()))

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

    def redraw() -> None:
        screen.draw_status_bar()
        screen.draw_output(current_output_lines)
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
            screen.draw_nav_hint(view_hint(), notice=notice)
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
        nonlocal input_buffer, current_output_lines, notice, mode
        cancelled = False
        if dispatcher.picker_state is not None:
            current_output_lines = _coerce_lines(run_async(dispatcher.cancel_picker()))
            cancelled = True
        elif dispatcher.prompt_state is not None:
            current_output_lines = _coerce_lines(run_async(dispatcher.cancel_prompt()))
            cancelled = True
        elif mode in {"command", "search"}:
            current_output_lines = _coerce_lines(run_async(dispatcher.render_current()))
        elif ctx.pop() is None:
            return quit_at_home
        else:
            current_output_lines = _coerce_lines(run_async(dispatcher.render_current()))
            _sync_session_context(session, ctx)
        reset_to_view()
        if cancelled:
            consume_notice()
        return False

    def handle_resize(_signum: int, _frame: FrameType | None) -> None:
        screen.clear_screen()
        redraw()

    previous_handler = signal.getsignal(signal.SIGWINCH)
    signal.signal(signal.SIGWINCH, handle_resize)
    redraw()

    try:  # pylint: disable=too-many-nested-blocks  # blessed inkey loop; prompt/picker/list branches require deep nesting
        while True:
            try:
                key = term.inkey()
            except KeyboardInterrupt:
                if handle_back(quit_at_home=True):
                    break
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
                    break
                redraw()
                continue
            if key_name == "KEY_ESCAPE":
                handle_back(quit_at_home=False)
                redraw()
                continue

            if dispatcher.prompt_state is not None:
                if dispatcher.prompt_state.is_select_field:
                    if _is_enter(key_name, key_text):
                        current_output_lines = _coerce_lines(
                            run_async(dispatcher.submit_prompt_selection())
                        )
                        input_buffer = ""
                        consume_notice()
                    elif key_name in {"KEY_UP", "KEY_DOWN"}:
                        direction = "up" if key_name == "KEY_UP" else "down"
                        current_output_lines = dispatcher.prompt_move(direction)
                    redraw()
                    continue
                if _is_enter(key_name, key_text):
                    current_output_lines = _coerce_lines(
                        run_async(dispatcher.advance_prompt(input_buffer))
                    )
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
                    current_output_lines = _coerce_lines(run_async(dispatcher.picker_select()))
                    input_buffer = ""
                    consume_notice()
                elif key_name in {"KEY_UP", "KEY_DOWN"}:
                    direction = "up" if key_name == "KEY_UP" else "down"
                    current_output_lines = dispatcher.picker_move(direction)
                elif _is_backspace(key_name, key_text):
                    input_buffer = input_buffer[:-1]
                    current_output_lines = dispatcher.update_picker_query(input_buffer)
                elif _is_text_input(key):
                    input_buffer += key_text
                    current_output_lines = dispatcher.update_picker_query(input_buffer)
                redraw()
                continue

            if mode == "command":
                if _is_enter(key_name, key_text):
                    result = run_async(dispatcher.dispatch(input_buffer))
                    if result == "__QUIT__":
                        break
                    current_output_lines = _coerce_lines(result)
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
                    current_output_lines = _coerce_lines(run_async(dispatcher.search(input_buffer)))
                elif _is_text_input(key):
                    input_buffer += key_text
                    current_output_lines = _coerce_lines(run_async(dispatcher.search(input_buffer)))
                redraw()
                continue

            # View mode: arrow/Enter list navigation, then "/", ":", "?", and hotkeys.
            if _in_list_mode(ctx) and dispatcher.list_navigator is not None:
                selected = dispatcher.list_navigator.handle_key(key_name)
                if selected is not None:
                    current_output_lines = _coerce_lines(
                        run_async(dispatcher.activate_list_selection(selected))
                    )
                    _sync_session_context(session, ctx)
                    consume_notice()
                    redraw()
                    continue
                if key_name in {"KEY_UP", "KEY_DOWN"} or key_text in {"j", "k"}:
                    current_output_lines = _coerce_lines(run_async(dispatcher.render_current()))
                    redraw()
                    continue

            if key_text == "/" and dispatcher.supports_search():
                mode = "search"
                input_buffer = ""
                current_output_lines = _coerce_lines(run_async(dispatcher.search("")))
            elif key_text == ":":
                mode = "command"
                input_buffer = ""
            elif key_text == "?":
                current_output_lines = dispatcher.help_legend()
            elif _is_hotkey(key, key_text):
                hotkey_result = run_async(dispatcher.handle_hotkey(key_text))
                if hotkey_result == "__QUIT__":
                    break
                if hotkey_result is not None:
                    current_output_lines = _coerce_lines(hotkey_result)
                    _sync_session_context(session, ctx)
                    consume_notice()
            redraw()
    finally:
        signal.signal(signal.SIGWINCH, previous_handler)


def _in_list_mode(ctx: ContextManager) -> bool:
    return ctx.current.track in {"home", "project", "route_select", "stage_focus"}


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
