# -*- coding: utf-8 -*-
"""S14.2: at-most-one 识别 + 核验 + 专用传播

核心：
1. 从二元子句识别互斥组（at-most-one 团）；
2. 语义核验：区分纯互斥 vs 混合（互斥+蕴含）；
3. 专用传播：把互斥组压缩为基数约束（sequential counter 思路）。
"""
from collections import defaultdict, Counter


def extract_binary_relation(clauses):
    """提取二元子句，分类：互斥(全负) / 蕴含(1正1负)。"""
    mutex = defaultdict(set)   # 互斥关系：¬x∨¬y
    imply = defaultdict(set)   # 蕴含关系：x→y（¬x∨y 即 [-x, y]）
    for cl in clauses:
        if len(cl) != 2:
            continue
        pos = sum(1 for l in cl if l > 0)
        if pos == 0:
            a, b = -cl[0], -cl[1]
            mutex[a].add(b)
            mutex[b].add(a)
        elif pos == 1:
            # ¬x ∨ y => x→y
            if cl[0] < 0:
                x, y = -cl[0], cl[1]
            else:
                x, y = -cl[1], cl[0]
            imply[x].add(y)
    return mutex, imply


def identify_amone_groups(mutex):
    """在互斥图上识别 at-most-one 组（团）。

    用贪心团检测：从每个顶点扩展，找与组内所有顶点都互斥的顶点。
    返回互斥组列表（每个组是变量集合，两两互斥）。
    """
    groups = []
    visited = set()
    for start in mutex:
        if start in visited:
            continue
        # 贪心扩展团
        clique = {start}
        candidates = set(mutex[start])
        for v in candidates:
            if v in visited:
                continue
            if all(v in mutex[u] for u in clique):
                clique.add(v)
        if len(clique) >= 2:
            groups.append(clique)
            visited |= clique
    return groups


def verify_pure_amone(groups, imply):
    """核验：互斥组的变量是否也出现在蕴含关系里（若出现，则不是纯互斥组）。

    返回 (纯互斥组, 混合组)。
    """
    pure, mixed = [], []
    for g in groups:
        has_imply = any(v in imply or any(v in imply[u] for u in imply) for v in g)
        # 更精确：组内变量是否参与蕴含
        contaminated = False
        for v in g:
            if v in imply and imply[v]:
                contaminated = True
                break
        if contaminated:
            mixed.append(g)
        else:
            pure.append(g)
    return pure, mixed


if __name__ == '__main__':
    import os, lzma
    D = 'projects/miplib_solve/instances/satcomp/unknown'
    def load(f):
        content = lzma.decompress(open(os.path.join(D, f), 'rb').read()).decode('utf-8', 'ignore')
        clauses = []
        nv = 0
        for line in content.splitlines():
            line = line.strip()
            if not line or line.startswith('c') or line.startswith('p'):
                continue
            lits = [int(x) for x in line.split() if x != '0']
            if lits:
                clauses.append(lits)
                for l in lits:
                    nv = max(nv, abs(l))
        return clauses, nv

    for name, f in [('pcmax-m37', 'pcmax-scheduling-m37-28831-324346-SAT.sanitized.cnf.xz'),
                    ('Break_18_32', 'Break_18_32.xml.cnf.xz')]:
        clauses, nv = load(f)
        mutex, imply = extract_binary_relation(clauses)
        groups = identify_amone_groups(mutex)
        pure, mixed = verify_pure_amone(groups, imply)
        print('=' * 70)
        print('%s: 互斥关系 %d 条, 蕴含关系 %d 条' % (name, sum(len(v) for v in mutex.values())//2, sum(len(v) for v in imply.values())))
        print('  识别互斥组 %d 个（纯 %d, 混合 %d）' % (len(groups), len(pure), len(mixed)))
        if groups:
            sizes = sorted(len(g) for g in groups)
            print('  互斥组大小分布:', dict(Counter(sizes)))
