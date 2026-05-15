# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from argparse import ArgumentParser, Namespace
from datetime import datetime
from pathlib import Path
from time import perf_counter

from dotenv import load_dotenv


# 基于当前文件位置计算项目级路径，这样无论从哪个目录启动脚本都能找到资源。
ROOT = Path(__file__).resolve().parents[1]
OUTPUT_DIR = ROOT / "outputs"
CREWAI_STORAGE_DIR = ROOT / ".cache" / "crewai"
LOCAL_APP_DATA = ROOT / ".cache" / "localappdata"
MODEL_ALIASES = {
    "flash": "deepseek-v4-flash",
    "pro": "deepseek-v4-pro",
}
CREWAI_PROVIDER_PREFIX = "deepseek/"

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


def parse_args() -> Namespace:
    default_model = default_model_alias()

    parser = ArgumentParser(description="运行通用问题解决多 Agent 工作流。")
    parser.add_argument(
        "--model",
        choices=sorted(MODEL_ALIASES),
        default=default_model,
        help="选择 DeepSeek 模型档位：flash 更快，pro 能力更强。",
    )
    parser.add_argument("topic", nargs="*", help="要分析和解决的问题主题。")
    return parser.parse_args()


def default_model_alias() -> str:
    configured_alias = os.getenv("MODEL_VARIANT", "")
    if configured_alias in MODEL_ALIASES:
        return configured_alias

    configured_model = (
        os.getenv("MODEL")
        or os.getenv("MODEL_NAME")
        or os.getenv("OPENAI_MODEL_NAME")
        or ""
    )
    for alias, model_name in MODEL_ALIASES.items():
        if configured_model in {model_name, crewai_model_name(model_name)}:
            return alias

    return "flash"


def formal_model_name(model_alias: str) -> str:
    # 命令行模型选择优先；如果传入未知别名，则退回到 flash。
    return MODEL_ALIASES.get(model_alias, MODEL_ALIASES["flash"])


def crewai_model_name(model_name: str) -> str:
    # CrewAI/LiteLLM 需要 deepseek/ 前缀来识别供应商；DeepSeek 正式模型名本身不带该前缀。
    if model_name.startswith(CREWAI_PROVIDER_PREFIX):
        return model_name
    return f"{CREWAI_PROVIDER_PREFIX}{model_name}"


def create_output_run_dir() -> Path:
    # 每次运行都创建独立目录，避免覆盖之前生成的完整报告和精简报告。
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = OUTPUT_DIR / timestamp
    suffix = 1

    while run_dir.exists():
        run_dir = OUTPUT_DIR / f"{timestamp}_{suffix:02d}"
        suffix += 1

    run_dir.mkdir(parents=True)
    return run_dir


def usage_to_dict(usage: object | None) -> dict[str, int]:
    if usage is None:
        return {}

    if hasattr(usage, "model_dump"):
        dumped = usage.model_dump()
        return {key: int(value) for key, value in dumped.items() if isinstance(value, int)}

    if isinstance(usage, dict):
        return {key: int(value) for key, value in usage.items() if isinstance(value, int)}

    fields = (
        "total_tokens",
        "prompt_tokens",
        "cached_prompt_tokens",
        "completion_tokens",
        "reasoning_tokens",
        "cache_creation_tokens",
        "successful_requests",
    )
    return {
        field: int(value)
        for field in fields
        if isinstance((value := getattr(usage, field, None)), int)
    }


def extract_token_usage(result: object, crew: Crew) -> dict[str, int]:
    # CrewAI 版本不同，token 统计可能挂在 result.token_usage 或 crew.usage_metrics 上。
    for usage in (
        getattr(result, "token_usage", None),
        getattr(result, "usage_metrics", None),
        getattr(crew, "usage_metrics", None),
        getattr(crew, "token_usage", None),
    ):
        usage_dict = usage_to_dict(usage)
        if usage_dict.get("total_tokens", 0) > 0:
            return usage_dict
    return {}


