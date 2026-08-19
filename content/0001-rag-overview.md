# RAG 全景与架构选型:从 Naive 到 Agentic

> **Outcome:** 学完你能画出 RAG 流水线七环节,说清 LLM 的四大短板怎么被 RAG 补上,按失败模式给系统选对架构档位(Naive / Hybrid / Advanced / GraphRAG / Agentic),并指出 WeKnora 源码里每一环的落点。

## Why this matters

这一课是整个课程的坐标系。后面 11 课会逐环拆 WeKnora 的源码,但如果你一开始不知道 RAG 为什么存在、现代 RAG 有多少种形态、自己遇到的是哪一类问题,学完源码也只是"会读不会选"。第一讲给的是 RAG 的"为什么",第二讲给的是"自然语言改造传统系统的收益模型",而 2026 年的生产实践补上了最关键的一层:**架构不是越新越好,是按失败模式爬梯子**。这一课把三层合并成一张决策地图。

## Core idea

### 一、LLM 四大短板,与 RAG 的解法

课程里把大模型的局限归纳为四点,现代 RAG 的价值全部建立在它们之上:

|          |                      |                                 |
|----------|----------------------|---------------------------------|
| **短板** | **表现**             | **RAG 解法**                    |
| 领域知识缺乏 | 训练数据是公开互联网,覆盖不了企业内部知识 | 私有文档入库,检索私有知识       |
| 信息过时 | 训练截止后不知道新事   | 文档实时入库,检索最新内容       |
| 幻觉 | 基于概率生成,不懂装懂编答案 | 强制基于检索片段作答,附来源引用 |
| 数据安全 | 私有数据不能交给公开模型 | 知识只进检索库,LLM 只看到检索片段 |

为什么不全量把所有知识塞进 prompt?两个原因:一是 token 有上限且贵,二是**提供少量相关关键信息,回答质量反而更高**——噪声会稀释模型的注意力。这就是"检索"存在的意义:不是把所有知识给模型,是给模型此刻最需要的几块。

### 二、流水线七环节:入库 4 + 问答 3

```text
原始文档 → ①解析(docparser)→ ②切分(chunker)→ ③嵌入(embedding)
→ ④索引(向量库)→ 用户提问 → ⑤检索(retriever)→ ⑥融合/重排(rerank)
→ ⑦生成(LLM 基于片段作答,附引用)
```

前四步是"入库"(离线,文档写进来一次),后三步是"问答"(在线,每次提问跑一遍)。WeKnora 的 Go 代码里,这七环分别对应:

|          |                                              |                                                  |
|----------|----------------------------------------------|--------------------------------------------------|
| **环节** | **代码位置**                                 | **核心类型**                                     |
| 解析     | `internal/infrastructure/docparser/`         | engine_registry.go(多引擎注册)                   |
| 切分     | `internal/infrastructure/chunker/`           | strategy.go / splitter.go                        |
| 嵌入     | `internal/models/embedding/`                 | batch.go(批量池)                                 |
| 索引     | `internal/application/repository/retriever/` | postgres/sqlite/es/milvus 等                     |
| 检索     | `internal/application/service/retriever/`    | composite.go(按类型路由)                         |
| 重排     | `internal/models/rerank/`                    | rerank provider                                  |
| 生成     | `internal/agent/` + `internal/modelcontext/` | ReAct agent + prompt 组装                        |

### 三、架构谱系:2026 年按失败模式爬梯子

2024 年的课程讲的是基础流水线;2026 年生产实践给了一张更完整的谱系。关键判断:**不要按"新不新"选架构,按"当前系统死在哪一环"选**:

|          |                                                    |                                   |                                      |
|----------|----------------------------------------------------|-----------------------------------|--------------------------------------|
| **档位** | **解决什么问题**                                   | **什么时候上**                    | **对应能力**                         |
| Naive RAG | 最小可用:解析→切分→向量→生成                      | 起步,验证场景                    | 单一向量检索                         |
| Hybrid RAG | 向量漏掉精确匹配(名字/编号/代码/政策号)             | 出现精确词召回失败时              | BM25 关键词 + 向量双路,RRF 融合      |
| + Reranker | 候选集里有正确答案,但排不在前面                     | 正确内容被埋没时                  | 跨编码器/API 重排                    |
| Advanced RAG | 检索前/中/后逐段优化(查询变换/元数据/上下文压缩)   | 检索质量成为瓶颈时                | 查询重写、混合检索、重排、压缩       |
| CRAG / Self-RAG | 答案错了代价高,必须验证检索质量                     | 金融/医疗/客服等高风险场景        | 检索结果评分循环,低质量则修正或跳过 |
| GraphRAG | 需要跨文档综合、关系推理                             | 单一文档检索拼不出答案时          | 知识图谱 + 社区摘要                  |
| Agentic RAG | 一次检索拿不够上下文,需要自主决定查哪、查几次       | 复杂任务、多数据源、编排需求      | 多智能体:分解→检索→验证→组装       |

