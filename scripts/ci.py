"""GitHub workflow entry points; no cloud SDK or credentials needed for detection."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOTS = ('bootstrap', 'foundation', 'workloads')
CREDENTIALS = ('OCI_TENANCY_OCID', 'OCI_USER_OCID', 'OCI_FINGERPRINT', 'OCI_PRIVATE_KEY', 'OCI_REGION')
# The owner wizard installs these repository variables last, after every Environment's
# credentials. Setup counts as complete once either is set, or once every credential is
# present (see README "Unconfigured versus configured setup").
STATE_VARIABLES = ('TF_STATE_BUCKET', 'TF_STATE_NAMESPACE')


def output(name, value):
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write(f'{name}={value}\n')
    print(value)


def summary(*lines):
    if os.getenv('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as stream:
            stream.write('\n'.join(lines) + '\n')


def credentials():
    """Decide whether the live plan may run; report names only, never values."""
    missing = [key for key in CREDENTIALS + STATE_VARIABLES if not os.getenv(key, '').strip()]
    if not missing:
        output('available', 'true')
        return
    if all(key in missing for key in STATE_VARIABLES) and any(key in missing for key in CREDENTIALS):
        output('available', 'false')
        summary('### Live plan skipped: initial setup not complete',
                'Plan credentials and backend variables are not configured, so **no live plan ran** and',
                'infrastructure is **not verified** by this run. Static checks are the only evidence.',
                'Missing: ' + ', '.join(f'`{key}`' for key in missing))
        return
    names = ', '.join(missing)
    print(f'::error title=Plan setup incomplete::Setup is complete but required inputs are missing or empty: {names}', file=sys.stderr)
    summary('### Live plan failed: required input missing or empty',
            'Setup is complete (backend variables or all credentials exist), so every Plan credential and backend variable is required.',
            'Missing or empty: ' + ', '.join(f'`{key}`' for key in missing),
            'Restore them in the `plan` Environment (secrets) or repository variables, then re-run.')
    output('available', 'false')
    sys.exit(1)


def main():
    command = sys.argv[1]
    if command == 'detect':
        paths = json.loads(Path(sys.argv[2]).read_text())
        shared = any(p.startswith(('modules/', '.github/', 'scripts/', 'tests/')) or
                     p in ('.terraform-version', '.tflint.hcl') for p in paths)
        roots = [r for r in ROOTS if shared or any(p.startswith(r + '/') for p in paths)]
        output('matrix', json.dumps({'root': roots}))
    elif command == 'credentials':
        credentials()
    elif command == 'static':
        gate = sys.argv[2]
        if gate == 'fmt':
            subprocess.run(['terraform', 'fmt', '-check', '-recursive'], check=True)
        else:
            for root in ROOTS:
                if gate == 'validate':
                    subprocess.run(['terraform', f'-chdir={root}', 'init', '-backend=false', '-input=false', '-lockfile=readonly'], check=True)
                    subprocess.run(['terraform', f'-chdir={root}', 'validate', '-no-color'], check=True)
                    result = subprocess.run(['terraform', f'-chdir={root}', 'test', '-json', '-verbose'], check=True, capture_output=True, text=True)
                    with tempfile.TemporaryDirectory() as tmp:
                        source = Path(tmp) / 'test.jsonl'
                        source.write_text(result.stdout)
                        subprocess.run([sys.executable, 'scripts/assert-root-plan.py', root, str(source)], check=True)
                elif gate == 'tflint':
                    subprocess.run(['tflint', f'--chdir={root}', f'--config={Path(".tflint.hcl").resolve()}'], check=True)
                else:
                    raise ValueError(f'Unknown gate: {gate}')
    else:
        raise ValueError(f'Unknown command: {command}')


if __name__ == '__main__':
    main()
