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
SUMMARY_FILE = OUTPUT_DIR / "latest_summary.md"
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


def task_output_text(task_output: object) -> str:
    # CrewAI 的任务输出通常有 raw 字段；如果版本不同，就退回到字符串形式。
    raw = getattr(task_output, "raw", None)
    return str(raw if raw is not None else task_output)


def build_crew(topic: str) -> Crew:
    # 优先使用环境变量中显式配置的模型；如果没有配置，则使用 DeepSeek 默认模型。
    model_name = (
        os.getenv("MODEL")
        or os.getenv("MODEL_NAME")
        or os.getenv("OPENAI_MODEL_NAME")
        or "deepseek/deepseek-v4-flash"
    )

    # 第一个 agent：把问题背景拆解清楚，识别目标、约束、相关方和关键矛盾。
    analyst = Agent(
        role="Problem Analyst",
        goal="把模糊问题拆成清晰的背景、目标、约束、关键矛盾和判断标准。",
        backstory=(
            "你是一名擅长结构化思考的问题分析师，能够从不完整描述中梳理事实、"
            "假设、未知信息、利益相关方、限制条件和优先级。"
        ),
        llm=model_name,
        verbose=True,
    )

    # 第二个 agent：基于问题分析提出可执行的解决方案和实施路径。
    solver = Agent(
        role="Solution Strategist",
        goal="基于问题分析设计可执行、可验证、成本可控的解决方案。",
        backstory=(
            "你是一名务实的解决方案专家，习惯把抽象目标落到策略选项、"
            "执行步骤、资源需求、里程碑和验证方式上。"
        ),
        llm=model_name,
        verbose=True,
    )

    # 第三个 agent：审查方案中的实际风险、模糊假设、过度复杂度和缺失约束。
    reviewer = Agent(
        role="Critical Reviewer",
        goal="发现解决方案中的风险、遗漏、脆弱假设和过度设计，并给出务实改进建议。",
        backstory=(
            "你是一名严谨的评审者，关注边界条件、机会成本、失败场景、"
            "可观测指标和真实可落地性。"
        ),
        llm=model_name,
        verbose=True,
    )

    # 第四个 agent：在完整报告之外，额外生成便于快速阅读和决策的精简报告。
    summarizer = Agent(
        role="Executive Summarizer",
        goal="把完整分析和建议压缩成重点明确、可快速阅读的中文精简报告。",
        backstory=(
            "你是一名擅长高密度表达的总结者，能够保留结论、关键理由、"
            "优先行动和主要风险，同时删除重复解释和次要细节。"
        ),
        llm=model_name,
        verbose=True,
    )

    # 任务 1 不依赖前置上下文，用于围绕主题产出结构化问题分析。
    analysis_task = Task(
        description=(
            "围绕主题《{topic}》做通用问题分析。请输出：问题背景、核心目标、"
            "关键事实与假设、利益相关方、约束条件、主要矛盾、成功标准、"
            "仍需澄清的问题。"
        ),
        expected_output="一份结构清晰的中文问题分析，包含可直接给下游 agent 使用的要点。",
        agent=analyst,
    )

    # 任务 2 依赖任务 1。CrewAI 会把问题分析结果作为上下文传给方案设计者。
    solution_task = Task(
        description=(
            "基于上一步问题分析，设计一套可执行的解决方案。请说明："
            "总体思路、可选方案对比、推荐方案、执行步骤、资源需求、"
            "优先级、里程碑、验证指标和应急预案。"
        ),
        expected_output="一份中文解决方案报告，足够让执行者开始落地。",
        agent=solver,
        context=[analysis_task],
    )

    # 任务 3 依赖任务 2。评审员会检查解决方案，并在识别风险后给出完整报告。
    review_task = Task(
        description=(
            "评审上一步解决方案。请指出主要风险、遗漏点、脆弱假设、"
            "可以简化的地方和需要补充的数据，然后给出一版最终完整报告。"
            "最终报告需要包含：问题定义、推荐方案、执行计划、风险控制、"
            "验证指标和下一步行动。"
        ),
        expected_output="一份中文完整报告，包含评审意见和最终推荐方案。",
        agent=reviewer,
        context=[solution_task],
    )

    # 任务 4 依赖任务 3。总结者会在完整报告之外生成一份更短的精简报告。
    summary_task = Task(
        description=(
            "基于完整报告生成一份额外的中文精简报告。请控制在 500 字以内，"
            "保留：一句话结论、最重要的 3 个理由、优先行动、最大风险、"
            "需要立即确认的问题。不要重复完整报告中的长段解释。"
        ),
        expected_output="一份 500 字以内的中文精简报告，适合快速阅读和转发。",
        agent=summarizer,
        context=[review_task],
    )

    # 按固定顺序运行所有 agent：先分析，再解法设计，再评审，最后总结。
    return Crew(
        agents=[analyst, solver, reviewer, summarizer],
        tasks=[analysis_task, solution_task, review_task, summary_task],
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

    topic = " ".join(sys.argv[1:]).strip() or "分析并解决一个需要多方权衡的复杂问题"
    # 如果命令行传入了参数，就作为主题；否则使用上面的内置演示主题。
    crew = build_crew(topic)
    # 启动 CrewAI 工作流。inputs 中的 topic 会对应任务描述里的 {topic} 占位符。
    result = crew.kickoff(inputs={"topic": topic})

    # 将完整报告和精简报告分别保存到文件，方便后续查看；同时也打印到终端。
    OUTPUT_DIR.mkdir(exist_ok=True)
    task_outputs = getattr(result, "tasks_output", None) or []
    full_report = task_output_text(task_outputs[2]) if len(task_outputs) >= 3 else str(result)
    concise_report = task_output_text(task_outputs[3]) if len(task_outputs) >= 4 else str(result)

    OUTPUT_FILE.write_text(full_report, encoding="utf-8")
    SUMMARY_FILE.write_text(concise_report, encoding="utf-8")

    print("\n\n===== FULL REPORT =====\n")
    print(full_report)
    print(f"\n已保存到: {OUTPUT_FILE}")
    print("\n\n===== CONCISE REPORT =====\n")
    print(concise_report)
    print(f"\n精简报告已保存到: {SUMMARY_FILE}")


if __name__ == "__main__":
    main()