2026 年的一个反直觉结论:**大部分团队最大的、最便宜的提升在梯子中间**——检索漏精确词,先上混合检索和重排,这两周就能上线;GraphRAG 和 Agent 是热词,但往往是"还不需要时就被架上去"的过度设计。

### 四、WeKnora 站在梯子的哪一级

WeKnora(腾讯开源,19.8k★)不是 Naive RAG,它是 Hybrid + Advanced + 可扩展 Agent 的生产级实现:

- 检索引擎注册表(`internal/container/container.go` 的 `initRetrieveEngineRegistry`):PostgreSQL、SQLite、Elasticsearch v7/v8、OpenSearch、Qdrant、Weaviate、Milvus 七种后端,同一种 `RetrieveEngineService` 接口
- 混合检索:ParadeDB BM25(`|||` 全文搜索)+ pgvector(`<=>` 余弦距离),上层 `CompositeRetrieveEngine` 按 `RetrieverType` 路由
- 融合/重排:`internal/models/rerank/` 接重排模型
- 生成层带 ReAct Agent 编排和引用溯源

所以这门课以 WeKnora 为实战对象,等于直接学一个"2026 年企业级 RAG 该长什么样"的完整标本——不是玩具 demo,是微信对话开放平台在用的核心。

## Worked example

**案例一(Naive 为什么失败)**:用户问"分析 Nvidia 和 Apple 过去三年的财务表现,哪家更值得投资"。Naive RAG 检索到的是不同年度报告里的同一章节,时间范围混了,Apple 内容缺失,最后只输出股价信息,给不出分析。问题出在:**复杂问题需要跨文档、带时间约束的检索,单次向量检索做不到**。Advanced RAG 靠检索前优化(查询重写/时间过滤)、检索中优化(多路召回)、检索后优化(重排/压缩)补救——这就是 0006、0008、0010 课的内容。

**案例二(收益模型)**:传统 MIS 系统查一条数据要 2+N+1 步,自然语言查询只 1 步,省 N+2 步;录入 3+N+1 步变 1 步。N 越大收益越大——RAG 对传统系统的价值是**把操作步骤压缩成一句自然语言**。这是 RAG 最朴素也最扎实的商业场景。

**案例三(2026 混合检索的必然性)**:企业客服问"能退钱吗",知识库里写的是"退款流程";又问"X200 激活码怎么弄",向量检索把"激活码"漂移到"验证码"的块上。前者关键词漏,后者向量漂——**单一检索路线的死穴正好被另一路补上**,这就是 0005 课混合检索的动机。

## Retrieval practice

1. 闭卷题:LLM 的四大短板是什么?为什么 RAG 不把所有知识直接塞进 prompt?
2. 迁移题:你的客服知识库,用户问"订单 S12345 为什么没发货"——精确订单号、政策条款、情绪化表达三种情况,分别会死在哪一路检索?该上哪一档架构?

<details>
<summary>Check answers</summary>

1. 领域知识缺乏、信息过时、幻觉、数据安全。不全量塞 prompt 因为:token 上限和成本;噪声稀释注意力,少量相关片段反而回答更准。RAG 的本质是"给模型此刻最需要的几块知识"。
2. 订单号 S12345 是精确标识符,纯向量检索会"模糊掉"精确匹配,需要 BM25 关键词路(Hybrid 档);政策条款涉及精确引用,同理由关键词路兜底,高风险时加 CRAG 评分;情绪化表达"为什么没发货"语义宽泛,靠向量路召回,若候选正确但排序不对,加重排。判断依据:先看失败模式是"精确词漏了"(→关键词路)还是"语义没对上"(→向量路)还是"答案在候选里排不上去"(→重排)。

</details>

## Try it

打开 WeKnora 源码的 `README_CN.md`,找到"三大能力"或"架构"章节,对照本课的七环节表格,标出你已经认识的环节和完全陌生的环节——陌生环节就是接下来 11 课的重点。

## Source

- WeKnora 源码的 `README_CN.md`、`internal/container/container.go`(1080-1310 行引擎注册)、`internal/types/retriever.go`(RetrieverType 常量)
- 2026 RAG 架构模式参考:How to Build RAG Systems in 2026: 8 Architecture Patterns(aithinkerlab.com)

- [Retrieval-Augmented Generation for Large Language Models: A Survey](https://arxiv.org/abs/2312.10997)
- [Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG](https://arxiv.org/abs/2501.09136)
