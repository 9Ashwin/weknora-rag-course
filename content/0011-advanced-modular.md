# Advanced RAG 与 Modular RAG:检索前中后逐段优化 + 模块化编排

> **Outcome:** 学完你能区分 Naive / Advanced / Modular 三种 RAG 范式,按"检索前→检索中→检索后"三个环节说出主流优化手段,解释 Modular RAG 为何靠编排(路由/调度/知识引导)脱颖而出,并在 WeKnora 源码里指出每个优化环节的落点与缺失项(哪些内置、哪些要做 CRAG/语义缓存扩展)。

## Why this matters

Naive RAG("切分→向量→生成")能跑,但一遇到复杂问题就漏召回、答得糙。Nvidia 与 Apple 三年财务分析的经典案例,讲清楚了"从 Naive 到 Advanced 再到 Modular"的演进逻辑;2026 年的生产实践又补上了两层:一是 **CRAG / Self-RAG 这类"检索质量评分循环"**让系统能自己判断检索够不够好,二是 **语义缓存**把重复查询挡在 LLM 之前省钱。别把它们当玩具——这决定了 RAG 从"demo"走向"能用、可控、便宜"的三道坎。

## Core idea

### 一、三个范式是"继承与发展"关系

核心结论:**Advanced RAG 是 Modular RAG 的一种特例,Naive RAG 又是 Advanced RAG 的基础特例**。不是三个并列选项,是一条演进链:

|          |                                                              |                                  |                                     |
|----------|--------------------------------------------------------------|----------------------------------|-------------------------------------|
| **范式** | **核心**                                                     | **能解决的**                     | **局限**                            |
| Naive RAG | 索引 + 检索 + 生成,最小链路                                 | MVP、基础任务                    | 复杂/多文档/时间约束问题答不好     |
| Advanced RAG | 检索前 / 中 / 后三段逐项优化                                  | 提升召回准确率与生成相关性       | 流程仍是固定链式,场景一换要重调    |
| Modular RAG | 把流程拆成可插拔模块,靠**编排**自由组合                      | 多场景自适应、高扩展性           | 编排本身有设计/调试成本             |

### 二、Advanced RAG 的检索前 / 检索中 / 检索后

以 Nvidia / Apple 案例为骨架:问题要求"分析两家公司**过去三年**财务表现,判断哪家更值得投资",涉及**时间范围 + 多文档 + 专业财务指标**三重复杂度。

**检索前优化**(索引与查询侧,让"待检索的东西"更好找):
- 滑动窗口/重叠切分:块间留重叠,保住上下文连贯
- 元数据添加:给块挂"年份、章节、文档类型",查询时可一键过滤时间段
- 分层索引 / 查询重写:把口语问题改写成"关键财务指标 + 股票价格"的清晰查询

**检索中优化**(召回侧,多路抓取):
- 层次化结构检索:按章节层级(业务 / 风险因素)更精准定位
- 多路召回 + 融合:关键词 + 向量各召回一批再融合

**检索后优化**(给 LLM 之前):
- 重排序(Rerank):用 query-doc 相关性把最相关的排前面
- 上下文压缩:只保留真正相关的几段,省 token、降噪声

案例里 Advanced RAG 的答案补上了 Nvidia 与 Apple 的收入、波动性比较和投资机会分析,而 Naive 只罗列了股价——差距就出在这三段优化上。

### 三、Modular RAG:编排(Orchestration)是灵魂

Modular RAG 区别于 Advanced RAG 的**最显著部分是编排**,核心是**自由流程控制 + 动态决策**,关键模块:

- **路由(Routing)**:收到查询后按特点/上下文选最合适的流程(复杂问题走多步,简单问题直接答)
- **调度(Scheduling)**:决定各模块的执行顺序、是否并行
- **知识引导(Knowledge Guidance)** 与推理路径:动态决定查询处理路径

编排的价值:同一个系统能面对多样场景自适应,不用每个场景重写一套链。

### 四、2026 演进:CRAG / Self-RAG、查询变换与语义缓存

- **CRAG(改正式检索)**:检索结果先评分,评分低就触发修正(重写查询 / 换检索源 / 拓宽召回)或直接跳过,再进入生成——把"检索质量"变成可校验的循环
- **Self-RAG**:让 LLM 自己反思"这段够不够支持我的回答",用反思 token 决定要不要再检索
- **查询变换(Query Transformation)**:HyDE、子问题分解、多查询,让一次粗糙提问变成多发、更精准的检索
- **语义缓存**:相同/相似的查询命中缓存直接返回,不进 LLM——省成本、降延迟

