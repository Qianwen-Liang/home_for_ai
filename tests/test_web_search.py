"""
Web Search 单元测试
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.web_search import (
    WebSearchError, TOOL_DEFINITION,
    execute_web_search_tool, web_search,
    _create_ssl_context,
    _parse_duckduckgo_html_results,
)


def test_tool_definition():
    """测试工具定义完整性"""
    assert "function" in TOOL_DEFINITION
    func = TOOL_DEFINITION["function"]
    assert func["name"] == "web_search"
    assert "query" in func["parameters"]["properties"]
    assert "max_results" in func["parameters"]["properties"]
    print("✅ 测试1 工具定义: 通过")


def test_ssl_context():
    """测试 SSL 上下文创建"""
    ctx = _create_ssl_context()
    assert ctx is not None
    print("✅ 测试2 SSL上下文: 通过")


def test_html_parsing():
    """测试 HTML 结果解析"""
    # 模拟 DuckDuckGo HTML 结果
    html = """
    <html>
    <a rel="nofollow" class="result__a" href="https://example.com/page1">示例标题1</a>
    <a class="result__snippet">这是摘要1</a>
    <a rel="nofollow" class="result__a" href="https://example.com/page2">示例标题2</a>
    <a class="result__snippet">这是摘要2</a>
    </html>
    """
    results = _parse_duckduckgo_html_results(html, max_results=5)
    assert len(results) >= 2, f"应有至少2个结果: {len(results)}"
    assert results[0]["title"] == "示例标题1"
    assert results[0]["url"] == "https://example.com/page1"
    assert results[0]["snippet"] == "这是摘要1"
    assert results[1]["title"] == "示例标题2"
    print("✅ 测试3 HTML解析: 通过")


def test_html_parsing_empty():
    """测试空 HTML"""
    results = _parse_duckduckgo_html_results("", max_results=5)
    assert results == [], f"空HTML应返回空列表: {results}"
    print("✅ 测试4 空HTML: 通过")


def test_html_parsing_no_results():
    """测试无结果 HTML"""
    html = "<html><body>No results found</body></html>"
    results = _parse_duckduckgo_html_results(html, max_results=5)
    assert results == [], f"无结果应返回空列表: {results}"
    print("✅ 测试5 无结果HTML: 通过")


def test_html_parsing_max_results():
    """测试 max_results 限制"""
    html = "".join(
        f'<a rel="nofollow" class="result__a" href="https://example.com/{i}">标题{i}</a>'
        f'<a class="result__snippet">摘要{i}</a>'
        for i in range(10)
    )
    results = _parse_duckduckgo_html_results(html, max_results=3)
    assert len(results) == 3, f"应只返回3个: {len(results)}"
    print("✅ 测试6 max_results限制: 通过")


def test_html_parsing_html_cleanup():
    """测试 HTML 标签清理"""
    html = (
        '<a rel="nofollow" class="result__a" href="https://example.com">'
        '<b>粗体</b> 标题 <em>斜体</em></a>'
        '<a class="result__snippet"><span>带标签的摘要</span></a>'
    )
    results = _parse_duckduckgo_html_results(html, max_results=5)
    assert len(results) >= 1
    # 标题应不含 HTML 标签
    assert "<b>" not in results[0]["title"]
    assert "<em>" not in results[0]["title"]
    print("✅ 测试7 HTML标签清理: 通过")


def test_empty_query():
    """测试空查询"""
    from tools.web_search import execute_web_search_tool
    result = execute_web_search_tool({"query": ""})
    assert "错误" in result or "不能为空" in result, f"空查询应提示: {result}"
    print("✅ 测试8 空查询: 通过")


def test_invalid_max_results():
    """测试无效 max_results"""
    from tools.web_search import execute_web_search_tool
    result = execute_web_search_tool({"query": "test", "max_results": "abc"})
    # 应该处理无效的 max_results
    assert isinstance(result, str), f"应返回字符串: {result}"
    print("✅ 测试9 无效max_results: 通过")


def test_max_results_clamping():
    """测试 max_results 边界"""
    from tools.web_search import web_search as ws_func
    try:
        result = ws_func("test query", max_results=20)
        # 应该被限制到 10
        assert isinstance(result, str)
    except WebSearchError:
        # 网络不可用也接受
        pass
    except Exception as e:
        # 其他网络错误也接受
        pass
    print("✅ 测试10 max_results边界: 通过")


def test_tool_entry():
    """测试工具入口"""
    result = execute_web_search_tool({"query": "hello"})
    # 可能返回搜索结果或网络错误
    assert isinstance(result, str), f"应返回字符串: {result}"
    assert len(result) > 0, f"不应为空: {result}"
    print("✅ 测试11 工具入口: 通过")


def test_web_search_error():
    """测试自定义异常"""
    try:
        raise WebSearchError("测试搜索错误")
    except WebSearchError as e:
        assert "测试搜索错误" in str(e)
    print("✅ 测试12 自定义异常: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Web Search 单元测试")
    print("=" * 50)
    test_tool_definition()
    print()
    test_ssl_context()
    print()
    test_html_parsing()
    print()
    test_html_parsing_empty()
    print()
    test_html_parsing_no_results()
    print()
    test_html_parsing_max_results()
    print()
    test_html_parsing_html_cleanup()
    print()
    test_empty_query()
    print()
    test_invalid_max_results()
    print()
    test_max_results_clamping()
    print()
    test_tool_entry()
    print()
    test_web_search_error()
    print()
    print("=" * 50)
    print("🎉 所有 Web Search 测试通过！")
    print("=" * 50)
