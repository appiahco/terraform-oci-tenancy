import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml

REPO = Path(__file__).resolve().parents[1]
CREDENTIALS = ['OCI_TENANCY_OCID', 'OCI_USER_OCID', 'OCI_FINGERPRINT', 'OCI_PRIVATE_KEY', 'OCI_REGION']
STATE = ['TF_STATE_BUCKET', 'TF_STATE_NAMESPACE']
INPUTS = CREDENTIALS + STATE
COMPLETE = {k: 'fixture-only' for k in INPUTS}

class WorkflowTests(unittest.TestCase):
    def test_detection_entry_point(self):
        for paths, expected in [(['workloads/main.tf'], ['workloads']),
                                (['modules/network/main.tf'], ['bootstrap', 'foundation', 'workloads']),
                                (['.terraform-version'], ['bootstrap', 'foundation', 'workloads']),
                                (['docs/spec.md'], [])]:
            with self.subTest(paths=paths), tempfile.TemporaryDirectory() as tmp:
                source = Path(tmp) / 'paths.json'
                source.write_text(json.dumps(paths))
                result = subprocess.run(['python3', 'scripts/ci.py', 'detect', str(source)], cwd=REPO, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), {'root': expected})


class CredentialTests(unittest.TestCase):
    def test_plan_comment_permission_crosses_reusable_workflow_boundary(self):
        caller = yaml.safe_load((REPO / '.github/workflows/pr.yml').read_text())['jobs']['plan']
        called = yaml.safe_load((REPO / '.github/workflows/_terraform.yml').read_text())['jobs']['plan']
        for job in (caller, called):
            self.assertEqual(job['permissions'], {'contents': 'read', 'pull-requests': 'write'})

    def test_plan_environment_secrets_cross_reusable_workflow_boundary(self):
        caller = yaml.safe_load((REPO / '.github/workflows/pr.yml').read_text())['jobs']['plan']
        called = yaml.safe_load((REPO / '.github/workflows/_terraform.yml').read_text())
        keys = ['OCI_TENANCY_OCID', 'OCI_USER_OCID', 'OCI_FINGERPRINT', 'OCI_PRIVATE_KEY', 'OCI_REGION']
        # GitHub resolves Environment secrets to empty strings unless the caller
        # passes their names, even when the called job selects the Environment.
        self.assertEqual(caller.get('secrets'), {key: '${{ secrets.' + key + ' }}' for key in keys})
        for job in ('preflight', 'plan'):
            self.assertEqual(called['jobs'][job]['environment'], 'plan')

    def run_preflight(self, **overrides):
        """Run the credentials entry point with only the given CI inputs set."""
        base = {k: v for k, v in os.environ.items() if not k.startswith(('OCI_', 'TF_STATE_', 'GITHUB_'))}
        with tempfile.TemporaryDirectory() as tmp:
            output, summary = Path(tmp) / 'output', Path(tmp) / 'summary'
            env = base | overrides | {'GITHUB_OUTPUT': str(output), 'GITHUB_STEP_SUMMARY': str(summary)}
            result = subprocess.run(['python3', 'scripts/ci.py', 'credentials'], cwd=REPO, env=env, text=True, capture_output=True)
            written = output.read_text() if output.exists() else ''
            return result, written, summary.read_text() if summary.exists() else ''

    def test_valid_credentials_after_setup_enable_the_live_plan(self):
        result, output, summary = self.run_preflight(**COMPLETE)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('available=true', output)
        self.assertNotIn('fixture-only', result.stdout + result.stderr + summary)

    def test_missing_or_empty_input_after_setup_fails_with_sanitized_diagnostic(self):
        for name in INPUTS:
            for label, value in [('missing', None), ('empty', ''), ('blank', '  \n')]:
                with self.subTest(name=name, case=label):
                    env = dict(COMPLETE)
                    if value is None:
                        del env[name]
                    else:
                        env[name] = value
                    result, output, summary = self.run_preflight(**env)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('available=true', output)
                    self.assertIn(name, result.stderr)
                    self.assertIn(name, summary)
                    self.assertEqual(result.stderr.count('::error'), 1)
                    # Only names are reported; no configured value may leak.
                    self.assertNotIn('fixture-only', result.stdout + result.stderr + summary)

    def test_state_variables_mark_setup_complete_even_when_credentials_are_gone(self):
        result, output, _ = self.run_preflight(TF_STATE_BUCKET='fixture-only')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('available=true', output)

    def test_unconfigured_setup_skips_visibly_and_never_claims_verification(self):
        for env in [{}, {k: 'fixture-only' for k in CREDENTIALS[:3]}, {k: ' ' for k in INPUTS}]:
            with self.subTest(env=sorted(env)):
                result, output, summary = self.run_preflight(**env)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('available=false', output)
                self.assertIn('skipped', summary.lower())
                self.assertIn('not verified', summary.lower())
                self.assertNotIn('fixture-only', summary)

    def test_preflight_step_receives_every_input_from_the_plan_environment(self):
        called = yaml.safe_load((REPO / '.github/workflows/_terraform.yml').read_text())
        step = next(s for s in called['jobs']['preflight']['steps'] if s.get('id') == 'credentials')
        expected = {k: '${{ secrets.' + k + ' }}' for k in CREDENTIALS} | {k: '${{ vars.' + k + ' }}' for k in STATE}
        self.assertEqual(step['env'], expected)
        self.assertEqual(step['run'], 'python3 scripts/ci.py credentials')
        self.assertNotIn('continue-on-error', step)
        self.assertNotIn('continue-on-error', called['jobs']['preflight'])

    def test_plan_cannot_run_without_a_passing_preflight(self):
        plan = yaml.safe_load((REPO / '.github/workflows/_terraform.yml').read_text())['jobs']['plan']
        self.assertEqual(plan['needs'], 'preflight')
        self.assertIn("needs.preflight.outputs.available == 'true'", plan['if'])

    def test_fork_pull_requests_never_reach_credential_jobs(self):
        guard = 'github.event.pull_request.head.repo.full_name == github.repository'
        caller = yaml.safe_load((REPO / '.github/workflows/pr.yml').read_text())
        called = yaml.safe_load((REPO / '.github/workflows/_terraform.yml').read_text())
        self.assertIn(guard, caller['jobs']['plan']['if'])
        for job in ('preflight', 'plan'):
            self.assertIn(guard, called['jobs'][job]['if'])
        triggers = caller.get('on', caller.get(True))  # YAML 1.1 reads a bare `on` key as True
        self.assertEqual(triggers, {'pull_request': None})
        # Static jobs hold no Environment and no secrets.
        for name, job in caller['jobs'].items():
            if name != 'plan':
                self.assertNotIn('environment', job)
                self.assertNotIn('secrets', job)

    def test_preflight_has_no_write_permission(self):
        called = yaml.safe_load((REPO / '.github/workflows/_terraform.yml').read_text())
        self.assertEqual(called['permissions'], {'contents': 'read'})
        self.assertNotIn('permissions', called['jobs']['preflight'])

    def test_comment_step_reads_the_files_the_plan_entry_point_writes(self):
        called = yaml.safe_load((REPO / '.github/workflows/_terraform.yml').read_text())
        step = next(s for s in called['jobs']['plan']['steps'] if s.get('name') == 'Update Root comment')
        self.assertIn('${root}/plan.json', step['with']['script'])
        self.assertIn('${root}/plan.txt', step['with']['script'])
        script = (REPO / 'scripts/plan.sh').read_text()
        self.assertIn('"$root/plan.json"', script)
        self.assertIn('"$root/plan.txt"', script)

    def test_plan_invocation_uses_only_supplied_plan_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / 'bootstrap').mkdir()
            log = workspace / 'invocations.jsonl'
            fake = workspace / 'terraform'
            fake.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['FIXTURE_LOG'], 'a') as stream:
    stream.write(json.dumps({'args': sys.argv[1:], 'credentials': {k:v for k,v in os.environ.items() if k.startswith('OCI_')}}) + '\\n')
