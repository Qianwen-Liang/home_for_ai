"""graph_verification.py — 图算法任务客观验证（QuixBugs 全部 9 个 graph-based 任务）

针对 QuixBugs 中 9 个 graph-based 任务（其测试为打印输出/对象断言，而非
json_testcases），重建官方测试用例的图结构，客观验证 Agent 1 的修复作答。

覆盖任务：
  topological_ordering, shortest_paths, detect_cycle,
  breadth_first_search, depth_first_search, reverse_linked_list,
  shortest_path_length, minimum_spanning_tree, shortest_path_lengths

用法：
    python -X utf8 tests/agent1_bench/objective/graph_verification.py
"""

from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path
from typing import Any

BENCH_DIR = Path(__file__).resolve().parent
RESULTS_FILE = BENCH_DIR / "graph_results.json"


class Node:
    """与 QuixBugs python_testcases/node.py 语义一致的 Node（修正可变默认参数）。"""

    def __init__(
        self,
        value=None,
        successor=None,
        successors=None,
        predecessors=None,
        incoming_nodes=None,
        outgoing_nodes=None,
    ):
        self.value = value
        self.successor = successor
        self.successors = successors if successors is not None else []
        self.predecessors = predecessors if predecessors is not None else []
        self.incoming_nodes = incoming_nodes if incoming_nodes is not None else []
        self.outgoing_nodes = outgoing_nodes if outgoing_nodes is not None else []


