# Python 代码复杂度分析器

一款轻量级、SonarQube 风格的 Python 项目复杂度分析与 Web 可视化平台。集成 Python AST 分析引擎、FastAPI 后端和 React 前端，提供代码指标、依赖图和风险评分的交互式可视化。

## ✨ 功能特性

| 功能 | 详情 |
|------|------|
| **圈复杂度 (CC)** | 基于 AST 的 McCabe 圈复杂度，支持 `async for`、`match/case` (Python 3.10+) |
| **参数数量分析** | 报告每个函数的参数数量，标记超过阈值的函数（默认 >5 个参数） |
| **LOC / SLOC 统计** | 每个文件的总行数、有效代码行、空行、注释行 |
| **函数分析** | 函数数量、平均/最大复杂度、长函数和高复杂度函数标记 |
| **重复代码检测** | 通过归一化函数体 MD5 哈希值跨文件识别逻辑相同的函数 |
| **依赖图** | 导入级别依赖图 + 循环依赖检测（基于 NetworkX） |
| **风险评分** | 加权 0–100 分 + 字母等级（A–F），按模块和全局计算 |
| **实时进度** | WebSocket 流式推送 + HTTP 轮询 |
| **任务超时控制** | 超过配置时限的分析任务自动取消并标记为失败 |
| **失败文件追踪** | 解析失败的文件（语法错误、编码问题）单独列出，不静默跳过 |
| **HTML 报告导出** | 自包含、可打印的 HTML 报告（内置 ECharts 图表），支持 UI 下载和 API 获取 |
| **速率限制** | 按 IP 的滑动窗口限流（默认：10 次/60 秒） |
| **交互式 UI** | 树形图、力导向图、柱状图、可排序/搜索表格、行内展开详情 |
| **CLI 工具** | 独立运行，支持 JSON 或人类可读摘要输出 |
| **路径安全防护** | 服务端目录遍历保护（`ALLOWED_BASE_DIR`） |
| **CI 持续集成** | GitHub Actions 多版本矩阵测试（Python 3.10/3.11/3.12），覆盖率门禁 ≥ 70% |

## 📂 项目结构

```
Python_Complexity_Analyzer/
├── backend/
│   ├── analyzer/           # 核心分析引擎
│   │   ├── core.py         # 主编排器 (analyze_project)
│   │   ├── metrics.py      # LOC/SLOC 统计、文件收集
│   │   ├── complexity.py   # McCabe 圈复杂度 (_CCVisitor)
│   │   ├── functions.py    # 函数提取 & 重复检测
│   │   ├── dependencies.py # 导入依赖图 & 循环检测
│   │   └── risk.py         # 风险评分算法
│   └── api/                # FastAPI REST + WebSocket 服务
│       ├── main.py         # 应用入口、路由、CORS、限流、路径守卫
│       ├── models.py       # Pydantic 数据模型 + 输入验证
│       ├── report.py       # 自包含 HTML 报告生成
│       └── tasks.py        # 后台任务执行器 (ThreadPoolExecutor + 看门狗)
├── cli/
│   └── analyze.py          # CLI 入口
├── frontend/               # React + Vite + ECharts
│   └── src/
│       ├── pages/          # Dashboard, DependencyGraph, ModuleAnalysis, RiskList
│       ├── components/     # Layout, MetricCard
│       ├── api/            # axios 客户端 (VITE_API_BASE 可配置)
│       ├── i18n/           # 英文 / 中文翻译
│       └── utils/          # 共享颜色工具
└── tests/                  # pytest 测试套件 (219 个测试)
    ├── test_metrics.py
    ├── test_complexity.py
    ├── test_functions.py
    ├── test_dependencies.py
    ├── test_risk.py
    ├── test_core.py
    ├── test_api.py
    └── test_report.py
```

## 🔧 环境要求

**后端**

- Python 3.10+（`match/case` 复杂度计数需要 3.10）
- `fastapi >= 0.100`
- `uvicorn`
- `networkx`
- `pydantic >= 2.0`

**前端**

- Node.js 18+
- npm

**开发 / 测试**

- `pytest >= 7.0`
- `pytest-cov >= 4.0`
- `httpx`

## 🚀 安装与使用

### 1. 安装依赖

```bash
# 克隆仓库
git clone https://github.com/aaronharveyhan/python_complexity_analyzer.git
cd Python_Complexity_Analyzer

# 安装后端依赖
pip install "fastapi>=0.100" "pydantic>=2.0" uvicorn networkx httpx

# 安装前端依赖
cd frontend && npm install && cd ..
```

### 2. CLI 模式（无需服务器）

```bash
# 人类可读摘要报告
python cli/analyze.py /path/to/your/project

# 输出完整 JSON 到终端
python cli/analyze.py /path/to/your/project --json

# 保存 JSON 报告到文件
python cli/analyze.py /path/to/your/project --output report.json

# 排除额外目录（与内置默认列表合并）
python cli/analyze.py /path/to/your/project --ignore tests docs migrations
```