2026 年的实操排序(呼应 0001 的"按失败模式爬梯子"):先确认**失败发生在哪一段**——是"查不到"→改检索前/中;是"查到了排不对"→重排;是"答案错了代价高"→上 CRAG/Self-RAG;是"重复问题多"→语义缓存。

## Worked example

**案例(Nvidia / Apple)**:Naive RAG 检索到不同年度 Nvidia 报告的同一章节,时间范围混了、Apple 内容缺失,输出只有股价。逐段排查:
- 检索前:给块加"年份"元数据、把问题重写成"近三年 Nvidia 与 Apple 的收入与波动率对比"→解决时间混用
- 检索中:按章节层级 + 双路召回→解决 Apple 缺失
- 检索后:rerank 把财务指标排前→解决"内容对了但顺序错"

**对照 WeKnora 源码(哪些内置,哪些缺失)**——用真实函数/路径说话:

|          |                                                            |                                    |
|----------|------------------------------------------------------------|------------------------------------|
| **优化** | **WeKnora 落点**                                           | **是否内置**                       |
| 多引擎/可插拔 | `internal/container/container.go` `initRetrieveEngineRegistry`(约 1090 行) | ✅ 七种检索引擎 + `RetrieveEngineRegistry`,天然模块化 |
| 混合检索 | `internal/application/service/retriever/` composite 按 `RetrieverType` 路由 | ✅ 关键词 + 向量双路(0005)          |
| 重排 | `internal/models/rerank/`(aliyun/jina/nvidia/volcengine/zhipu 等 provider) | ✅ 多 provider 可插拔              |
| 检索后 LLM 重排 | `internal/agent/tools/knowledge_search.go` 的 `rerankWithLLM` `rerankThreshold` | ✅ 模型/阈值可选                    |
| 查询重写/查询变换 | 依赖 ReAct agent 多工具迭代,无独立 rewrite 模块            | ⚠️ 未内置,作为扩展方向             |
| CRAG/Self-RAG 评分循环 | 无检索质量自评模块                                         | ⚠️ 未内置,作为扩展方向             |
| 语义缓存 | `internal/models/chat/prompt_cache.go`                      | ✅ 有 prompt 层缓存,可在检索侧扩展 |

一句话:**WeKnora 把"检索中多路 + 检索后可插拔重排 + 模块化注册表"做扎实了;CRAG 评分循环与显式查询变换它不内置,正是你要自己补的 2026 增强项。**

## Retrieval practice

1. 闭卷题:Advanced RAG 按"检索前 / 检索中 / 检索后"各举一个优化手段;Modular RAG 区别于 Advanced RAG 最显著的部分是什么?
2. 迁移题:你的客服 RAG 频繁收到"怎么退钱"(语义宽泛)和"工单 S12345 状态"(精确标识符)两类问题,且大量重复咨询。对照三个环节和 2026 演进方向,你会分别加哪一类优化?为什么?

<details>
<summary>Check answers</summary>

1. 检索前:滑动窗口/元数据/分层索引/查询重写;检索中:层次结构检索、多路召回+融合;检索后:重排、上下文压缩。Modular 区别于 Advanced 的最显著部分是**编排(Orchestration)——路由、调度、知识引导等动态流程控制**,而非固定链式。三者是继承关系:Advanced ⊂ Modular,Naive ⊂ Advanced。
2. "怎么退钱"语义宽泛→靠向量路召回,若排序不对加重排(检索后);"工单 S12345"是精确标识符→靠关键词路(检索中混合检索),必要时加元数据过滤工单号字段(检索前);大量重复咨询→上**语义缓存**,命中直接返回,避开 LLM;"答案错了代价高"的退款政策→上 **CRAG**,对检索片段评分,低分则重写查询或换源。按失败模式上优化,别一步到位堆 CRAG。

</details>

## Try it

打开 WeKnora 源码的 `internal/models/rerank/reranker.go`,看接口定义了哪些方法;再对照 `internal/container/container.go` 的 `initRetrieveEngineRegistry`,画出 WeKnora 的"可插拔"结构——哪些环节你做扩展时是"换实现"而不是"改主流程"。

## Source

- WeKnora 源码的 `internal/container/container.go`(initRetrieveEngineRegistry 约 1090 行)、`internal/models/rerank/`、`internal/agent/tools/knowledge_search.go`(rerankWithLLM / rerankThreshold)、`internal/models/chat/prompt_cache.go`
- 2026 演进参考:CRAG / Self-RAG 检索质量评分循环、查询变换、语义缓存(How to Build RAG Systems in 2026: 8 Architecture Patterns)

- [Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection](https://arxiv.org/abs/2310.11511)
- [Corrective Retrieval Augmented Generation (CRAG)](https://arxiv.org/abs/2401.15884)
