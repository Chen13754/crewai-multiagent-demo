# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import json
import sys
from pathlib import Path
from typing import Any

import streamlit as st
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent))

from crew_runner import (
    AGENTS_FILE,
    DEFAULT_TOPIC,
    MODEL_ALIASES,
    ROOT,
    TASKS_FILE,
    config_to_dicts,
    default_model_alias,
    load_agent_configs,
    load_json_file,
    load_task_configs,
    run_crew,
    save_json_file,
    validate_configs,
)


st.set_page_config(
    page_title="Multiagent Studio",
    layout="wide",
    initial_sidebar_state="expanded",
)


CUSTOM_CSS = """
<style>
  .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
  div[data-testid="stMetricValue"] { font-size: 1.35rem; }
  .event-card {
    border: 1px solid rgba(49, 51, 63, 0.14);
    border-radius: 8px;
    padding: 0.75rem 0.85rem;
    margin-bottom: 0.5rem;
    background: rgba(250, 250, 250, 0.7);
  }
  .event-title { font-weight: 650; margin-bottom: 0.2rem; }
  .muted { color: rgba(49, 51, 63, 0.65); font-size: 0.9rem; }
  .small-code {
    font-family: ui-monospace, SFMono-Regular, Consolas, monospace;
    font-size: 0.84rem;
    color: rgba(49, 51, 63, 0.72);
  }
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


load_dotenv(ROOT / ".env")


def init_state() -> None:
    st.session_state.setdefault("events", [])
    st.session_state.setdefault("last_result", None)
    st.session_state.setdefault("agents_editor", AGENTS_FILE.read_text(encoding="utf-8"))
    st.session_state.setdefault("tasks_editor", TASKS_FILE.read_text(encoding="utf-8"))


def event_label(event_type: str) -> str:
    labels = {
        "run_started": "运行开始",
        "task_completed": "任务完成",
        "run_completed": "运行完成",
    }
    return labels.get(event_type, event_type)


def render_event(event: dict[str, Any]) -> None:
    title = event_label(str(event.get("type", "")))
    time = event.get("time", "")
    details = []
    if event.get("agent"):
        details.append(f"Agent: {event['agent']}")
    if event.get("model"):
        details.append(f"Model: {event['model']}")
    if event.get("elapsed_seconds") is not None:
        details.append(f"{float(event['elapsed_seconds']):.2f}s")
    body = " · ".join(details)

    st.markdown(
        f"""
        <div class="event-card">
          <div class="event-title">{title}</div>
          <div class="muted">{time} {body}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_run_page() -> None:
    st.title("Multiagent Studio")
    st.caption("用可视化界面运行、观察和调整 CrewAI 多 Agent 工作流。")

    with st.sidebar:
        st.subheader("运行设置")
        model_alias = st.radio(
            "模型档位",
            options=sorted(MODEL_ALIASES),
            index=sorted(MODEL_ALIASES).index(default_model_alias()),
            horizontal=True,
        )
        topic = st.text_area(
            "任务主题",
            value=DEFAULT_TOPIC,
            height=130,
            placeholder="输入你希望多 Agent 分析的问题。",
        )
        has_key = bool(os.getenv("DEEPSEEK_API_KEY") or os.getenv("OPENAI_API_KEY"))
        if not has_key:
            st.warning("未检测到 API key。请先在 .env 中配置 DEEPSEEK_API_KEY。")

        run_clicked = st.button("运行工作流", type="primary", use_container_width=True)

    if run_clicked:
        st.session_state.events = []
        st.session_state.last_result = None

        if not has_key:
            st.error("缺少 API key，无法运行。")
            return

        event_box = st.empty()
        progress = st.progress(0, text="准备运行")

        def on_event(event: dict[str, Any]) -> None:
            st.session_state.events.append(event)
            completed = sum(1 for item in st.session_state.events if item.get("type") == "task_completed")
            progress.progress(min(95, 10 + completed * 20), text=event_label(str(event.get("type", ""))))
            with event_box.container():
                st.subheader("运行过程")
                for item in st.session_state.events[-8:]:
                    render_event(item)

        try:
            result = run_crew(topic=topic, model_alias=model_alias, on_event=on_event)
        except Exception as exc:
            progress.empty()
            st.error(f"运行失败：{exc}")
            return

        progress.progress(100, text="完成")
        st.session_state.last_result = result
        st.success(f"运行完成，输出目录：{result.run_dir}")

    result = st.session_state.last_result
    left, right = st.columns([0.95, 1.35], gap="large")

    with left:
        st.subheader("运行过程")
        if st.session_state.events:
            for event in st.session_state.events:
                render_event(event)
        else:
            st.info("点击左侧运行后，这里会显示任务状态、负责 agent 和公开输出节点。")

        st.subheader("说明")
        st.write(
            "这里展示的是 CrewAI 公开事件、任务输出和运行日志。模型隐藏推理链通常不会通过 API 暴露，因此不会伪造或强行展示。"
        )

    with right:
        st.subheader("输出")
        if result is None:
            st.info("暂无运行结果。")
            return

        metric_cols = st.columns(3)
        metric_cols[0].metric("模型", result.model_alias)
        metric_cols[1].metric("用时", f"{result.elapsed_seconds:.1f}s")
        metric_cols[2].metric("Tasks", str(len(result.task_outputs)))

        tab_summary, tab_full, tab_tasks, tab_files = st.tabs(
            ["精简报告", "完整报告", "任务输出", "文件"]
        )
        with tab_summary:
            st.markdown(result.concise_report)
        with tab_full:
            st.markdown(result.full_report)
        with tab_tasks:
            for index, task_output in enumerate(result.task_outputs, start=1):
                title = task_output.get("agent") or f"Task {index}"
                with st.expander(f"{index}. {title}", expanded=index == len(result.task_outputs)):
                    st.markdown(task_output.get("output", ""))
        with tab_files:
            st.code(str(result.run_dir), language="text")
            st.write("- full_report.md")
            st.write("- summary_report.md")
            st.write("- run_metadata.md")
            st.write("- events.json")


