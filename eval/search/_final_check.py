import sys, py_compile
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent.parent
for f in ["tools/search_router.py", "tools/search_sources.py", "tools/web_search.py"]:
    py_compile.compile(str(ROOT / f), doraise=True)
print("✅ 三个文件语法校验通过")

sys.path.insert(0, str(ROOT))
from tools.search_router import FAST_PROFILE, DEEP_PROFILE, SLOW_SOURCES, _quality_ok
print(f"fast 配置: {FAST_PROFILE}")
print(f"deep 配置: {DEEP_PROFILE}")
print(f"慢源规避: {SLOW_SOURCES}")
