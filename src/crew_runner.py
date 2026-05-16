# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "config"
AGENTS_FILE = CONFIG_DIR / "agents.json"
TASKS_FILE = CONFIG_DIR / "tasks.json"
OUTPUT_DIR = ROOT / "outputs"
CREWAI_STORAGE_DIR = ROOT / ".cache" / "crewai"
LOCAL_APP_DATA = ROOT / ".cache" / "localappdata"
MODEL_ALIASES = {
    "flash": "deepseek-v4-flash",
    "pro": "deepseek-v4-pro",
}
CREWAI_PROVIDER_PREFIX = "deepseek/"
DEFAULT_TOPIC = "分析并解决一个需要多方权衡的复杂问题"


os.environ.setdefault("CREWAI_STORAGE_DIR", str(CREWAI_STORAGE_DIR))
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")
os.environ["LOCALAPPDATA"] = str(LOCAL_APP_DATA)
os.environ.setdefault("CREWAI_TRACING_ENABLED", "false")
os.environ.setdefault("CREWAI_TESTING", "true")

from crewai import Agent, Crew, Process, Task


EventCallback = Callable[[dict[str, Any]], None]


@dataclass(frozen=True)
class AgentConfig:
    id: str
    role: str
    goal: str
    backstory: str
    enabled: bool = True


@dataclass(frozen=True)
class TaskConfig:
    id: str
    name: str
    description: str
    expected_output: str
    agent_id: str
    context_task_ids: list[str]
    enabled: bool = True


@dataclass(frozen=True)
class RunResult:
    topic: str
    model_alias: str
    model_name: str
    crewai_model: str
    elapsed_seconds: float
    token_usage: dict[str, int]
    run_dir: Path
    full_report: str
    concise_report: str
    task_outputs: list[dict[str, str]]
    events: list[dict[str, Any]]


