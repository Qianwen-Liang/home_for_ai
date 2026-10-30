import re
src = open("tools/knowledge_store.py", encoding="utf-8").read()
lines = src.splitlines()
for i, l in enumerate(lines):
    if re.match(r"class (SemanticSearchEngine|SearchEnhancer)", l):
        print("=" * 60)
        print("--- line", i + 1, ":", l.strip())
        print("=" * 60)
        # 打印到下一个 class 或 40 行
        end = min(i + 45, len(lines))
        for j in range(i, end):
            if j > i and re.match(r"class ", lines[j]):
                break
            print(lines[j])
        print()
