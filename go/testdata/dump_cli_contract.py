#!/usr/bin/env python3
"""Dump froster's argparse CLI surface as JSON.

This is the compatibility contract for the Go rewrite: the cobra command
tree in go/internal/cli is tested against the output of this script.

Regenerate with:
    unset SLURM_CPUS_ON_NODE SLURM_MEM_PER_NODE
    .venv/bin/python3 go/testdata/dump_cli_contract.py > go/testdata/cli-contract.json

Note: --cores and --mem defaults are environment-dependent (Slurm env vars);
they are recorded here with a clean environment (4 cores, 16 GB) and marked
"env_dependent" so the Go test compares presence/type, not the default value.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

os.environ.pop('SLURM_CPUS_ON_NODE', None)
os.environ.pop('SLURM_MEM_PER_NODE', None)

from froster.froster import Commands  # noqa: E402

ENV_DEPENDENT_FLAGS = {'--cores', '--mem'}


def type_name(action):
    if isinstance(action, argparse._StoreTrueAction):
        return 'bool'
    if action.type is int:
        return 'int'
    if action.type is None or action.type is str:
        return 'string'
    return getattr(action.type, '__name__', str(action.type))


def dump_action(action):
    entry = {
        'flags': list(action.option_strings),
        'dest': action.dest,
        'type': type_name(action),
        'help': (action.help or '').strip(),
    }
    if not action.option_strings:  # positional
        entry['positional'] = True
        entry['nargs'] = action.nargs
    if isinstance(action, argparse._StoreTrueAction):
        entry['default'] = False
    elif any(f in ENV_DEPENDENT_FLAGS for f in action.option_strings):
        entry['default'] = None
        entry['env_dependent'] = True
    else:
        entry['default'] = action.default
    return entry


def dump_parser(parser):
    out = {'options': [], 'positionals': [], 'subcommands': {}}
    for action in parser._actions:
        if isinstance(action, argparse._HelpAction):
            continue
        if isinstance(action, argparse._SubParsersAction):
            seen = {}
            for name, sub in action.choices.items():
                if id(sub) in seen:
                    out['subcommands'][seen[id(sub)]]['aliases'].append(name)
                else:
                    seen[id(sub)] = name
                    out['subcommands'][name] = dump_parser(sub)
                    out['subcommands'][name]['aliases'] = []
            continue
        entry = dump_action(action)
        if entry.get('positional'):
            out['positionals'].append(entry)
        else:
            out['options'].append(entry)
    return out


def main():
    cmd = Commands.__new__(Commands)  # skip __init__ side effects
    parser = Commands.parse_arguments(cmd)
    contract = dump_parser(parser)
    contract['_meta'] = {
        'source': 'froster/froster.py',
        'generator': 'go/testdata/dump_cli_contract.py',
    }
    json.dump(contract, sys.stdout, indent=1, sort_keys=True)
    sys.stdout.write('\n')


if __name__ == '__main__':
    main()
