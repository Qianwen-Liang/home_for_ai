"""批量把各源 _http_get 调用超时统一降到 5s"""
import re
from pathlib import Path

p = Path(__file__).resolve().parent.parent.parent / "tools" / "search_sources.py"
src = p.read_text(encoding="utf-8")

# 只替换 _http_get(...) 调用体内的 timeout=15 / timeout=8
before = len(re.findall(r"_http_get\([^)]*timeout=(?:15|8)\b", src))
src_new = re.sub(r"(_http_get\([^)]*?)timeout=(?:15|8)\b", r"\1timeout=5", src)

# _http_get 默认参数保持 8.0 不变（仅改调用点）
assert "def _http_get(url: str, timeout: float = 8.0" in src_new, "默认参数被误改"

p.write_text(src_new, encoding="utf-8")
after = len(re.findall(r"_http_get\([^)]*timeout=(?:15|8)\b", src_new))
print(f"替换前含 15/8 的调用点: {before}")
print(f"替换后剩余: {after}")
print("各源 timeout 现值:", re.findall(r"timeout=(\d+)[,)]", src_new))
