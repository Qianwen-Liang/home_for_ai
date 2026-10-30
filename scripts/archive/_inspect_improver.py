# -*- coding: utf-8 -*-
import re
s = open('evolver/self_improver.py', encoding='utf-8').read()

def extract(name, limit=2600):
    i = s.find(name)
    if i < 0:
        print('NOT FOUND:', name)
        return
    j = s.find('\n    def ', i + 10)
    if j < 0:
        j = min(len(s), i + limit)
    print('=' * 70)
    print(s[i:min(j, i + limit)])
    print()

for fn in ['def run_cycle', 'def improve_module', 'def _phase_generate_patch', 'def _phase_deploy']:
    extract(fn)
