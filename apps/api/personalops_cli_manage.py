"""Workspace management commands for the PersonalOps CLI (Desktop parity)."""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from personalops_cli_nav import NavResult, parse_nav, submenu_prompt

from personalops_cli_nav import NavResult, parse_nav, submenu_prompt

TOOL_KEYS: list[tuple[str, str]] = [
    ("file_search", "File search (RAG)"),
    ("web_search", "Web search"),
    ("memory", "Memory injection"),
    ("github_read", "GitHub read"),
    ("code_search", "Code search (ripgrep)"),
]

CODE_ONLY_TOOL_KEYS = frozenset({"github_read", "code_search"})

CHAT_MODE_CHOICES: list[tuple[str, str, str]] = [
    (
        "langgraph",
        "LangGraph RAG",
        "Chroma vector search + OpenAI generate/verify",
    ),
    (
        "cursor_agent",
        "Cursor Agent",
        "Reads uploads/ directly; memory syncs to .cursor/rules",
    ),
]


def normalize_chat_mode(mode: str | None) -> str:
    normalized = (mode or "langgraph").strip().lower()
    return normalized if normalized in {"langgraph", "cursor_agent"} else "langgraph"


def format_chat_mode_badge(mode: str | None) -> str:
    if normalize_chat_mode(mode) == "cursor_agent":
        return "[bold magenta]Cursor Agent[/]"
    return "[bold cyan]LangGraph RAG[/]"


def format_chat_mode_short(mode: str | None) -> str:
    if normalize_chat_mode(mode) == "cursor_agent":
        return "cursor"
    return "langgraph"


async def get_workspace_chat_mode(workspace_id: str) -> str:
    workspace = await _get_workspace(workspace_id)
    return normalize_chat_mode(getattr(workspace, "chat_mode", "langgraph"))


async def set_workspace_chat_mode(workspace_id: str, mode: str) -> str:
    from database import SessionLocal
    from models import Workspace
    from services.cursor_agent.memory_sync import sync_cursor_memory_file

    normalized = normalize_chat_mode(mode)
    async with SessionLocal() as db:
        row = await db.get(Workspace, workspace_id)
        if row is None:
            raise ValueError("Workspace not found")
        row.chat_mode = normalized
        await db.commit()
        if normalized == "cursor_agent":
            await sync_cursor_memory_file(workspace_id, db)
    return normalized


