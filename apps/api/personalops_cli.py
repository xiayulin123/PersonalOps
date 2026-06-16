from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import warnings
from datetime import datetime
from typing import Awaitable, Literal, Optional, TypeVar

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

app = typer.Typer(
    name="personalops",
    help="PersonalOps — local-first AI workspace (guided terminal CLI)",
    no_args_is_help=False,
    add_completion=True,
)
console = Console()

WORKSPACE_TYPE_CHOICES: list[tuple[str, str]] = [
    ("study", "Study — lectures, exams, assignments"),
    ("code", "Code — repos, README, CI logs"),
    ("life", "Life — notes, todos, personal docs"),
    ("career", "Career — resume, JD, interview prep"),
]

workspace_app = typer.Typer(help="Create, list, or delete workspaces.")
app.add_typer(workspace_app, name="workspace")

T = TypeVar("T")


class CliQuit(Exception):
    """User chose to leave the guided CLI session."""


class CliBack(Exception):
    """User chose to return to a previous guided step."""

    def __init__(self, to: Literal["workspace", "chat"]) -> None:
        self.to = to
        super().__init__(to)


ChatLoopResult = Literal["exit", "back_chat"]


def _print_step_footer(step: Literal["workspace", "chat", "chat_loop"]) -> None:
    from personalops_cli_nav import (
        step_footer_chat,
        step_footer_chat_loop,
        step_footer_workspace,
    )

    if step == "workspace":
        console.print(step_footer_workspace())
    elif step == "chat":
        console.print(step_footer_chat())
    else:
        console.print()
        console.print(step_footer_chat_loop())


def _handle_submenu_nav(result: Literal["back", "quit"] | None) -> None:
    if result == "quit":
        console.print("[dim]Bye.[/]")
        raise CliQuit()


async def _cleanup_runtime() -> None:
    from database import engine
    import services.indexer as indexer
    from services.cursor_agent.bridge import stop_cursor_bridge

    await stop_cursor_bridge()
    await engine.dispose()
    indexer._client = None
    indexer._openai = None


async def _ensure_runtime() -> None:
    from services.cursor_agent.bridge import start_cursor_bridge

    await start_cursor_bridge()


def run_cli(coro: Awaitable[T]) -> T | None:
    """Run async CLI work and always release DB connections before returning."""

    async def _runner() -> T | None:
        try:
            await _ensure_runtime()
            return await coro
        except CliQuit:
            return None
        finally:
            await _cleanup_runtime()

    return asyncio.run(_runner())


def _suppress_noisy_library_warnings() -> None:
    """Hide LangGraph/LangChain deprecation noise in the terminal CLI."""
    try:
        from langchain_core._api.deprecation import LangChainPendingDeprecationWarning

        warnings.filterwarnings("ignore", category=LangChainPendingDeprecationWarning)
    except ImportError:
        warnings.filterwarnings("ignore", message=".*allowed_objects.*")


def _bootstrap() -> None:
    from db_migrate import run_migrations

    _suppress_noisy_library_warnings()
    run_migrations()


def _startup_banner_extra() -> str:
    from config import settings

    cursor_line = (
        "[green]CURSOR_API_KEY set[/]"
        if settings.cursor_api_key.strip()
        else "[yellow]CURSOR_API_KEY not set[/] — Cursor Agent unavailable"
    )
    default_mode = settings.chat_default_mode.strip().lower()
    if default_mode not in {"langgraph", "cursor_agent"}:
        default_mode = "langgraph"
    from personalops_cli_manage import format_chat_mode_badge

    return (
        f"[dim]default engine:[/] {format_chat_mode_badge(default_mode)} · {cursor_line}"
    )


def _print_agent_meta(result: dict) -> None:
    from personalops_cli_manage import format_chat_mode_badge

    engine = result.get("chat_engine")
    label = result.get("agent_label") or result.get("route")
    parts: list[str] = []
    if engine == "cursor_agent":
        parts.append(format_chat_mode_badge("cursor_agent"))
    elif engine == "langgraph":
        parts.append(format_chat_mode_badge("langgraph"))
    if label:
        parts.append(f"[dim]{label}[/]")
    if parts:
        console.print(" · ".join(parts))


def _format_last_used(value: datetime | None) -> str:
    if value is None:
        return "no messages yet"
    return value.strftime("%b %d, %Y · %I:%M %p")


def _format_workspace_created(value: datetime) -> str:
    return value.strftime("%b %d, %Y")


def _read_menu_choice(prompt: str, min_value: int, max_value: int) -> int:
    while True:
        try:
            raw = console.input(f"[bold cyan]{prompt}[/] ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled.[/]")
            raise CliQuit() from None

        if not raw:
            console.print("[yellow]Please enter a number.[/]")
            continue
        if not raw.isdigit():
            console.print("[yellow]Enter a number from the menu.[/]")
            continue

        choice = int(raw)
        if min_value <= choice <= max_value:
            return choice
        console.print(f"[yellow]Choose between {min_value} and {max_value}.[/]")


