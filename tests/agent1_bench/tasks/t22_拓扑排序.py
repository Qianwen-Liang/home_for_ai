"""
任务 t22: 拓扑排序
难度: 困难
能力维度: L1-代码生成

实现 topo_sort(graph)，输入邻接表，返回一个拓扑序列表；若存在环返回 None。
"""

TASK_TITLE = "拓扑排序"
TASK_DIMENSION = "L1-代码生成"
TASK_DIFFICULTY = "困难"

def topo_sort(graph):
    from collections import deque
    indegree = {u: 0 for u in graph}
    for u in graph:
        for v in graph[u]:
            indegree[v] = indegree.get(v, 0) + 1
    q = deque([u for u in indegree if indegree[u] == 0])
    result = []
    while q:
        u = q.popleft()
        result.append(u)
        for v in graph[u]:
            indegree[v] -= 1
            if indegree[v] == 0:
                q.append(v)
    return result if len(result) == len(indegree) else None
# ── 测试（自动评分，请勿修改）──
def _test():
    assert topo_sort({1: [2], 2: [3], 3: []}) == [1, 2, 3]
    assert topo_sort({}) == []
    assert topo_sort({1: [2], 2: [1]}) is None
    r = topo_sort({1: [2, 3], 2: [4], 3: [4], 4: []})
    assert r is not None and r[0] == 1 and r[-1] == 4
