# Mini Research

一个适合初学者逐段学习的资料研究助手。输入主题后，它会规划搜索词、搜索公开网页、
筛选相关证据、判断信息缺口、在预算内继续研究，并输出带可点击来源链接的 Markdown
报告。

当前版本保留完整的单 Agent 研究骨架，但刻意不加入 MCP、多 Agent、向量库、数据库或
Web UI。我们先把“搜索—证据—总结—引用”这条主链路真正弄清楚。

## 当前目标与边界

已经实现：

- 根据主题生成结构化 Research Brief；
- 每轮规划少量、不重复的搜索词；
- 使用 Tavily 搜索网页并进行 URL 级去重；
- 从网页正文中提取结构化证据；
- 分析信息缺口，在硬预算内进行下一轮搜索；
- 只根据已接受证据撰写报告；
- 使用任务内稳定来源 ID（`S1`、`S2`……）；
- 由程序校验引用并渲染真实链接；
- 使用 Fake 服务进行完全离线的整图测试。

暂未实现：

- 验证模型给出的摘录一定逐字存在于网页正文；
- 判断引用是否在语义上真正支持对应结论；
- 来源类型、独立性与可信度策略；
- 搜索超时、429 重试和指数退避；
- 成本、延迟和固定主题评测；
- 实时进度 UI、缓存、多 Agent 或 Supervisor。

## 完整工作流

```text
topic
  ↓
build_brief          把主题整理成目标和子问题
  ↓
plan_queries         根据目标/缺口规划查询
  ↓
search_web           搜索并登记去重后的来源 S1、S2...
  ↓
extract_evidence     从每个新来源提取结构化证据
  ↓
analyze_gaps ─────── 证据不足且预算剩余 ──────┐
  ↓                                           │
write_report                                   │
  ↓                                           │
validate_citations                             │
  ↓                                           │
final Markdown report                         │
                                              │
                 plan_queries ←───────────────┘
```

这里最重要的设计是：模型只生成 `[S1]`，不能自行写 URL。只有引用通过程序校验后，
`citations.py` 才会把 `S1` 替换成来源台账中的真实链接。

## 项目结构

```text
mini_research/
├── src/mini_research/
│   ├── app.py              # CLI 与真实服务的组装入口
│   ├── config.py           # 密钥配置、硬预算与质量门槛
│   ├── models.py           # 节点之间共享的数据合同
│   ├── prompts.py          # 每个 LLM 职责的 Prompt
│   ├── graph.py            # LangGraph 节点、条件边与研究循环
│   ├── citations.py        # 确定性引用校验与链接渲染
│   ├── nodes/
│   │   ├── brief.py        # 研究 Brief
│   │   ├── research.py     # 查询、证据、缺口分析
│   │   └── writer.py       # 基于证据写作
│   └── tools/
│       └── search.py       # 搜索接口、Tavily 适配和 URL 去重
├── tests/                  # 不调用真实 API 的离线测试
├── docs/
│   ├── learning-guide.md   # 分阶段阅读与练习路线
│   └── git-guide.md        # 第一次使用 Git/GitHub
├── .env.example            # 可以提交的纯占位配置
└── pyproject.toml
```

## 1. 先运行离线测试

推荐 Python 3.11。进入项目目录后创建独立环境：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

运行测试和静态检查：

```bash
python -m pytest
python -m ruff check src tests
```

离线测试使用 Fake 模型和 Fake 搜索服务，不需要 API Key，也不会产生费用。第一次学习时，
建议先阅读 `tests/test_graph_offline.py`，观察一套可预测的假依赖如何走完整张真实图。

## 2. 配置真实 API

首次配置时：

```bash
cp .env.example .env
```

然后只在 `.env` 中填写：

```dotenv
OPENAI_API_KEY=你的新密钥
TAVILY_API_KEY=你的新密钥
```

安全规则：

- `.env` 只保存在本机，并已被 `.gitignore` 忽略；
- `.env.example` 永远只能放占位符；
- 私有 GitHub 仓库也不能提交真实密钥；
- 密钥一旦出现在可提交文件中，应在服务后台撤销旧密钥并创建新密钥；
- 初学阶段默认关闭 `LANGSMITH_TRACING`，需要调试追踪时再明确开启。

