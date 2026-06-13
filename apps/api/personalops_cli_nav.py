"""Shared guided-CLI navigation keys and prompt fragments."""

from __future__ import annotations

from typing import Literal

NavResult = Literal["back", "quit"]

QUIT_KEYS = frozenset({"q", "quit", "/quit", "/exit", "exit"})
BACK_KEYS = frozenset({"b", "back", "/back"})


def normalize_input(raw: str) -> str:
    return raw.strip().lower()


def parse_nav(raw: str, *, allow_back: bool = True) -> NavResult | None:
    """Return back/quit if raw is a navigation command, else None."""
    lowered = normalize_input(raw)
    if lowered in QUIT_KEYS:
        return "quit"
    if allow_back and lowered in BACK_KEYS:
        return "back"
    return None


def workspace_prompt(count: int) -> str:
    if count == 0:
        return "Workspace [0] new · q quit"
    return (
        f"Workspace [0-{count}] · t tools · m memory · e engine · "
        f"d delete · q quit"
    )


def chat_prompt(count: int) -> str:
    return (
        f"Chat [0-{count}] · t tools · m memory · e engine · "
        f"b back · q quit"
    )


def submenu_prompt(action: str, *, extra: str = "") -> str:
    """Prompt for tools/memory/engine submenus."""
    base = f"{action} · b back · q quit"
    return f"{base} · {extra}" if extra else base


def step_panel_shortcuts_workspace() -> str:
    return (
        "[dim][t] tools · [m] memory · [e] engine · [d] delete · [q] quit[/]"
    )


def step_panel_shortcuts_chat() -> str:
    return "[dim][t] tools · [m] memory · [e] engine · [b] back · [q] quit[/]"


def step_footer_workspace() -> str:
    return (
        "[dim]Pick a number · [bold]0[/] new · [bold]t[/] tools · [bold]m[/] memory · "
        "[bold]e[/] engine · [bold]d[/] delete · [bold]q[/] quit[/]"
    )


def step_footer_chat() -> str:
    return (
        "[dim]Pick a number · [bold]0[/] new chat · [bold]t[/] tools · [bold]m[/] memory · "
        "[bold]e[/] engine · [bold]b[/] back · [bold]q[/] quit[/]"
    )


def step_footer_chat_loop() -> str:
    return (
        "[dim]Type a question · [bold]t[/]/[bold]/tool[/] tools · "
        "[bold]m[/]/[bold]/memory[/] memory · [bold]e[/]/[bold]/mode[/] engine · "
        "[bold]b[/]/[bold]/back[/] back · [bold]q[/]/[bold]/quit[/] quit[/]"
    )
