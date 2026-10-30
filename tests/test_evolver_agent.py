"""
Evolver Agent 单元测试
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tools.evolver_agent import (
    EvolverAgent, EvolutionDomain, EVOLUTION_DOMAINS,
)
from tools.specialist_base import TaskInput, TaskStatus


def test_agent_creation():
    """创建 Evolver Agent"""
    agent = EvolverAgent()
    assert agent.agent_id == "evolver"
    assert agent.name == "Evolver"
    assert agent.specialist_type == "evolver"
    assert "research" in agent.capabilities
    assert "design" in agent.capabilities
    assert "implementation" in agent.capabilities
    assert "evaluation" in agent.capabilities
    assert "architecture" in agent.capabilities
    print("✅ 测试1 创建 Evolver: 通过")


def test_agent_tools():
    """Evolver 工具集"""
    agent = EvolverAgent()
    tools = agent.tools
    assert "read_file" in tools
    assert "write_file" in tools
    assert "web_search" in tools
    assert "knowledge" in tools
    assert "monitor" in tools
    assert "self_check" in tools
    assert "test_runner" in tools
    assert "task_tracker" in tools
    assert "specialist" in tools
    assert "agent_profile" in tools
    assert "orchestrator" in tools
    print("✅ 测试2 工具集: 通过")


def test_system_prompt():
    """系统提示词"""
    agent = EvolverAgent()
    prompt = agent.get_system_prompt()
    assert "Evolver" in prompt
    # 身份标识：人设已迁移至 village/personas.md 作为单一事实来源，
    # 断言校验稳健特征（进化/智能体/agent），不再绑定固定文案，避免文案迭代即失败
    assert any(k in prompt.lower() for k in ("进化", "智能体", "agent"))
    assert "调研" in prompt or "实现" in prompt
    print("✅ 测试3 系统提示词: 通过")


def test_evolution_domains():
    """进化领域定义"""
    assert EvolutionDomain.ARCHITECTURE == "architecture"
    assert EvolutionDomain.TOOLING == "tooling"
    assert EvolutionDomain.PERFORMANCE == "performance"
    assert EvolutionDomain.ROBUSTNESS == "robustness"
    assert EvolutionDomain.CAPABILITY == "capability"
    assert EvolutionDomain.RESEARCH == "research"
    assert EvolutionDomain.MAINTENANCE == "maintenance"

    for domain_key in EVOLUTION_DOMAINS:
        assert EVOLUTION_DOMAINS[domain_key], f"{domain_key} 无描述"
    print("✅ 测试4 进化领域: 通过")


def test_research_topics():
    """研究主题"""
    assert len(EvolverAgent.RESEARCH_TOPICS) >= 8
    for topic in EvolverAgent.RESEARCH_TOPICS:
        assert len(topic) > 10, f"主题太短: {topic}"
    print("✅ 测试5 研究主题: 通过")


def test_architecture_checks():
    """架构检查规则"""
    assert len(EvolverAgent.ARCHITECTURE_CHECKS) >= 6
    total_weight = sum(c["weight"] for c in EvolverAgent.ARCHITECTURE_CHECKS)
    assert 0.9 <= total_weight <= 1.1, f"权重总和应接近 1.0: {total_weight}"
    print("✅ 测试6 架构检查: 通过")


def test_process_task_survey():
    """调研任务"""
    agent = EvolverAgent()
    task = TaskInput(
        task_id="T001",
        description="调研multi-agent协作",
        params={"action": "survey", "target": "multi-agent collaboration"},
    )
    result = agent.process_task(task)
    assert result.status == TaskStatus.DONE.value
    assert result.summary
    assert "调研" in result.summary or "survey" in str(result.output).lower()
    assert "recommended_search" in str(result.output)
    print("✅ 测试7 调研任务: 通过")


def test_process_task_evaluate():
    """评估任务"""
    agent = EvolverAgent()
    task = TaskInput(
        task_id="T002",
        description="评估添加向量数据库的可行性",
        params={"action": "evaluate", "target": "向量数据库集成"},
    )
    result = agent.process_task(task)
    assert result.status == TaskStatus.DONE.value
    assert "评估" in result.summary or "evaluate" in str(result.output).lower()
    assert len(agent._improvement_backlog) >= 1
    print("✅ 测试8 评估任务: 通过")


def test_process_task_implement():
    """实现任务"""
    agent = EvolverAgent()
    task = TaskInput(
        task_id="T003",
        description="实现日志轮转",
        params={"action": "implement", "target": "添加日志轮转功能"},
    )
    result = agent.process_task(task)
    assert result.status == TaskStatus.DONE.value
    assert "implementation_plan" in str(result.output) or "实现" in result.summary
    assert len(agent._evolution_log) >= 1
    print("✅ 测试9 实现任务: 通过")


def test_process_task_maintain():
    """维护任务"""
    agent = EvolverAgent()
    task = TaskInput(
        task_id="T004",
        description="系统维护",
        params={"action": "maintain"},
    )
    result = agent.process_task(task)
    assert result.status == TaskStatus.DONE.value
    assert "maintenance_plan" in str(result.output) or "维护" in result.summary
    print("✅ 测试10 维护任务: 通过")


def test_process_task_health():
    """架构健康检查"""
    agent = EvolverAgent()
    task = TaskInput(
        task_id="T005",
        description="架构健康检查",
        params={"action": "health"},
    )
    result = agent.process_task(task)
    assert result.status == TaskStatus.DONE.value
    output = result.output
    assert "architecture_checks" in str(output)
    assert "health_score" in str(output)
    print("✅ 测试11 架构健康检查: 通过")


def test_process_task_backlog():
    """查看 backlog"""
    agent = EvolverAgent()
    # 先添加一些评估
    for i in range(2):
        task = TaskInput(
            task_id=f"TB{i}",
            description=f"评估{i}",
            params={"action": "evaluate", "target": f"提案{i}"},
        )
        agent.process_task(task)

    task = TaskInput(
        task_id="T006",
        description="查看backlog",
        params={"action": "backlog"},
    )
    result = agent.process_task(task)
    assert result.status == TaskStatus.DONE.value
    assert "total" in str(result.output)
    print("✅ 测试12 查看 backlog: 通过")


def test_process_task_log():
    """查看进化日志"""
    agent = EvolverAgent()
    task = TaskInput(
        task_id="T007",
        description="查看日志",
        params={"action": "log"},
    )
    result = agent.process_task(task)
    assert result.status == TaskStatus.DONE.value
    print("✅ 测试13 进化日志: 通过")


def test_process_task_invalid_action():
    """无效操作"""
    agent = EvolverAgent()
    task = TaskInput(
        task_id="T008",
        description="无效操作",
        params={"action": "nonexistent"},
    )
    result = agent.process_task(task)
    assert result.status == TaskStatus.FAILED.value
    print("✅ 测试14 拒绝无效操作: 通过")


def test_chat():
    """对话回应"""
    agent = EvolverAgent()
    response = agent.chat("帮我调研最新的Agent框架", {})
    assert "Evolver" in response
    assert "进化" in response or "调研" in response
    # 应包含操作提示
    assert "survey" in response.lower() or "operate" in response.lower()
    print("✅ 测试15 对话回应: 通过")


if __name__ == "__main__":
    print("=" * 50)
    print("🧪 Evolver Agent 单元测试")
    print("=" * 50)
    test_agent_creation()
    test_agent_tools()
    test_system_prompt()
    test_evolution_domains()
    test_research_topics()
    test_architecture_checks()
    test_process_task_survey()
    test_process_task_evaluate()
    test_process_task_implement()
    test_process_task_maintain()
    test_process_task_health()
    test_process_task_backlog()
    test_process_task_log()
    test_process_task_invalid_action()
    test_chat()
    print()
    print("=" * 50)
    print("🎉 所有测试通过！")
    print("=" * 50)