def load_json_file(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json_file(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_agent_configs() -> list[AgentConfig]:
    return [
        AgentConfig(
            id=str(item["id"]).strip(),
            role=str(item["role"]).strip(),
            goal=str(item["goal"]).strip(),
            backstory=str(item["backstory"]).strip(),
            enabled=bool(item.get("enabled", True)),
        )
        for item in load_json_file(AGENTS_FILE)
    ]


def load_task_configs() -> list[TaskConfig]:
    return [
        TaskConfig(
            id=str(item["id"]).strip(),
            name=str(item.get("name") or item["id"]).strip(),
            description=str(item["description"]).strip(),
            expected_output=str(item["expected_output"]).strip(),
            agent_id=str(item["agent_id"]).strip(),
            context_task_ids=[str(task_id).strip() for task_id in item.get("context_task_ids", [])],
            enabled=bool(item.get("enabled", True)),
        )
        for item in load_json_file(TASKS_FILE)
    ]


def config_to_dicts(configs: list[AgentConfig] | list[TaskConfig]) -> list[dict[str, Any]]:
    return [config.__dict__ for config in configs]


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
    return MODEL_ALIASES.get(model_alias, MODEL_ALIASES["flash"])


def crewai_model_name(model_name: str) -> str:
    if model_name.startswith(CREWAI_PROVIDER_PREFIX):
        return model_name
    return f"{CREWAI_PROVIDER_PREFIX}{model_name}"


def task_output_text(task_output: object) -> str:
    raw = getattr(task_output, "raw", None)
    return str(raw if raw is not None else task_output)


def create_output_run_dir() -> Path:
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


def validate_configs(agents: list[AgentConfig], tasks: list[TaskConfig]) -> None:
    enabled_agents = {agent.id for agent in agents if agent.enabled}
    enabled_tasks = {task.id for task in tasks if task.enabled}
    previous_enabled_tasks: set[str] = set()

    if not enabled_agents:
        raise ValueError("至少需要启用一个 agent。")
    if not enabled_tasks:
        raise ValueError("至少需要启用一个 task。")

    for task in tasks:
        if not task.enabled:
            continue
        if task.agent_id not in enabled_agents:
            raise ValueError(f"任务 {task.name} 调用了不存在或未启用的 agent: {task.agent_id}")
        missing_context = [task_id for task_id in task.context_task_ids if task_id not in enabled_tasks]
        if missing_context:
            raise ValueError(f"任务 {task.name} 依赖不存在或未启用的 task: {', '.join(missing_context)}")
        future_context = [
            task_id
            for task_id in task.context_task_ids
            if task_id not in previous_enabled_tasks
        ]
        if future_context:
            raise ValueError(f"任务 {task.name} 只能依赖排在它前面的 task: {', '.join(future_context)}")
        previous_enabled_tasks.add(task.id)


def build_crew(
    model_name: str,
    *,
    agents_config: list[AgentConfig] | None = None,
    tasks_config: list[TaskConfig] | None = None,
    on_event: EventCallback | None = None,
) -> Crew:
    agents_config = agents_config or load_agent_configs()
    tasks_config = tasks_config or load_task_configs()
    validate_configs(agents_config, tasks_config)

    agent_by_id: dict[str, Agent] = {}
    for config in agents_config:
        if not config.enabled:
            continue
        agent_by_id[config.id] = Agent(
            role=config.role,
            goal=config.goal,
            backstory=config.backstory,
            llm=model_name,
            verbose=True,
        )

    task_by_id: dict[str, Task] = {}
    tasks: list[Task] = []
    for config in tasks_config:
        if not config.enabled:
            continue
        task = Task(
            description=config.description,
            expected_output=config.expected_output,
            agent=agent_by_id[config.agent_id],
            context=[task_by_id[task_id] for task_id in config.context_task_ids],
        )
        task_by_id[config.id] = task
        tasks.append(task)

    def task_callback(task_output: object) -> None:
        if on_event is None:
            return
        on_event(
            {
                "type": "task_completed",
                "time": datetime.now().isoformat(timespec="seconds"),
                "agent": getattr(task_output, "agent", ""),
                "output": task_output_text(task_output),
            }
        )

    return Crew(
        agents=list(agent_by_id.values()),
        tasks=tasks,
        process=Process.sequential,
        verbose=True,
        task_callback=task_callback,
    )


def write_task_outputs(run_dir: Path, task_outputs: list[dict[str, str]]) -> None:
    tasks_dir = run_dir / "tasks"
    tasks_dir.mkdir(exist_ok=True)

    for index, task_output in enumerate(task_outputs, start=1):
        agent = task_output.get("agent") or f"task_{index}"
        safe_agent = "".join(char if char.isalnum() else "_" for char in agent).strip("_")
        filename = f"{index:02d}_{safe_agent or 'task'}.md"
        (tasks_dir / filename).write_text(task_output.get("output", ""), encoding="utf-8")


def write_event_log(run_dir: Path, events: list[dict[str, Any]]) -> None:
    (run_dir / "events.json").write_text(
        json.dumps(events, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def run_crew(
    *,
    topic: str,
    model_alias: str,
    on_event: EventCallback | None = None,
    agents_config: list[AgentConfig] | None = None,
    tasks_config: list[TaskConfig] | None = None,
) -> RunResult:
    events: list[dict[str, Any]] = []

    def emit(event: dict[str, Any]) -> None:
        events.append(event)
        if on_event is not None:
            on_event(event)

    model_name = formal_model_name(model_alias)
    crewai_model = crewai_model_name(model_name)
    resolved_topic = topic.strip() or DEFAULT_TOPIC

    emit(
        {
            "type": "run_started",
            "time": datetime.now().isoformat(timespec="seconds"),
            "model": model_alias,
            "topic": resolved_topic,
        }
    )
    crew = build_crew(
        crewai_model,
        agents_config=agents_config,
        tasks_config=tasks_config,
        on_event=emit,
    )
    started_at = perf_counter()
    result = crew.kickoff(inputs={"topic": resolved_topic})
    elapsed_seconds = perf_counter() - started_at
    token_usage = extract_token_usage(result, crew)

    task_outputs_raw = getattr(result, "tasks_output", None) or []
    task_outputs = [
        {
            "agent": str(getattr(task_output, "agent", "")),
            "description": str(getattr(task_output, "description", "")),
            "output": task_output_text(task_output),
        }
        for task_output in task_outputs_raw
    ]
    if len(task_outputs) >= 2:
        full_report = task_outputs[-2]["output"]
        concise_report = task_outputs[-1]["output"]
    elif task_outputs:
        full_report = task_outputs[-1]["output"]
        concise_report = task_outputs[-1]["output"]
    else:
        full_report = str(result)
        concise_report = str(result)

    run_dir = create_output_run_dir()
    (run_dir / "full_report.md").write_text(full_report, encoding="utf-8")
    (run_dir / "summary_report.md").write_text(concise_report, encoding="utf-8")
    write_run_metadata(
        run_dir / "run_metadata.md",
        topic=resolved_topic,
        model_alias=model_alias,
        model_name=model_name,
        crewai_model=crewai_model,
        elapsed_seconds=elapsed_seconds,
        token_usage=token_usage,
    )
    write_task_outputs(run_dir, task_outputs)
    emit(
        {
            "type": "run_completed",
            "time": datetime.now().isoformat(timespec="seconds"),
            "elapsed_seconds": elapsed_seconds,
            "run_dir": str(run_dir),
        }
    )
    write_event_log(run_dir, events)

    return RunResult(
        topic=resolved_topic,
        model_alias=model_alias,
        model_name=model_name,
        crewai_model=crewai_model,
        elapsed_seconds=elapsed_seconds,
        token_usage=token_usage,
        run_dir=run_dir,
        full_report=full_report,
        concise_report=concise_report,
        task_outputs=task_outputs,
        events=events,
    )
