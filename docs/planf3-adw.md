# PlanF3 planning integration

Installed on 2026-09-29 from https://github.com/disler/planf3 at
`f34b7ba5ff8167ef6283791763f4b578bfb3a2c0` (MIT).

Use `/planf3 "<request>"` in Claude, `$planf3` in Codex, or
`/skill:planf3 <request>` in Pi. Codex discovers it on the next turn.
Hermes has the package in its base skill store. The shared `.agents` store
links to the verified Codex copy. Optional upstream image scripts require
`OPENAI_API_KEY` in the process environment or the current project's `.env`;
no credentials are stored in the package or this document.

## ADW behavior

`adw_modules/agents.py` calls `planf3.compose()` before saving and dispatching
planning prompts, and automatically includes `planf3.artifacts_valid` in the
existing same-session gate/correction loop. Calls returning `PlanOutput` or
`TeamPlanOutput` receive the pinned skill/template and Create Plan workflow.
This applies even when a caller overrides the role prompts. Other output
types keep their normal dispatch.

`PlanOutput` retains the builder's `context_handoff/plan.md` and its versioned
`specs/` copy, and adds `context_handoff/plan.html` plus the matching versioned
HTML spec. Both formats go in the existing artifacts list; the JSON schema
is compatible. Company `TeamPlanOutput` retains its prescribed `PLAN.md` and
`plan_path`, and adds sibling `PLAN.html`. Task scope and work-item limits
still come from the caller. The HTML uses the upstream plan template, with
inline diagrams/text when images are not requested. Headless runs skip
browser launch and optional paid image calls.

The gate checks declared artifacts exist and are nonempty, requires both
formats, and checks HTML sections/checklist and absence of template tokens.
It verifies structure; plan quality still needs review. Markdown citation
checks and permission enforcement continue to run.

## Installation and maintenance

Canonical global package: `agentic-os/capabilities/skills/planf3`, registered
in `capabilities/registry.json`. Use the capability controller's `plan`,
`sync`, and `verify` commands restricted to `--capability planf3` and the
intended surfaces. Existing destination drift must be reviewed.

Each engine bundles the same package under `adw_modules/resources/planf3`,
including license and upstream provenance. SSSF install stamps these
resources with the module, so a fresh project does not depend on host-global
skill discovery. Nine dispatch locations were installed: software and
company modules in the three current Agentic OS development checkouts,
the standalone SSSF software engine, and both SSSF template copies.
Historical baseline-source snapshots and the sealed production factory
checkout were excluded. A production release/repin remains a separate step.

## Verification

78 focused tests passed across four software checkouts and a fresh SSSF
stamp (36 + 21 + 7 + 7 + 7; repeated adapter tests are not independent task
samples). The real executor was exercised with synthetic Pi responses:
markdown-only -> gate rejection -> same-session correction -> accepted
Markdown and HTML envelope. Existing completion/revision and SSSF shared
contract tests passed. The company module's team-plan injection and
missing-HTML rejection passed. Pi RPC `get_commands` discovered
`skill:planf3` from its automatic user skill store. Four global package
hashes matched; portable scenario coverage was 8/8.

No real model-written plan or image API call was used as proof. Local receipt:
`~/.cache/planf3-install/2026-09-29/receipt.json`; pre-edit backups are beside it.
Adapter tests: `adws/tests/test_planf3.py`.

---
Governed by AGENTS.md.
