# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


# 基于当前文件位置计算项目级路径，这样无论从哪个目录启动脚本都能找到资源。
ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs"
OUTPUT_FILE = OUTPUT_DIR / "latest_result.md"
CREWAI_STORAGE_DIR = ROOT / ".cache" / "crewai"
LOCAL_APP_DATA = ROOT / ".cache" / "localappdata"

# CrewAI reads these at import time, so keep them before importing crewai.
os.environ.setdefault("CREWAI_STORAGE_DIR", str(CREWAI_STORAGE_DIR))
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ["LOCALAPPDATA"] = str(LOCAL_APP_DATA)
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
os.environ.setdefault("CREWAI_TESTING", "true")

from crewai import Agent, Crew, Process, Task


def build_crew(topic: str) -> Crew:
    # 优先使用环境变量中显式配置的模型；如果没有配置，则使用 DeepSeek 默认模型。
    model_name = (
        os.getenv("MODEL")
        or os.getenv("MODEL_NAME")
        or os.getenv("OPENAI_MODEL_NAME")
        or "deepseek/deepseek-v4-flash"
    )

    # 第一个 agent：把宽泛或模糊的产品想法拆解为具体的用户、场景、痛点和成功标准。
    researcher = Agent(
        role="Researcher",
        goal="把模糊想法拆成清晰的用户、场景、痛点和成功标准。",
        backstory=(
            "你是一名偏实战的产品研究员，擅长从一句需求里识别目标用户、"
            "关键使用场景、约束条件和最小可行版本。"
        ),
        llm=model_name,
        verbose=True,
    )

    # 第二个 agent：把研究结果转化为可实现、可演示的多 agent 产品架构。
    architect = Agent(
        role="Solution Architect",
        goal="基于研究结论设计一个可演示、可实现的多 agent 产品方案。",
        backstory=(
            "你是一名工程背景很强的产品架构师，喜欢把方案落到模块、流程、"
            "数据结构、工具接口和演示步骤上。"
        ),
        llm=model_name,
        verbose=True,
    )

    # 第三个 agent：审查方案中的实际风险、模糊假设、过度复杂度和缺失约束。
    reviewer = Agent(
        role="Critical Reviewer",
        goal="发现方案中的风险、含糊点和过度设计，并给出务实改进建议。",
        backstory=(
            "你是一名严谨的技术评审，关注边界条件、成本、失败场景、"
            "可观测性和用户真正能体验到的价值。"
        ),
        llm=model_name,
        verbose=True,
    )

    # 任务 1 不依赖前置上下文，用于让研究员围绕主题产出基础需求分析。
    research_task = Task(
        description=(
            "围绕主题《{topic}》做需求分析。请输出：目标用户、核心痛点、"
            "三个典型使用场景、Demo 成功标准、最小可行范围。"
        ),
        expected_output="一份结构清晰的中文需求分析，包含可直接给下游 agent 使用的要点。",
        agent=researcher,
    )

    # 任务 2 依赖任务 1。CrewAI 会把需求分析结果作为上下文传给架构师。
    design_task = Task(
        description=(
            "基于上一步需求分析，设计一个多 agent Demo 方案。请说明："
            "agent 角色分工、协作流程、输入输出、关键提示词思路、"
            "最小代码结构和一次完整演示步骤。"
        ),
        expected_output="一份中文多 agent Demo 设计方案，足够让开发者开始实现。",
        agent=architect,
        context=[research_task],
    )

    # 任务 3 依赖任务 2。评审员会检查设计方案，并在识别风险后给出最终建议。
    review_task = Task(
        description=(
            "评审上一步方案。请指出主要风险、遗漏点、可以简化的地方，"
            "然后给出一版最终建议。最终建议要保留多 agent 协作的学习价值，"
            "但避免为了炫技而复杂化。"
        ),
        expected_output="一份中文评审意见和最终推荐方案。",
        agent=reviewer,
        context=[design_task],
    )

    # 按固定顺序运行所有 agent：先研究，再设计，最后评审，便于检查和调试输出。
    return Crew(
        agents=[researcher, architect, reviewer],
        tasks=[research_task, design_task, review_task],
        process=Process.sequential,
        verbose=True,
    )


def main() -> None:
    # 先加载本地 .env 配置，再检查 API key 或选择模型；已有环境变量仍然优先生效。
    load_dotenv(ROOT / ".env")

    # CrewAI 需要大模型服务的 API key；这里同时支持 DeepSeek 和 OpenAI。
    if not (os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")):
        raise SystemExit(
            "缺少 API key。请复制 .env.example 为 .env，并填入 DEEPSEEK_API_KEY。"
        )

    topic = " ".join(sys.argv[1:]).strip() or "给个人知识管理用户做一个 AI 知识库助手"
    # 如果命令行传入了参数，就作为主题；否则使用上面的内置演示主题。
    crew = build_crew(topic)
    # 启动 CrewAI 工作流。inputs 中的 topic 会对应任务描述里的 {topic} 占位符。
    result = crew.kickoff(inputs={"topic": topic})

    # 将最终结果保存到文件，方便后续查看；同时也打印到终端，便于立即确认输出。
    OUTPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(str(result), encoding="utf-8")

    print("\n\n===== FINAL RESULT =====\n")
    print(result)
    print(f"\n已保存到: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