def write_run_metadata(
    metadata_file: Path,
    *,
    topic: str,
    model_alias: str,
    model_name: str,
    crewai_model: str,
    elapsed_seconds: float,
    token_usage: dict[str, int],
) -> None:
    lines = [
        "# 运行元数据",
        "",
        f"- 主题：{topic}",
        f"- 模型档位：{model_alias}",
        f"- 模型正式名：{model_name}",
        f"- CrewAI 模型字符串：{crewai_model}",
        f"- 总用时：{elapsed_seconds:.2f} 秒",
    ]

    if token_usage:
        lines.extend(
            [
                f"- 总 token：{token_usage.get('total_tokens', 0)}",
                f"- 输入 token：{token_usage.get('prompt_tokens', 0)}",
                f"- 输出 token：{token_usage.get('completion_tokens', 0)}",
                f"- 缓存输入 token：{token_usage.get('cached_prompt_tokens', 0)}",
                f"- 推理 token：{token_usage.get('reasoning_tokens', 0)}",
                f"- 成功请求数：{token_usage.get('successful_requests', 0)}",
            ]
        )
    else:
        lines.append("- token 用量：当前 CrewAI/模型返回中未读取到 token 统计。")

    metadata_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_crew(topic: str, model_name: str) -> Crew:
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
        goal="把解决方案打磨成正式交付报告，保留关键评审结论但减少过程化表达。",
        backstory=(
            "你是一名严谨的评审者，关注边界条件、机会成本、失败场景、"
            "可观测指标和真实可落地性。你的输出应像正式咨询报告，"
            "不要写 agent 自我介绍或评审过程旁白。"
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
            "优先行动和主要风险，同时删除重复解释、技术细枝末节和过程性话术。"
        ),
        llm=model_name,
        verbose=True,
    )

    # 任务 1 不依赖前置上下文，用于围绕主题产出结构化问题分析。
    analysis_task = Task(
        description=(
            "围绕主题《{topic}》做通用问题分析。请输出结构化要点，不要写寒暄或自我介绍。"
            "必须包含：1. 问题背景；2. 核心目标；3. 已知事实；4. 明确假设；"
            "5. 利益相关方；6. 约束条件；7. 关键矛盾；8. 成功标准；"
            "9. 仍需澄清的问题。对缺少依据的信息必须标注为“假设”。"
        ),
        expected_output="一份结构清晰的中文问题分析，包含可直接给下游 agent 使用的要点。",
        agent=analyst,
    )

    # 任务 2 依赖任务 1。CrewAI 会把问题分析结果作为上下文传给方案设计者。
    solution_task = Task(
        description=(
            "基于上一步问题分析，设计一套可执行的解决方案。输出要面向执行团队，"
            "不要写成头脑风暴。必须包含：1. 总体思路；2. 2-3 个可选方案对比；"
            "3. 推荐方案及推荐理由；4. 分阶段执行步骤；5. 资源需求；"
            "6. 优先级；7. 里程碑；8. 验证指标；9. 应急预案。"
            "所有数字指标都要说明依据；如果没有依据，必须标注为“初始假设，需验证”。"
        ),
        expected_output="一份中文解决方案报告，足够让执行者开始落地。",
        agent=solver,
        context=[analysis_task],
    )

    # 任务 3 依赖任务 2。评审员会检查解决方案，并在识别风险后给出完整报告。
    review_task = Task(
        description=(
            "评审上一步解决方案，并把它改写成正式完整报告。不要以“作为评审者”开头，"
            "不要输出长篇评审过程，不要把重点放在你如何审查。"
            "最终报告请严格使用以下结构："
            "一、结论摘要：用 3-5 句话先给最终建议；"
            "二、问题定义：说明要解决什么、边界是什么、哪些信息仍是假设；"
            "三、推荐方案：说明方案内容、为什么优于备选方案、删掉了哪些过度设计；"
            "四、执行计划：给出阶段、行动、负责人类型、产出物和时间顺序；"
            "五、风险与缓解：列出最高优先级风险、触发条件、缓解措施和回滚方案；"
            "六、验证指标：每个指标都要说明依据，依据不足的标注“初始假设，需验证”；"
            "七、下一步行动：列出 3-5 个最先做的动作；"
            "八、附录：被否决方案和关键评审意见。"
            "语言要像交付给团队的正式文档，直接、克制、可执行。"
        ),
        expected_output="一份中文正式完整报告，先给结论和执行方案，再在附录保留关键评审意见。",
        agent=reviewer,
        context=[solution_task],
    )

    # 任务 4 依赖任务 3。总结者会在完整报告之外生成一份更短的精简报告。
    summary_task = Task(
        description=(
            "基于完整报告生成一份额外的中文精简报告。请控制在 500 字以内，"
            "不要复述完整报告的长段解释，不要写过程性话术。必须包含："
            "1. 一句话结论；2. 最重要的 3 个理由；3. 接下来最优先的 3 个行动；"
            "4. 最大风险；5. 需要立即确认的 1-3 个问题。"
            "如果完整报告中的数字指标依据不足，要提醒它们属于待验证假设。"
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
    args = parse_args()

    # CrewAI 需要大模型服务的 API key；这里同时支持 DeepSeek 和 OpenAI。
    if not (os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")):
        raise SystemExit(
            "缺少 API key。请复制 .env.template 为 .env，并填入 DEEPSEEK_API_KEY。"
        )

    model_name = formal_model_name(args.model)
    crewai_model = crewai_model_name(model_name)
    topic = " ".join(args.topic).strip() or "分析并解决一个需要多方权衡的复杂问题"
    # 如果命令行传入了参数，就作为主题；否则使用上面的内置演示主题。
    crew = build_crew(topic, crewai_model)
    # 启动 CrewAI 工作流。inputs 中的 topic 会对应任务描述里的 {topic} 占位符。
    started_at = perf_counter()
    result = crew.kickoff(inputs={"topic": topic})
    elapsed_seconds = perf_counter() - started_at
    token_usage = extract_token_usage(result, crew)

    # 将完整报告和精简报告分别保存到本次运行的独立目录，避免覆盖历史结果。
    run_dir = create_output_run_dir()
    output_file = run_dir / "full_report.md"
    summary_file = run_dir / "summary_report.md"
    metadata_file = run_dir / "run_metadata.md"
    task_outputs = getattr(result, "tasks_output", None) or []
    full_report = task_output_text(task_outputs[2]) if len(task_outputs) >= 3 else str(result)
    concise_report = task_output_text(task_outputs[3]) if len(task_outputs) >= 4 else str(result)

    output_file.write_text(full_report, encoding="utf-8")
    summary_file.write_text(concise_report, encoding="utf-8")
    write_run_metadata(
        metadata_file,
        topic=topic,
        model_alias=args.model,
        model_name=model_name,
        crewai_model=crewai_model,
        elapsed_seconds=elapsed_seconds,
        token_usage=token_usage,
    )

    print("\n\n===== FULL REPORT =====\n")
    print(full_report)
    print(f"\n已保存到: {output_file}")
    print("\n\n===== CONCISE REPORT =====\n")
    print(concise_report)
    print(f"\n精简报告已保存到: {summary_file}")
    print("\n\n===== RUN STATS =====\n")
    print(f"模型: {args.model} ({model_name})")
    print(f"CrewAI 模型字符串: {crewai_model}")
    print(f"总用时: {elapsed_seconds:.2f} 秒")
    if token_usage:
        print(f"总 token: {token_usage.get('total_tokens', 0)}")
        print(f"输入 token: {token_usage.get('prompt_tokens', 0)}")
        print(f"输出 token: {token_usage.get('completion_tokens', 0)}")
    else:
        print("token 用量: 当前 CrewAI/模型返回中未读取到 token 统计。")
    print(f"运行元数据已保存到: {metadata_file}")


if __name__ == "__main__":
    main()
