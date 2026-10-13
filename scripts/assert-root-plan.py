"""Assert the mocked Root plan JSON contract without snapshotting provider schemas."""
import json
from pathlib import Path
import sys

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
    else:
        assert not changes, 'Foundation/Workloads contracts must not provision infrastructure'
    contract = plan['output_changes']['root_contract']['after']
    assert contract['root'] == root, 'Wrong Root boundary'
    assert contract['state_key'] == f'{root}/terraform.tfstate', 'Root state key is not independent'
    assert contract['owned_scopes'], 'Ownership must be explicit'
print(f'{root}: mocked plan JSON boundary passed')