def _confirm_delete(message: str) -> bool:
    """Return True to proceed with delete, False to cancel."""
    while True:
        try:
            console.print(f"[bold yellow]{message}[/]")
            raw = console.input(
                "[dim](y/yes or Enter to confirm, q to cancel)[/] "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled.[/]")
            return False

        if raw in {"", "y", "yes"}:
            return True
        if raw in {"q", "quit", "cancel", "n", "no"}:
            return False
        console.print("[yellow]Enter y/yes/Enter to confirm, or q to cancel.[/]")


def _read_delete_target_choice(max_value: int) -> int | None:
    """Pick a workspace index to delete, or None if user cancels."""
    from personalops_cli_nav import parse_nav

    while True:
        try:
            raw = console.input(
                f"[bold cyan]Delete which workspace [1-{max_value}] · "
                f"b back · q quit[/] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled.[/]")
            return None

        nav = parse_nav(raw)
        if nav == "quit":
            console.print("[dim]Bye.[/]")
            raise CliQuit()
        if nav == "back":
            return None
        if not raw.isdigit():
            console.print(
                f"[yellow]Enter a number 1-{max_value}, b back, or q quit.[/]"
            )
            continue

        choice = int(raw)
        if 1 <= choice <= max_value:
            return choice
        console.print(
            f"[yellow]Choose between 1 and {max_value}, b back, or q quit.[/]"
        )


def _read_workspace_step_input(existing_count: int) -> tuple[str, int | None]:
    from personalops_cli_nav import parse_nav, workspace_prompt

    while True:
        try:
            raw = console.input(
                f"[bold cyan]{workspace_prompt(existing_count)}[/] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled.[/]")
            raise CliQuit() from None

        nav = parse_nav(raw, allow_back=False)
        if nav == "quit":
            console.print("[dim]Bye.[/]")
            raise CliQuit()
        lowered = raw.lower()
        if lowered in {"t", "tool", "tools"}:
            if existing_count == 0:
                console.print("[yellow]No workspace to edit yet.[/]")
                continue
            return ("tools", None)
        if lowered in {"m", "memory", "mem"}:
            if existing_count == 0:
                console.print("[yellow]No workspace to edit yet.[/]")
                continue
            return ("memory", None)
        if lowered in {"e", "engine", "mode"}:
            if existing_count == 0:
                console.print("[yellow]No workspace to edit yet.[/]")
                continue
            return ("mode", None)
        if lowered in {"d", "delete"}:
            if existing_count == 0:
                console.print("[yellow]No workspace to delete.[/]")
                continue
            return ("delete", None)
        if lowered in {"0", "n", "new"}:
            return ("new", None)
        if lowered.isdigit():
            choice = int(lowered)
            if 1 <= choice <= existing_count:
                return ("select", choice)
            if choice == 0 and existing_count > 0:
                return ("new", None)
        console.print(
            "[yellow]Enter 0 for new"
            + (f", 1-{existing_count} to select" if existing_count else "")
            + (", t for tools" if existing_count else "")
            + (", m for memory" if existing_count else "")
            + (", e for engine" if existing_count else "")
            + (", d to delete" if existing_count else "")
            + ", or q to quit."
        )


async def _prompt_create_workspace() -> str:
    from database import SessionLocal
    from services.workspace_ops import create_workspace

    console.print()
    console.print(
        Panel.fit(
            "[bold]Create workspace[/]\n"
            "Name + type (study, code, life, career). Uploads folder is created automatically.",
            border_style="green",
        )
    )

    while True:
        try:
            name = console.input(
                "[bold cyan]Name[/] [dim](or b to go back)[/] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled.[/]")
            raise CliQuit() from None
        if name.lower() in {"b", "back"}:
            raise CliBack("workspace")
        if name:
            break
        console.print("[yellow]Name cannot be empty.[/]")

    table = Table(show_header=True, header_style="bold green", expand=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Type", width=10)
    table.add_column("Description", min_width=30)
    for index, (type_key, description) in enumerate(WORKSPACE_TYPE_CHOICES, start=1):
        table.add_row(str(index), type_key, description)
    console.print(table)

    type_choice = _read_menu_choice(f"Type [1-{len(WORKSPACE_TYPE_CHOICES)}]", 1, len(WORKSPACE_TYPE_CHOICES))
    workspace_type = WORKSPACE_TYPE_CHOICES[type_choice - 1][0]

    async with SessionLocal() as db:
        try:
            workspace = await create_workspace(name, workspace_type, db)
        except ValueError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1) from exc

    console.print(
        f"[green]Created workspace[/] {workspace.name} ({workspace.type}) · {workspace.id}"
    )
    return workspace.id


async def _prompt_delete_workspace(workspaces: list) -> None:
    from database import SessionLocal
    from services.workspace_ops import delete_workspace

    console.print()
    console.print(
        Panel.fit(
            "[bold]Delete workspace[/]\n"
            "Removes DB records, uploads, vectors, and stops folder watchers.\n"
            "[dim]Press [bold]q[/] to cancel and return to workspace list.[/]",
            border_style="red",
        )
    )

    table = Table(show_header=True, header_style="bold red", expand=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Name", min_width=18)
    table.add_column("Type", width=10)
    for index, workspace in enumerate(workspaces, start=1):
        table.add_row(str(index), workspace.name, workspace.type)
    console.print(table)

    choice = _read_delete_target_choice(len(workspaces))
    if choice is None:
        console.print("[dim]Delete cancelled — back to workspace list.[/]")
        return

    target = workspaces[choice - 1]

    if not _confirm_delete(
        f"Delete '{target.name}'? This cannot be undone."
    ):
        console.print("[dim]Delete cancelled — back to workspace list.[/]")
        return

    async with SessionLocal() as db:
        try:
            await delete_workspace(target.id, db)
        except ValueError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1) from exc

    console.print(f"[green]Deleted workspace[/] {target.name}")


async def _edit_workspace_tools(workspace_id: str) -> None:
    from personalops_cli_manage import run_tools_interactive

    _handle_submenu_nav(await run_tools_interactive(console, workspace_id))


async def _edit_workspace_chat_mode(workspace_id: str) -> None:
    from personalops_cli_manage import run_chat_mode_interactive

    _handle_submenu_nav(await run_chat_mode_interactive(console, workspace_id))


async def _edit_workspace_memory(workspace_id: str) -> None:
    from personalops_cli_manage import run_memory_interactive

    _handle_submenu_nav(
        await run_memory_interactive(
            console,
            workspace_id,
            read_menu_choice=_read_menu_choice,
            confirm_action=_confirm_delete,
        )
    )


async def _prompt_edit_workspace_tools(workspaces: list) -> None:
    console.print()
    console.print(
        Panel.fit(
            "[bold]Edit workspace tools[/]\n"
            "Pick which workspace to configure (same as [bold]/tool[/] in chat).",
            border_style="cyan",
        )
    )

    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Name", min_width=18)
    table.add_column("Type", width=10)
    for index, workspace in enumerate(workspaces, start=1):
        table.add_row(str(index), workspace.name, workspace.type)
    console.print(table)

    from personalops_cli_nav import parse_nav

    while True:
        try:
            raw = console.input(
                f"[bold cyan]Edit tools for workspace [1-{len(workspaces)}] · "
                f"b back · q quit[/] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("[dim]Cancelled — back to workspace list.[/]")
            return

        nav = parse_nav(raw)
        if nav == "quit":
            console.print("[dim]Bye.[/]")
            raise CliQuit()
        if nav == "back":
            console.print("[dim]Cancelled — back to workspace list.[/]")
            return
        if not raw.isdigit():
            console.print(
                f"[yellow]Enter a number 1-{len(workspaces)}, b back, or q quit.[/]"
            )
            continue

        choice = int(raw)
        if not 1 <= choice <= len(workspaces):
            console.print(
                f"[yellow]Choose between 1 and {len(workspaces)}, b back, or q quit.[/]"
            )
            continue

        await _edit_workspace_tools(workspaces[choice - 1].id)
        return


async def _prompt_edit_workspace_chat_mode(workspaces: list) -> None:
    console.print()
    console.print(
        Panel.fit(
            "[bold]Switch chat engine[/]\n"
            "Pick which workspace to set LangGraph RAG vs Cursor Agent.",
            border_style="magenta",
        )
    )

    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Name", min_width=18)
    table.add_column("Type", width=10)
    table.add_column("Engine", width=10)
    from personalops_cli_manage import format_chat_mode_short

    for index, workspace in enumerate(workspaces, start=1):
        table.add_row(
            str(index),
            workspace.name,
            workspace.type,
            format_chat_mode_short(getattr(workspace, "chat_mode", "langgraph")),
        )
    console.print(table)

    from personalops_cli_nav import parse_nav

    while True:
        try:
            raw = console.input(
                f"[bold cyan]Engine for workspace [1-{len(workspaces)}] · "
                f"b back · q quit[/] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("[dim]Cancelled — back to workspace list.[/]")
            return

        nav = parse_nav(raw)
        if nav == "quit":
            console.print("[dim]Bye.[/]")
            raise CliQuit()
        if nav == "back":
            console.print("[dim]Cancelled — back to workspace list.[/]")
            return
        if not raw.isdigit():
            console.print(
                f"[yellow]Enter a number 1-{len(workspaces)}, b back, or q quit.[/]"
            )
            continue

        choice = int(raw)
        if not 1 <= choice <= len(workspaces):
            console.print(
                f"[yellow]Choose between 1 and {len(workspaces)}, b back, or q quit.[/]"
            )
            continue

        await _edit_workspace_chat_mode(workspaces[choice - 1].id)
        return


async def _prompt_edit_workspace_memory(workspaces: list) -> None:
    console.print()
    console.print(
        Panel.fit(
            "[bold]Edit workspace memory[/]\n"
            "Pick which workspace to configure (same as [bold]/memory[/] in chat).",
            border_style="cyan",
        )
    )

    table = Table(show_header=True, header_style="bold cyan", expand=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Name", min_width=18)
    table.add_column("Type", width=10)
    for index, workspace in enumerate(workspaces, start=1):
        table.add_row(str(index), workspace.name, workspace.type)
    console.print(table)

    from personalops_cli_nav import parse_nav

    while True:
        try:
            raw = console.input(
                f"[bold cyan]Edit memory for workspace [1-{len(workspaces)}] · "
                f"b back · q quit[/] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("[dim]Cancelled — back to workspace list.[/]")
            return

        nav = parse_nav(raw)
        if nav == "quit":
            console.print("[dim]Bye.[/]")
            raise CliQuit()
        if nav == "back":
            console.print("[dim]Cancelled — back to workspace list.[/]")
            return
        if not raw.isdigit():
            console.print(
                f"[yellow]Enter a number 1-{len(workspaces)}, b back, or q quit.[/]"
            )
            continue

        choice = int(raw)
        if not 1 <= choice <= len(workspaces):
            console.print(
                f"[yellow]Choose between 1 and {len(workspaces)}, b back, or q quit.[/]"
            )
            continue

        await _edit_workspace_memory(workspaces[choice - 1].id)
        return


async def _load_workspaces():
    from sqlalchemy import select

    from database import SessionLocal
    from models import Workspace

    async with SessionLocal() as db:
        result = await db.execute(
            select(Workspace).order_by(Workspace.created_at.desc())
        )
        return list(result.scalars().all())


async def _resolve_workspace_id(workspace_id: str | None) -> str:
    if workspace_id:
        from database import SessionLocal
        from models import Workspace

        async with SessionLocal() as db:
            workspace = await db.get(Workspace, workspace_id)
            if workspace is None:
                console.print(f"[red]Workspace not found:[/] {workspace_id}")
                raise typer.Exit(1)
        return workspace_id

    default_id = os.environ.get("PERSONALOPS_WORKSPACE", "").strip()
    if default_id:
        return await _resolve_workspace_id(default_id)

    while True:
        workspaces = await _load_workspaces()

        console.print()
        from personalops_cli_manage import format_chat_mode_short
        from personalops_cli_nav import step_panel_shortcuts_workspace

        console.print(
            Panel.fit(
                "[bold]Step 1 · Choose a workspace[/]\n"
                "Select a workspace or start a new one.\n"
                f"{step_panel_shortcuts_workspace()}\n"
                f"{_startup_banner_extra()}",
                border_style="cyan",
            )
        )

        table = Table(show_header=True, header_style="bold cyan", expand=True)
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column("Name", min_width=18)
        table.add_column("Type", width=10)
        table.add_column("Engine", width=10)
        table.add_column("Created", width=18)

        table.add_row("0", "[bold]+ New workspace[/]", "—", "—", "—")
        for index, workspace in enumerate(workspaces, start=1):
            table.add_row(
                str(index),
                workspace.name,
                workspace.type,
                format_chat_mode_short(getattr(workspace, "chat_mode", "langgraph")),
                _format_workspace_created(workspace.created_at),
            )

        console.print(table)
        _print_step_footer("workspace")
        action, choice = _read_workspace_step_input(len(workspaces))

        if action == "new":
            return await _prompt_create_workspace()
        if action == "delete":
            await _prompt_delete_workspace(workspaces)
            continue
        if action == "tools":
            await _prompt_edit_workspace_tools(workspaces)
            continue
        if action == "memory":
            await _prompt_edit_workspace_memory(workspaces)
            continue
        if action == "mode":
            await _prompt_edit_workspace_chat_mode(workspaces)
            continue
        assert choice is not None
        return workspaces[choice - 1].id


async def pick_workspace_simple(workspace_id: str | None) -> str:
    """Pick a workspace for manage/tools commands (no create/delete loop)."""
    if workspace_id:
        from database import SessionLocal
        from models import Workspace

        async with SessionLocal() as db:
            workspace = await db.get(Workspace, workspace_id)
            if workspace is None:
                console.print(f"[red]Workspace not found:[/] {workspace_id}")
                raise typer.Exit(1)
        return workspace_id

    default_id = os.environ.get("PERSONALOPS_WORKSPACE", "").strip()
    if default_id:
        return await pick_workspace_simple(default_id)

    workspaces = await _load_workspaces()
    if not workspaces:
        console.print(
            "[yellow]No workspaces yet.[/] Run: [bold]personalops workspace create -n \"Name\"[/]"
        )
        raise typer.Exit(1)

    from personalops_cli_manage import format_chat_mode_short

    table = Table(title="Choose workspace", header_style="bold cyan", expand=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Name", min_width=18)
    table.add_column("Type", width=10)
    table.add_column("Engine", width=10)
    for index, workspace in enumerate(workspaces, start=1):
        table.add_row(
            str(index),
            workspace.name,
            workspace.type,
            format_chat_mode_short(getattr(workspace, "chat_mode", "langgraph")),
        )
    console.print(table)

    choice = _read_menu_choice(f"Workspace [1-{len(workspaces)}]", 1, len(workspaces))
    return workspaces[choice - 1].id


_LOCAL_MISS_PATTERNS = re.compile(
    r"cannot find enough evidence|could not find relevant passages|"
    r"cannot find it in the workspace documents|not find enough evidence|"
    r"not enough information in (the )?workspace|"
    r"无法找到足够的证据|找不到足够的证据|无法在工作空间|工作空间文件.*(找不到|无法)|"
    r"没有足够.*(信息|证据).*工作空间|本地.*文件.*(找不到|无法)",
    re.IGNORECASE,
)


def _is_local_file_miss(answer: str, result: dict) -> bool:
    """Detect when file RAG did not find useful workspace evidence."""
    if _LOCAL_MISS_PATTERNS.search(answer):
        return True
    route = str(result.get("route") or "")
    sources = result.get("sources") or []
    web_sources = result.get("web_sources") or []
    if route in {"file_rag", "hybrid"} and not sources and not web_sources:
        return True
    return False


def _read_chat_step_input(conversation_count: int) -> tuple[str, int | None]:
    """Pick a chat, start new, edit tools, go back to workspaces, or quit."""
    from personalops_cli_nav import chat_prompt, parse_nav

    while True:
        try:
            raw = console.input(
                f"[bold cyan]{chat_prompt(conversation_count)}[/] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled.[/]")
            raise CliQuit() from None

        lowered = raw.lower()
        nav = parse_nav(raw)
        if nav == "quit":
            console.print("[dim]Bye.[/]")
            raise CliQuit()
        if nav == "back":
            return ("back", None)
        if lowered in {"t", "tool", "tools"}:
            return ("tools", None)
        if lowered in {"m", "memory", "mem"}:
            return ("memory", None)
        if lowered in {"e", "engine", "mode"}:
            return ("mode", None)
        if lowered in {"0", "n", "new"}:
            return ("new", None)
        if lowered.isdigit():
            choice = int(lowered)
            if 0 <= choice <= conversation_count:
                if choice == 0:
                    return ("new", None)
                return ("select", choice)
        console.print(
            f"[yellow]Enter 0-{conversation_count}, t tools, m memory, e engine, "
            "b back, or q quit.[/]"
        )


def _print_web_search_off_tip(workspace_id: str) -> None:
    """Show how to enable web search when local file search misses."""
    tools_cmd = f"personalops tools --web-search -w {workspace_id}"
    console.print()
    console.print(
        Panel.fit(
            "[yellow]No match in local workspace files[/] (file search / RAG).\n"
            "Web search is [bold]OFF[/] — the agent only used your indexed files.\n\n"
            "To search the web for this workspace:\n"
            "  • In chat: [bold]/tool[/] or [bold]t[/] → toggle [bold]Web search[/] (#2) ON\n"
            f"  • Or run: [bold cyan]{tools_cmd}[/]",
            border_style="yellow",
        )
    )


async def _maybe_suggest_web_search(
    workspace_id: str,
    answer: str,
    result: dict,
) -> None:
    """When local RAG misses and web search is off, show non-blocking enable tips."""
    from personalops_cli_manage import _load_tool_settings

    settings = await _load_tool_settings(workspace_id)
    if settings.get("web_search"):
        return
    if not _is_local_file_miss(answer, result):
        return

    _print_web_search_off_tip(workspace_id)


async def _resolve_conversation_id(
    workspace_id: str,
    conversation_id: str | None,
    *,
    force_new: bool,
) -> str:
    from database import SessionLocal
    from services.conversation import (
        create_conversation,
        get_conversation_for_workspace,
        list_workspace_conversations,
    )

    if force_new:
        async with SessionLocal() as db:
            conversation = await create_conversation(workspace_id, db)
            await db.commit()
            return conversation.id

    if conversation_id:
        async with SessionLocal() as db:
            conversation = await get_conversation_for_workspace(
                conversation_id, workspace_id, db
            )
            if conversation is None:
                console.print(f"[red]Conversation not found:[/] {conversation_id}")
                raise typer.Exit(1)
        return conversation_id

    from models import Workspace

    from personalops_cli_manage import format_chat_mode_badge
    from personalops_cli_nav import step_panel_shortcuts_chat

    async with SessionLocal() as db:
        workspace = await db.get(Workspace, workspace_id)
        workspace_label = workspace.name if workspace else workspace_id
        chat_mode = getattr(workspace, "chat_mode", "langgraph") if workspace else "langgraph"

    while True:
        async with SessionLocal() as db:
            conversations = await list_workspace_conversations(workspace_id, db)
            workspace = await db.get(Workspace, workspace_id)
            if workspace is not None:
                chat_mode = getattr(workspace, "chat_mode", "langgraph")

        console.print()
        console.print(
            Panel.fit(
                f"[bold]Step 2 · Choose a chat[/] · {workspace_label}\n"
                f"Engine: {format_chat_mode_badge(chat_mode)}\n"
                "Pick an existing topic or start a new conversation.\n"
                f"{step_panel_shortcuts_chat()}",
                border_style="cyan",
            )
        )

        table = Table(show_header=True, header_style="bold cyan", expand=True)
        table.add_column("#", style="dim", width=4, justify="right")
        table.add_column("Topic", min_width=24)
        table.add_column("Messages", width=10, justify="right")
        table.add_column("Last used", min_width=22)

        table.add_row(
            "0",
            "[bold]+ New chat[/]",
            "—",
            "—",
        )

        for index, item in enumerate(conversations, start=1):
            table.add_row(
                str(index),
                item["title"] or "Untitled",
                str(item["message_count"]),
                _format_last_used(item.get("last_used_at")),
            )

        console.print(table)
        _print_step_footer("chat")
        action, choice = _read_chat_step_input(len(conversations))

        if action == "tools":
            await _edit_workspace_tools(workspace_id)
            continue
        if action == "memory":
            await _edit_workspace_memory(workspace_id)
            continue
        if action == "mode":
            await _edit_workspace_chat_mode(workspace_id)
            continue
        if action == "back":
            raise CliBack("workspace")
        if action == "new":
            async with SessionLocal() as db:
                conversation = await create_conversation(workspace_id, db)
                await db.commit()
                return conversation.id

        assert choice is not None
        return conversations[choice - 1]["id"]


async def _ask_once(
    workspace_id: str,
    conversation_id: str,
    text: str,
    *,
    verbose: bool,
) -> None:
    import json as json_module
    import time

    from database import SessionLocal
    from models import Message
    from services.agent.runner import run_agent_stream
    from services.conversation import (
        load_recent_history,
        maybe_update_conversation_title,
    )
    from services.metrics import record_chat_metric

    async with SessionLocal() as db:
        history = await load_recent_history(conversation_id, db)

    console.print(Panel(text, title="You", border_style="cyan"))
    result: dict | None = None
    started = time.perf_counter()

    with console.status("[bold cyan]Thinking...[/]", spinner="dots"):
        async for event in run_agent_stream(workspace_id, text, history=history):
            if event["type"] == "step" and verbose:
                step = event["data"]
                console.print(
                    f"[dim]→ {step.get('label', 'step')}: {step.get('detail', '')}[/]"
                )
            elif event["type"] == "done":
                result = event["data"]

    if not result:
        console.print("[red]No response from agent.[/]")
        return

    console.print(
        Panel(
            Markdown(result.get("answer", "")),
            title="Assistant",
            border_style="green",
        )
    )
    _print_agent_meta(result)

    if result.get("sources"):
        console.print("[dim]Sources:[/]")
        for source in result["sources"][:5]:
            console.print(
                f"  • {source.get('filename')} p.{source.get('page', '?')}"
            )

    async with SessionLocal() as db:
        db.add(
            Message(conversation_id=conversation_id, role="user", content=text)
        )
        await maybe_update_conversation_title(conversation_id, text, db)
        db.add(
            Message(
                conversation_id=conversation_id,
                role="assistant",
                content=result["answer"],
                sources_json=json_module.dumps(
                    {
                        "sources": result.get("sources", []),
                        "web_sources": result.get("web_sources", []),
                        "trace": result.get("trace", []),
                        "route": result.get("route"),
                        "chat_engine": result.get("chat_engine"),
                        "agent_label": result.get("agent_label"),
                    }
                ),
            )
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        await record_chat_metric(
            workspace_id,
            result,
            latency_ms=latency_ms,
            db=db,
        )
        await db.commit()

    await _maybe_suggest_web_search(
        workspace_id,
        result.get("answer", ""),
        result,
    )
    _print_step_footer("chat_loop")


async def _chat_loop(
    workspace_id: str,
    conversation_id: str,
    message: str | None,
    *,
    verbose: bool,
) -> ChatLoopResult | None:
    if message:
        await _ask_once(
            workspace_id,
            conversation_id,
            message.strip(),
            verbose=verbose,
        )
        return None

    from personalops_cli_manage import format_chat_mode_badge, get_workspace_chat_mode

    chat_mode = await get_workspace_chat_mode(workspace_id)
    console.print()
    console.print(
        f"[bold]PersonalOps chat ready.[/] Engine: {format_chat_mode_badge(chat_mode)}"
    )
    _print_step_footer("chat_loop")

    while True:
        try:
            line = console.input("[bold cyan]you>[/] ")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Bye.[/]")
            return "exit"

        stripped = line.strip()
        if not stripped:
            continue
        from personalops_cli_nav import parse_nav

        lowered = stripped.lower()
        nav = parse_nav(stripped)
        if nav == "quit":
            console.print("[dim]Bye.[/]")
            return "exit"
        if nav == "back":
            console.print("[dim]Back to chat list.[/]")
            return "back_chat"
        if lowered in {"/tool", "/tools", "t", "tool", "tools"}:
            await _edit_workspace_tools(workspace_id)
            _print_step_footer("chat_loop")
            continue
        if lowered in {"/memory", "/mem", "m", "memory", "mem"}:
            await _edit_workspace_memory(workspace_id)
            _print_step_footer("chat_loop")
            continue
        if lowered in {"/mode", "/engine", "e", "engine", "mode"}:
            await _edit_workspace_chat_mode(workspace_id)
            chat_mode = await get_workspace_chat_mode(workspace_id)
            console.print(
                f"[dim]Engine is now[/] {format_chat_mode_badge(chat_mode)}"
            )
            _print_step_footer("chat_loop")
            continue

        await _ask_once(
            workspace_id,
            conversation_id,
            stripped,
            verbose=verbose,
        )


async def _run_guided_chat(
    message: str | None,
    workspace_id: str | None,
    conversation_id: str | None,
    *,
    new_chat: bool,
    verbose: bool,
) -> None:
    _bootstrap()
    console.print(
        Panel.fit(
            "[bold cyan]PersonalOps[/] · Local-first AI workspace\n"
            f"[dim]data:[/] {os.environ.get('PERSONALOPS_DATA_DIR', '(auto)')}\n"
            f"{_startup_banner_extra()}",
            border_style="bright_blue",
        )
    )

    active_workspace: str | None = workspace_id
    active_conversation: str | None = conversation_id
    one_shot_message = message
    start_new_chat = new_chat

    while True:
        try:
            if active_workspace is None:
                active_workspace = await _resolve_workspace_id(None)

            resolved_conversation = await _resolve_conversation_id(
                active_workspace,
                active_conversation,
                force_new=start_new_chat,
            )
            active_conversation = resolved_conversation
            start_new_chat = False

            loop_result = await _chat_loop(
                active_workspace,
                resolved_conversation,
                one_shot_message,
                verbose=verbose,
            )
            one_shot_message = None

            if loop_result == "back_chat":
                active_conversation = None
                continue
            break
        except CliBack:
            active_workspace = None
            active_conversation = None
            continue


def _print_welcome() -> None:
    _bootstrap()
    console.print(
        Panel.fit(
            "[bold cyan]PersonalOps[/]\n"
            "Guided terminal mode — pick workspace, pick chat, then ask questions.\n"
            f"{_startup_banner_extra()}",
            border_style="bright_blue",
        )
    )


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    """Default: start the guided PersonalOps session."""
    if ctx.invoked_subcommand is None:
        _print_welcome()
        run_cli(
            _run_guided_chat(
                None,
                None,
                None,
                new_chat=False,
                verbose=False,
            )
        )
        sys.exit(0)


@app.command("chat")
def chat_cmd(
    message: Optional[str] = typer.Argument(
        None, help="One-shot question. Omit for interactive chat."
    ),
    workspace: Optional[str] = typer.Option(
        None, "--workspace", "-w", help="Skip workspace menu with this UUID"
    ),
    conversation: Optional[str] = typer.Option(
        None, "--conversation", "-c", help="Skip chat menu with this conversation UUID"
    ),
    new_chat: bool = typer.Option(
        False, "--new", help="Start a new conversation (skip chat menu)"
    ),
    verbose: bool = typer.Option(
        False, "--verbose", "-v", help="Show agent trace steps"
    ),
    guided: bool = typer.Option(
        True,
        "--guided/--no-guided",
        help="Run workspace + chat picker menus (default: on)",
    ),
) -> None:
    """Chat with your workspace agent (guided by default)."""
    if not guided:
        if not workspace:
            console.print("[red]--no-guided requires --workspace / -w[/]")
            raise typer.Exit(1)
        if not conversation and not new_chat:
            console.print("[red]--no-guided requires --conversation / -c or --new[/]")
            raise typer.Exit(1)

    run_cli(
        _run_guided_chat(
            message,
            workspace,
            conversation,
            new_chat=new_chat,
            verbose=verbose,
        )
    )


@workspace_app.command("create")
def workspace_create_cmd(
    name: str = typer.Option(..., "--name", "-n", help="Workspace name"),
    type: str = typer.Option(
        "study",
        "--type",
        "-t",
        help="study | code | life | career",
    ),
) -> None:
    """Create a workspace (same rules as Desktop/API)."""
    _bootstrap()
    run_cli(_create_workspace_cli(name, type))


async def _create_workspace_cli(name: str, workspace_type: str) -> None:
    from database import SessionLocal
    from services.workspace_ops import create_workspace

    async with SessionLocal() as db:
        try:
            workspace = await create_workspace(name, workspace_type, db)
        except ValueError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1) from exc
    console.print(
        f"[green]Created[/] {workspace.name} ({workspace.type}) · {workspace.id}"
    )


@workspace_app.command("delete")
def workspace_delete_cmd(
    workspace: str = typer.Option(..., "--workspace", "-w", help="Workspace UUID"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
) -> None:
    """Delete a workspace and its files, chats, and vectors."""
    _bootstrap()
    run_cli(_delete_workspace_cli(workspace, skip_confirm=yes))


async def _delete_workspace_cli(workspace_id: str, *, skip_confirm: bool) -> None:
    from database import SessionLocal
    from models import Workspace
    from services.workspace_ops import delete_workspace

    async with SessionLocal() as db:
        target = await db.get(Workspace, workspace_id)
        if target is None:
            console.print(f"[red]Workspace not found:[/] {workspace_id}")
            raise typer.Exit(1)
        label = target.name

    if not skip_confirm and not _confirm_delete(
        f"Delete '{label}'? This cannot be undone."
    ):
        console.print("[dim]Delete cancelled.[/]")
        raise typer.Exit(0)

    async with SessionLocal() as db:
        try:
            await delete_workspace(workspace_id, db)
        except ValueError as exc:
            console.print(f"[red]{exc}[/]")
            raise typer.Exit(1) from exc
    console.print(f"[green]Deleted workspace[/] {label}")


@app.command("workspaces")
def workspaces_cmd() -> None:
    """List all workspaces."""
    _bootstrap()
    run_cli(_print_workspaces())


async def _print_workspaces() -> None:
    workspaces = await _load_workspaces()
    if not workspaces:
        console.print("[yellow]No workspaces yet.[/]")
        return

    table = Table(title="Workspaces", header_style="bold cyan", expand=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("ID", style="dim")
    table.add_column("Name")
    table.add_column("Type", width=10)
    table.add_column("Created", width=18)

    for index, workspace in enumerate(workspaces, start=1):
        table.add_row(
            str(index),
            workspace.id,
            workspace.name,
            workspace.type,
            _format_workspace_created(workspace.created_at),
        )

    console.print(table)


@app.command("conversations")
def conversations_cmd(
    workspace: str = typer.Option(..., "--workspace", "-w", help="Workspace UUID"),
) -> None:
    """List chats for a workspace (topic, message count, last used)."""
    _bootstrap()
    run_cli(_print_conversations(workspace))


async def _print_conversations(workspace_id: str) -> None:
    from database import SessionLocal
    from services.conversation import list_workspace_conversations

    async with SessionLocal() as db:
        items = await list_workspace_conversations(workspace_id, db)

    if not items:
        console.print("[yellow]No conversations in this workspace.[/]")
        return

    table = Table(title="Conversations", header_style="bold cyan", expand=True)
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("ID", style="dim")
    table.add_column("Topic", min_width=20)
    table.add_column("Messages", width=10, justify="right")
    table.add_column("Last used", min_width=22)

    for index, item in enumerate(items, start=1):
        table.add_row(
            str(index),
            item["id"],
            item["title"] or "Untitled",
            str(item["message_count"]),
            _format_last_used(item.get("last_used_at")),
        )

    console.print(table)


@app.command("prompt-loadtest")
def prompt_loadtest_cmd(
    workspace: str = typer.Option(
        ..., "--workspace", "-w", help="Workspace UUID"
    ),
    file: str = typer.Option(
        "docs/PersonalOps-Prompt-LoadTest-96.md",
        "--file",
        "-f",
        help="Markdown file with numbered questions (1. ...)",
    ),
    mode: str = typer.Option(
        "seed",
        "--mode",
        "-m",
        help="seed = fast prompt_log only; live = full /chat API (slow, uses LLM)",
    ),
    delay: float = typer.Option(
        0.0,
        "--delay",
        help="Seconds between requests (live mode only)",
    ),
    conversation: Optional[str] = typer.Option(
        None, "--conversation", "-c", help="Optional conversation UUID"
    ),
    archive_after: bool = typer.Option(
        False,
        "--archive",
        help="Run GCS/S3 archive for today after seeding",
    ),
    archive_force: bool = typer.Option(
        True,
        "--archive-force/--no-archive-force",
        help="Force archive upload even if object exists",
    ),
    api_base: str = typer.Option(
        "http://127.0.0.1:8000",
        "--api",
        help="API base URL (live mode only)",
    ),
) -> None:
    """Send load-test questions to bump prompt_log (for P0/P3 archive testing)."""
    if mode not in {"seed", "live"}:
        console.print("[red]--mode must be 'seed' or 'live'[/]")
        raise typer.Exit(1)

    _bootstrap()

    async def _run() -> dict:
        from datetime import date as date_type

        from services.personalization.archive_job import archive_single_workspace
        from services.personalization.prompt_loadtest import (
            live_chat_prompts,
            parse_questions_from_markdown,
            resolve_question_file,
            seed_prompt_logs,
        )

        path = resolve_question_file(file)
        questions = parse_questions_from_markdown(path)
        console.print(
            f"[dim]Loaded {len(questions)} questions from {path}[/]"
        )

        if mode == "seed":
            result = await seed_prompt_logs(
                workspace,
                questions,
                conversation_id=conversation,
            )
        else:
            result = await live_chat_prompts(
                workspace,
                questions,
                api_base=api_base,
                conversation_id=conversation,
                delay_sec=delay,
            )

        if archive_after:
            today = date_type.today()
            archive_out = await archive_single_workspace(
                workspace,
                period_start=today,
                force=archive_force,
            )
            result["archive"] = archive_out

        return result

    try:
        result = run_cli(_run())
    except Exception as exc:
        console.print(f"[red]prompt-loadtest failed:[/] {exc}")
        raise typer.Exit(1) from exc

    stats = result.get("stats") or {}
    console.print(
        f"[green]Done[/] mode={result.get('mode')} "
        f"today_count={stats.get('today_count', '?')}/"
        f"{stats.get('daily_threshold', '?')}"
    )
    if result.get("written") is not None:
        console.print(f"  prompt_log written: {result['written']}")
    if result.get("sent") is not None:
        console.print(f"  live chat sent: {result['sent']}")
        if result.get("errors"):
            console.print(f"  [yellow]errors: {len(result['errors'])}[/]")
    if result.get("archive"):
        arch = result["archive"]
        console.print(
            f"  archive: {arch.get('status')} "
            f"records={arch.get('record_count', 0)} "
            f"uri={arch.get('uri', '')}"
        )
    console.print_json(json.dumps(result, indent=2, default=str))


@app.command("archive")
def archive_cmd(
    workspace: Optional[str] = typer.Option(
        None, "--workspace", "-w", help="Workspace UUID (omit for all workspaces)"
    ),
    period_start: Optional[str] = typer.Option(
        None,
        "--date",
        "-d",
        help="Day to archive (YYYY-MM-DD). Default: yesterday UTC",
    ),
    force: bool = typer.Option(
        False, "--force", "-f", help="Re-upload even if object already exists"
    ),
) -> None:
    """Upload encrypted redacted prompt logs to GCS/S3 (P3)."""
    from datetime import date as date_type

    archive_day: date_type | None = None
    if period_start:
        try:
            archive_day = date_type.fromisoformat(period_start)
        except ValueError:
            console.print("[red]--date must be YYYY-MM-DD[/]")
            raise typer.Exit(1)

    _bootstrap()

    async def _run() -> list[dict] | dict:
        from services.personalization.archive_job import (
            archive_single_workspace,
            run_archive_pass,
        )

        if workspace:
            return await archive_single_workspace(
                workspace, period_start=archive_day, force=force
            )
        return await run_archive_pass(period_start=archive_day, force=force)

    try:
        result = run_cli(_run())
    except Exception as exc:
        console.print(f"[red]Archive failed:[/] {exc}")
        raise typer.Exit(1) from exc

    if isinstance(result, dict):
        console.print_json(json.dumps(result, indent=2))
        return

    for item in result:
        ws = item.get("workspace_id", "?")
        status = item.get("status")
        count = item.get("record_count", 0)
        console.print(f"[cyan]{ws}[/] -> {status} (records={count})")


@app.command("distill")
def distill_cmd(
    workspace: Optional[str] = typer.Option(
        None, "--workspace", "-w", help="Workspace UUID (omit for all workspaces)"
    ),
    period: str = typer.Option("day", "--period", "-p", help="day or week"),
    force: bool = typer.Option(
        False, "--force", "-f", help="Run even if below prompt threshold"
    ),
) -> None:
    """Summarize prompt history into auto-learned memory/rules/habits (P1)."""
    if period not in {"day", "week"}:
        console.print("[red]--period must be 'day' or 'week'[/]")
        raise typer.Exit(1)

    _bootstrap()

    async def _run() -> list[dict] | dict:
        from services.personalization.distillation import (
            distill_single_workspace,
            run_distillation_pass,
        )

        if workspace:
            return await distill_single_workspace(workspace, period, force=force)
        return await run_distillation_pass(period, force=force)

    try:
        result = run_cli(_run())
    except Exception as exc:
        console.print(f"[red]Distill failed:[/] {exc}")
        raise typer.Exit(1) from exc

    if isinstance(result, dict):
        console.print_json(json.dumps(result, indent=2))
        return

    for item in result:
        ws = item.get("workspace_id", "?")
        status = item.get("status")
        written = item.get("written", 0)
        console.print(f"[cyan]{ws}[/] -> {status} (written={written})")


@app.command("health")
def health_cmd() -> None:
    """Check OpenAI, Chroma, Cursor Agent, and tool availability."""
    _bootstrap()
    from services.health_check import build_health_payload

    payload = build_health_payload()
    console.print_json(json.dumps(payload, indent=2))


@app.command("serve")
def serve_cmd(
    host: str = typer.Option("127.0.0.1", "--host"),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload"),
) -> None:
    """Start FastAPI for the Desktop app."""
    import uvicorn

    _bootstrap()
    uvicorn.run("main:app", host=host, port=port, reload=reload)


admin_app = typer.Typer(help="Cloud admin bootstrap (Plan B B1/B2).")
app.add_typer(admin_app, name="admin")


@admin_app.command("bootstrap")
def admin_bootstrap_cmd(
    email: Optional[str] = typer.Option(None, "--email", help="Admin email (or ADMIN_EMAIL)"),
    password: Optional[str] = typer.Option(
        None, "--password", help="Admin password (or ADMIN_PASSWORD)"
    ),
    no_gcs: bool = typer.Option(False, "--no-gcs", help="Skip GCS credentials backup"),
) -> None:
    """Create admin user, claim legacy workspaces, import .env API keys to user storage."""
    from database import SessionLocal
    from services.auth.bootstrap_admin import bootstrap_admin

    _bootstrap()

    async def _run() -> None:
        async with SessionLocal() as db:
            result = await bootstrap_admin(
                db,
                email=email,
                password=password,
                sync_gcs=not no_gcs,
            )
        console.print("[green]Admin bootstrap complete[/green]")
        console.print(f"  email: {result.email}")
        console.print(f"  user_id: {result.user_id}")
        console.print(f"  created_user: {result.created_user}")
        console.print(f"  workspaces_claimed: {result.workspaces_claimed}")
        console.print(f"  credentials_imported: {', '.join(result.credentials_imported) or '(none)'}")
        if result.gcs_credentials_uri:
            console.print(f"  gcs_credentials: {result.gcs_credentials_uri}")
        if result.gcs_error:
            console.print(f"[yellow]  gcs_warning: {result.gcs_error}[/yellow]")

    run_cli(_run())


@admin_app.command("seed-demo")
def admin_seed_demo_cmd(
    force: bool = typer.Option(False, "--force", help="Delete and rebuild demo data"),
    skip_index: bool = typer.Option(False, "--skip-index", help="Skip Chroma indexing"),
    with_gcs: bool = typer.Option(
        False,
        "--with-gcs",
        help="Upload demo files and conversations to GCS (requires cloud + credentials)",
    ),
    publish_bundle: bool = typer.Option(
        False,
        "--publish-bundle",
        help="Copy demo user GCS prefix to system/demo-bundle",
    ),
) -> None:
    """Create the read-only demo account with sample workspaces and data."""
    from database import SessionLocal
    from services.demo.bootstrap_demo import bootstrap_demo

    _bootstrap()

    async def _run() -> None:
        async with SessionLocal() as db:
            result = await bootstrap_demo(
                db,
                force=force,
                index_files=not skip_index,
                use_gcs=with_gcs,
                publish_gcs_bundle=publish_bundle,
            )
        console.print("[green]Demo seed complete[/green]")
        console.print(f"  email: {result.email}")
        console.print(f"  password: (see DEMO_PASSWORD in .env)")
        console.print(f"  user_id: {result.user_id}")
        console.print(f"  workspaces: {result.workspaces}")
        console.print(f"  files: {result.files}")
        console.print(f"  conversations: {result.conversations}")
        console.print(f"  indexed_files: {result.indexed_files}")
        if result.gcs_bundle_prefix:
            console.print(f"  gcs_bundle: {result.gcs_bundle_prefix}")
        for warning in result.warnings:
            console.print(f"[yellow]  warning: {warning}[/yellow]")

    run_cli(_run())


@admin_app.command("export-conversations")
def admin_export_conversations_cmd(
    email: Optional[str] = typer.Option(None, "--email", help="User email (default ADMIN_EMAIL)"),
) -> None:
    """Backfill GCS conversation exports for all workspaces owned by a user."""
    from sqlalchemy import select

    from config import settings
    from database import SessionLocal
    from models import Conversation, User, Workspace
    from services.storage.conversation_export import export_conversation_to_gcs

    _bootstrap()
    target_email = (email or settings.admin_email).strip().lower()
    if not target_email:
        raise typer.BadParameter("Provide --email or set ADMIN_EMAIL in .env")

    async def _run() -> None:
        async with SessionLocal() as db:
            user = await db.scalar(select(User).where(User.email == target_email))
            if user is None:
                console.print(f"[red]User not found: {target_email}[/red]")
                return

            workspaces = await db.execute(
                select(Workspace).where(Workspace.user_id == user.id)
            )
            exported = 0
            skipped = 0
            for workspace in workspaces.scalars().all():
                conversations = await db.execute(
                    select(Conversation).where(Conversation.workspace_id == workspace.id)
                )
                for conversation in conversations.scalars().all():
                    uri = await export_conversation_to_gcs(
                        user_id=user.id,
                        workspace_id=workspace.id,
                        conversation_id=conversation.id,
                    )
                    if uri:
                        exported += 1
                    else:
                        skipped += 1

        console.print("[green]Conversation export backfill complete[/green]")
        console.print(f"  user: {target_email}")
        console.print(f"  exported: {exported}")
        console.print(f"  skipped: {skipped}")

    run_cli(_run())


@admin_app.command("restore-conversations")
def admin_restore_conversations_cmd(
    email: Optional[str] = typer.Option(None, "--email", help="User email (default ADMIN_EMAIL)"),
    workspace_id: Optional[str] = typer.Option(
        None, "--workspace-id", help="Limit restore to one workspace"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Report what would be restored without writing to DB"
    ),
) -> None:
    """Restore conversations from GCS JSONL when DB rows are missing or empty."""
    from sqlalchemy import select

    from config import settings
    from database import SessionLocal
    from models import User
    from services.storage.conversation_export import restore_user_conversations_from_gcs

    _bootstrap()
    target_email = (email or settings.admin_email).strip().lower()
    if not target_email:
        raise typer.BadParameter("Provide --email or set ADMIN_EMAIL in .env")

    async def _run() -> None:
        async with SessionLocal() as db:
            user = await db.scalar(select(User).where(User.email == target_email))
            if user is None:
                console.print(f"[red]User not found: {target_email}[/red]")
                return
            user_id = user.id

        counts = await restore_user_conversations_from_gcs(
            user_id=user_id,
            workspace_id=workspace_id,
            dry_run=dry_run,
        )

        label = "dry-run complete" if dry_run else "Conversation restore complete"
        console.print(f"[green]{label}[/green]")
        console.print(f"  user: {target_email}")
        if workspace_id:
            console.print(f"  workspace_id: {workspace_id}")
        console.print(f"  restored: {counts['restored']}")
        console.print(f"  skipped: {counts['skipped']}")
        console.print(f"  failed: {counts['failed']}")

    run_cli(_run())


from personalops_cli_manage import register_manage_commands

register_manage_commands(
    app,
    console=console,
    run_cli=run_cli,
    bootstrap=_bootstrap,
    pick_workspace=pick_workspace_simple,
    read_menu_choice=_read_menu_choice,
    confirm_action=_confirm_delete,
    cli_quit=CliQuit,
)


if __name__ == "__main__":
    app()