def render_json_editor(
    *,
    title: str,
    description: str,
    state_key: str,
    file_path: Path,
) -> None:
    st.subheader(title)
    st.caption(description)

    raw_text = st.text_area(
        f"{title} JSON",
        value=st.session_state[state_key],
        height=430,
        label_visibility="collapsed",
    )
    st.session_state[state_key] = raw_text

    controls = st.columns([1, 1, 4])
    if controls[0].button(f"保存 {title}", use_container_width=True):
        try:
            parsed = json.loads(raw_text)
            save_json_file(file_path, parsed)
        except Exception as exc:
            st.error(f"保存失败：{exc}")
        else:
            st.success("已保存。")

    if controls[1].button(f"重新读取 {title}", use_container_width=True):
        st.session_state[state_key] = file_path.read_text(encoding="utf-8")
        st.rerun()


def render_agents_table_editor() -> None:
    st.subheader("Agents")
    st.caption("直接在表格中新增、删除或修改角色。")
    edited = st.data_editor(
        load_json_file(AGENTS_FILE),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": st.column_config.TextColumn("id", required=True),
            "role": st.column_config.TextColumn("role", required=True),
            "goal": st.column_config.TextColumn("goal", width="large", required=True),
            "backstory": st.column_config.TextColumn("backstory", width="large", required=True),
            "enabled": st.column_config.CheckboxColumn("enabled"),
        },
        key="agents_table_editor",
    )
    if st.button("保存 Agents 表格", type="primary"):
        try:
            save_json_file(AGENTS_FILE, edited)
            st.session_state.agents_editor = AGENTS_FILE.read_text(encoding="utf-8")
        except Exception as exc:
            st.error(f"保存失败：{exc}")
        else:
            st.success("Agents 已保存。")


def task_rows_for_editor() -> list[dict[str, Any]]:
    rows = load_json_file(TASKS_FILE)
    for row in rows:
        row["context_task_ids"] = ", ".join(row.get("context_task_ids", []))
    return rows


