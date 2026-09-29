"""PlanF3 dispatch, artifact rejection, and same-session correction evidence."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from adw_modules import agents, planf3
from adw_modules.data_types import AgentCall, BuildOutput, PhaseParams, PiResult, PlanOutput
from adw_modules.runner import Run
from adw_modules.tracer import Tracer

ROOT = Path(__file__).resolve().parents[2]
HTML = ('<!doctype html><html><body>' + ''.join(
    f'<section id="{name}"><p>Read app.py and run pytest.</p></section>'
    for name in sorted(planf3.SECTIONS))
    + '<ul class="checklist"><li>[] Read app.py</li></ul></body></html>')


class PlanF3Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.handoff = self.root / 'data/context_handoff'
        self.handoff.mkdir(parents=True)
        (self.root / 'specs').mkdir()
        self.run = SimpleNamespace(repo_root=self.root, context_handoff_dir=self.handoff)

    def envelope(self, include_html=True, html=HTML):
        artifacts = []
        for suffix, body in (('.md', '- [ ] Read `app.py` and run `pytest`\n'), ('.html', html)):
            if suffix == '.html' and not include_html:
                continue
            for path in (self.handoff / f'plan{suffix}', self.root / f'specs/fixture_work{suffix}'):
                path.write_text(body)
                artifacts.append(str(path))
        return PlanOutput(status='success', summary='fixture', artifacts=artifacts)

    def test_valid_pair(self):
        report = planf3.artifacts_valid(self.envelope(), self.run)
        self.assertEqual(report.violations, [])

    def test_markdown_only_fails(self):
        report = planf3.artifacts_valid(self.envelope(include_html=False), self.run)
        self.assertTrue(report.violations)
        self.assertTrue(any('html' in item.lower() for item in report.violations))

    def test_stub_html_fails(self):
        report = planf3.artifacts_valid(self.envelope(html='<html>{{PLAN_TITLE}}</html>'), self.run)
        self.assertGreaterEqual(len(report.violations), 2)

    def test_deleted_artifact_fails(self):
        envelope = self.envelope()
        (self.handoff / 'plan.html').unlink()
        self.assertTrue(planf3.artifacts_valid(envelope, self.run).violations)

    def test_bundled_skill_is_cwd_independent_and_builds_untouched(self):
        with patch('os.getcwd', return_value='/'):
            text = planf3.compose('# Current role', PlanOutput)
        self.assertIn('## Plan Template', text)
        self.assertIn('## Bundled Create Plan workflow', text)
        self.assertIn('PlanF3 ADW adapter', text)
        self.assertEqual(planf3.compose('# Builder', BuildOutput), '# Builder')

    def test_missing_bundle_fails(self):
        with patch.object(planf3, 'skill_root', return_value=self.root / 'missing'):
            with self.assertRaises(FileNotFoundError):
                planf3.compose('role', PlanOutput)

    def test_real_executor_corrects_markdown_only_in_same_session(self):
        cfg = agents.load_config(str(ROOT / 'adws/adw_sssf_config/sssf.config.yaml'))
        cfg.defaults.data_dir = str(self.root / 'data')
        cfg.observability.db = str(self.root / 'trace.db')
        tracer = Tracer(cfg.observability.db, self.root / 'events.jsonl')
        self.addCleanup(tracer.conn.close)
        tracer.session_start('fixture', 'test')
        with patch('adw_modules.runner.git_helper.repo_root', return_value=self.root):
            run = Run(cfg, 'fixture', tracer, 'test')
        run.console = Mock()
        self.handoff = run.context_handoff_dir
        requests = []

        def send(request, **kwargs):
            requests.append(request)
            envelope = self.envelope(include_html=len(requests) > 1)
            return PiResult(text=envelope.model_dump_json(), returncode=0,
                            terminal_seen=True, settled=True, stop_reason='stop',
                            completion_ok=True, failure_reason='')

        with patch.object(agents.agent_pi, 'run', side_effect=send), \
             patch.object(agents.permissions, 'snapshot', return_value={}), \
             patch.object(agents.permissions, 'enforce', return_value=[]):
            with run.phase(PhaseParams(name='plan', kind='agent', owner='planner', retries=1,
                                      description='Require both plan formats before builder handoff')) as ph:
                envelope = ph.call(AgentCall(output_type=PlanOutput, prompt='Plan app.py'))
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].session_id, requests[1].session_id)
        self.assertIn('PlanF3 ADW adapter', requests[0].system_prompt)
        self.assertIn('failed validation', requests[1].prompt)
        saved = run.session_dir / 'planner/prompts/system.md'
        self.assertEqual(saved.read_text(), requests[0].system_prompt)
        events = tracer.conn.execute("select type from events where name='artifacts_valid'").fetchall()
        self.assertEqual([row[0] for row in events], ['gate_fail', 'gate_pass'])
        self.assertTrue(any(p.endswith('.html') for p in envelope.artifacts))
        self.assertEqual(run.finish(), 0)


if __name__ == '__main__':
    unittest.main()
