"""Pinned PlanF3 instructions and artifact validation for ADW planning turns."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from pathlib import Path

from .data_types import GateReport, PlanOutput

SECTIONS = {"purpose", "problem", "solution", "files", "phases", "validation", "notes", "amendments"}
ADAPTER = """
## PlanF3 ADW adapter (mandatory for this planning turn)

Use the bundled PlanF3 template and Create Plan workflow below. The ADW
owns sequencing, retries, permissions, and acceptance. Plan only; never
invoke Build Plan or implement the work from inside this turn.
The role's existing markdown plan, output schema, paths, and task scope
remain required. Write the same concrete decisions, file references,
implementation tasks, and verification commands in both formats.

For PlanOutput: keep context_handoff/plan.md and its collision-free specs/
copy. Also write context_handoff/plan.html and copy it to specs/ with the
same basename/version as the markdown spec and an .html extension. List
ALL four actual paths in artifacts. Include the HTML spec path in
notes_for_next_agent. Pick a version free for BOTH .md and .html files.
For TeamPlanOutput: keep the task's prescribed PLAN.md and plan_path;
write a sibling PLAN.html, list both in artifacts, and keep the existing
team_id, first_work_items, and any task limit on the number of work items.

Use the supplied request as USER_PROMPT. Metadata must name the actual
agent/session and implementation repository. Include assumptions in the
Questionables section when needed. Replace every template token, including
image slots. Without image generation, use inline SVG diagrams or plain
HTML explanations so the plan is self-contained and has no empty tokens.
Run headlessly: skip Create Plan's Open in Browser step. Images are optional:
skip its Generate Images step unless the current request explicitly calls
for paid image generation and an appropriate credential is available. Use
the skill's absolute script paths when needed; do not change the working
directory to the skill. A missing image credential must not block planning.
The HTML must contain purpose, problem, solution, files, phases, validation,
notes, and amendments sections with those ids, and a concrete checklist.
Finish with ONLY the role's existing Report JSON; the artifacts example
above takes precedence over any older example that lists only markdown.
"""


def is_planning(output_type: type) -> bool:
    return issubclass(output_type, PlanOutput) or output_type.__name__ == "TeamPlanOutput"


def skill_root() -> Path:
    return Path(__file__).resolve().parent / "resources" / "planf3"


def compose(system_text: str, output_type: type) -> str:
    """Inject pinned instructions before saving/dispatch, including overrides."""
    if not is_planning(output_type):
        return system_text
    root = skill_root()
    skill = (root / "SKILL.md").read_text()
    workflow = (root / "workflows" / "create-plan.md").read_text()
    # Keep adapter rules last so headless paths and the typed report prevail.
    return (f"{system_text}\n\n## Bundled PlanF3 ({root})\n\n{skill}"
            f"\n\n## Bundled Create Plan workflow\n\n{workflow}\n{ADAPTER}")


class _Structure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.html = False
        self.checklist = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.html |= tag == "html"
        if tag == "section":
            self.ids.add(attrs.get("id"))
        self.checklist |= tag == "ul" and "checklist" in attrs.get("class", "").split()


def artifacts_valid(envelope, run) -> GateReport:
    """Require actual markdown + HTML; catch template stubs before handoff."""
    report = GateReport()
    root = Path(run.repo_root).resolve()
    paths = [Path(a).expanduser() for a in envelope.artifacts]
    paths = [p.resolve() if p.is_absolute() else (root / p).resolve() for p in paths]
    markdown = [p for p in paths if p.suffix.lower() == ".md"]
    html = [p for p in paths if p.suffix.lower() == ".html"]
    report.check("PlanF3 markdown handoff", bool(markdown), "declare the existing markdown plan in artifacts")
    report.check("PlanF3 HTML plan", bool(html), "declare the companion HTML plan in artifacts")
    if isinstance(envelope, PlanOutput):
        handoff = Path(run.context_handoff_dir).resolve()
        for name in ("plan.md", "plan.html"):
            report.check(name, handoff / name in paths, f"declare {handoff / name} in artifacts")
        specs = root / "specs"
        for suffix in (".md", ".html"):
            report.check(f"PlanF3 specs {suffix}", any(p.parent == specs and p.suffix == suffix for p in paths),
                         f"declare the collision-free specs/ copy ending in {suffix}")
    for p in paths:
        present = p.is_file() and p.stat().st_size > 0
        report.check(str(p), present, "artifact exists and is nonempty" if present else "missing or empty artifact")
    for p in html:
        if not p.is_file():
            continue
        text = p.read_text(errors="replace")
        structure = _Structure()
        structure.feed(text)
        missing = sorted(SECTIONS - structure.ids)
        report.check(f"HTML structure: {p}", structure.html and not missing and structure.checklist,
                     f"html={structure.html}, missing sections={missing}, checklist={structure.checklist}")
        report.check(f"HTML placeholders: {p}", not re.search(r"\{\{[\s\S]*?\}\}", text),
                     "all template tokens must be replaced")
    return report
