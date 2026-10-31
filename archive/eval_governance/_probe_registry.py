"""步骤2 关键假设实测：dict查表 vs if-elif；字节稳定性"""
import timeit, json, hashlib

NAMES = ['run_command', 'write_file', 'replace_text', 'web_search', 'task_tracker',
         'knowledge', 'read_file', 'list_directory', 'calculate', 'self_check',
         'test_runner', 'safe_deploy', 'artifact_validator', 'evidence_verifier',
         'multi_reviewer', 'make_directory']

# ── 1) dict 查表 vs if-elif 链 ──
tbl = {n: (lambda a: a) for n in NAMES}
src = "def lookup(name):\n"
for n in NAMES:
    src += f"    if name == {n!r}:\n        return 1\n"
src += "    return None\n"
ns = {}
exec(src, ns)
lookup = ns["lookup"]

N = 200_000
t_dict = timeit.timeit(lambda: tbl.get("read_file"), number=N)
t_elif = timeit.timeit(lambda: lookup("read_file"), number=N)
print("── 分派性能（命中第 7 项 read_file）──")
print(f"  dict.get : {t_dict*1000:7.1f}ms ({t_dict/N*1e9:5.0f} ns/次)")
print(f"  if-elif  : {t_elif*1000:7.1f}ms ({t_elif/N*1e9:5.0f} ns/次)")
print(f"  加速比   : {t_elif/t_dict:.2f}x")

# 最坏情况：命中最后一项
t_elif_last = timeit.timeit(lambda: lookup("make_directory"), number=N)
print(f"  if-elif 命中末项: {t_elif_last*1000:.1f}ms  → 与首项差 {t_elif_last/t_elif:.2f}x（位置相关）")

# ── 2) 字节稳定性：同一工具集序列化是否稳定 ──
print("\n── 字节稳定性（prompt caching 关键）──")
s1 = json.dumps([{"function": {"name": n}} for n in NAMES], ensure_ascii=False)
s2 = json.dumps([{"function": {"name": n}} for n in NAMES], ensure_ascii=False)
print(f"  两次序列化一致: {s1 == s2}")
print(f"  sha256: {hashlib.sha256(s1.encode()).hexdigest()[:16]}")

# 顺序敏感性
s3 = json.dumps([{"function": {"name": n}} for n in sorted(NAMES)], ensure_ascii=False)
print(f"  排序后是否相同: {s1 == s3}  → 顺序变化会改变前缀哈希")

# dict 迭代顺序（Python 3.7+ 保序）
d = {}
for n in NAMES:
    d[n] = 1
print(f"  dict 保序: {list(d.keys()) == NAMES}")

# ── 3) 装饰器注册的开销 ──
print("\n── 装饰器注册开销（应在导入期一次性付出）──")
REG = {}
def make_registry(n_items):
    r = {}
    def register(name):
        def deco(fn):
            r[name] = fn
            return fn
        return deco
    return register, r

for cnt in (16, 42, 100):
    reg_fn, r = make_registry(cnt)
    def build():
        for i in range(cnt):
            @reg_fn(f"t{i}")
            def f(x):
                return x
    t = timeit.timeit(build, number=200)
    print(f"  注册 {cnt:3d} 个工具: {t/200*1000:.3f} ms/轮")
