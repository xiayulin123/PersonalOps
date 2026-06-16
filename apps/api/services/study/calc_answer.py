"""Calculation answer parsing and reconciliation (Study S1)."""

from __future__ import annotations

import re

_FINAL_ANSWER_RE = re.compile(r"final answer:\s*(.+)$", re.IGNORECASE)
_NUMERIC_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")


def parse_numeric_value(text: str) -> float | None:
    cleaned = (text or "").strip().replace(",", "")
    if not cleaned:
        return None

    is_percent = "%" in cleaned
    if is_percent:
        cleaned = cleaned.replace("%", "").strip()

    matches = _NUMERIC_RE.findall(cleaned)
    if not matches:
        return None

    try:
        value = float(matches[-1])
    except ValueError:
        return None

    if is_percent and value > 1:
        return value / 100.0
    return value


def extract_final_answer_text(solution_steps: list[str]) -> str | None:
    if not solution_steps:
        return None

    last = solution_steps[-1].strip()
    if not last:
        return None

    final_match = _FINAL_ANSWER_RE.search(last)
    if final_match:
        return final_match.group(1).strip()

    if "=" in last:
        return last.rsplit("=", 1)[-1].strip()

    return last


def numeric_values_close(left: str, right: str, *, tolerance: float = 0.02) -> bool:
    left_num = parse_numeric_value(left)
    right_num = parse_numeric_value(right)
    if left_num is None or right_num is None:
        return left.strip().casefold() == right.strip().casefold()
    scale = max(abs(left_num), abs(right_num), 1e-9)
    return abs(left_num - right_num) / scale <= tolerance


def reconcile_calculation_answer(
    correct_answer: str,
    solution_steps: list[str],
) -> tuple[str, list[str]]:
    """Prefer the final value shown in solution steps when fields disagree."""
    step_final = extract_final_answer_text(solution_steps)
    if not step_final:
        return correct_answer, solution_steps

    if numeric_values_close(correct_answer, step_final):
        return correct_answer, solution_steps

    return step_final, solution_steps
