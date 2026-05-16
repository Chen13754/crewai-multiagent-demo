# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from argparse import ArgumentParser, Namespace

from dotenv import load_dotenv

from crew_runner import (
    DEFAULT_TOPIC,
    MODEL_ALIASES,
    ROOT,
    default_model_alias,
    run_crew,
)


def parse_args() -> Namespace:
    parser = ArgumentParser(description="运行通用问题解决多 Agent 工作流。")
    parser.add_argument(
        "--model",
        choices=sorted(MODEL_ALIASES),
        default=default_model_alias(),
        help="选择 DeepSeek 模型档位：flash 更快，pro 能力更强。",
    )
    parser.add_argument("topic", nargs="*", help="要分析和解决的问题主题。")
    return parser.parse_args()


def main() -> None:
    load_dotenv(ROOT / ".env")
    args = parse_args()

    if not (os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY")):
        raise SystemExit(
            "缺少 API key。请复制 .env.template 为 .env，并填入 DEEPSEEK_API_KEY。"
        )

    topic = " ".join(args.topic).strip() or DEFAULT_TOPIC
    result = run_crew(topic=topic, model_alias=args.model)

    print("\n\n===== FULL REPORT =====\n")
    print(result.full_report)
    print(f"\n已保存到: {result.run_dir / 'full_report.md'}")
    print("\n\n===== CONCISE REPORT =====\n")
    print(result.concise_report)
    print(f"\n精简报告已保存到: {result.run_dir / 'summary_report.md'}")
    print("\n\n===== RUN STATS =====\n")
    print(f"模型: {result.model_alias} ({result.model_name})")
    print(f"CrewAI 模型字符串: {result.crewai_model}")
    print(f"总用时: {result.elapsed_seconds:.2f} 秒")
    if result.token_usage:
        print(f"总 token: {result.token_usage.get('total_tokens', 0)}")
        print(f"输入 token: {result.token_usage.get('prompt_tokens', 0)}")
        print(f"输出 token: {result.token_usage.get('completion_tokens', 0)}")
    else:
        print("token 用量: 当前 CrewAI/模型返回中未读取到 token 统计。")
    print(f"运行元数据已保存到: {result.run_dir / 'run_metadata.md'}")


if __name__ == "__main__":
    main()
