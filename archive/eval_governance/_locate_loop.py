from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
s = (ROOT / "agent1.py").read_text(encoding="utf-8")
i = s.find("for _name, _handler")
print("找到于:", i)
if i > 0:
    print(repr(s[i:i + 480]))
else:
    # 找注册循环
    j = s.find("REGISTRY.register")
    print("REGISTRY.register 位置:", j)
    print(repr(s[max(0, j - 300):j + 400]))