async def run_chat_mode_interactive(
    console: Console, workspace_id: str
) -> NavResult | None:
    """Pick LangGraph vs Cursor Agent (Desktop Tools tab parity)."""
    from config import settings

    workspace = await _get_workspace(workspace_id)
    current = normalize_chat_mode(getattr(workspace, "chat_mode", "langgraph"))
    cursor_ok = bool(settings.cursor_api_key.strip())

    while True:
        console.print()
        console.print(
            Panel.fit(
                f"[bold]Chat engine · {workspace.name}[/]\n"
                f"Current: {format_chat_mode_badge(current)}\n"
                f"[dim]CURSOR_API_KEY: {'set' if cursor_ok else 'missing in .env'}[/]\n\n"
                "[bold]1[/] LangGraph RAG\n"
                "[bold]2[/] Cursor Agent\n"
                "[dim][b] back · [q] quit[/]",
                border_style="magenta" if current == "cursor_agent" else "cyan",
            )
        )
        try:
            raw = console.input(
                f"[bold cyan]{submenu_prompt('Choose [1-2]')}[/] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            return "back"
        nav = parse_nav(raw)
        if nav is not None:
            return nav
        lowered = raw.lower()
        if lowered == "1":
            next_mode = "langgraph"
        elif lowered == "2":
            next_mode = "cursor_agent"
        else:
            console.print("[yellow]Enter 1, 2, b back, or q quit.[/]")
            continue

        if next_mode == current:
            console.print("[dim]Already using this engine.[/]")
            return "back"

        if next_mode == "cursor_agent" and not cursor_ok:
            console.print(
                "[yellow]CURSOR_API_KEY is not set — Cursor Agent will not run until you add it to .env.[/]"
            )

        current = await set_workspace_chat_mode(workspace_id, next_mode)
        console.print(
            f"[green]Chat engine set to[/] {format_chat_mode_badge(current)}"
        )
        if current == "cursor_agent":
            console.print(
                "[dim]Memory synced to uploads/.cursor/rules/personalops-memory.mdc[/]"
            )
        return "back"


def tools_for_workspace_type(workspace_type: str) -> list[tuple[str, str]]:
    """Match Desktop Tools tab: GitHub/code tools only on code workspaces."""
    if workspace_type == "code":
        return TOOL_KEYS
    return [item for item in TOOL_KEYS if item[0] not in CODE_ONLY_TOOL_KEYS]


async def _print_github_read_status(
    console: Console,
    workspace_id: str,
    *,
    github_read_on: bool,
) -> None:
    if not github_read_on:
        return

    from sqlalchemy import select

    from database import SessionLocal
    from models import File, GitHubLink

    async with SessionLocal() as db:
        link = (
            await db.execute(
                select(GitHubLink).where(GitHubLink.workspace_id == workspace_id)
            )
        ).scalar_one_or_none()
        synced = (
            await db.execute(
                select(File).where(
                    File.workspace_id == workspace_id,
                    File.filename.like("_github_%"),
                    File.chunk_count > 0,
                )
            )
        ).scalars().all()

    if link is None:
        console.print(
            "[yellow]GitHub read is ON but no repo is linked — it cannot fetch GitHub yet.[/]"
        )
        console.print(
            "[dim]Link a repo: personalops manage -w "
            f"{workspace_id}[/] → GitHub link, then sync README & issues."
        )
        return

    repo_label = link.repo_full_name or link.repo_url
    if not synced:
        console.print(
            f"[yellow]GitHub read is ON · repo linked ({repo_label}) but not synced yet.[/]"
        )
        console.print(
            "[dim]Run sync in personalops manage → GitHub link → sync.[/]"
        )
        return

    names = ", ".join(item.filename for item in synced)
    console.print(
        f"[dim]GitHub synced: {repo_label} · indexed {names}[/]"
    )


async def _get_workspace(workspace_id: str):
    from database import SessionLocal
    from models import Workspace

    async with SessionLocal() as db:
        workspace = await db.get(Workspace, workspace_id)
        if workspace is None:
            raise ValueError("Workspace not found")
        return workspace


async def _load_tool_settings(workspace_id: str) -> dict[str, bool]:
    from routers.tools import _parse_tool_settings

    workspace = await _get_workspace(workspace_id)
    return _parse_tool_settings(workspace.tool_settings_json)


async def _save_tool_settings(workspace_id: str, settings: dict[str, bool]) -> dict[str, bool]:
    from database import SessionLocal
    from models import Workspace

    async with SessionLocal() as db:
        workspace = await db.get(Workspace, workspace_id)
        if workspace is None:
            raise ValueError("Workspace not found")
        workspace.tool_settings_json = json.dumps(settings)
        await db.commit()
    return settings


async def _toggle_tool(workspace_id: str, key: str, enabled: bool) -> dict[str, bool]:
    settings = await _load_tool_settings(workspace_id)
    settings[key] = enabled
    return await _save_tool_settings(workspace_id, settings)


def _tool_onoff(value: bool) -> str:
    return "[green]ON[/]" if value else "[dim]OFF[/]"


async def print_workspace_tools(console: Console, workspace_id: str) -> None:
    settings = await _load_tool_settings(workspace_id)
    workspace = await _get_workspace(workspace_id)
    visible_tools = tools_for_workspace_type(workspace.type)
    table = Table(title=f"Tools · {workspace.name}", header_style="bold cyan")
    table.add_column("Tool", min_width=22)
    table.add_column("Status", width=8)
    for key, label in visible_tools:
        table.add_row(label, _tool_onoff(settings.get(key, False)))
    console.print(table)
    if workspace.type == "code":
        await _print_github_read_status(
            console, workspace_id, github_read_on=settings.get("github_read", False)
        )


async def run_tools_interactive(
    console: Console, workspace_id: str
) -> NavResult | None:
    """Interactive tool toggles (Desktop Tools tab parity)."""
    while True:
        settings = await _load_tool_settings(workspace_id)
        workspace = await _get_workspace(workspace_id)
        chat_mode = normalize_chat_mode(getattr(workspace, "chat_mode", "langgraph"))
        visible_tools = tools_for_workspace_type(workspace.type)
        tool_count = len(visible_tools)
        console.print()
        subtitle = (
            f"Engine: {format_chat_mode_badge(chat_mode)}\n"
            f"Enter a number to toggle · [bold]e[/] engine · [bold]b[/] back · [bold]q[/] quit"
        )
        if workspace.type == "code":
            subtitle += (
                "\n[dim]GitHub read uses synced _github_* files — link + sync a repo first.[/]"
            )
        if chat_mode == "cursor_agent":
            subtitle += (
                "\n[dim]Cursor mode reads uploads/ directly — file_search is for LangGraph only.[/]"
            )
        console.print(
            Panel.fit(
                f"[bold]Tools · {workspace.name}[/] ({workspace.type})\n{subtitle}",
                border_style="cyan",
            )
        )
        table = Table(show_header=True, header_style="bold cyan")
        table.add_column("#", width=4, justify="right")
        table.add_column("Tool", min_width=22)
        table.add_column("Status", width=8)
        for index, (key, label) in enumerate(visible_tools, start=1):
            table.add_row(str(index), label, _tool_onoff(settings.get(key, False)))
        console.print(table)
        if workspace.type == "code":
            await _print_github_read_status(
                console, workspace_id, github_read_on=settings.get("github_read", False)
            )
        try:
            raw = console.input(
                f"[bold cyan]{submenu_prompt(f'Toggle [1-{tool_count}]', extra='e engine')}[/] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            return "back"
        nav = parse_nav(raw)
        if nav is not None:
            return nav
        lowered = raw.lower()
        if lowered in {"e", "engine", "mode"}:
            engine_nav = await run_chat_mode_interactive(console, workspace_id)
            if engine_nav == "quit":
                return "quit"
            continue
        if not lowered.isdigit() or not 1 <= int(lowered) <= tool_count:
            console.print(
                f"[yellow]Enter 1-{tool_count}, e engine, b back, or q quit.[/]"
            )
            continue
        key = visible_tools[int(lowered) - 1][0]
        next_enabled = not settings.get(key, False)
        await _toggle_tool(workspace_id, key, next_enabled)
        console.print(f"[green]Updated[/] {key}")
        if key == "github_read" and next_enabled:
            console.print(
                "[dim]Tip: ON alone does not pull GitHub — link a repo and sync first.[/]"
            )


MEMORY_EXAMPLES_BY_TYPE: dict[str, list[tuple[str, str]]] = {
    "study": [
        ("language_preference", "Prefer Chinese explanations with bilingual technical terms."),
        ("course", "ECE457A real-time systems"),
        ("explanation_style", "Step-by-step with examples."),
    ],
    "code": [
        ("tech_stack", "AWS, Kubernetes, Terraform, React, FastAPI"),
        ("explanation_style", "Production-style, concise debugging steps."),
    ],
    "life": [
        ("timezone", "America/Toronto (EST/EDT)"),
        ("priority_style", "Prefer urgent deadlines first, then health errands."),
        ("document_categories", "Bills, medical, travel, personal goals"),
    ],
    "career": [
        ("target_role", "Software engineering intern / new grad"),
        ("resume_tone", "Concise bullets with measurable impact."),
        ("highlight_skills", "Python, React, AWS, distributed systems"),
    ],
}


def _print_memory_add_tips(console: Console, workspace_type: str) -> None:
    examples = MEMORY_EXAMPLES_BY_TYPE.get(
        workspace_type, MEMORY_EXAMPLES_BY_TYPE["study"]
    )
    example_lines = "\n".join(
        f"  [cyan]{key}[/] → {value}" for key, value in examples
    )
    console.print()
    console.print(
        Panel.fit(
            "[bold]Memory key & value[/]\n\n"
            "[bold]Key[/] = short label (unique in this workspace)\n"
            "  e.g. [cyan]language_preference[/], [cyan]target_role[/], [cyan]tech_stack[/]\n\n"
            "[bold]Value[/] = the preference you want the agent to follow\n"
            "  e.g. \"Use Chinese with bilingual terms\" or \"Step-by-step with examples\"\n\n"
            "Used in chat only when [bold]Memory injection[/] is ON in Tools.\n\n"
            f"[bold]Examples ({workspace_type} workspace):[/]\n"
            f"{example_lines}\n\n"
            "[dim]Press Enter on Key/Value to cancel add.[/]",
            border_style="yellow",
            title="Tips",
        )
    )


async def list_workspace_memory(console: Console, workspace_id: str) -> None:
    from sqlalchemy import select

    from database import SessionLocal
    from models import Memory

    async with SessionLocal() as db:
        result = await db.execute(
            select(Memory)
            .where(Memory.workspace_id == workspace_id)
            .order_by(Memory.key.asc())
        )
        items = list(result.scalars().all())

    if not items:
        console.print("[yellow]No memory items in this workspace.[/]")
        return

    table = Table(title="Memory", header_style="bold cyan")
    table.add_column("#", width=4, justify="right")
    table.add_column("ID", style="dim")
    table.add_column("Key")
    table.add_column("Value", max_width=48)
    for index, item in enumerate(items, start=1):
        preview = item.value if len(item.value) <= 48 else item.value[:45] + "..."
        table.add_row(str(index), item.id, item.key, preview)
    console.print(table)


async def run_memory_interactive(
    console: Console,
    workspace_id: str,
    *,
    read_menu_choice: Callable[[str, int, int], int],
    confirm_action: Callable[[str], bool],
) -> NavResult | None:
    """Interactive memory editor (Desktop Memory tab parity)."""
    from sqlalchemy import select

    from database import SessionLocal
    from models import Memory, Workspace

    async with SessionLocal() as db:
        workspace = await db.get(Workspace, workspace_id)
    workspace_type = workspace.type if workspace else "study"
    workspace_name = workspace.name if workspace else workspace_id

    async def _sync_cursor_memory_if_needed() -> None:
        mode = await get_workspace_chat_mode(workspace_id)
        if mode != "cursor_agent":
            return
        from services.cursor_agent.memory_sync import sync_cursor_memory_file

        async with SessionLocal() as db:
            await sync_cursor_memory_file(workspace_id, db)

    while True:
        async with SessionLocal() as db:
            workspace = await db.get(Workspace, workspace_id)
            result = await db.execute(
                select(Memory)
                .where(Memory.workspace_id == workspace_id)
                .order_by(Memory.key.asc())
            )
            items = list(result.scalars().all())

        chat_mode = normalize_chat_mode(
            getattr(workspace, "chat_mode", "langgraph") if workspace else "langgraph"
        )

        cursor_note = ""
        if chat_mode == "cursor_agent":
            cursor_note = (
                "\n[dim]Cursor mode: also written to "
                "uploads/.cursor/rules/personalops-memory.mdc[/]"
            )

        console.print()
        console.print(
            Panel.fit(
                f"[bold]Memory · {workspace_name}[/] ({workspace_type}) · "
                f"engine: {format_chat_mode_badge(chat_mode)}\n"
                "[bold]a[/] add · [bold]e[/] edit · [bold]d[/] delete · "
                "[bold]b[/] back · [bold]q[/] quit\n"
                "[dim]Preferences for chat — enable Memory injection in Tools to use them.[/]"
                f"{cursor_note}",
                border_style="cyan",
            )
        )
        await list_workspace_memory(console, workspace_id)
        if not items:
            console.print(
                "[dim]No items yet — press [bold]a[/] to add. "
                "You'll see key/value tips before entering.[/]"
            )
        try:
            raw = console.input(
                f"[bold cyan]{submenu_prompt('Action [a/e/d]')}[/] "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            return "back"
        nav = parse_nav(raw)
        if nav is not None:
            return nav
        lowered = raw.lower()
        if lowered == "a":
            _print_memory_add_tips(console, workspace_type)
            try:
                key = console.input(
                    "[bold cyan]Key[/] [dim](short label, e.g. language_preference)[/] "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                continue
            if not key:
                console.print("[dim]Add cancelled.[/]")
                continue
            try:
                value = console.input(
                    "[bold cyan]Value[/] [dim](what the agent should follow)[/] "
                ).strip()
            except (EOFError, KeyboardInterrupt):
                continue
            if not value:
                console.print("[dim]Add cancelled.[/]")
                continue
            async with SessionLocal() as db:
                dup = await db.execute(
                    select(Memory).where(
                        Memory.workspace_id == workspace_id,
                        Memory.key == key,
                    )
                )
                if dup.scalar_one_or_none() is not None:
                    console.print("[red]Memory key already exists.[/]")
                    continue
                db.add(Memory(workspace_id=workspace_id, key=key, value=value))
                await db.commit()
            await _sync_cursor_memory_if_needed()
            console.print("[green]Memory added.[/]")
            continue
        if lowered in {"e", "d"} and not items:
            console.print("[yellow]No items to change.[/]")
            continue
        if lowered in {"e", "d"}:
            choice = read_menu_choice(f"Which item [1-{len(items)}]", 1, len(items))
            target = items[choice - 1]
            if lowered == "d":
                if not confirm_action(f"Delete memory '{target.key}'?"):
                    continue
                async with SessionLocal() as db:
                    row = await db.get(Memory, target.id)
                    if row:
                        await db.delete(row)
                        await db.commit()
                await _sync_cursor_memory_if_needed()
                console.print("[green]Deleted.[/]")
            else:
                console.print(
                    f"[dim]Editing value for [bold]{target.key}[/] — "
                    "describe what the agent should do.[/]"
                )
                value = console.input(f"New value for '{target.key}': ").strip()
                if not value:
                    continue
                async with SessionLocal() as db:
                    row = await db.get(Memory, target.id)
                    if row:
                        row.value = value
                        await db.commit()
                await _sync_cursor_memory_if_needed()
                console.print("[green]Updated.[/]")
            continue
        console.print("[yellow]Use a, e, d, b back, or q quit.[/]")


def register_manage_commands(
    app: typer.Typer,
    *,
    console: Console,
    run_cli: Callable[[Awaitable[Any]], Any],
    bootstrap: Callable[[], None],
    pick_workspace: Callable[[str | None], Awaitable[str]],
    read_menu_choice: Callable[[str, int, int], int],
    confirm_action: Callable[[str], bool],
    cli_quit: type[Exception],
) -> None:
    tools_app = typer.Typer(help="View or toggle workspace agent tools.")
    memory_app = typer.Typer(help="Manage workspace memory key/value preferences.")
    files_app = typer.Typer(help="List or delete indexed workspace files.")
    manage_app = typer.Typer(help="Interactive workspace settings hub.")

    @tools_app.callback(invoke_without_command=True)
    def tools_entry(
        ctx: typer.Context,
        workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
        file_search: Optional[bool] = typer.Option(None, "--file-search/--no-file-search"),
        web_search: Optional[bool] = typer.Option(None, "--web-search/--no-web-search"),
        memory: Optional[bool] = typer.Option(None, "--memory/--no-memory"),
        github_read: Optional[bool] = typer.Option(None, "--github-read/--no-github-read"),
        code_search: Optional[bool] = typer.Option(None, "--code-search/--no-code-search"),
    ) -> None:
        """Show or change tool toggles (same as Desktop Tools tab)."""
        bootstrap()

        async def _run() -> None:
            ws_id = await pick_workspace(workspace)
            updates = {
                k: v
                for k, v in {
                    "file_search": file_search,
                    "web_search": web_search,
                    "memory": memory,
                    "github_read": github_read,
                    "code_search": code_search,
                }.items()
                if v is not None
            }
            if ctx.invoked_subcommand is not None:
                return
            if updates:
                settings = await _load_tool_settings(ws_id)
                settings.update(updates)
                await _save_tool_settings(ws_id, settings)
                await print_workspace_tools(console, ws_id)
                return
            if workspace is not None and not updates:
                await print_workspace_tools(console, ws_id)
                return
            nav = await run_tools_interactive(console, ws_id)
            if nav == "quit":
                raise cli_quit()

        run_cli(_run())

    @tools_app.command("show")
    def tools_show(workspace: str = typer.Option(..., "--workspace", "-w")) -> None:
        bootstrap()
        run_cli(print_workspace_tools(console, workspace))

    @memory_app.callback(invoke_without_command=True)
    def memory_entry(
        ctx: typer.Context,
        workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    ) -> None:
        bootstrap()

        async def _run() -> None:
            ws_id = await pick_workspace(workspace)
            if ctx.invoked_subcommand is not None:
                return
            nav = await run_memory_interactive(
                console,
                ws_id,
                read_menu_choice=read_menu_choice,
                confirm_action=confirm_action,
            )
            if nav == "quit":
                raise cli_quit()

        run_cli(_run())

    @memory_app.command("list")
    def memory_list(workspace: str = typer.Option(..., "--workspace", "-w")) -> None:
        bootstrap()
        run_cli(list_workspace_memory(console, workspace))

    @memory_app.command("add")
    def memory_add(
        workspace: str = typer.Option(..., "--workspace", "-w"),
        key: str = typer.Option(..., "--key", "-k"),
        value: str = typer.Option(..., "--value", "-v"),
    ) -> None:
        bootstrap()

        async def _run() -> None:
            from sqlalchemy import select

            from database import SessionLocal
            from models import Memory

            async with SessionLocal() as db:
                dup = await db.execute(
                    select(Memory).where(
                        Memory.workspace_id == workspace,
                        Memory.key == key.strip(),
                    )
                )
                if dup.scalar_one_or_none() is not None:
                    console.print("[red]Memory key already exists.[/]")
                    raise typer.Exit(1)
                row = Memory(
                    workspace_id=workspace,
                    key=key.strip(),
                    value=value.strip(),
                )
                db.add(row)
                await db.commit()
            console.print(f"[green]Added memory[/] {row.key}")

        run_cli(_run())

    @memory_app.command("delete")
    def memory_delete(
        workspace: str = typer.Option(..., "--workspace", "-w"),
        memory_id: str = typer.Option(..., "--id"),
    ) -> None:
        bootstrap()

        async def _run() -> None:
            from database import SessionLocal
            from models import Memory

            if not confirm_action("Delete this memory item?"):
                return
            async with SessionLocal() as db:
                row = await db.get(Memory, memory_id)
                if row is None or row.workspace_id != workspace:
                    console.print("[red]Memory not found.[/]")
                    raise typer.Exit(1)
                await db.delete(row)
                await db.commit()
            console.print("[green]Memory deleted.[/]")

        run_cli(_run())

    async def _upload_file(workspace_id: str, source_path: str) -> None:
        import os
        import shutil
        from pathlib import Path

        from config import settings
        from database import SessionLocal
        from models import File
        from routers.files import run_indexing

        src = Path(source_path).expanduser().resolve()
        if not src.is_file():
            console.print("[red]Path must be an existing file.[/]")
            return

        filename = src.name
        workspace_dir = os.path.join(settings.uploads_dir, workspace_id)
        os.makedirs(workspace_dir, exist_ok=True)
        dest_path = os.path.join(workspace_dir, filename)
        shutil.copy2(src, dest_path)

        async with SessionLocal() as db:
            file_record = File(
                workspace_id=workspace_id,
                filename=filename,
                path=dest_path,
                status="pending",
                chunk_count=0,
            )
            db.add(file_record)
            await db.commit()
            await db.refresh(file_record)
            file_id = file_record.id

        with console.status(f"[cyan]Indexing {filename}...[/]", spinner="dots"):
            await run_indexing(file_id)

        async with SessionLocal() as db:
            row = await db.get(File, file_id)
            if row:
                console.print(
                    f"[green]Uploaded[/] {row.filename} · status={row.status} · "
                    f"chunks={row.chunk_count}"
                )

    async def _files_interactive(workspace_id: str) -> None:
        from sqlalchemy import select

        from database import SessionLocal
        from models import File

        while True:
            console.print()
            console.print(
                Panel.fit(
                    "[bold]Files[/] · [bold]u[/] upload · [bold]d[/] delete · [bold]q[/] back",
                    border_style="cyan",
                )
            )
            await _list_files(workspace_id)
            try:
                raw = console.input("[bold cyan]Action[/] ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                return
            if raw in {"q", "quit", "back", ""}:
                return
            if raw == "u":
                path = console.input("Path to file on disk: ").strip()
                if path:
                    await _upload_file(workspace_id, path)
                continue
            if raw == "d":
                async with SessionLocal() as db:
                    result = await db.execute(
                        select(File)
                        .where(File.workspace_id == workspace_id)
                        .order_by(File.filename.asc())
                    )
                    items = list(result.scalars().all())
                if not items:
                    console.print("[yellow]No files to delete.[/]")
                    continue
                choice = read_menu_choice(f"Delete which file [1-{len(items)}]", 1, len(items))
                target = items[choice - 1]
                if not confirm_action(f"Delete '{target.filename}' and its chunks?"):
                    continue
                from services.indexer import delete_file_chunks
                import os

                async with SessionLocal() as db:
                    row = await db.get(File, target.id)
                    if row is None:
                        continue
                    path = row.path
                    await db.delete(row)
                    await db.commit()
                delete_file_chunks(workspace_id, target.id)
                if path and os.path.isfile(path):
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                console.print("[green]File deleted.[/]")
                continue
            console.print("[yellow]Use u, d, or q.[/]")

    async def _list_files(workspace_id: str) -> None:
        from sqlalchemy import select

        from database import SessionLocal
        from models import File

        async with SessionLocal() as db:
            result = await db.execute(
                select(File)
                .where(File.workspace_id == workspace_id)
                .order_by(File.filename.asc())
            )
            items = list(result.scalars().all())

        if not items:
            console.print("[yellow]No files in this workspace.[/]")
            console.print("[dim]Upload files in Desktop Files tab, or copy into data/uploads/{workspace_id}/[/]")
            return

        table = Table(title="Files", header_style="bold cyan")
        table.add_column("#", width=4, justify="right")
        table.add_column("ID", style="dim")
        table.add_column("Filename")
        table.add_column("Status", width=12)
        table.add_column("Chunks", width=8, justify="right")
        for index, item in enumerate(items, start=1):
            table.add_row(
                str(index),
                item.id,
                item.filename,
                item.status,
                str(item.chunk_count),
            )
        console.print(table)

    @files_app.command("upload")
    def files_upload(
        workspace: str = typer.Option(..., "--workspace", "-w"),
        path: str = typer.Argument(..., help="Local file path to copy into the workspace"),
    ) -> None:
        bootstrap()
        run_cli(_upload_file(workspace, path))

    @files_app.command("list")
    def files_list(workspace: Optional[str] = typer.Option(None, "--workspace", "-w")) -> None:
        bootstrap()

        async def _run() -> None:
            ws_id = await pick_workspace(workspace)
            await _list_files(ws_id)

        run_cli(_run())

    @files_app.command("delete")
    def files_delete(
        workspace: str = typer.Option(..., "--workspace", "-w"),
        file_id: str = typer.Option(..., "--id"),
    ) -> None:
        bootstrap()

        async def _run() -> None:
            from database import SessionLocal
            from models import File
            from services.indexer import delete_file_chunks
            import os

            if not confirm_action("Delete this file and its indexed chunks?"):
                return
            async with SessionLocal() as db:
                row = await db.get(File, file_id)
                if row is None or row.workspace_id != workspace:
                    console.print("[red]File not found.[/]")
                    raise typer.Exit(1)
                path = row.path
                await db.delete(row)
                await db.commit()
            delete_file_chunks(workspace, file_id)
            if path and os.path.isfile(path):
                try:
                    os.remove(path)
                except OSError:
                    pass
            console.print("[green]File deleted.[/]")

        run_cli(_run())

    @manage_app.callback(invoke_without_command=True)
    def manage_entry(
        workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    ) -> None:
        """Open settings hub (tools, memory, files, overview, templates, github)."""
        bootstrap()

        async def _run() -> None:
            ws_id = await pick_workspace(workspace)
            workspace_row = await _get_workspace(ws_id)

            while True:
                console.print()
                chat_mode = getattr(workspace_row, "chat_mode", "langgraph")
                console.print(
                    Panel.fit(
                        f"[bold]Manage · {workspace_row.name}[/] ({workspace_row.type}) · chat: {chat_mode}",
                        border_style="bright_blue",
                    )
                )
                console.print("  [bold]1[/] Tools")
                console.print("  [bold]2[/] Memory")
                console.print("  [bold]3[/] Files (upload / delete)")
                console.print("  [bold]4[/] Overview")
                console.print("  [bold]5[/] Templates")
                console.print("  [bold]6[/] Evaluation (metrics)")
                if workspace_row.type == "code":
                    console.print("  [bold]7[/] GitHub link")
                    console.print("  [bold]8[/] Watch folder")
                else:
                    console.print("  [bold]7[/] Watch folder")
                console.print("  [bold]q[/] Back / quit")
                try:
                    raw = console.input("[bold cyan]Choose[/] ").strip().lower()
                except (EOFError, KeyboardInterrupt):
                    raise cli_quit() from None
                if raw in {"q", "quit", "exit"}:
                    raise cli_quit()
                if raw == "1":
                    nav = await run_tools_interactive(console, ws_id)
                    if nav == "quit":
                        raise cli_quit()
                elif raw == "2":
                    nav = await run_memory_interactive(
                        console,
                        ws_id,
                        read_menu_choice=read_menu_choice,
                        confirm_action=confirm_action,
                    )
                    if nav == "quit":
                        raise cli_quit()
                elif raw == "3":
                    await _files_interactive(ws_id)
                elif raw == "4":
                    await _print_overview(ws_id)
                elif raw == "5":
                    await _print_templates(ws_id)
                elif raw == "6":
                    await _print_metrics(ws_id)
                elif raw == "7" and workspace_row.type == "code":
                    await _github_interactive(ws_id)
                elif raw == "7" or raw == "8":
                    await _watch_interactive(ws_id)
                else:
                    console.print("[yellow]Invalid choice.[/]")

        run_cli(_run())

    async def _print_overview(workspace_id: str) -> None:
        from database import SessionLocal
        from models import Workspace
        from services.overview import build_workspace_overview

        async with SessionLocal() as db:
            workspace = await db.get(Workspace, workspace_id)
            if workspace is None:
                console.print("[red]Workspace not found.[/]")
                return
            overview = await build_workspace_overview(workspace, db)

        console.print(Panel.fit(f"[bold]Overview · {workspace.name}[/]", border_style="cyan"))
        idx = overview.get("indexing_summary", {})
        console.print(
            f"Files: {idx.get('total', 0)} total · {idx.get('ready', 0)} ready · "
            f"{idx.get('failed', 0)} failed"
        )
        console.print(f"Memory items: {overview.get('memory_count', 0)}")
        console.print(
            f"Chat engine: {format_chat_mode_badge(getattr(workspace, 'chat_mode', 'langgraph'))}"
        )
        tools = overview.get("tool_settings", {})
        console.print(
            "Tools: "
            + ", ".join(f"{k}={'on' if v else 'off'}" for k, v in tools.items())
        )

    async def _print_templates(workspace_id: str) -> None:
        from database import SessionLocal
        from models import Workspace
        from services.templates import get_templates

        async with SessionLocal() as db:
            workspace = await db.get(Workspace, workspace_id)
            if workspace is None:
                console.print("[red]Workspace not found.[/]")
                return
            templates = get_templates(workspace.type)

        table = Table(title=f"Templates · {workspace.type}", header_style="bold cyan")
        table.add_column("ID")
        table.add_column("Label")
        table.add_column("Description", max_width=40)
        for item in templates:
            table.add_row(item["id"], item["label"], item.get("description", ""))
        console.print(table)

    async def _github_interactive(workspace_id: str) -> None:
        from sqlalchemy import select

        from database import SessionLocal
        from models import GitHubLink
        from services.github_sync import save_github_link, sync_github_workspace

        async with SessionLocal() as db:
            result = await db.execute(
                select(GitHubLink).where(GitHubLink.workspace_id == workspace_id)
            )
            link = result.scalar_one_or_none()

        if link:
            console.print(f"Repo: {link.repo_url}")
            console.print(f"Branch: {link.default_branch}")
        else:
            console.print("[dim]No GitHub repo linked.[/]")

        action = console.input("[bold cyan][s]et URL · [y] sync · [q] back[/] ").strip().lower()
        if action in {"q", ""}:
            return
        if action == "s":
            url = console.input("GitHub repo URL: ").strip()
            if not url:
                return
            async with SessionLocal() as db:
                try:
                    await save_github_link(workspace_id, url, db)
                except Exception as exc:
                    console.print(f"[red]{exc}[/]")
                    return
            console.print("[green]GitHub link saved.[/]")
        elif action == "y":
            async with SessionLocal() as db:
                result = await db.execute(
                    select(GitHubLink).where(GitHubLink.workspace_id == workspace_id)
                )
                link = result.scalar_one_or_none()
                if link is None:
                    console.print("[red]Link a repo first.[/]")
                    return
                try:
                    out = await sync_github_workspace(workspace_id, link, db)
                except Exception as exc:
                    console.print(f"[red]{exc}[/]")
                    return
            console.print(f"[green]Synced[/] {out.get('files_synced', 0)} file(s)")

    async def _watch_interactive(workspace_id: str) -> None:
        from sqlalchemy import select

        from database import SessionLocal
        from models import WatchFolder
        from services import folder_watcher

        async with SessionLocal() as db:
            result = await db.execute(
                select(WatchFolder).where(WatchFolder.workspace_id == workspace_id)
            )
            record = result.scalar_one_or_none()

        if record:
            console.print(f"Watch path: {record.path} ({'enabled' if record.enabled else 'disabled'})")
        else:
            console.print("[dim]No watch folder configured.[/]")

        action = console.input("[bold cyan][s]et path · [x] remove · [q] back[/] ").strip().lower()
        if action in {"q", ""}:
            return
        if action == "s":
            path = console.input("Absolute folder path to watch: ").strip()
            if not path:
                return
            from pathlib import Path

            resolved = Path(path).expanduser().resolve()
            if not resolved.is_dir():
                console.print("[red]Path must be an existing directory.[/]")
                return
            async with SessionLocal() as db:
                from models import WatchFolder

                record = await db.get(WatchFolder, workspace_id)
                if record is None:
                    record = WatchFolder(
                        workspace_id=workspace_id,
                        path=str(resolved),
                        enabled=True,
                    )
                    db.add(record)
                else:
                    record.path = str(resolved)
                    record.enabled = True
                await db.commit()
            folder_watcher.stop_watcher(workspace_id)
            try:
                folder_watcher.start_watcher(workspace_id, str(resolved))
                await folder_watcher.scan_watch_folder(workspace_id, str(resolved))
            except ValueError as exc:
                console.print(f"[red]{exc}[/]")
                return
            console.print("[green]Watch folder saved.[/]")
        elif action == "x" and record:
            folder_watcher.stop_watcher(workspace_id)
            async with SessionLocal() as db:
                row = await db.get(WatchFolder, workspace_id)
                if row:
                    await db.delete(row)
                    await db.commit()
            console.print("[green]Watch folder removed.[/]")

    async def _print_metrics(workspace_id: str) -> None:
        from database import SessionLocal
        from models import Workspace
        from services.metrics import get_metrics_summary

        async with SessionLocal() as db:
            workspace = await db.get(Workspace, workspace_id)
            if workspace is None:
                console.print("[red]Workspace not found.[/]")
                return
            summary = await get_metrics_summary(workspace_id, db)

        console.print(Panel.fit(f"[bold]Evaluation · {workspace.name}[/]", border_style="cyan"))
        console.print(f"Total chats recorded: {summary.get('total_chats', 0)}")
        console.print(f"Avg latency: {summary.get('avg_latency_ms', 0)} ms")
        console.print(f"Citation rate: {summary.get('citation_rate', 0.0):.0%}")
        console.print(
            f"Feedback: 👍 {summary.get('feedback_up', 0)} · "
            f"👎 {summary.get('feedback_down', 0)}"
        )
        breakdown = summary.get("route_breakdown") or {}
        if breakdown:
            console.print("Route breakdown:")
            for route, count in sorted(breakdown.items(), key=lambda item: -item[1]):
                console.print(f"  • {route}: {count}")
        else:
            console.print("[dim]No routed chats yet — send messages in chat to populate metrics.[/]")

    @app.command("chat-mode")
    def chat_mode_cmd(
        mode: str = typer.Argument(..., help="langgraph | cursor_agent"),
        workspace: Optional[str] = typer.Option(None, "--workspace", "-w"),
    ) -> None:
        """Set workspace chat engine (LangGraph RAG or Cursor Agent)."""
        bootstrap()
        normalized = mode.strip().lower()
        if normalized not in {"langgraph", "cursor_agent"}:
            console.print("[red]Mode must be langgraph or cursor_agent.[/]")
            raise typer.Exit(1)

        async def _run() -> None:
            ws_id = await pick_workspace(workspace)
            try:
                await set_workspace_chat_mode(ws_id, normalized)
            except ValueError:
                console.print("[red]Workspace not found.[/]")
                return
            console.print(
                f"[green]Chat engine for workspace {ws_id} set to "
                f"{format_chat_mode_badge(normalized)}.[/]"
            )
            if normalized == "cursor_agent":
                from config import settings

                if not settings.cursor_api_key.strip():
                    console.print(
                        "[yellow]CURSOR_API_KEY is not set in .env — "
                        "Cursor Agent will not run until configured.[/]"
                    )
                else:
                    console.print(
                        "[dim]Memory synced to uploads/.cursor/rules/personalops-memory.mdc[/]"
                    )

        run_cli(_run())

    @app.command("metrics")
    def metrics_cmd(workspace: Optional[str] = typer.Option(None, "--workspace", "-w")) -> None:
        """Show chat evaluation metrics (same as Desktop Evaluation tab)."""
        bootstrap()

        async def _run() -> None:
            ws_id = await pick_workspace(workspace)
            await _print_metrics(ws_id)

        run_cli(_run())

    @app.command("overview")
    def overview_cmd(workspace: Optional[str] = typer.Option(None, "--workspace", "-w")) -> None:
        bootstrap()

        async def _run() -> None:
            ws_id = await pick_workspace(workspace)
            await _print_overview(ws_id)

        run_cli(_run())

    @app.command("templates")
    def templates_cmd(workspace: Optional[str] = typer.Option(None, "--workspace", "-w")) -> None:
        bootstrap()

        async def _run() -> None:
            ws_id = await pick_workspace(workspace)
            await _print_templates(ws_id)

        run_cli(_run())

    app.add_typer(tools_app, name="tools")
    app.add_typer(memory_app, name="memory")
    app.add_typer(files_app, name="files")
    app.add_typer(manage_app, name="manage")
