# -*- coding: utf-8 -*-
import re

def show(path, names, limit=4000):
    s = open(path, encoding='utf-8').read()
    lines = s.splitlines()
    print('=' * 72)
    print('FILE:', path)
    for name in names:
        # 找定义行
        start = None
        for i, l in enumerate(lines):
            if re.match(r'\s*def\s+' + re.escape(name) + r'\b', l):
                start = i
                break
        if start is None:
            print('NOT FOUND:', name)
            continue
        # 找下一个同级 def
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

show('evolver/improvement_generator.py', ['__init__', 'generate_all', '_create_idea', 'list_ideas', 'update_status', '_save', '_load'])
