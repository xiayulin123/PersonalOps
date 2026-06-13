from __future__ import annotations

import logging
from typing import Any

from services.agent.state import AgentState

logger = logging.getLogger("personalops.agent")


def log_agent_node(node: str, state: AgentState, **details: Any) -> None:
    """Emit a grep-friendly structured line for each LangGraph node."""
    parts = [
        f"node={node}",
        f"workspace_id={state.get('workspace_id', '')}",
        f"workspace_type={state.get('workspace_type', '')}",
    ]

    route = state.get("route")
    if route:
        parts.append(f"route={route}")

    for key, value in details.items():
        if value is None:
            continue
        parts.append(f"{key}={value}")

    logger.info("agent_node %s", " ".join(parts))
