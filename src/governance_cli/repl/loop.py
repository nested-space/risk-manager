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
from .escape_handler import EscapeHandler
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
    escape_handler = EscapeHandler()
    current_output_lines = _coerce_lines(run_async(dispatcher.render_current()))

    def redraw() -> None:
        screen.draw_status_bar()
        screen.draw_output(current_output_lines)
        if dispatcher.prompt_state is not None:
            prompt = f"{dispatcher.prompt_state.current_field.label}: "
            screen.draw_input_line(prompt=prompt, text=input_buffer)
        elif _in_list_mode(ctx) and not input_buffer:
            screen.draw_nav_hint()
        else:
            screen.draw_input_line(text=input_buffer)

    def handle_resize(_signum: int, _frame: FrameType | None) -> None:
        screen.draw_full(current_output_lines, input_buffer)
        if _in_list_mode(ctx) and not input_buffer and dispatcher.prompt_state is None:
            screen.draw_nav_hint()

    previous_handler = signal.getsignal(signal.SIGWINCH)
    signal.signal(signal.SIGWINCH, handle_resize)
    redraw()

    try:  # pylint: disable=too-many-nested-blocks  # blessed inkey loop; escape/prompt/list branches require deep nesting
        while True:
            key = term.inkey()
            if not key:
                continue
            key_name = key.name or str(key)
            key_text = str(key)

            if key_text == "\x04":
                break
            if key_text == "\x03":
                raise KeyboardInterrupt

            if key_name == "KEY_ESCAPE":
                message = escape_handler.handle_esc(dispatcher.prompt_state is not None)
                if message == "NAVIGATE_UP":
                    if dispatcher.prompt_state is not None:
                        current_output_lines = dispatcher.cancel_prompt()
                    else:
                        popped = ctx.pop()
                        if popped is None:
                            current_output_lines = ["Already at home."]
                        else:
                            current_output_lines = _coerce_lines(
                                run_async(dispatcher.render_current())
                            )
                            _sync_session_context(session, ctx)
                    input_buffer = ""
                else:
                    current_output_lines = [message]
                redraw()
                continue

            escape_handler.disarm()

            if dispatcher.prompt_state is not None:
                if _is_enter(key_name, key_text):
                    current_output_lines = _coerce_lines(
                        run_async(dispatcher.advance_prompt(input_buffer))
                    )
                    input_buffer = ""
                elif _is_backspace(key_name, key_text):
                    input_buffer = input_buffer[:-1]
                elif _is_text_input(key):
                    input_buffer += key_text
                redraw()
                continue

            if _in_list_mode(ctx) and not input_buffer and dispatcher.list_navigator is not None:
                selected = dispatcher.list_navigator.handle_key(key_name)
                if selected is not None:
                    current_output_lines = _coerce_lines(
                        run_async(dispatcher.activate_list_selection(selected))
                    )
                    _sync_session_context(session, ctx)
                    redraw()
                    continue
                if key_name in {"KEY_UP", "KEY_DOWN"}:
                    current_output_lines = _coerce_lines(run_async(dispatcher.render_current()))
                    redraw()
                    continue

            if _is_enter(key_name, key_text):
                result = run_async(dispatcher.dispatch(input_buffer))
                if result == "__QUIT__":
                    break
                current_output_lines = _coerce_lines(result)
                input_buffer = ""
                _sync_session_context(session, ctx)
            elif _is_backspace(key_name, key_text):
                input_buffer = input_buffer[:-1]
            elif _is_text_input(key):
                input_buffer += key_text
            redraw()
    finally:
        signal.signal(signal.SIGWINCH, previous_handler)


def _in_list_mode(ctx: ContextManager) -> bool:
    return ctx.current.track in {"home", "route_select"}


def _is_enter(key_name: str, key_text: str) -> bool:
    return key_name == "KEY_ENTER" or key_text in {"\n", "\r"}


def _is_backspace(key_name: str, key_text: str) -> bool:
    return key_name in {"KEY_BACKSPACE", "KEY_DELETE"} or key_text in {"\b", "\x7f"}


def _is_text_input(key: blessed.keyboard.Keystroke) -> bool:
    text = str(key)
    return bool(text) and not key.is_sequence and text.isprintable()


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
