"""GitHub workflow entry points; no cloud SDK or credentials needed for detection."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOTS = ('bootstrap', 'foundation', 'workloads')
CREDENTIALS = ('OCI_TENANCY_OCID', 'OCI_USER_OCID', 'OCI_FINGERPRINT', 'OCI_PRIVATE_KEY', 'OCI_REGION')


def output(name, value):
    if os.getenv('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a') as stream:
            stream.write(f'{name}={value}\n')
    print(value)


def main():
    command = sys.argv[1]
    if command == 'detect':
        paths = json.loads(Path(sys.argv[2]).read_text())
        shared = any(p.startswith(('modules/', '.github/', 'scripts/', 'tests/')) or
                     p in ('.terraform-version', '.tflint.hcl') for p in paths)
        roots = [r for r in ROOTS if shared or any(p.startswith(r + '/') for p in paths)]
        output('matrix', json.dumps({'root': roots}))
    elif command == 'credentials':
        available = all(os.getenv(key, '').strip() for key in CREDENTIALS)
        output('available', str(available).lower())
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
