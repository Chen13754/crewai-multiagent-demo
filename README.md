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

复制 `.env.example` 为 `.env`，填入你的 API key：

```powershell
Copy-Item .env.example .env
```

然后编辑 `.env`：

```text
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
MODEL=deepseek/deepseek-v4-flash
CREWAI_STORAGE_DIR=.cache/crewai
CREWAI_DISABLE_TELEMETRY=true
CREWAI_TRACING_ENABLED=false
CREWAI_TESTING=true
OTEL_SDK_DISABLED=true
```

## 运行

```powershell
.\.venv\Scripts\python.exe .\src\main.py
```

传入自定义主题：

```powershell
.\.venv\Scripts\python.exe .\src\main.py "如何降低一个小团队的软件交付延期风险"
```

每次运行都会在 `outputs/` 下创建一个新的时间戳目录，例如：

```text
outputs/20260515_142030/
```

其中包含：

- `full_report.md`：完整报告
- `summary_report.md`：精简报告
