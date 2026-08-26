# Mini Research

Mini Research 是一个面向初学者的网页资料研究助手。输入一个主题后，它会先整理研究
目标，再规划搜索词、搜索公开网页、提取相关证据、判断资料是否充分，最后生成带真实
来源链接的 Markdown 报告。

这个项目没有急着加入多 Agent、向量库、数据库或 Web UI，而是先把“搜索—证据—总结—
引用”这条主链路完整跑通。当前版本规模不大，但已经包含一次真实研究任务需要的状态
管理、循环控制、外部工具调用、结构化模型输出、引用校验和离线测试。

## 项目是怎样搭起来的

项目首先用 `pyproject.toml` 建立标准 Python 工程，源码、测试和文档分别放在
`src`、`tests` 和 `docs` 中。真实密钥只保存在被 Git 忽略的 `.env` 里，
`.env.example` 只提供可以安全提交的配置模板。这样的基础结构让本地运行、安装后的
命令行运行和测试使用同一套包导入方式。

业务代码没有从工作流图开始写，而是先在 `models.py` 中定义各阶段共享的数据结构。
研究任务、搜索结果、来源记录、证据、信息缺口和最终报告都通过这些模型连接起来；
`ResearchState` 则是整张图共同传递的状态。与研究内容不同，轮数、搜索次数、来源
数量和最低证据门槛统一放在 `config.py` 中，并由 Python 代码强制执行。这样即使模型
没有严格遵守 Prompt，运行成本和循环次数仍然有明确上限。

接下来实现的是结果可预测的基础能力。`tools/search.py` 负责调用 Tavily、规范化 URL、
合并重复网页，并给来源分配 `S1`、`S2` 这样的任务内编号。`citations.py` 负责检查
报告引用的编号是否真实存在，再把编号替换成来源台账中的链接。模型只能写 `[S1]`，
不能自己生成 URL，所以语言组织由模型完成，来源真实性则尽量由程序控制。

大模型相关职责被拆到 `nodes` 目录中：Brief 节点负责把主题变成研究目标和子问题，
研究节点负责规划查询、提取证据和分析缺口，Writer 节点只根据已经接受的证据写报告。
不同阶段的 Prompt 集中放在 `prompts.py` 中。`graph.py` 最后使用 LangGraph 把这些
能力连成可循环的研究流程，而 `app.py` 只在真正启动命令行时读取配置、创建模型和
Tavily 客户端，并把它们注入工作流。

这种拆分的好处是每一层都只处理自己的问题：数据结构不会和 Prompt 混在一起，模型
调用不会和流程跳转混在一起，真实网络服务也不会在导入模块时自动启动。测试时可以把
模型和搜索服务换成 Fake 实现，不联网也能运行同一张 LangGraph。

## 代码结构

```text
mini_research/
├── src/mini_research/
│   ├── app.py              # CLI 与真实服务的组装入口
│   ├── config.py           # 外部配置、硬预算与质量门槛
│   ├── models.py           # 各节点共享的数据合同和 ResearchState
│   ├── prompts.py          # 不同 LLM 阶段使用的 Prompt
│   ├── graph.py            # 节点、条件边和研究循环
│   ├── citations.py        # 引用校验与真实链接渲染
│   ├── nodes/
│   │   ├── brief.py        # 生成研究 Brief
│   │   ├── research.py     # 查询规划、证据提取和缺口分析
│   │   └── writer.py       # 根据已接受证据撰写报告
│   └── tools/
│       └── search.py       # Tavily 适配、URL 规范化和来源登记
├── tests/                  # 使用 Fake 依赖的离线测试
├── docs/
│   ├── learning-guide.md   # 分阶段学习路线
│   └── git-guide.md        # Git 与 GitHub 初学者指南
├── .env.example            # 不包含真实密钥的配置模板
└── pyproject.toml
```

一次真实运行从 `app.py` 开始。它创建依赖并调用 `graph.py`，图中的节点再使用
`nodes` 和 `tools` 完成具体工作。所有中间结果都按照 `models.py` 中的结构写入
`ResearchState`，最后由 `citations.py` 校验草稿并生成可发布报告。

## 工作流程

```text
topic
  ↓
build_brief          整理研究目标和子问题
  ↓
plan_queries         根据目标或当前缺口规划查询
  ↓
search_web           搜索并登记去重后的来源 S1、S2...
  ↓
extract_evidence     从新来源中提取结构化证据
  ↓
analyze_gaps ─────── 资料不足且预算剩余 ──────┐
  ↓                                           │
write_report                                   │
  ↓                                           │
validate_citations                             │
  ↓                                           │
final Markdown report                         │
                                              │
                 plan_queries ←───────────────┘
```

缺口分析认为资料不足时，工作流会带着当前缺口回到查询规划，生成更有针对性的下一轮
搜索词。证据达到最低门槛，或者轮数、搜索次数、来源数量达到上限后，流程才会进入写作。
报告完成后还必须通过引用校验；失败的草稿不会被当成最终结果发布。

## 快速开始

推荐使用 Python 3.11。进入项目目录后创建独立环境并安装项目：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

先运行完全离线的测试和代码检查，它们不需要 API Key，也不会产生费用：

```bash
python -m pytest
python -m ruff check src tests
```

需要真实运行时，复制配置模板：

```bash
cp .env.example .env
```

然后只在本机的 `.env` 中填写 `OPENAI_API_KEY` 和 `TAVILY_API_KEY`。无论仓库是否
私有，都不要提交真实密钥。

用较小预算完成第一次联网测试：

```bash
mini-research "大模型推理优化技术" \
  --max-rounds 1 \
  --max-searches 1 \
  --max-pages 2 \
  --show-trace
```

如果没有执行可编辑安装，也可以使用：

```bash
PYTHONPATH=src python -m mini_research "大模型推理优化技术" \
  --max-rounds 1 --max-searches 1 --max-pages 2 --show-trace
```

保存 Markdown 报告：

```bash
mini-research "大模型推理优化技术" \
  --output reports/llm-inference.md \
  --show-trace
```

`--show-trace` 会显示节点执行顺序、停止原因以及来源和证据数量。如果引用校验失败，
可以增加 `--show-draft-on-error` 查看明确标记为未发布的调试草稿。

## 当前边界

当前版本能够确认引用编号来自已登记来源，却还不能判断某个来源是否在语义上真正支持
对应结论，也没有机械检查模型给出的摘录是否逐字存在于网页正文。来源可信度规则、
搜索重试、缓存、成本评测和多 Agent 都留作后续增量能力。首版最重要的成果，是先得到
一条结构清楚、预算可控、可以离线测试并且不会让模型随意编造链接的研究主流程。

更详细的代码阅读顺序和练习见
[学习指南](docs/learning-guide.md)，第一次使用 Git 和 GitHub 的过程见
[Git 初学者指南](docs/git-guide.md)。

## 来源与许可证

本项目的学习起点来自
[langchain-ai/deep_research_from_scratch](https://github.com/langchain-ai/deep_research_from_scratch)，
当前仓库只保留重新整理后的 Mini Research 项目代码。许可证见 [LICENSE](LICENSE)。
