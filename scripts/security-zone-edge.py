"""Provider gap adapter, invoked only by the reviewed main Foundation apply."""
import configparser
import json
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    if os.getenv('GITHUB_REF') != 'refs/heads/main' or os.getenv('GITHUB_EVENT_NAME') != 'push':
        raise RuntimeError('Edge exclusion requires the reviewed main apply job')
    zone, edge = os.environ['SECURITY_ZONE_ID'], os.environ['EDGE_COMPARTMENT_ID']
    # Isolate CLI configuration from any runner profile. The private key never
    # enters Terraform configuration, state, arguments, or subprocess output.
    with tempfile.TemporaryDirectory() as tmp:
        key = Path(tmp) / 'key.pem'
        key.write_text(os.environ['OCI_PRIVATE_KEY'])
        key.chmod(0o600)
        config = configparser.ConfigParser(interpolation=None)
        config['apply'] = {
            'tenancy': os.environ['OCI_TENANCY_OCID'],
            'user': os.environ['OCI_USER_OCID'],
            'fingerprint': os.environ['OCI_FINGERPRINT'],
            'region': os.environ['OCI_REGION'],
            'key_file': str(key),
        }
        path = Path(tmp) / 'config'
        with path.open('w') as stream:
            config.write(stream)
        path.chmod(0o600)

        def invoke(operation, *arguments):
            result = subprocess.run([
                'oci', 'cloud-guard', 'security-zone', operation,
                '--config-file', str(path), '--profile', 'apply', '--auth', 'api_key',
                '--security-zone-id', zone, *arguments,
            ], capture_output=True, text=True)
            if result.returncode:
                # Do not expose SDK diagnostics or input credentials to logs.
                raise RuntimeError(f'Security Zone {operation} failed (exit {result.returncode})')
            return json.loads(result.stdout)

        inherited = invoke('get')['data']['inherited-by-compartments']
        if edge in inherited:
            invoke('remove', '--compartment-id', edge, '--wait-for-state', 'ACTIVE')
            if edge in invoke('get')['data']['inherited-by-compartments']:
                raise RuntimeError('Production Edge still inherits the Security Zone')
        print('Production Edge exclusion verified.')


if __name__ == '__main__':
    main()
