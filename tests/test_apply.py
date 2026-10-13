"""Run the execution entry point against a Terraform boundary fixture, never OCI."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[1]


class ApplyTests(unittest.TestCase):
    def test_main_replans_and_applies_identical_locked_plan(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / 'foundation').mkdir()
            fake = workspace / 'terraform'
            fake.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
args = sys.argv[1:]
root = pathlib.Path(args[0].split('=', 1)[1])
with open(os.environ['FIXTURE_LOG'], 'a') as f: f.write(json.dumps(args) + '\\n')
if args[1] == 'plan':
    if os.environ.get('FAIL_PLAN'): sys.exit(7)
    (root / 'plan.tfplan').write_text('fixture authoritative main plan')
elif args[1] == 'show': print('{"resource_changes": []}')
elif args[1] == 'apply':
    assert args[-1] == 'plan.tfplan'
    assert (root / args[-1]).read_text() == 'fixture authoritative main plan'
''')
            fake.chmod(0o755)
            env = {k: v for k, v in os.environ.items() if not k.startswith(('OCI_', 'TF_', 'GITHUB_'))}
            env |= {k: 'fixture' for k in ['OCI_TENANCY_OCID', 'OCI_USER_OCID', 'OCI_FINGERPRINT', 'OCI_PRIVATE_KEY', 'OCI_REGION', 'TF_STATE_BUCKET', 'TF_STATE_NAMESPACE']}
            env |= {'PATH': tmp + os.pathsep + env['PATH'], 'FIXTURE_LOG': str(workspace / 'calls'), 'GITHUB_REF': 'refs/heads/main', 'GITHUB_EVENT_NAME': 'push'}
            for failure in [False, True]:
                with self.subTest(plan_failure=failure):
                    log = workspace / 'calls'
                    log.unlink(missing_ok=True)
                    (workspace / 'foundation/plan.tfplan').write_text('untrusted PR plan')
                    result = subprocess.run(['bash', str(REPO / 'scripts/plan.sh'), 'foundation', 'apply'], cwd=workspace, env=env | ({'FAIL_PLAN': '1'} if failure else {}), capture_output=True, text=True)
                    calls = [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
                    self.assertEqual(result.returncode == 0, not failure, result.stderr)
                    self.assertEqual([c[1] for c in calls], ['init', 'plan'] if failure else ['init', 'plan', 'show', 'apply'])
                    self.assertIn('-lock=true', calls[1])
                    self.assertIn('-out=plan.tfplan', calls[1])

    def test_apply_rejects_bootstrap_pr_and_non_main_before_terraform(self):
        for root, event, ref in [('bootstrap', 'push', 'refs/heads/main'), ('foundation', 'pull_request', 'refs/heads/main'), ('workloads', 'push', 'refs/heads/topic')]:
            with self.subTest(root=root, event=event, ref=ref):
                result = subprocess.run(['bash', str(REPO / 'scripts/plan.sh'), root, 'apply'], cwd=REPO, env=os.environ | {'GITHUB_EVENT_NAME': event, 'GITHUB_REF': ref}, capture_output=True, text=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Apply requires', result.stderr)


class EdgeExclusionTests(unittest.TestCase):
    def test_exclusion_is_idempotent_verified_and_failure_blocks_foundation(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            fake = workspace / 'oci'
            fake.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
args=sys.argv[1:]
log=pathlib.Path(os.environ['FIXTURE_LOG'])
with log.open('a') as f: f.write(json.dumps(args)+'\\n')
state=pathlib.Path(os.environ['FIXTURE_STATE'])
if 'remove' in args:
    if os.environ.get('FAIL_REMOVE'): sys.exit(7)
    state.write_text('excluded')
    print('{}')
else:
    included=not state.exists() or bool(os.environ.get('FAIL_VERIFY'))
    print(json.dumps({'data': {'inherited-by-compartments': ['fixture-edge'] if included else []}}))
''')
            fake.chmod(0o755)
            env = {k: v for k, v in os.environ.items() if not k.startswith(('OCI_', 'GITHUB_'))}
            env |= {k: 'fixture' for k in ['OCI_TENANCY_OCID','OCI_USER_OCID','OCI_FINGERPRINT','OCI_PRIVATE_KEY','OCI_REGION']}
            env |= {'PATH': tmp + os.pathsep + env['PATH'], 'FIXTURE_LOG': str(workspace / 'calls'), 'FIXTURE_STATE': str(workspace / 'state'), 'SECURITY_ZONE_ID': 'fixture-zone', 'EDGE_COMPARTMENT_ID': 'fixture-edge', 'GITHUB_REF': 'refs/heads/main', 'GITHUB_EVENT_NAME': 'push'}
            for case in ['new', 'already_excluded', 'remove_failure', 'verify_failure']:
                with self.subTest(case=case):
                    log=workspace / 'calls'; log.unlink(missing_ok=True)
                    if case != 'already_excluded': (workspace / 'state').unlink(missing_ok=True)
                    extra={'FAIL_REMOVE':'1'} if case == 'remove_failure' else {'FAIL_VERIFY':'1'} if case == 'verify_failure' else {}
                    result=subprocess.run(['python3', str(REPO / 'scripts/security-zone-edge.py')], env=env | extra, capture_output=True, text=True)
                    self.assertEqual(result.returncode == 0, case in ['new','already_excluded'], result.stderr)
                    calls=[json.loads(line) for line in log.read_text().splitlines()]
                    operations=[c[2] for c in calls]
                    self.assertEqual(operations, ['get'] if case == 'already_excluded' else ['get','remove'] if case == 'remove_failure' else ['get','remove','get'])
                    if 'remove' in operations:
                        remove=calls[1]
                        self.assertIn('fixture-zone',remove); self.assertIn('fixture-edge',remove)
                        self.assertIn('--wait-for-state',remove)


class ApplyWorkflowTests(unittest.TestCase):
    def test_review_ordering_serialization_and_caller_credentials(self):
        import yaml
        workflow = yaml.safe_load((REPO / '.github/workflows/apply.yml').read_text())
        reusable = yaml.safe_load((REPO / '.github/workflows/_terraform.yml').read_text())
        self.assertEqual(workflow.get('on', workflow.get(True))['push']['branches'], ['main'])
        self.assertEqual(set(workflow['jobs']), {'foundation', 'workloads'})
        self.assertEqual(workflow['jobs']['workloads']['needs'], 'foundation')
        from test_entrypoints import condition
        for result in ['success', 'failure', 'cancelled', 'skipped']:
            self.assertEqual(condition(workflow['jobs']['workloads']['if'], needs={'foundation':{'result':result}}), result == 'success')
        keys=['OCI_TENANCY_OCID','OCI_USER_OCID','OCI_FINGERPRINT','OCI_PRIVATE_KEY','OCI_REGION']
        for root in ['foundation','workloads']:
            job=workflow['jobs'][root]
            self.assertEqual(job['with'], {'root':root,'mode':'apply'})
            self.assertEqual(job['secrets'], {k:'${{ secrets.'+k+' }}' for k in keys})
        job=reusable['jobs']['apply']
        self.assertEqual(job['environment'], "${{ format('apply-{0}', inputs.root) }}")
        self.assertEqual(job['concurrency'], {'group':'terraform-${{ inputs.root }}-apply', 'cancel-in-progress':False})
        self.assertIn("github.ref == 'refs/heads/main'",job['if'])
        self.assertIn("github.event_name == 'push'",job['if'])
        self.assertIn("inputs.root != 'bootstrap'",job['if'])
        steps=job['steps']
        credential_index=next(i for i,s in enumerate(steps) if s.get('name') == 'Validate Apply credentials')
        execute_index=next(i for i,s in enumerate(steps) if s.get('name') == 'Re-plan and apply with the Apply user')
        self.assertLess(credential_index,execute_index)
        self.assertEqual(steps[credential_index]['run'],'python3 scripts/ci.py credentials')
        self.assertEqual(steps[credential_index]['env']['MODE'],'apply')
        self.assertEqual(steps[execute_index]['run'],'bash scripts/plan.sh "$ROOT" "$MODE"')
        self.assertFalse(any('download-artifact' in s.get('uses','') for s in steps))
        self.assertFalse(any(s.get('continue-on-error') for s in steps))

    def test_apply_credentials_never_skip_even_initial_setup(self):
        env={k:v for k,v in os.environ.items() if not k.startswith(('OCI_','TF_STATE_','GITHUB_'))}
        result=subprocess.run(['python3',str(REPO / 'scripts/ci.py'),'credentials'],env=env | {'MODE':'apply'},capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)
        self.assertIn('Apply',result.stderr)
        self.assertNotIn('available=true',result.stdout)
