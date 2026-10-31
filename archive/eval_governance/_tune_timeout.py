"""把各源 _http_get 超时从 5s 降到 3.5s（多候选重试下最坏 2x=7s）"""
import re
from pathlib import Path

p = Path(__file__).resolve().parent.parent.parent / "tools" / "search_sources.py"
src = p.read_text(encoding="utf-8")

PAT = r"_http_get\([^)]*timeout=5\b"
n_before = len(re.findall(PAT, src))
src = re.sub(r"(_http_get\([^)]*?)timeout=5\b", r"\1timeout=3.5", src)
p.write_text(src, encoding="utf-8")
n_after = len(re.findall(PAT, src))
print("替换调用点:", n_before, "-> 剩余", n_after)
print("现超时值:", re.findall(r"timeout=([\d.]+)[,)]", src))
