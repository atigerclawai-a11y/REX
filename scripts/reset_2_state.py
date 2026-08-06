#!/usr/bin/env python3
"""Reset state for doc006889/006891 so they re-process with the name-first parser."""
import json
import os

STATE = os.path.expanduser('~/.hermes/profiles/work/state/signin_attendance_processed.json')
if os.path.exists(STATE):
    st = json.load(open(STATE))
    for k in list(st):
        if k in ('doc00688920260729104631', 'doc00689120260729104710'):
            st.pop(k)
    json.dump(st, open(STATE, 'w'))
    print(f'reset {STATE}: {st}')

BSTATE = os.path.expanduser('~/.hermes/profiles/work/state/signin_attendance_backup_state.json')
if os.path.exists(BSTATE):
    st = json.load(open(BSTATE))
    for k in list(st):
        if k in ('doc00688920260729104631', 'doc00689120260729104710'):
            st.pop(k)
    json.dump(st, open(BSTATE, 'w'))
    print(f'reset backup state')
