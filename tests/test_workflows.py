import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import yaml

REPO = Path(__file__).resolve().parents[1]

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
    def test_plan_environment_secrets_cross_reusable_workflow_boundary(self):
        caller = yaml.safe_load((REPO / '.github/workflows/pr.yml').read_text())['jobs']['plan']
        called = yaml.safe_load((REPO / '.github/workflows/_terraform.yml').read_text())
        keys = ['OCI_TENANCY_OCID', 'OCI_USER_OCID', 'OCI_FINGERPRINT', 'OCI_PRIVATE_KEY', 'OCI_REGION']
        # GitHub resolves Environment secrets to empty strings unless the caller
        # passes their names, even when the called job selects the Environment.
        self.assertEqual(caller.get('secrets'), {key: '${{ secrets.' + key + ' }}' for key in keys})
        for job in ('preflight', 'plan'):
            self.assertEqual(called['jobs'][job]['environment'], 'plan')

    def test_credential_preflight_entry_point(self):
        keys = ['OCI_TENANCY_OCID', 'OCI_USER_OCID', 'OCI_FINGERPRINT', 'OCI_PRIVATE_KEY', 'OCI_REGION']
        base = {k: v for k, v in os.environ.items() if not k.startswith('OCI_')}
        for missing in [None, *keys, 'all']:
            env = base | {k: 'fixture-only' for k in keys if missing not in (k, 'all')}
            result = subprocess.run(['python3', 'scripts/ci.py', 'credentials'], cwd=REPO, env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(result.stdout.strip(), 'true' if missing is None else 'false')

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