def load_answers():
    spec = importlib.util.spec_from_file_location(
        "agent_answers", BENCH_DIR / "agent_answers.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ─────────────────────────── 各任务验证函数 ───────────────────────────


def verify_topological_ordering(fn):
    results = []

    # Case 1: Wikipedia graph
    five, seven, three = Node(5), Node(7), Node(3)
    eleven, eight, two = Node(11), Node(8), Node(2)
    nine, ten = Node(9), Node(10)
    five.outgoing_nodes = [eleven]
    seven.outgoing_nodes = [eleven, eight]
    three.outgoing_nodes = [eight, ten]
    eleven.incoming_nodes = [five, seven]
    eleven.outgoing_nodes = [two, nine, ten]
    eight.incoming_nodes = [seven, three]
    eight.outgoing_nodes = [nine]
    two.incoming_nodes = [eleven]
    nine.incoming_nodes = [eleven, eight]
    ten.incoming_nodes = [eleven, three]
    case1_nodes = [five, seven, three, eleven, eight, two, nine, ten]

    # Case 2: GeeksforGeeks
    five2, zero, four = Node(5), Node(0), Node(4)
    one, two2, three2 = Node(1), Node(2), Node(3)
    five2.outgoing_nodes = [two2, zero]
    four.outgoing_nodes = [zero, one]
    two2.incoming_nodes = [five2]
    two2.outgoing_nodes = [three2]
    zero.incoming_nodes = [five2, four]
    one.incoming_nodes = [four, three2]
    three2.incoming_nodes = [two2]
    three2.outgoing_nodes = [one]
    case2_nodes = [zero, one, two2, three2, four, five2]

    for idx, nodes in enumerate([case1_nodes, case2_nodes], 1):
        order = fn(nodes)
        ok = len(order) == len(nodes)
        if ok:
            pos = {id(n): i for i, n in enumerate(order)}
            for n in nodes:
                for succ in n.outgoing_nodes:
                    if pos[id(n)] >= pos.get(id(succ), 0):
                        ok = False
                        break
                if not ok:
                    break
        results.append((f"topological_ordering case{idx}", ok, order if not ok else None))
    return results


def verify_shortest_paths(fn):
    cases = [
        ("case1", 'A', {
            ('A', 'B'): 3, ('A', 'C'): 3, ('A', 'F'): 5, ('C', 'B'): -2,
            ('C', 'D'): 7, ('C', 'E'): 4, ('D', 'E'): -5, ('E', 'F'): -1,
        }, {'A': 0, 'C': 3, 'B': 1, 'E': 5, 'D': 10, 'F': 4}),
        ("case2", 'A', {
            ('A', 'B'): 1, ('B', 'C'): 2, ('C', 'D'): 3, ('D', 'E'): -1,
            ('E', 'F'): 4,
        }, {'A': 0, 'C': 3, 'B': 1, 'E': 5, 'D': 6, 'F': 9}),
        ("case3", 'A', {
            ('A', 'B'): 1, ('B', 'C'): 2, ('C', 'D'): 3, ('D', 'E'): -1,
            ('E', 'D'): 1, ('E', 'F'): 4,
        }, {'A': 0, 'B': 1, 'C': 3, 'D': 6, 'E': 5, 'F': 9}),
    ]
    results = []
    for name, src, graph, expected in cases:
        actual = fn(src, graph)
        results.append((f"shortest_paths {name}", actual == expected, actual))
    return results


def verify_detect_cycle(fn):
    results = []
    n1 = Node(1)
    n2 = Node(2, n1)
    n3 = Node(3, n2)
    n4 = Node(4, n3)
    n5 = Node(5, n4)
    results.append(("detect_cycle case1(无环)", fn(n5) is False))
    n1.successor = n5
    results.append(("detect_cycle case2(有环)", fn(n5) is True))
    n1.successor = n2
    results.append(("detect_cycle case3(有环)", fn(n2) is True))
    n6 = Node(6)
    n7 = Node(7, n6)
    results.append(("detect_cycle case4(无环)", fn(n7) is False))
    results.append(("detect_cycle case5(单节点)", fn(Node(0)) is False))
    n1.successor = n2
    results.append(("detect_cycle case6(有环)", fn(n5) is True))
    return results


def verify_breadth_first_search(fn):
    results = []

    # Case 1: Strongly connected graph
    station1 = Node("Westminster")
    station2 = Node("Waterloo", None, [station1])
    station3 = Node("Trafalgar Square", None, [station1, station2])
    station4 = Node("Canary Wharf", None, [station2, station3])
    station5 = Node("London Bridge", None, [station4, station3])
    station6 = Node("Tottenham Court Road", None, [station5, station4])
    results.append(("breadth_first_search case1", fn(station6, station1) is True))

    # Case 2: Branching graph
    nodef = Node("F")
    nodee = Node("E")
    noded = Node("D")
    nodec = Node("C", None, [nodef])
    nodeb = Node("B", None, [nodee])
    nodea = Node("A", None, [nodeb, nodec, noded])
    results.append(("breadth_first_search case2", fn(nodea, nodee) is True))

    # Case 3: Two unconnected nodes
    nodef2 = Node("F")
    nodee2 = Node("E")
    results.append(("breadth_first_search case3", fn(nodef2, nodee2) is False))

    # Case 4: One node graph
    nodef3 = Node("F")
    results.append(("breadth_first_search case4", fn(nodef3, nodef3) is True))

    # Case 5: Graph with cycles
    nodef4 = Node("F")
    nodee4 = Node("E")
    noded4 = Node("D")
    nodec4 = Node("C", None, [nodef4])
    nodeb4 = Node("B", None, [nodee4])
    nodea4 = Node("A", None, [nodeb4, nodec4, noded4])
    nodee4.successors = [nodea4]
    results.append(("breadth_first_search case5", fn(nodea4, nodef4) is True))

    return results


def verify_depth_first_search(fn):
    results = []

    # Case 1: Strongly connected graph
    station1 = Node("Westminster")
    station2 = Node("Waterloo", None, [station1])
    station3 = Node("Trafalgar Square", None, [station1, station2])
    station4 = Node("Canary Wharf", None, [station2, station3])
    station5 = Node("London Bridge", None, [station4, station3])
    station6 = Node("Tottenham Court Road", None, [station5, station4])
    results.append(("depth_first_search case1", fn(station6, station1) is True))

    # Case 2: Branching graph
    nodef = Node("F")
    nodee = Node("E")
    noded = Node("D")
    nodec = Node("C", None, [nodef])
    nodeb = Node("B", None, [nodee])
    nodea = Node("A", None, [nodeb, nodec, noded])
    results.append(("depth_first_search case2", fn(nodea, nodee) is True))

    # Case 3: Two unconnected nodes
    nodef2 = Node("F")
    nodee2 = Node("E")
    results.append(("depth_first_search case3", fn(nodef2, nodee2) is False))

    # Case 4: One node graph
    nodef3 = Node("F")
    results.append(("depth_first_search case4", fn(nodef3, nodef3) is True))

    # Case 5: Graph with cycles
    nodef4 = Node("F")
    nodee4 = Node("E")
    noded4 = Node("D")
    nodec4 = Node("C", None, [nodef4])
    nodeb4 = Node("B", None, [nodee4])
    nodea4 = Node("A", None, [nodeb4, nodec4, noded4])
    nodee4.successors = [nodea4]
    results.append(("depth_first_search case5", fn(nodea4, nodef4) is True))

    return results


def verify_reverse_linked_list(fn):
    results = []

    # Case 1: 5-node list
    node1 = Node(1)
    node2 = Node(2, node1)
    node3 = Node(3, node2)
    node4 = Node(4, node3)
    node5 = Node(5, node4)
    result = fn(node5)
    output = []
    cur = result
    while cur:
        output.append(cur.value)
        cur = cur.successor
    results.append((
        "reverse_linked_list case1",
        result is node1 and output == [1, 2, 3, 4, 5],
    ))

    # Case 2: 1-node list
    node = Node(0)
    result = fn(node)
    output = []
    cur = result
    while cur:
        output.append(cur.value)
        cur = cur.successor
    results.append(("reverse_linked_list case2", result is node and output == [0]))

    # Case 3: None input
    result = fn(None)
    results.append(("reverse_linked_list case3", result is None))

    return results


def verify_shortest_path_length(fn):
    node1 = Node("1")
    node5 = Node("5")
    node4 = Node("4", None, [node5])
    node3 = Node("3", None, [node4])
    node2 = Node("2", None, [node1, node3, node4])
    node0 = Node("0", None, [node2, node5])

    length_by_edge = {
        (node0, node2): 3,
        (node0, node5): 10,
        (node2, node1): 1,
        (node2, node3): 2,
        (node2, node4): 4,
        (node3, node4): 1,
        (node4, node5): 1,
    }

    return [
        ("shortest_path_length case1", fn(length_by_edge, node0, node1) == 4),
        ("shortest_path_length case2", fn(length_by_edge, node0, node5) == 7),
        ("shortest_path_length case3", fn(length_by_edge, node2, node2) == 0),
        ("shortest_path_length case4", fn(length_by_edge, node1, node5) == float("inf")),
    ]


def verify_minimum_spanning_tree(fn):
    cases = [
        ({
            (1, 2): 10, (2, 3): 15, (3, 4): 10, (1, 4): 10,
        }, {(1, 2), (3, 4), (1, 4)}),
        ({
            (1, 2): 6, (1, 3): 1, (1, 4): 5, (2, 3): 5, (2, 5): 3,
            (3, 4): 5, (3, 5): 6, (3, 6): 4, (4, 6): 2, (5, 6): 6,
        }, {(2, 5), (1, 3), (2, 3), (4, 6), (3, 6)}),
        ({
            (1, 2): 6, (1, 3): 1, (2, 4): 2,
        }, {(1, 2), (1, 3), (2, 4)}),
    ]
    results = []
    for i, (graph, expected) in enumerate(cases, 1):
        actual = fn(graph)
        results.append((f"minimum_spanning_tree case{i}", actual == expected, actual))
    return results


def verify_shortest_path_lengths(fn):
    cases = [
        (6, {
            (0, 2): 3, (0, 5): 5, (2, 1): -2, (2, 3): 7, (2, 4): 4,
            (3, 4): -5, (4, 5): -1,
        }, {
            (0, 0): 0, (1, 1): 0, (2, 2): 0, (3, 3): 0, (4, 4): 0, (5, 5): 0,
            (0, 2): 3, (0, 5): 4, (2, 1): -2, (2, 3): 7, (2, 4): 2, (3, 4): -5,
            (4, 5): -1, (0, 1): 1, (0, 3): 10, (0, 4): 5,
            (1, 0): float("inf"), (1, 2): float("inf"), (1, 3): float("inf"),
            (1, 4): float("inf"), (1, 5): float("inf"), (2, 0): float("inf"),
            (2, 5): 1, (3, 0): float("inf"), (3, 1): float("inf"),
            (3, 2): float("inf"), (3, 5): -6, (4, 0): float("inf"),
            (4, 1): float("inf"), (4, 2): float("inf"), (4, 3): float("inf"),
            (5, 0): float("inf"), (5, 1): float("inf"), (5, 2): float("inf"),
            (5, 3): float("inf"), (5, 4): float("inf"),
        }),
        (5, {
            (0, 1): 3, (1, 2): 5, (2, 3): -2, (3, 4): 7,
        }, {
            (0, 0): 0, (1, 1): 0, (2, 2): 0, (3, 3): 0, (4, 4): 0,
            (0, 1): 3, (1, 2): 5, (2, 3): -2, (3, 4): 7,
            (0, 2): 8, (0, 3): 6, (0, 4): 13,
            (1, 0): float("inf"), (1, 3): 3, (1, 4): 10,
            (2, 0): float("inf"), (2, 1): float("inf"), (2, 4): 5,
            (3, 0): float("inf"), (3, 1): float("inf"), (3, 2): float("inf"),
            (4, 0): float("inf"), (4, 1): float("inf"), (4, 2): float("inf"),
            (4, 3): float("inf"),
        }),
        (4, {
            (0, 1): 3, (2, 3): 5,
        }, {
            (0, 0): 0, (1, 1): 0, (2, 2): 0, (3, 3): 0,
            (0, 1): 3, (2, 3): 5,
            (0, 2): float("inf"), (0, 3): float("inf"),
            (1, 0): float("inf"), (1, 2): float("inf"), (1, 3): float("inf"),
            (2, 0): float("inf"), (2, 1): float("inf"),
            (3, 0): float("inf"), (3, 1): float("inf"), (3, 2): float("inf"),
        }),
        (3, {
            (0, 1): 3, (1, 2): 5, (2, 0): -1,
        }, {
            (0, 0): 0, (1, 1): 0, (2, 2): 0,
            (0, 1): 3, (1, 2): 5, (2, 0): -1,
            (0, 2): 8, (1, 0): 4, (2, 1): 2,
        }),
    ]
    results = []
    for i, (n, graph, expected) in enumerate(cases, 1):
        actual = fn(n, graph)
        results.append((
            f"shortest_path_lengths case{i}", actual == expected, actual
        ))
    return results


# ─────────────────────────── 汇总与入口 ───────────────────────────


def run_all(answers) -> dict[str, Any]:
    verifiers = [
        ("topological_ordering", verify_topological_ordering),
        ("shortest_paths", verify_shortest_paths),
        ("detect_cycle", verify_detect_cycle),
        ("breadth_first_search", verify_breadth_first_search),
        ("depth_first_search", verify_depth_first_search),
        ("reverse_linked_list", verify_reverse_linked_list),
        ("shortest_path_length", verify_shortest_path_length),
        ("minimum_spanning_tree", verify_minimum_spanning_tree),
        ("shortest_path_lengths", verify_shortest_path_lengths),
    ]

    task_results: list[dict[str, Any]] = []
    all_cases: list[tuple[str, bool]] = []

    for name, verify in verifiers:
        fn = getattr(answers, name, None)
        if fn is None:
            task_results.append({
                "task": name, "status": "ERROR", "detail": "缺少作答函数",
            })
            continue
        case_results = verify(fn)
        passed = sum(1 for _, ok, *_ in case_results if ok)
        total = len(case_results)
        task_results.append({
            "task": name,
            "status": "PASS" if passed == total else "FAIL",
            "passed": passed,
            "total": total,
        })
        all_cases.extend((c, ok) for c, ok, *_ in case_results)

    passed_tasks = sum(1 for r in task_results if r["status"] == "PASS")
    total_tasks = len(task_results)
    passed_cases = sum(1 for _, ok in all_cases if ok)
    total_cases = len(all_cases)

    return {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "QuixBugs (external public benchmark, graph tasks)",
        "total_tasks": total_tasks,
        "passed_tasks": passed_tasks,
        "task_pass_rate": round(passed_tasks / total_tasks, 4) if total_tasks else 0.0,
        "total_cases": total_cases,
        "passed_cases": passed_cases,
        "case_pass_rate": round(passed_cases / total_cases, 4) if total_cases else 0.0,
        "results": task_results,
    }


def format_report(data: dict[str, Any]) -> str:
    lines = [
        "🎯 Agent1-bench 客观评测报告（QuixBugs 图算法）",
        "=" * 56,
        f"时间: {data['timestamp']}",
        f"数据源: {data['source']}",
        f"任务通过率: {data['task_pass_rate']*100:.1f}% "
        f"({data['passed_tasks']}/{data['total_tasks']})",
        f"用例通过率: {data['case_pass_rate']*100:.1f}% "
        f"({data['passed_cases']}/{data['total_cases']})",
        "",
        "📋 逐任务结果:",
    ]
    for r in data["results"]:
        icon = {"PASS": "✅", "FAIL": "❌", "ERROR": "⚠️"}.get(r["status"], "•")
        lines.append(f"  {icon} {r['task']:24s} {r.get('passed',0)}/{r.get('total',0)}")
    return "\n".join(lines)


def main() -> int:
    answers = load_answers()
    data = run_all(answers)
    RESULTS_FILE.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    sys.stdout.reconfigure(encoding="utf-8")
    print(format_report(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
