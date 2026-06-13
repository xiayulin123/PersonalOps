"""Quick manual test script for Step 2.6 agent."""
import asyncio
import json
import sqlite3

from database import SessionLocal, engine
from models import Workspace
from routers.tools import _parse_tool_settings
from services.agent.runner import run_agent


def get_workspace():
    conn = sqlite3.connect("../../data/personalops.db")
    row = conn.execute(
        "SELECT id, name, type, tool_settings_json FROM workspaces LIMIT 1"
    ).fetchone()
    conn.close()
    if not row:
        raise RuntimeError("No workspace found")
    return row


async def patch_web_search(workspace_id: str, enabled: bool) -> None:
    async with SessionLocal() as session:
        workspace = await session.get(Workspace, workspace_id)
        settings = _parse_tool_settings(workspace.tool_settings_json)
        settings["web_search"] = enabled
        workspace.tool_settings_json = json.dumps(settings)
        await session.commit()


def print_result(label: str, question: str, result: dict) -> None:
    print(f"\n### {label}")
    print(f"Q: {question}")
    print(f"route: {result.get('route')}")
    print(f"file sources: {len(result.get('sources', []))}")
    print(f"web sources: {len(result.get('web_sources', []))}")
    print("trace:")
    for step in result.get("trace", []):
        detail = step.get("detail")
        suffix = f" -> {detail}" if detail else ""
        print(f"  {step.get('step')}. {step.get('label')}{suffix}")
    answer = result.get("answer") or ""
    preview = answer[:220] + ("..." if len(answer) > 220 else "")
    print(f"answer: {preview}")


async def main() -> None:
    try:
        wid, name, wtype, tools_json = get_workspace()
        print(f"Workspace: {name} ({wtype})")
        print(f"ID: {wid}")
        print(f"Tools: {tools_json}")
        print("=" * 60)

        # A: direct
        r1 = await run_agent(wid, "What is 2 + 2?")
        print_result("A - direct (math)", "What is 2 + 2?", r1)
        ok_a = r1.get("route") == "direct" and len(r1.get("sources", [])) == 0

        # B: file_rag
        r2 = await run_agent(
            wid,
            "Summarize the main topics in my uploaded lecture materials",
        )
        print_result(
            "B - file_rag",
            "Summarize the main topics in my uploaded lecture materials",
            r2,
        )
        ok_b = r2.get("route") in ("file_rag", "hybrid") and len(r2.get("sources", [])) > 0

        # C: web_search
        await patch_web_search(wid, True)
        print("\n(patched web_search=true for test C)")
        r3 = await run_agent(wid, "Is FastAPI still actively maintained in 2025?")
        print_result("C - web_search", "Is FastAPI still actively maintained in 2025?", r3)
        ok_c = r3.get("route") in ("web_search", "hybrid") and len(r3.get("web_sources", [])) > 0

        print("\n" + "=" * 60)
        print("RESULTS:")
        print(f"  A direct + no file sources: {'PASS' if ok_a else 'CHECK'}")
        print(f"  B file_rag + file sources:  {'PASS' if ok_b else 'CHECK'}")
        print(f"  C web_search + web sources: {'PASS' if ok_c else 'CHECK'}")
        print("Done.")
    finally:
        # Release SQLite pool threads so the script exits cleanly.
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
