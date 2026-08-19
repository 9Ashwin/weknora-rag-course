# GraphRAG:知识图谱增强检索,打通跨文档综合与关系推理

> **Outcome:** 学完你能说清微软 GraphRAG 解决 RAG 的哪两个痛点(片段连接有限、归纳总结不足),解释实体/关系/多跳推理的工作方式,列出 GraphRAG 的高门槛与适用场景,并在 WeKnora 源码里找到它真实内置的知识图谱实现(graphBuilder / query_knowledge_graph 工具),同时知道 2026 年"GraphRAG 不是万灵药、别默认上 agent 和 graph"的取舍。

## Why this matters

传统向量 RAG 把文本切碎映射成向量,擅长"局部语义匹配",却不擅长两件事:跨多个信息片段**建立联系**,以及在超长文档里**归纳总结**。微软 2024 年 2 月博客、4 月论文《From Local to Global》与 7 月开源 GraphRAG,正是冲着这两个短板来的。后续课程会分别讲它"为什么强"和"贵在哪、什么时候才值得上"。2026 年的生产实践给了冷静的一刀:**GraphRAG 是关系推理/跨文档综合的特种工具,不是默认架构**——先把它的价值和代价都看清,才能选对。

## Core idea

### 一、微软指出的 RAG 两大局限

课程原文的核心要点:

1. **信息片段之间的连接能力有限**:回答需要"通过共享属性在不同信息间建立联系"的复杂问题时(即**多跳推理**、整合多源),纯向量 RAG 抓不住关系
2. **归纳总结能力不足**:从数百页长文档中提取关键要点、总结复杂语义概念,RAG 力不从心

### 二、知识图谱与 GraphRAG 的做法

知识图谱 = **实体(Entities)+ 属性(Attributes)+ 关系(Relations)**。GraphRAG 用 LLM 把文档里的实体和关系结构化地抽出来建图:

```text
文档 → LLM 抽取实体/关系 → 构建图谱(节点=实体,边=关系)
→ 查询时先关联查询实体 → 沿边做多跳推理 → 召回相关文档片段 → 生成
```

- 精确关系捕捉:实体间关系显式存在图里
- 多跳推理:通过一条条边把不相邻的信息连起来
- 微软论文声称业务复杂问题上 LLM 响应准确度平均提升 3 倍以上

### 三、GraphRAG 的优点与硬伤

**优点**:擅长**超长文档 + 复杂关系**。"菩提祖师和唐僧是什么关系?"——两人不出现在同一章节,传统 RAG 只查得到各自的知识、推不出关系;GraphRAG 入库时抽出"菩提祖师—师傅—孙悟空"和"唐僧—师傅—孙悟空"两条边,检索到三实体两关系,大模型就能答"两人都是孙悟空的师傅"。关系越多越复杂,优势越明显。

**硬伤(门槛极高)**:
- 算力、时间、人力成本都高(举例:有公司花 8 个月和大量技术人力才做成熟)
- **最大难点是"知识如何正确入库"**:同名实体可能不是同一个(两处"土地公公"其实是两个),识别错关系图就错
- 典型适用场景:知识本身已被正确结构化入库的场景,如社交关系风控系统

### 四、WeKnora 有真实的知识图谱实现(不是只有理论)

⚠️ 纠正一个常见误判:"WeKnora 靠混合检索、GraphRAG 只是扩展方向"**不准确**——它内置了知识图谱增强检索。真实证据:

- 类型定义:`internal/types/graph.go` 定义 `Entity`(ID/ChunkIDs/Frequency/Degree/Type)、`Relationship`(Source/Target/Weight/Strength)、`GraphBuilder` 接口(`BuildGraph` / `GetRelationChunks`)
- 图构建服务:`internal/application/service/graph.go` 的 `graphBuilder.BuildGraph`(约 356 行),含实体/关系抽取并发上限(各 4)、PMI(PMIWeight=0.6)+ 强度(StrengthWeight=0.4)加权、间接关系权重衰减(IndirectRelationWeightDecay=0.5)
- 图检索:`GetRelationChunks(chunkID, topK)` 按关系强度返回关联块
- Agent 工具:`internal/agent/tools/query_knowledge_graph.go`(`ToolQueryKnowledgeGraph`),让 agent 主动查"实体间关系与知识网络"，例如 Docker 与 Kubernetes 的关系

