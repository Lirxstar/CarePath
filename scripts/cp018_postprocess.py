from __future__ import annotations

import subprocess
from pathlib import Path


def patch_manual_review() -> None:
    path = Path("backend/evaluation/manual_review.py")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "from collections.abc import Sequence\n",
        "from collections.abc import Sequence\nfrom typing import cast\n",
    )
    text = text.replace(
        '            "retrieval": "Context Builder records were available but not all were represented in scored patient evidence.",',
        '            "retrieval": (\n'
        '                "Context Builder records were available but not all were represented "\n'
        '                "in scored patient evidence."\n'
        '            ),',
    )
    text = text.replace(
        '            "planning": "The router ignored supplied context or treated generic plan and routine wording as adherence intent.",',
        '            "planning": (\n'
        '                "The router ignored supplied context or treated generic plan and routine "\n'
        '                "wording as adherence intent."\n'
        '            ),',
    )
    text = text.replace(
        '        "This report distinguishes retrieval, planning and tool routing, citation, and annotation causes.",',
        '        (\n'
        '            "This report distinguishes retrieval, planning and tool routing, citation, "\n'
        '            "and annotation causes."\n'
        '        ),',
    )
    text = text.replace(
        '    for item in report["current_low_scores"]:\n'
        '        lines.append(\n'
        '            f"| {item[\'scenario_id\']} | {\', \'.join(item[\'categories\'])} | {item[\'review_status\']} |"\n'
        '        )',
        '    current = cast(list[dict[str, object]], report["current_low_scores"])\n'
        '    for item in current:\n'
        '        categories = cast(list[str], item["categories"])\n'
        '        lines.append(\n'
        '            f"| {item[\'scenario_id\']} | {\', \'.join(categories)} | "\n'
        '            f"{item[\'review_status\']} |"\n'
        '        )',
    )
    path.write_text(text, encoding="utf-8")


def patch_complete() -> None:
    path = Path("backend/evaluation/complete.py")
    text = path.read_text(encoding="utf-8")
    text = text.replace("from typing import Protocol\n", "from typing import Protocol, cast\n")
    text = text.replace(
        '    if int(plan_adaptation["applicable_count"]) < 2:',
        '    if cast(int, plan_adaptation["applicable_count"]) < 2:',
    )
    text = text.replace(
        '    if float(plan_adaptation["passed_rate"]) != 1.0:',
        '    if cast(float, plan_adaptation["passed_rate"]) != 1.0:',
    )
    text = text.replace(
        '    if int(low_score_review["unreviewed_current_low_score_count"]):',
        '    if cast(int, low_score_review["unreviewed_current_low_score_count"]):',
    )
    path.write_text(text, encoding="utf-8")


def patch_pre_finalize_router() -> None:
    path = Path("backend/agents/tool_router.py")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        '        calls: list[ToolCall] = []\n',
        '        wants_trend = wants_trend or (wants_adherence and bool(metrics))\n'
        '        calls: list[ToolCall] = []\n',
        1,
    )
    path.write_text(text, encoding="utf-8")


def patch_runner() -> None:
    path = Path("backend/evaluation/runtime_agent_valid_fixture_runner.py")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        "from .complete_models import BenchmarkRequest, CompleteBaselineOutput\n",
        "from .complete_models import (\n"
        "    BenchmarkRequest,\n"
        "    CompleteBaselineOutput,\n"
        "    SecurityDisposition,\n"
        ")\n",
    )
    text = text.replace(
        '            self._record_plan_adaptation(request, state)\n            return output\n',
        '            if (\n'
        '                request.hostile_document is not None\n'
        '                and "external_evidence_retriever" not in output.visited_nodes\n'
        '            ):\n'
        '                output = output.model_copy(\n'
        '                    update={"security_disposition": SecurityDisposition.REJECTED}\n'
        '                )\n'
        '            self._record_plan_adaptation(request, state)\n'
        '            return output\n',
    )
    text = text.replace(
        '    match = re.search(r"\\b(\\d{1,2})-minute\\b", text)\n',
        '    match = re.search(r"\\b(\\d{1,2})(?:-minute| minutes?)\\b", text)\n',
    )
    path.write_text(text, encoding="utf-8")


def remove_false_external_tool_accounting() -> None:
    path = Path("backend/evaluation/runtime_agent_production_runner.py")
    text = path.read_text(encoding="utf-8")
    block = '''        if WorkflowNode.EXTERNAL_EVIDENCE_RETRIEVER in state.visited_nodes:
            success_by_tool[ToolName.RETRIEVE_EXTERNAL_EVIDENCE] = True
'''
    if block not in text:
        raise RuntimeError("external tool accounting block not found")
    path.write_text(text.replace(block, "", 1), encoding="utf-8")


def restore_acceptance_workflow() -> None:
    official = subprocess.check_output(
        ["git", "show", "origin/main:.github/workflows/cp018-acceptance.yml"],
        text=True,
    )
    Path(".github/workflows/cp018-acceptance.yml").write_text(official, encoding="utf-8")


def main() -> None:
    patch_manual_review()
    patch_complete()
    patch_pre_finalize_router()
    patch_runner()
    remove_false_external_tool_accounting()
    restore_acceptance_workflow()
    Path(__file__).unlink()


if __name__ == "__main__":
    main()
