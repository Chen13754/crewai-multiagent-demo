# CrewAI 多 Agent 协作 Demo

这个 Demo 用 CrewAI 搭了一个小型“AI 产品团队”：

- `Researcher`：分析用户需求和场景
- `Architect`：设计产品方案和技术流程
- `Reviewer`：检查风险、遗漏和可改进点

默认示例任务是：为“个人知识库助手”生成一份产品方案。你可以在运行时传入自己的主题。

## 项目内依赖策略

为了尽量不污染全局环境，建议把所有东西都放在当前项目目录：

- 虚拟环境：`.venv/`
- pip 下载缓存：`.cache/pip/`
- CrewAI 运行存储：`.cache/crewai/`
- Windows 应用数据兼容目录：`.cache/localappdata/`
- 运行输出：`outputs/`
- 密钥配置：`.env`

## 初始化

在本机有 Python 的情况下：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
$env:PIP_CACHE_DIR="$PWD\.cache\pip"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

在当前 Codex 工作区里，我会优先使用内置 Python 创建 `.venv`。

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
.\.venv\Scripts\python.exe .\src\main.py "给独立开发者做一个自动化竞品分析工具"
```

结果会打印到终端，并保存到 `outputs/latest_result.md`。
