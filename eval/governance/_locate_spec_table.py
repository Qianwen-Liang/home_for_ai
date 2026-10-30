from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
p = ROOT / "agent1.py"
s = p.read_text(encoding="utf-8")
i = s.find("_TOOL_SPEC_TABLE = [")
j = s.find("\n]\n", i)
if j < 0:
    j = s.find("]\n", i)
print("起始", i, "结束", j)
seg = s[i:j + 2]
print("段长度", len(seg), "行数", seg.count("\n") + 1)
print("--- 前 400 字符 ---")
print(seg[:400])
print("--- 后 300 字符 ---")
print(seg[-300:])
