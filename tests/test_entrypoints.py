"""Exercise checked-in workflow commands and their job conditions with boundary fixtures."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
import yaml

REPO = Path(__file__).resolve().parents[1]
PR = yaml.safe_load((REPO / '.github/workflows/pr.yml').read_text())
TF = yaml.safe_load((REPO / '.github/workflows/_terraform.yml').read_text())


def scope(value):
    return SimpleNamespace(**{k: scope(v) if isinstance(v, dict) else v for k, v in value.items()})


def condition(expression, **values):
    # Only the small, checked-in boolean job guards; GitHub validates full YAML separately.
    expression = ' '.join(expression.split()).replace('&&', ' and ').replace('||', ' or ')
    return eval(expression, {'__builtins__': {}}, {k: scope(v) for k, v in values.items()})


class EntryPointTests(unittest.TestCase):
    def test_root_matrix_from_workflow_step(self):
        step = PR['jobs']['detect']['steps'][-1]
        self.assertEqual(step['id'], 'roots')
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'paths.json'
            output = Path(tmp) / 'output'
            for paths, roots in [(['bootstrap/main.tf'], ['bootstrap']),
                                 (['foundation/main.tf'], ['foundation']),
                                 (['modules/shared/main.tf'], ['bootstrap', 'foundation', 'workloads']),
                                 (['.terraform-version'], ['bootstrap', 'foundation', 'workloads'])]:
                source.write_text(json.dumps(paths))
                command = step['run'].replace('/tmp/paths.json', str(source))
                result = subprocess.run(command, shell=True, cwd=REPO, env=os.environ | {'GITHUB_OUTPUT': str(output)}, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout), {'root': roots})
                self.assertIn('matrix=' + result.stdout.strip(), output.read_text())

    def test_forks_static_failure_and_no_secrets_block_plans(self):
        jobs = PR['jobs']
        self.assertEqual(set(jobs['plan']['needs']), {'detect', 'fmt', 'validate', 'tflint', 'fixtures'})
        for gate in ['fmt', 'validate', 'tflint']:
            self.assertNotIn('if', jobs[gate])
            self.assertNotIn('secrets', jobs[gate])
        self.assertNotIn('secrets', jobs['plan'].get('env', {}))
        self.assertTrue(all('OCI_PLAN_' in value for value in jobs['plan']['secrets'].values()))
        github = {'repository': 'owner/repo', 'event_name': 'pull_request', 'event': {'pull_request': {'head': {'repo': {'full_name': 'fork/repo'}}}}}
        needs = {'detect': {'outputs': {'matrix': '{"root": ["bootstrap"]}'}}}
        self.assertFalse(condition(jobs['plan']['if'], github=github, needs=needs))
        github['event']['pull_request']['head']['repo']['full_name'] = 'owner/repo'
        self.assertTrue(condition(jobs['plan']['if'], github=github, needs=needs))
        step = next(s for s in TF['jobs']['preflight']['steps'] if s.get('id') == 'credentials')
        with tempfile.TemporaryDirectory() as tmp:
            env = {k: v for k, v in os.environ.items() if not k.startswith('OCI_')}
            env['GITHUB_OUTPUT'] = str(Path(tmp) / 'output')
            result = subprocess.run(step['run'], shell=True, cwd=REPO, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0)
            available = (Path(tmp) / 'output').read_text().strip().split('=')[1]
            self.assertEqual(available, 'false')
            self.assertFalse(condition(TF['jobs']['plan']['if'], github=github, needs={'preflight': {'outputs': {'available': available}}}))
        self.assertTrue(condition(TF['jobs']['plan']['if'], github=github, needs={'preflight': {'outputs': {'available': 'true'}}}))
        github['event']['pull_request']['head']['repo']['full_name'] = 'fork/repo'
        self.assertFalse(condition(TF['jobs']['plan']['if'], github=github, needs={'preflight': {'outputs': {'available': 'true'}}}))
        self.assertIn('inputs.root', TF['jobs']['plan']['concurrency']['group'])
        self.assertIn('pull_request.number', TF['jobs']['plan']['concurrency']['group'])
        self.assertTrue(TF['jobs']['plan']['concurrency']['cancel-in-progress'])

    def test_workflow_static_commands_propagate_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            for binary in ['terraform', 'tflint']:
                fake = Path(tmp) / binary
                fake.write_text('#!/bin/sh\nexit 7\n')
                fake.chmod(0o755)
            for gate in ['fmt', 'validate', 'tflint']:
                command = PR['jobs'][gate]['steps'][-1]['run']
                result = subprocess.run(command, shell=True, cwd=REPO, env=os.environ | {'PATH': tmp + os.pathsep + os.environ['PATH']}, capture_output=True)
                self.assertNotEqual(result.returncode, 0)