def normalize_task_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized = []
    for row in rows:
        row = dict(row)
        context_value = row.get("context_task_ids", "")
        if isinstance(context_value, list):
            context_ids = [str(item).strip() for item in context_value if str(item).strip()]
        else:
            context_ids = [
                item.strip()
                for item in str(context_value).split(",")
                if item.strip()
            ]
        row["context_task_ids"] = context_ids
        normalized.append(row)
    return normalized


def render_tasks_table_editor() -> None:
    st.subheader("Tasks")
    st.caption("context_task_ids 用英文逗号分隔，例如：analysis, solution。")
    edited = st.data_editor(
        task_rows_for_editor(),
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "id": st.column_config.TextColumn("id", required=True),
            "name": st.column_config.TextColumn("name"),
            "description": st.column_config.TextColumn("description", width="large", required=True),
            "expected_output": st.column_config.TextColumn("expected_output", width="large", required=True),
            "agent_id": st.column_config.TextColumn("agent_id", required=True),
            "context_task_ids": st.column_config.TextColumn("context_task_ids"),
            "enabled": st.column_config.CheckboxColumn("enabled"),
        },
        key="tasks_table_editor",
    )
    if st.button("保存 Tasks 表格", type="primary"):
        try:
            save_json_file(TASKS_FILE, normalize_task_rows(edited))
            st.session_state.tasks_editor = TASKS_FILE.read_text(encoding="utf-8")
        except Exception as exc:
            st.error(f"保存失败：{exc}")
        else:
            st.success("Tasks 已保存。")


def render_config_page() -> None:
    st.title("配置中心")
    st.caption("查看、修改、新增或删除 agent 与 task。保存后下一次运行会使用新配置。")

    agent_tab, task_tab, json_tab, validate_tab = st.tabs(["Agents", "Tasks", "JSON", "配置检查"])
    with agent_tab:
        render_agents_table_editor()
    with task_tab:
        render_tasks_table_editor()
    with json_tab:
        render_json_editor(
            title="Agents",
            description="每个 agent 需要 id、role、goal、backstory 和 enabled。",
            state_key="agents_editor",
            file_path=AGENTS_FILE,
        )
        render_json_editor(
            title="Tasks",
            description="每个 task 需要 id、description、expected_output、agent_id、context_task_ids 和 enabled。",
            state_key="tasks_editor",
            file_path=TASKS_FILE,
        )
    with validate_tab:
        st.subheader("当前配置")
        if st.button("检查配置", type="primary"):
            try:
                validate_configs(load_agent_configs(), load_task_configs())
            except Exception as exc:
                st.error(f"配置有问题：{exc}")
            else:
                st.success("配置检查通过。")

        st.write("Agents")
        st.dataframe(config_to_dicts(load_agent_configs()), use_container_width=True)
        st.write("Tasks")
        st.dataframe(config_to_dicts(load_task_configs()), use_container_width=True)


def render_history_page() -> None:
    st.title("历史输出")
    output_root = ROOT / "outputs"
    if not output_root.exists():
        st.info("还没有输出目录。")
        return

    run_dirs = sorted(
        [path for path in output_root.iterdir() if path.is_dir()],
        key=lambda path: path.name,
        reverse=True,
    )
    if not run_dirs:
        st.info("还没有历史运行。")
        return

    selected = st.selectbox("选择运行记录", run_dirs, format_func=lambda path: path.name)
    summary_file = selected / "summary_report.md"
    full_file = selected / "full_report.md"
    metadata_file = selected / "run_metadata.md"

    tab_summary, tab_full, tab_meta = st.tabs(["精简报告", "完整报告", "元数据"])
    with tab_summary:
        st.markdown(summary_file.read_text(encoding="utf-8") if summary_file.exists() else "无")
    with tab_full:
        st.markdown(full_file.read_text(encoding="utf-8") if full_file.exists() else "无")
    with tab_meta:
        st.markdown(metadata_file.read_text(encoding="utf-8") if metadata_file.exists() else "无")


def main() -> None:
    init_state()
    page = st.sidebar.radio(
        "页面",
        ["运行", "配置", "历史"],
        label_visibility="collapsed",
    )
    if page == "运行":
        render_run_page()
    elif page == "配置":
        render_config_page()
    else:
        render_history_page()


if __name__ == "__main__":
    main()
