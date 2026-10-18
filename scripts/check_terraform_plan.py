"""Reject deletions and replacements before an automated release applies a plan."""
import json
import sys


def destructive_changes(plan):
    if not isinstance(plan, dict) or not str(plan.get('format_version', '')).startswith('1.'):
        raise ValueError('Unsupported Terraform plan format.')
    changes = plan.get('resource_changes', [])
    if not isinstance(changes, list):
        raise ValueError('Invalid Terraform resource changes.')
    blocked = []
    for resource in changes:
        actions = resource['change']['actions']
        if not isinstance(actions, list) or not actions or any(
                action not in {'no-op', 'read', 'create', 'update', 'delete'} for action in actions):
            raise ValueError('Invalid Terraform resource actions.')
        if 'delete' in actions:
            blocked.append(resource['address'])
    return blocked


def main():
    try:
        with open(sys.argv[1], encoding='utf-8') as source:
            blocked = destructive_changes(json.load(source))
    except (OSError, ValueError, KeyError, TypeError, IndexError):
        print('Cannot validate Terraform plan; automatic apply stopped.', file=sys.stderr)
        return 1
    if blocked:
        print('Automatic deployment cannot delete or replace resources:', file=sys.stderr)
        for address in blocked:
            print(f'  {address}', file=sys.stderr)
        print('Prepare an explicit infrastructure migration before retrying.', file=sys.stderr)
        return 1
    print('Terraform plan accepted: no deletions or replacements.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
