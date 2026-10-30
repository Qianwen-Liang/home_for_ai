"""补齐落地缺口：用 jsonschema 做真正的参数契约校验（C7 新增断言）"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

import json
import jsonschema
from jsonschema import Draft202012Validator
import agent1

print("jsonschema 版本:", __import__("importlib.metadata", fromlist=["version"]).version("jsonschema"))

# 1) 校验每个工具的 parameters 本身是否为合法 JSON Schema
print("\n── 工具 parameters 是否为合法 JSON Schema 2020-12 ──")
bad = []
for t in agent1.ALL_TOOLS:
    fn = t.get("function", {})
    name = fn.get("name")
    schema = fn.get("inputSchema") or fn.get("parameters")
    try:
        Draft202012Validator.check_schema(schema)
        print(f"  ✅ {name}")
    except jsonschema.SchemaError as e:
        bad.append(name)
        print(f"  ❌ {name}: {str(e.message)[:80]}")
print(f"\n合法 {len(agent1.ALL_TOOLS) - len(bad)}/{len(agent1.ALL_TOOLS)}")

# 2) 用 jsonschema 验证：合法参数应通过，非法参数应被拒
print("\n── 参数校验示例（jsonschema 实际生效）──")
schema = next(t for t in agent1.ALL_TOOLS
              if t["function"]["name"] == "calculate")["function"]["parameters"]
v = Draft202012Validator(schema)
cases = [
    ({"expression": "1+1"}, True),
    ({"expression": 123}, False),          # 类型错误
    ({}, False),                            # 缺必填
    ({"expression": "1+1", "precision": "x"}, False),  # 可选参数类型错误
]
for args, should_pass in cases:
    errs = list(v.iter_errors(args))
    ok = not errs
    flag = "✅" if ok == should_pass else "❌"
    print(f"  {flag} {args} -> valid={ok} (期望 {should_pass})")
