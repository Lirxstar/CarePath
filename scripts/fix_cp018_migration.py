from __future__ import annotations

from pathlib import Path

path = Path("scripts/cp018_apply.py")
text = path.read_text(encoding="utf-8")
start_marker = "    replace_once(\n        path,\n        '''    acceptance_content = ("
end_marker = "    replace_once(\n        path,\n        '    acceptance_path.write_text"
start = text.index(start_marker)
end = text.index(end_marker, start)
replacement = r'''    replace_once(
        path,
        '    raw_path.write_text(raw_content, encoding="utf-8")\n',
        '    plan_adaptation_content = json.dumps(plan_adaptation, indent=2, sort_keys=True) + "\\n"\n'
        '    low_score_review_content = json.dumps(low_score_review, indent=2, sort_keys=True) + "\\n"\n'
        '    low_score_review_markdown = render_low_score_review_markdown(low_score_review)\n'
        '    raw_path.write_text(raw_content, encoding="utf-8")\n',
    )
'''
path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
Path(__file__).unlink()
