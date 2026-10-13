"""Assert the mocked Root plan JSON contract without snapshotting provider schemas."""
import json
from pathlib import Path
import sys

root, source = sys.argv[1:]
events = [json.loads(line) for line in Path(source).read_text().splitlines()]
plans = [event['test_plan'] for event in events if event.get('type') == 'test_plan']
assert plans, 'Mocked Terraform test must emit a plan'
for plan in plans:
    assert not plan.get('resource_changes'), 'Execution contracts must not provision infrastructure'
    contract = plan['output_changes']['root_contract']['after']
    assert contract['root'] == root, 'Wrong Root boundary'
    assert contract['state_key'] == f'{root}/terraform.tfstate', 'Root state key is not independent'
    assert contract['owned_scopes'], 'Ownership must be explicit'
print(f'{root}: mocked plan JSON boundary passed')
