"""Assert the mocked Root plan JSON contract without snapshotting provider schemas."""
import json
from pathlib import Path
import sys
import subprocess
import re
import tempfile

root, source = sys.argv[1:]
events = [json.loads(line) for line in Path(source).read_text().splitlines()]
plans = [event['test_plan'] for event in events if event.get('type') == 'test_plan' and event.get('@testrun') not in ('private_keys_rejected', 'duplicate_primary_emails_rejected')]
assert plans, 'Mocked Terraform test must emit a plan'
for plan in plans:
    changes = plan.get('resource_changes', [])
    if root == 'bootstrap':
        expected = {'oci_identity_compartment': 1, 'oci_objectstorage_bucket': 1,
                    'oci_identity_user': 2, 'oci_identity_group': 2,
                    'oci_identity_user_group_membership': 2, 'oci_identity_api_key': 2,
                    'oci_identity_policy': 2}
        from collections import Counter
        assert Counter(c['type'] for c in changes) == expected, 'Bootstrap ownership changed'
        for change in changes:
            after = change['change']['after']
            assert not after.get('defined_tags') and not after.get('freeform_tags'), 'Bootstrap stays untagged'
            if change['type'] == 'oci_objectstorage_bucket':
                assert after['versioning'] == 'Enabled' and after['access_type'] == 'NoPublicAccess'
                assert not after.get('kms_key_id'), 'Use Oracle-managed encryption'
            if change['type'] == 'oci_identity_api_key':
                assert 'BEGIN PUBLIC KEY' in after['key_value'] and 'PRIVATE KEY' not in after['key_value']
    elif root == 'foundation':
        from collections import Counter
        assert Counter(c['type'] for c in changes) == {
            'oci_identity_compartment': 5, 'oci_identity_tag_namespace': 1,
            'oci_identity_tag': 2, 'oci_identity_tag_default': 6,
            'oci_cloud_guard_security_recipe': 1, 'oci_cloud_guard_security_zone': 1,
            'terraform_data': 1, 'oci_cloud_guard_cloud_guard_configuration': 1,
        }, 'Foundation may own only governed structure and its Security Zone'
        resources = {c['address']: c['change']['after'] for c in changes}
        for change in changes:
            after = change['change']['after']
            if change['type'] in ('oci_identity_compartment', 'oci_cloud_guard_security_recipe', 'oci_cloud_guard_security_zone'):
                assert after['defined_tags']['appiahco.managed-by'] == 'terraform'
                assert after['defined_tags']['appiahco.environment'] in ('platform', 'production', 'staging')
            if change['type'] == 'oci_identity_tag_default':
                assert after['is_required'] is False
                assert after['compartment_id'] in ('fixture-platform', 'fixture-production', 'fixture-staging'), 'Defaults attach to environments, not Tenancy or Bootstrap'
        enablement = resources['oci_cloud_guard_cloud_guard_configuration.tenancy']
        assert enablement['compartment_id'] == 'ocid1.tenancy.oc1..fixture'
        assert enablement['reporting_region'] == 'us-ashburn-1'
        assert enablement['status'] == 'ENABLED' and enablement['self_manage_resources'] is False
        # Graph generation otherwise requires a live backend initialization.
        # Copy the checked-in configuration unchanged except for the backend;
        # reuse installed providers and keep the adapter hash path available.
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp) / 'foundation'
            directory.mkdir()
            for source_file in Path('foundation').glob('*.tf'):
                configuration = source_file.read_text()
                if source_file.name == 'main.tf':
                    configuration, removed = re.subn(r'  backend "oci" \{[^}]*\}', '', configuration)
                    assert removed == 1, 'Expected exactly one Foundation backend'
                (directory / source_file.name).write_text(configuration)
            for name in ('security-policy-names.json', '.terraform.lock.hcl'):
                (directory / name).write_bytes((Path('foundation') / name).read_bytes())
            (directory / '.terraform').mkdir()
            (directory / '.terraform/providers').symlink_to(Path('foundation/.terraform/providers').resolve())
            (Path(tmp) / 'scripts').symlink_to(Path('scripts').resolve())
            graph = subprocess.run(['terraform', f'-chdir={directory}', 'graph', '-type=plan'],
                                   check=True, capture_output=True, text=True).stdout
        dependency = '"[root] oci_cloud_guard_security_zone.production (expand)" -> "[root] oci_cloud_guard_cloud_guard_configuration.tenancy (expand)"'
        assert dependency in graph, 'Production Security Zone must explicitly depend on Cloud Guard enablement'
        zone = resources['oci_cloud_guard_security_zone.production']
        assert zone['compartment_id'] == 'fixture-production' and zone['security_zone_recipe_id'] == 'fixture-recipe'
        exclusion = resources['terraform_data.production_edge_exclusion']['input']
        assert exclusion == {'zone_id': 'fixture-zone', 'edge_id': 'fixture-production-edge'}
        names = plan['output_changes']['production_security_zone']['after']['policy_names']
        forbidden = {'deny internet_gateway', 'deny NAT_gateway', 'deny SGW_gateway', 'deny DRG_gateway', 'deny create_drg', 'deny public_load_balancer', 'deny block_volume_without_vault_key', 'deny boot_volume_without_vault_key', 'deny file_system_without_vault_key', 'deny buckets_without_vault_key'}
        assert 'deny public_subnets' in names and len(names) == 39 and not forbidden.intersection(names)
        catalogue = json.loads(Path('foundation/tests/security-policies.json').read_text())
        policies = {p['display_name']: p['id'] for p in catalogue}
        assert set(resources['oci_cloud_guard_security_recipe.production']['security_policies']) == {policies[n] for n in names}, 'Recipe must contain the selected policy identifiers'
    else:
        assert not changes, 'Workloads contract must not provision infrastructure yet'
    contract = plan['output_changes']['root_contract']['after']
    assert contract['root'] == root, 'Wrong Root boundary'
    assert contract['state_key'] == f'{root}/terraform.tfstate', 'Root state key is not independent'
    assert contract['owned_scopes'], 'Ownership must be explicit'
print(f'{root}: mocked plan JSON boundary passed')