示例输出：

```
============================================================
  📊 分析: my_project
============================================================
  文件数         : 42
  总行数 (LOC)    : 8,301
  有效代码行      : 5,920
  函数数         : 187
  平均复杂度      : 2.41
  最大复杂度      : 18
  高复杂度函数    : 7
  长函数         : 3
  重复函数        : 4  (2.1%)
  循环依赖        : 1
  风险评分        : 34.2 / 100
  耗时           : 0.38s
============================================================
```

### 3. Web UI 模式

```bash
# 终端 1 — 启动 API 服务（必须在项目根目录执行）
uvicorn backend.api.main:app --host 127.0.0.1 --port 8000 --reload

# 终端 2 — 启动前端开发服务器
cd frontend && npm run dev
```

打开 [http://localhost:5173](http://localhost:5173)，输入 Python 项目的**绝对路径**，点击 **分析**。`/health` 接口会返回一个 `suggested_path` 自动预填输入框。

#### Windows / 预览构建

在 PowerShell 中设置 `VITE_API_BASE`，使请求直接发送到 uvicorn：

```powershell
# 在 frontend/ 目录下
$env:VITE_API_BASE = "http://127.0.0.1:8000"
npm run build
npm run preview       # 访问 http://localhost:4173
```

### 4. HTML 报告导出

分析完成后，在 UI 右上角点击 **⬇ 导出 HTML**，或直接通过 API 下载：

```bash
curl http://localhost:8000/report/<task_id> -o report.html
```

报告是完全自包含的文件（仅依赖 ECharts CDN），适合分享或存档。

### 5. 前端生产构建

```bash
cd frontend
npm run build    # 优化后的静态文件 → dist/
npm run preview  # 本地测试生产构建（包含代理）
```

## ⚙️ 配置项

所有阈值和限制均可通过环境变量配置：

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `ALLOWED_BASE_DIR` | `~`（用户主目录） | 服务器允许分析的最高目录 |
| `ALLOWED_ORIGINS` | localhost:5173/4173/3000 | 逗号分隔的 CORS 源列表 |
| `ANALYZE_RATE_LIMIT` | `10` | 每 IP 每 60 秒最大 `/analyze` 请求数 |
| `ANALYSIS_TIMEOUT` | `300` | 分析任务超时时间（秒），超时自动终止 |
| `ANALYSIS_MAX_WORKERS` | CPU 核心数 | ThreadPoolExecutor 工作线程数 |
| `LONG_FUNC_THRESHOLD` | `50` | 判定为"长函数"的行数阈值 |
| `HIGH_CC_THRESHOLD` | `10` | 判定为"高复杂度"的圈复杂度阈值 |
| `MANY_PARAMS_THRESHOLD` | `5` | 判定为"参数过多"的参数数量阈值 |

## 🔒 安全

### 路径遍历防护

```bash
export ALLOWED_BASE_DIR=/srv/projects
uvicorn backend.api.main:app --port 8000
```

超出 `ALLOWED_BASE_DIR` 的路径将返回 HTTP **403 Forbidden**。`ignore_dirs` 字段仅接受简单目录名（不允许 `..`、`/` 或 `\`）。

### 速率限制

`/analyze` 端点对每个客户端 IP 实施滑动窗口限流。可通过环境变量调整：

```bash
export ANALYZE_RATE_LIMIT=20   # 允许每 60 秒 20 次请求
```

超限请求返回 HTTP **429 Too Many Requests**。

## 📡 API 参考

| 方法 | 端点 | 说明 |
|------|------|------|
| `GET` | `/health` | 健康检查 — 返回状态、Python 版本、建议路径、允许目录 |
| `POST` | `/analyze` | 提交项目路径进行分析，立即返回 `{task_id, status}` (HTTP 202) |
| `GET` | `/result/{task_id}` | 轮询任务状态，完成后获取完整分析结果 |
| `GET` | `/tasks` | 列出所有已提交任务 |
| `GET` | `/report/{task_id}` | 下载已完成任务的自包含 HTML 报告 |
| `WS` | `/ws/{task_id}` | WebSocket 实时进度推送 |

**提交分析：**

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{"project_path": "/absolute/path/to/project", "ignore_dirs": ["tests"]}'
```

**轮询结果：**

```bash
curl http://localhost:8000/result/<task_id>
```

**任务状态字段：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `task_id` | 字符串 | 提交时分配的 UUID |
| `status` | `pending` \| `processing` \| `completed` \| `failed` | 当前状态 |
| `progress` | 0–100 | 完成百分比 |
| `message` | 字符串 | 当前步骤描述 |
| `result` | 对象 \| 空 | 完整分析结果（仅 `completed` 时可用） |
| `error` | 字符串 \| 空 | 错误信息或堆栈跟踪（仅 `failed` 时可用） |

## 📊 指标说明

### 圈复杂度 (McCabe)

通过 AST 遍历每个函数/方法计算。基础值为 1，每个决策点 +1：

| 语法结构 | 增量 |
|----------|------|
| `if` / `elif` | +1 |
| `for` / `async for` / `while` | +1 |
| `except` 异常处理 | +1 |
| 三元表达式 (`x if c else y`) | +1 |
| 布尔运算符 `and` / `or`（N 个操作数） | +N−1 |
| 推导式迭代 | +1 |
| 推导式过滤（`if` 子句） | 每个子句 +1 |
| `match` 语句 (Python 3.10+) | 每个 `case` 分支 +1 |

当 CC ≥ `HIGH_CC_THRESHOLD`（默认 10）时，函数被标记为 **高复杂度**。

### 参数数量

`n_params` 统计所有参数类型：位置参数、仅限位置参数、仅限关键字参数、`*args` 和 `**kwargs`。超过 `MANY_PARAMS_THRESHOLD`（默认 5）的函数标记 `is_many_params`，并在 UI 中显示 **"参数过多"** 徽章。

### 风险评分

每个模块的加权综合评分（0–100）：

```
risk = 0.40 × normalize(avg_cc,  lo=0, hi=max(project_max_cc, 10))
     + 0.30 × normalize(loc,     lo=0, hi=max(project_max_loc, 500))
     + 0.20 × (高复杂度函数数 / 总函数数)  × 100
     + 0.10 × (重复函数数 / 总函数数)     × 100
```

> 注意：CC 和 LOC 的归一化设有绝对下限（CC=10、LOC=500），避免单文件项目因只与自己比较而失真。

| 等级 | 分数 |
|------|------|
| A | < 20 |
| B | 20 – 39 |
| C | 40 – 59 |
| D | 60 – 79 |
| F | ≥ 80 |

### 重复代码检测

超过 5 行的函数会被归一化（折叠空白字符）并用 MD5 哈希。跨文件共享相同哈希值的函数标记为重复。首次出现的函数保留 `is_duplicate=false`，后续出现标记 `duplicate_of` 指向首个出现。

### 默认忽略目录

```
venv  .venv  env  .env  .git  __pycache__  .tox  .mypy_cache
node_modules  dist  build  .pytest_cache  .eggs  *.egg-info
```

可通过 CLI 的 `--ignore` 参数或 API 的 `ignore_dirs` 字段追加额外目录。仅接受简单目录名，拒绝路径分隔符。

## 📈 可视化页面

| 页面 | 内容 | 备注 |
|------|------|------|
| 仪表盘 (Dashboard) | 风险树形图 + CC 分布直方图 + 高风险模块表 | 面积 = LOC；颜色 = 风险评分 |
| 依赖图 (Dependency Graph) | 力导向图 | 循环依赖标红；支持"仅项目"或"全部导入"过滤 |
| 模块分析 (Module Analysis) | 可排序/搜索的模块表 | 点击行展开查看函数级别 CC 柱状图 |
| 风险列表 (Risk List) | 可搜索的分页列表 | 高复杂度函数、长函数、最大文件、重复代码；参数列带"参数过多"徽章 |

## 🧪 运行测试

```bash
# 安装测试依赖
pip install pytest pytest-cov httpx

# 运行完整测试套件
python -m pytest

# 带覆盖率报告
python -m pytest --cov=backend --cov-report=term-missing

# 执行 70% 覆盖率门禁（与 CI 一致）
python -m pytest --cov=backend --cov-fail-under=70

# 单个模块测试
python -m pytest tests/test_complexity.py -v
```

测试套件包含 **219 个测试**，覆盖所有后端模块和 API 端点。

| 测试模块 | 覆盖内容 |
|----------|----------|
| `test_metrics.py` | `count_lines`、`collect_file_paths`、忽略目录合并 |
| `test_complexity.py` | `_CCVisitor` 决策点计数、`async for`、`match/case` |
| `test_functions.py` | `extract_functions`、`detect_duplicates`、参数计数、哈希稳定性 |
| `test_dependencies.py` | `parse_imports`、`_module_id`、图构建、循环检测 |
| `test_risk.py` | `_normalize`、`_grade`、`compute_risk_scores`、下限截断行为 |
| `test_core.py` | `analyze_project` 端到端、进度回调、忽略目录、失败文件 |
| `test_api.py` | `/health`、`/analyze`、`/result`、`/tasks`；403/404/400/429 边界情况 |
| `test_report.py` | HTML 报告生成、XSS 转义、KPI 卡片、表格行、截断 |

## 🔄 CI 持续集成

GitHub Actions 在每次推送到 `main`、`feature/**` 和 `claude/**` 分支时自动运行完整测试套件，覆盖 Python 3.10、3.11 和 3.12 三个版本。覆盖率必须 ≥ 70%，否则构建失败。Python 3.11 运行的覆盖率 XML 工件会被上传存档。

## 📜 许可证

MIT License — 版权所有 (c) 2026 AaronharveyHan
