import json
from pathlib import Path
import subprocess
import sys

import pytest

from scripts.check_terraform_plan import destructive_changes


def plan(actions):
    return {'format_version': '1.2', 'resource_changes': [
        {'address': f'example.resource_{index}', 'change': {'actions': action}}
        for index, action in enumerate(actions)]}


def test_release_allows_creation_updates_reads_and_no_changes():
    assert destructive_changes(plan([['create'], ['update'], ['read'], ['no-op']])) == []
    assert destructive_changes({'format_version': '1.2'}) == []


@pytest.mark.parametrize('actions', [['delete'], ['delete', 'create'], ['create', 'delete']])
def test_release_blocks_deletion_and_both_replacement_orders(actions):
    assert destructive_changes(plan([actions])) == ['example.resource_0']


@pytest.mark.parametrize('invalid', [{}, {'format_version': '2.0'},
    {'format_version': '1.2', 'resource_changes': None}, plan([['unknown']])])
def test_release_rejects_unrecognized_or_malformed_plans(invalid):
    with pytest.raises((ValueError, KeyError, TypeError)):
        destructive_changes(invalid)


def test_cli_stops_destructive_apply_without_printing_sensitive_plan_values(tmp_path):
    release_plan = plan([['delete', 'create']])
    release_plan['sensitive_values'] = {'password': 'must-not-be-logged'}
    source = tmp_path / 'plan.json'
    source.write_text(json.dumps(release_plan))
    result = subprocess.run([sys.executable, str(Path(__file__).parents[1] / 'scripts/check_terraform_plan.py'), str(source)],
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert 'example.resource_0' in result.stderr
    assert 'must-not-be-logged' not in result.stderr + result.stdout
