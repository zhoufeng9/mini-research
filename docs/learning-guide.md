# Mini Research 学习指南

这份指南的目标不是让你一次记住所有代码，而是让每一阶段都能回答三个问题：

1. 这一层解决什么问题？
2. 它接收什么、返回什么？
3. 不调用真实 API，怎样证明它工作正常？

建议严格按顺序学习。每完成一阶段，再进入下一阶段。

## 阶段 0：建立可运行基线

目标：先确认环境与项目本身正常，避免把安装问题误认为业务代码问题。

```bash
python -m pytest
python -m ruff check src tests
```

完成检查点：

- 所有测试通过；
- Ruff 没有报错；
- 你能解释为什么离线测试不需要 `.env`。

## 阶段 1：先读数据，不读流程

阅读：

- `src/mini_research/models.py`
- `src/mini_research/config.py`

重点理解：

- `SearchResult` 是供应商返回的临时结果；
- `SourceRecord` 是任务内带稳定 `S1/S2` 的来源台账；
- `ExtractedEvidence` 不允许模型决定来源 ID；
- `Evidence` 是程序绑定来源后的证据；
- `ResearchState` 是整张图共享的状态；
- `ResearchConfig` 的数字是代码硬预算，不是 Prompt 建议。

小练习：

```bash
PYTHONPATH=src python -c \
  'from mini_research.graph import initial_state; print(initial_state("测试主题"))'
```

完成检查点：你能指出“来源”“证据”“预算”“最终输出”分别存在哪些字段。

## 阶段 2：学习确定性边界

阅读：

- `src/mini_research/tools/search.py`
- `src/mini_research/citations.py`
- `tests/test_search.py`
- `tests/test_citations.py`

运行：

```bash
python -m pytest tests/test_search.py tests/test_citations.py -q
```

重点理解：

- URL 规范化为什么要移除 `utm_*` 和 fragment；
- 同一个 URL 被两次发现时为什么不能产生两个来源 ID；
- Writer 只写 `[S1]`，程序为什么还要检查未知 ID 和裸 URL；
- “引用 ID 存在”与“引用真的支持结论”是两个不同问题。

完成检查点：你能手写一个包含 `[S999]` 的报告，并预测校验结果。

## 阶段 3：理解结构化 LLM 输出

阅读：

- `src/mini_research/prompts.py`
- `src/mini_research/nodes/brief.py`
- `src/mini_research/nodes/research.py`
- `src/mini_research/nodes/writer.py`

重点理解：

- `Protocol` 是工作流依赖的接口，不是具体模型；
- `with_structured_output(Model)` 让模型输出直接解析成 Pydantic 对象；
- Brief、查询、证据、缺口分析、写作为什么要拆成不同职责；
- 网页正文为什么放在 `<untrusted_web_content>` 中；
- 程序为什么仍要截断模型返回的查询和证据数量。

完成检查点：你能说出哪些结果交给模型判断，哪些约束必须由代码强制执行。

## 阶段 4：最后再看 LangGraph

阅读：

- `src/mini_research/graph.py`
- `tests/test_routing.py`

先只看这四部分：

1. `initial_state`：从哪里开始；
2. `determine_stop_reason`：什么时候停；
3. `decide_next`：什么时候循环；
4. 文件底部的 `add_edge` / `add_conditional_edges`：节点如何连起来。

再逐个看内部节点函数。每个节点都问：

- 读取了哪些 state 字段？
- 返回了哪些局部更新？
- 失败时是终止、回退，还是记录非致命错误？

运行：

```bash
python -m pytest tests/test_routing.py -q
```

完成检查点：你能在纸上画出“证据不足但预算还在”时的循环路径。

## 阶段 5：用 Fake 看完整图

阅读：

- `tests/test_graph_offline.py`

这里的 Fake 只让外部结果可预测；执行的 `build_graph(...).invoke(...)` 仍是真实工作流。

运行：

```bash
python -m pytest tests/test_graph_offline.py -q
```

第一个推荐实战是代码中的 `TODO(next-step) [T1]`：

- 首轮 Gap Analyzer 返回 `sufficient=False`；
- 第二轮返回 `sufficient=True`；
- Query Planner 第二轮生成不同查询；
- 最后断言搜索调用两次、trace 中出现两次缺口分析。

这个练习不会消耗 API 额度，却能真正帮助你理解 LangGraph 循环。

## 阶段 6：受限真实运行

只有离线基线通过、密钥已正确轮换并写入 `.env` 后再运行：

```bash
mini-research "大模型推理优化技术" \
  --max-rounds 1 \
  --max-searches 1 \
  --max-pages 2 \
  --show-trace
```

运行结束后依次检查：

1. `stop_reason` 是否符合预算；
2. 来源数量和证据数量是否合理；
3. 报告里的链接是否都来自 Sources；
4. `errors` 是否出现搜索或证据抽取失败；
5. 不要只看文字“像不像答案”，还要抽查引用是否真的支持句子。

## 下一次一起实现什么

推荐顺序：

1. `T1`：两轮离线循环测试；
2. `G1`：证据摘录原文校验；
3. `R1`：搜索重试与错误分类；
4. `Q1/Q2`：来源质量和子问题覆盖；
5. `C1`：一次受限引用修复；
6. `E1`：固定主题评测。

每次只做一个能力，并保持全部旧测试继续通过。