**但要说清边界**:WeKnora 做的是"图增强检索"(graph enrichment + 关系召回),**不是微软 GraphRAG 的全局社区摘要(global search / Local→Global)那一整套**。主路径仍是混合检索(0005),图谱是可选的增强检索工具,需在知识库侧开启图抽取配置。

### 五、2026 取舍:GraphRAG 是特种工具,不是默认

- 只用于**跨文档综合 / 关系推理 / 超长文档归纳**这类场景;单文档、精确问答用不上
- **别把 agent 和 graph 当默认**——大多数客服/FAQ 场景,混合检索 + 重排(0006/0010)已经够且便宜得多
- 上 GraphRAG 前先问:我的问题真的需要"跨实体的关系推理"吗?还是只是词没对上?后者用关键词路就解决了

## Worked example

**案例一(关系推理)**:问"菩提祖师和唐僧的关系",两实体不在同一章节,传统 RAG 各查各的、答不出;GraphRAG 靠"两人同是孙悟空的师傅"这条共享关系答出。这正是跨文档综合的典型。

**案例二(WeKnora 里怎么用)**:在开启图抽取的知识库上,agent 可通过 `query_knowledge_graph` 工具查询实体关系,再结合 `knowledge_search` 的工具召回原文片段——**图负责"连关系",向量/关键词负责"取原文"**,两者互补而非互替。

**案例三(别过度设计)**:客服问"能退钱吗",知识库里有明确退款条款——这是单文档精确/语义检索问题,GraphRAG 帮不上忙,混合检索(0005)即可。硬上 GraphRAG 只会引入"入库错误 + 高成本"两个新问题。

## Retrieval practice

1. 闭卷题:微软指出纯向量 RAG 的两大局限是什么?GraphRAG 的最大实现难点是什么,举的"土地公公"例子说明了什么?
2. 迁移题:你的知识库要回答"A 部门的技术方案与 B 部门的下游依赖之间跨文档的关系"。在上 GraphRAG 之前,你会先做哪三步判断?WeKnora 现有能力(图谱 + 混合检索)里,哪一步可以先用起来?

<details>
<summary>Check answers</summary>

1. 两大局限:信息片段之间的连接能力有限(难以做多跳推理/整合多源);归纳总结能力不足(超长文档抽要点难)。最大难点是**知识正确入库**——"土地公公"例子说明:两个看似同名同义的实体可能是不同的实体,实体识别错误会导致整张关系图出错,属于门技术、贵成本、高风险。
2. 三步判断:①问题是否需要"跨实体的关系推理",还是纯单文档语义/精确检索(后者走混合检索即可);②知识是否已被结构化、实体边界是否清晰(不清晰则入库是最大的坑);③成本预算是否撑得起建图与维护。WeKnora 现成的两件事可以先做:开启知识库图抽取并调用 `query_knowledge_graph` 工具让 agent 做关系召回,同时保留混合检索取原文——先验证"图增强"是否真的提升,再决定要不要上完整的社区摘要式 GraphRAG。

</details>

## Try it

打开 WeKnora 源码的 `internal/types/graph.go`,读 `Entity` / `Relationship` 的字段和 `GraphBuilder` 接口;再打开 WeKnora 源码的 `internal/agent/tools/query_knowledge_graph.go`,看它的"何时使用"描述——想清楚它与 `knowledge_search.go` 的分工。

## Source

- 微软 GraphRAG 论文《From Local to Global: A Graph RAG Approach to Query-Focused Summarization》(arXiv:2404.16130)
- WeKnora 源码的 `internal/types/graph.go`、`internal/application/service/graph.go`(graphBuilder.BuildGraph / GetRelationChunks)、`internal/agent/tools/query_knowledge_graph.go`
- 2026 取舍参考:GraphRAG 用于跨文档综合/关系推理、避免默认 agent 与 graph 的过度设计

- [From Local to Global: A Graph RAG Approach to Query-Focused Summarization](https://arxiv.org/abs/2404.16130)
- [Microsoft LazyGraphRAG: Setting a new standard for quality and cost](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost)
