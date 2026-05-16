# CrewAI 通用问题解决多 Agent Demo

这个 Demo 用 CrewAI 搭了一个小型“通用问题解决团队”：

- `Problem Analyst`：拆解问题背景、目标、约束、关键矛盾和成功标准
- `Solution Strategist`：基于问题分析设计可执行的解决方案
- `Critical Reviewer`：审查方案风险、遗漏、脆弱假设和过度设计
- `Executive Summarizer`：在完整报告之外额外生成一份精简报告

默认示例任务是：分析并解决一个需要多方权衡的复杂问题。你可以在运行时传入自己的主题。

## 项目内依赖策略

为了尽量不污染全局环境，建议把所有东西都放在当前项目目录：

- 虚拟环境：`.venv/`
- pip 下载缓存：`.cache/pip/`
- CrewAI 运行存储：`.cache/crewai/`
- Windows 应用数据兼容目录：`.cache/localappdata/`
- 运行输出：`outputs/` 下按每次运行时间创建的子目录
- 密钥配置：`.env`

## 初始化

在本机有 Python 的情况下：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
$env:PIP_CACHE_DIR="$PWD\.cache\pip"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## 配置

复制 `.env.template` 为 `.env`，填入你的 API key：

```powershell
Copy-Item .env.template .env
```

然后编辑 `.env`：

```text
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
MODEL_VARIANT=flash
CREWAI_STORAGE_DIR=.cache/crewai
CREWAI_DISABLE_TELEMETRY=true
CREWAI_TRACING_ENABLED=false
CREWAI_TESTING=true
OTEL_SDK_DISABLED=true
```

## 运行

### 可视化界面

推荐使用可视化界面运行和调整多 Agent 工作流：

```powershell
.\ui.ps1
```

或者：

```powershell
.\run.ps1 -Ui
```

启动后浏览器会打开 Streamlit 页面。界面支持：

- 选择模型档位：`flash` 或 `pro`
- 输入主题并运行多 Agent 工作流
- 查看运行过程、任务输出、完整报告和精简报告
- 查看历史输出
- 在“配置”页新增、删除、启用、禁用和修改 agent/task

说明：界面展示的是 CrewAI 公开事件、任务状态、任务输出和日志，不展示模型隐藏推理链。隐藏推理链通常不会由模型/API 暴露，也不应伪造展示。

### 命令行

```powershell
.\.venv\Scripts\python.exe .\src\main.py
```

切换模型档位：

```powershell
.\.venv\Scripts\python.exe .\src\main.py --model flash
.\.venv\Scripts\python.exe .\src\main.py --model pro
```

模型档位对应 DeepSeek 正式模型名：

- `flash`：`deepseek-v4-flash`
- `pro`：`deepseek-v4-pro`

脚本内部会自动加上 CrewAI/LiteLLM 需要的 `deepseek/` 供应商前缀。

传入自定义主题：

```powershell
.\.venv\Scripts\python.exe .\src\main.py "如何降低一个小团队的软件交付延期风险"
```

使用 `run.ps1` 时也可以切换模型：

```powershell
.\run.ps1 -Model flash "如何降低一个小团队的软件交付延期风险"
.\run.ps1 -Model pro "如何降低一个小团队的软件交付延期风险"
```

每次运行都会在 `outputs/` 下创建一个新的时间戳目录，例如：

```text
outputs/20260515_142030/
```

其中包含：

- `full_report.md`：完整报告
- `summary_report.md`：精简报告
- `run_metadata.md`：本次运行的模型、总用时和 token 用量
- `events.json`：可视化界面使用的公开运行事件
- `tasks/`：每个 task 的单独输出

## 配置 agent 和 task

默认配置放在：

- `config/agents.json`
- `config/tasks.json`

你可以在可视化界面的“配置”页编辑，也可以直接改 JSON 文件。task 通过 `agent_id` 指定调用哪个 agent，通过 `context_task_ids` 指定依赖哪些前置 task。
