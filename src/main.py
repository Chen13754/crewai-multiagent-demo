# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv


# Resolve project-level paths from this file so the script can be launched
# from any current working directory.
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
    # Prefer an explicitly configured model, but keep a DeepSeek default so the
    # demo can run with only an API key and no extra model setting.
    model_name = (
        os.getenv("MODEL")
        or os.getenv("MODEL_NAME")
        or os.getenv("OPENAI_MODEL_NAME")
        or "deepseek/deepseek-v4-flash"
    )

    # First agent: turns a broad or vague product idea into concrete user needs,
    # scenarios, pain points, and demo success criteria.
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

    # Second agent: converts the research output into an implementable multi
    # agent product/demo architecture.
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

    # Third agent: reviews the proposed design for practical risks, unclear
    # assumptions, unnecessary complexity, and missing constraints.
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

    # Task 1 runs without prior context and asks the researcher to produce the
    # base requirements analysis for the given topic.
    research_task = Task(
        description=(
            "围绕主题《{topic}》做需求分析。请输出：目标用户、核心痛点、"
            "三个典型使用场景、Demo 成功标准、最小可行范围。"
        ),
        expected_output="一份结构清晰的中文需求分析，包含可直接给下游 agent 使用的要点。",
        agent=researcher,
    )

    # Task 2 depends on Task 1. CrewAI passes the research task result as context
    # so the architect can design from the requirements instead of starting cold.
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

    # Task 3 depends on Task 2. The reviewer evaluates the proposed design and
    # produces a final recommendation after identifying risks and simplifications.
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

    # Run all agents in a fixed sequence: research first, architecture second,
    # review last. This makes the output easier to inspect and debug.
    return Crew(
        agents=[researcher, architect, reviewer],
        tasks=[research_task, design_task, review_task],
        process=Process.sequential,
        verbose=True,
    )


def main() -> None:
    # Load local secrets/configuration before checking API keys or selecting the
    # model. Values already present in the environment still take precedence.
    load_dotenv(ROOT / ".env")

    # CrewAI needs an LLM provider key. This script accepts either DeepSeek or
    # OpenAI credentials, matching the model configuration above.
    if not (os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")):
        raise SystemExit(
            "缺少 API key。请复制 .env.example 为 .env，并填入 DEEPSEEK_API_KEY。"
        )

    topic = " ".join(sys.argv[1:]).strip() or "给个人知识管理用户做一个 AI 知识库助手"
    # Use command-line arguments as the topic when provided; otherwise the topic
    # variable above falls back to the built-in demo topic.
    crew = build_crew(topic)
    # Start the CrewAI workflow. The input key must match the {topic} placeholder
    # used in task descriptions.
    result = crew.kickoff(inputs={"topic": topic})

    # Persist the final crew result for later review, then also print it to the
    # terminal for immediate feedback.
    OUTPUT_DIR.mkdir(exist_ok=True)
    OUTPUT_FILE.write_text(str(result), encoding="utf-8")

    print("\n\n===== FINAL RESULT =====\n")
    print(result)
    print(f"\n已保存到: {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
