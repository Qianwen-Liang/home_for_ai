from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
lines = (ROOT / "agent1.py").read_text(encoding="utf-8").splitlines()
# 找埋点与 _tool_success 初始化
for i, l in enumerate(lines):
    if "_tool_start_time" in l or "_tool_success = True" in l or "tool_monitor._monitor.record" in l:
        print(f"{i+1:5}| {l}")
print("---")
# 打印埋点前后上下文
for i, l in enumerate(lines):
    if "tool_monitor._monitor.record" in l:
        for j in range(max(0, i - 12), min(i + 6, len(lines))):
            print(f"{j+1:5}| {lines[j]}")
        break
