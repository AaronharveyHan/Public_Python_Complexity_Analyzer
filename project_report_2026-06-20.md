# Python Complexity Analyzer — 项目报告

**日期**: 2026-06-20 ｜ **分支**: `claude/kind-pasteur-5iIta` ｜ **最新提交**: `2b95deb`

## 1. 项目概述

一个仿 SonarQube 风格的 Python 代码质量分析平台,由三部分组成:

| 层 | 技术 | 职责 |
|---|---|---|
| 分析引擎 | 纯 Python (`backend/analyzer/`) | AST 解析、复杂度/重复/依赖/风险计算 |
| API 服务 | FastAPI (`backend/api/`) | REST + WebSocket、任务队列、鉴权、限流、HTML 报告导出 |
| 前端 | React + ECharts (`frontend/src/`) | 仪表盘、依赖图、模块/风险列表的可视化 |
| CLI | `cli/analyze.py` | 本地一次性分析,JSON/文本输出,可选 HTML 报告 |

代码规模约 4,676 行(backend + frontend/src + cli),测试 **307 个全部通过**。

## 2. 核心分析引擎(`backend/analyzer/`)

- **core.py** — `analyze_project()` 总调度:文件收集 → 单文件解析(LOC/SLOC/函数/导入)→ 跨文件重复检测 → 风险打分 → 依赖图构建 → Top-N 列表汇总。对 `RecursionError`、语法错误、读取失败均有独立的 `failed_files` 兜底,不会让单文件问题中断整体分析。
- **complexity.py** — 基于 `ast.NodeVisitor` 的 McCabe 圈复杂度,支持 `match/case`、`async for`;已修复嵌套函数/方法的复杂度被重复计入外层函数的问题(`_CCVisitor` 对子函数定义短路)。
- **functions.py** — 函数提取 + 基于函数体 AST 规范化哈希的重复检测(对重命名、注释、参数名变化免疫);`self`/`cls` 的剥离改为基于"是否处于 class 作用域"而非参数名猜测,修复了模块级函数误把首参当作 self 的问题。
- **dependencies.py** — `networkx` 构建导入图、检测环;`from . import *` 不再生成虚假的 `"pkg.*"` 伪节点;根目录 `__init__.py` 的模块 ID 回退到项目名。
- **risk.py** — 加权 0–100 分 + A–F 评级,模块级 key 派生逻辑统一抽成 `module_risk_key()`,避免内外两处实现漂移。

## 3. API 服务(`backend/api/`)

- **任务模型**:内存 `_store`(实时进度)+ SQLite 持久化(历史结果),`ThreadPoolExecutor` 跑分析,带超时看门狗(`ANALYSIS_TIMEOUT`,协作式取消 + 终态守卫防止超时后过期结果覆盖)。
- **安全边界**:
  - 路径越权防护(`ALLOWED_BASE_DIR` + symlink 逃逸防护)
  - 可选 Bearer Token 鉴权(`API_TOKEN`,常量时间比较)
  - 按 IP 滑动窗口限流(默认 10 次/60s),带客户端字典硬上限防内存膨胀
  - CORS 白名单,已修复 `allow_headers` 缺失 `Authorization` 导致鉴权场景下预检失败的问题
- **WebSocket** `/ws/{task_id}` 实时进度流,已修复订阅竞态(任务在快照和订阅之间完成的窗口)。
- **report.py** — 自包含 HTML 报告生成器,最新一轮(M-8)刚完成:
  - 模块表/风险 Treemap 按风险排序后共享同一份截断列表,新增可配置参数 `max_modules`(默认 200),避免大型项目把报告渲染成几千行的表。
  - 环检测列表(cycles)、跳过文件列表(failed_files)同样接入截断提示(`.truncation-note`,各自上限 30),与既有的重复/超长/未标注函数列表风格一致。
  - 复杂度分箱(`ccBins`)从 5 次独立全表扫描合并为单次扫描,且不受 `max_modules` 截断影响(仍覆盖全部文件,属全项目聚合指标)。
  - 已修复:HTML 注入(treemap 提示/标签转义)、`risk_score`/`total_loc` 等字段为 `None` 时的格式化崩溃。

## 4. 前端(`frontend/src/`)

四个主要页面:Dashboard(KPI + 复杂度分布)、ModuleAnalysis(可搜索/排序的模块表)、RiskList、DependencyGraph(force-directed 依赖图 + 环列表)。已修复的健壮性问题:
- `riskColor`/`ccColor` 对非数值/NaN 输入回退灰色而非误判为"严重"(原会误标红)。
- 复杂度分布图对非有限值(`NaN`/`Infinity`)直接跳过而非计入最差档。
- 模块搜索过滤对缺失 `relative_path` 加了空值兜底。
- i18n Context 默认值从 `null` 改为安全占位对象,避免 Provider 外使用时崩溃。
- 依赖图渲染过滤空环数组,避免 `c[0]` 访问越界。

## 5. 本次会话完成的修复批次(按审计编号)

| 编号 | 内容 | 状态 |
|---|---|---|
| C-5 | 单文件 RecursionError 不中断整体分析 | ✅ |
| H-9 | 嵌套函数/方法 CC 重复计入 | ✅ |
| H-10 | self/cls 剥离基于类作用域而非参数名 | ✅ |
| H-11 | Treemap 提示/标签 XSS 转义 | ✅ |
| M-5 | 重复检测对重命名/注释免疫 | ✅ |
| M-6 | `from . import *` 伪节点 | ✅ |
| M-7 | 报告中 None 字段格式化崩溃 | ✅ |
| M-8 | 报告输出规模控制 | ✅ |
| M-9 | 复杂度分布对非数值的误分类 | ✅ |
| M-10 | risk/cc 颜色对非数值误判为严重 | ✅ |
| M-11 | 模块搜索缺失字段崩溃 | ✅ |
| L-5~L-13 | 模块 ID 回退、CORS 头、WS token 注释、SQLite 约束注释、锁窗口注释、i18n 默认值、空环渲染等 | ✅ |

加上之前会话已完成的 C-1~C-4、H-1~H-8、M-1~M-4(鉴权暴露、SLOC 误计、限流内存增长、超时取消、重复标记冲突、symlink 逃逸、错误边界、WS 竞态等),**审计 punch list 已全部清零**。

## 6. 当前状态与建议

- 测试:307 个全绿,无已知失败项。
- 待考虑的后续方向(非缺陷,设计权衡):
  - Treemap 现在和模块表共享同一份"按风险 Top-N"列表,体积很大但风险很低的文件可能在大项目里从图上消失(已确认为预期设计)。
  - `max_modules` 当前只能通过 Python 调用方传参,REST API(`/report/{task_id}`)和 CLI 尚未暴露对应的查询参数/命令行选项 —— 如果需要外部可调,这是下一个自然扩展点。
  - 分支尚未合并入 main,所有改动停留在 `claude/kind-pasteur-5iIta`,可视需要创建 PR。
