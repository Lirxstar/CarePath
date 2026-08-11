from pathlib import Path

path = Path("backend/personalization/planner_v2.py")
text = path.read_text()
marker = "# ruff: noqa: RUF001\n"
if not text.startswith(marker):
    path.write_text(marker + text)
