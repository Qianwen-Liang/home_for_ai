# -*- coding: utf-8 -*-
import re

def funcs(path):
    s = open(path, encoding='utf-8').read()
    print('#' * 70)
    print('FILE:', path, 'len=', len(s))
    print('#' * 70)
    for m in re.finditer(r'^\s*(?:async\s+)?def\s+(\w+)\([^)]*\)\s*(?:->[^:]*)?:', s, re.M):
        print(m.group(1), '-> line', s[:m.start()].count('\n') + 1)

funcs('evolver/improvement_generator.py')
print()
funcs('evolver/self_improver.py')
