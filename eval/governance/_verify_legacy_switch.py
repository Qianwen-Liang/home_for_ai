"""验证 legacy 配置化启停：改 JSON 即可增减工具（子进程验证）"""
import sys, json, subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
cfg_path = ROOT / "eval" / "governance" / "legacy_tools.json"

def run_probe():
    code = ("import sys; sys.path.insert(0,'.'); import agent1;"
            "print(len(agent1.ALL_TOOLS));"
            "print(','.join(agent1.ENABLED_LEGACY) or 'none')")
    r = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                       capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        return None, r.stderr.strip()[-200:]
    parts = r.stdout.strip().splitlines()
    return parts[0], parts[1] if len(parts) > 1 else ""

orig = json.loads(cfg_path.read_text(encoding="utf-8"))
backup = json.dumps(orig, ensure_ascii=False, indent=2)

try:
    # 基线：不启用
    n, en = run_probe()
    print(f"默认配置     -> 工具数 {n}, enabled={en}")

    # 启用 monitor
    orig["enabled_legacy"] = ["monitor"]
    cfg_path.write_text(json.dumps(orig, ensure_ascii=False, indent=2), encoding="utf-8")
    n2, en2 = run_probe()
    print(f"启用 monitor -> 工具数 {n2}, enabled={en2}")

    # 启用两个
    orig["enabled_legacy"] = ["monitor", "audit_log"]
    cfg_path.write_text(json.dumps(orig, ensure_ascii=False, indent=2), encoding="utf-8")
    n3, en3 = run_probe()
    print(f"启用 2 个    -> 工具数 {n3}, enabled={en3}")

    # 非法名字应被忽略（不应崩溃）
    orig["enabled_legacy"] = ["__nonexistent__"]
    cfg_path.write_text(json.dumps(orig, ensure_ascii=False, indent=2), encoding="utf-8")
    n4, en4 = run_probe()
    print(f"非法名容错   -> 工具数 {n4}, enabled={en4}")
finally:
    cfg_path.write_text(backup, encoding="utf-8")
    print("\n✅ 配置已恢复默认")