OpenAI 官方文档也要求把 API Key 当作秘密，并从服务端环境变量或密钥管理服务加载：
[OpenAI API Authentication](https://developers.openai.com/api/reference/overview#authentication)。

## 3. 做一次受限联网测试

先用很小的预算确认“模型 + 搜索 + 引用”能够连通：

```bash
mini-research "大模型推理优化技术" \
  --max-rounds 1 \
  --max-searches 1 \
  --max-pages 2 \
  --show-trace
```

也可以不做可编辑安装，直接运行：

```bash
PYTHONPATH=src python -m mini_research "大模型推理优化技术" \
  --max-rounds 1 --max-searches 1 --max-pages 2 --show-trace
```

这只是连通性测试，不代表研究已经充分。即使只有一次网页搜索，Brief、查询规划、证据
抽取、缺口分析和写作仍会分别调用模型，因此依然会产生少量费用。

保存 Markdown 报告：

```bash
mini-research "大模型推理优化技术" \
  --output reports/llm-inference.md \
  --show-trace
```

## 4. 如何观察运行结果

`--show-trace` 会在报告结束后把以下诊断信息写到 stderr：

- 实际执行过的步骤；
- 停止原因 `stop_reason`；
- 搜索次数、来源数量和证据数量。

如果退出码是 `2`，可以显式查看未通过引用校验的草稿：

```bash
mini-research "大模型推理优化技术" \
  --show-trace \
  --show-draft-on-error
```

这个草稿只用于排查模型到底写了 `[S1, S2]`、`【S1】`，还是完全漏掉引用。CLI 会用
`debug only; not published` 标记它；不要把失败草稿当成最终研究结果。

首版会把 `[ S1 ]` 这种仅在合法 ID 两侧多出空格的写法规范化为 `[S1]`，再进行来源
存在性校验和链接渲染。其他变体仍然失败关闭：多个来源必须写成 `[S1][S2]`，不能写
成 `[S1, S2]`。

常见停止原因：

| `stop_reason` | 含义 |
|---|---|
| `evidence_sufficient` | 模型判断充分，而且代码最低来源/证据门槛也满足 |
| `max_rounds_reached` | 达到最大研究轮数 |
| `max_searches_reached` | 达到最大搜索调用次数 |
| `max_pages_reached` | 达到任务内唯一来源上限 |
| `no_new_queries` | 模型没有提出新的有效查询 |

CLI 退出码：

- `0`：报告与引用校验成功；
- `1`：配置、模型、搜索或其他运行错误；
- `2`：研究走完，但引用校验失败，因此拒绝发布草稿。

## 5. 推荐学习顺序

不要从最长的 `graph.py` 开始。推荐按下面顺序学习：

1. `models.py` + `config.py`：先理解数据和预算；
2. `tools/search.py` + `citations.py`：学习不依赖 LLM 的确定性代码；
3. `prompts.py` + `nodes/brief.py`：理解结构化输出；
4. `nodes/research.py` + `nodes/writer.py`：理解不同 LLM 职责为什么要拆开；
5. `graph.py`：最后看节点、条件边、循环和停止条件；
6. `app.py`：理解真实模型、搜索客户端和图如何组装；
7. `tests/test_graph_offline.py`：用 Fake 验证整图，而不是验证随机模型文本。

更具体的每阶段目标、命令和检查点见 [学习指南](docs/learning-guide.md)。

## 节点读写速查

| 节点 | 主要读取 | 主要写入 | 是否可能进入循环 |
|---|---|---|---|
| `build_brief` | `topic` | `research_brief` | 否 |
| `plan_queries` | Brief、缺口、历史查询 | `current_queries` | 否 |
| `search_web` | 当前查询、预算、来源台账 | 新来源、计数器 | 否 |
| `extract_evidence` | 新来源、Brief | `evidence` | 否 |
| `analyze_gaps` | Brief、证据、来源 | 缺口、停止原因 | 是 |
| `write_report` | Brief、证据 | `draft_report` | 否 |
| `validate_citations` | 草稿、来源台账 | 校验结果、最终报告 | 否 |

## 下一阶段 TODO

代码中运行下面命令，可以找到为后续实战保留的位置：

```bash
rg "TODO\(next-step\)" src tests README.md
```

| 编号 | 下一步 | 验收标准 |
|---|---|---|
| T1 | 增加真正走两轮循环的离线测试 | 首轮不足、第二轮充分，断言搜索调用两次 |
| R1 | Tavily 超时、429 重试和结构化错误 | 重试有上限，永久错误不重试 |
| G1 | 校验摘录存在于网页正文 | 找不到原文的证据被拒绝并可诊断 |
| Q1 | 来源类型和可信度策略 | 官方/论文可识别，低质量来源不会只靠模型自评分入选 |
| Q2 | 按子问题记录证据覆盖度 | 缺口能够对应到具体子问题 |
| C1 | 一次受限引用修复 | 第二次仍失败时 `final_report` 保持为空 |
| E1 | 固定主题评测 | 记录成功率、停止原因、调用次数、延迟和估算成本 |

> TODO(next-step) [E1]: 准备至少 10 个固定主题和评测记录格式，先建立基线，再决定是否
> 需要多 Agent；不要仅凭“感觉答案不错”增加架构复杂度。

核心流程始终保持可运行；TODO 是下一阶段的练习入口，不会用 `pass` 故意破坏当前版本。

## Git

项目准备好后再初始化 Git，确保旧教程和真实密钥不会进入历史。`git init`、`git add`、
`git commit` 都只发生在本机，只有 `git push` 才会上传到 GitHub。完整步骤见
[Git 初学者指南](docs/git-guide.md)。

## 来源与许可证

本项目的学习起点来自
[langchain-ai/deep_research_from_scratch](https://github.com/langchain-ai/deep_research_from_scratch)，
现在只保留独立整理后的 `mini_research` 产品代码。许可证见 [LICENSE](LICENSE)。