if 'output' in sys.argv: print('{}')
elif 'show' in sys.argv: print('{"resource_changes": []}')
else: print('fixture plan')
''')
            fake.chmod(0o755)
            env = {k: v for k, v in os.environ.items() if not k.startswith('OCI_')}
            credentials = {k: 'fixture-plan-' + k for k in ['OCI_TENANCY_OCID', 'OCI_USER_OCID', 'OCI_FINGERPRINT', 'OCI_PRIVATE_KEY', 'OCI_REGION']}
            env |= credentials | {'PATH': tmp + os.pathsep + env['PATH'], 'FIXTURE_LOG': str(log), 'TF_STATE_BUCKET': 'fixture-bucket', 'TF_STATE_NAMESPACE': 'fixture-namespace'}
            workflow = yaml.safe_load((REPO / '.github/workflows/_terraform.yml').read_text())
            step = next(s for s in workflow['jobs']['plan']['steps'] if s.get('name') == 'Plan with the Plan user')
            command = step['run'].replace('scripts/plan.sh', str(REPO / 'scripts/plan.sh'))
            result = subprocess.run(command, shell=True, cwd=workspace, env=env | {'ROOT': 'bootstrap', 'MODE': 'plan'}, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual([c['args'][1] for c in calls], ['init', 'output', 'plan', 'show'])
            self.assertIn('-lock=false', calls[2]['args'])
            self.assertEqual([a for a in calls[0]['args'] if a.startswith('-backend-config=')], ['-backend-config=bucket=fixture-bucket', '-backend-config=namespace=fixture-namespace'])
            expected_credentials = credentials | {'OCI_' + k[4:].lower(): v for k, v in credentials.items()}
            self.assertTrue(all(c['credentials'] == expected_credentials for c in calls))
            self.assertEqual(json.loads((workspace / 'bootstrap/plan.json').read_text()), {'resource_changes': []})
            log.unlink()
            result = subprocess.run(['bash', str(REPO / 'scripts/plan.sh'), 'bootstrap', 'apply'], cwd=workspace, env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(log.exists())

    def test_static_gate_failure_entry_point(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / 'terraform'
            fake.write_text('#!/bin/sh\nexit 7\n')
            fake.chmod(0o755)
            env = os.environ | {'PATH': tmp + os.pathsep + os.environ['PATH']}
            result = subprocess.run(['python3', 'scripts/ci.py', 'static', 'fmt'], cwd=REPO, env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)

if __name__ == '__main__':
    unittest.main()
