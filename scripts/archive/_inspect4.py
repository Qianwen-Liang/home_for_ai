# -*- coding: utf-8 -*-
import re

def show(path, names, limit=5000):
    s = open(path, encoding='utf-8').read()
    lines = s.splitlines()
    print('=' * 72)
    print('FILE:', path)
    for name in names:
        start = None
        for i, l in enumerate(lines):
            if re.match(r'\s*def\s+' + re.escape(name) + r'\b', l):
                start = i
                break
        if start is None:
            print('NOT FOUND:', name)
            continue
        indent = len(lines[start]) - len(lines[start].lstrip())
        end = len(lines)
        for j in range(start + 1, len(lines)):
            l = lines[j]
            if l.strip() and (len(l) - len(l.lstrip())) <= indent and re.match(r'\s*(def |class |@)', l):
                end = j
                break
        body = '\n'.join(lines[start:end])
        print('-' * 60)
        print(f'--- {name} (line {start+1}~{end}) ---')
        print(body[:limit])
        print()

show('evolver/self_improver.py', ['run_cycle', '_phase_generate', '_phase_generate_patch', '_match_transform', '_phase_evaluate', 'improve_module'])
