# 全系统串讲:十八课一张图,四类面试口径一次讲清

> **Outcome:** 学完你能不看资料画出整个 WeKnora RAG 系统的全貌图,把它拆成"RAG 流水线 + 系统实现"两张大图讲给任何人听,并且面对四类必考题(被问 RAG 架构、被问 WeKnora 源码、被问生产实践、被问系统级设计)都有稳定、有源码支撑的讲法与话术。

## Why this matters

前面 17 课把主线学完了:RAG 流水线(0001-0013)解释了"文档怎么进来、怎么被检索、怎么被生成",系统实现(0014-0017)解释了"WeKnora 这套系统怎么搭起来:容器/依赖注入、Agent 引擎、Chat Pipeline、长时记忆"。现在的问题不是"还差哪一课",而是**知识是碎片,面试要的是体系**。这一课不做新东西,只做两件事:把所有课串成两张可复述的图;把面试最常被问的四类问题,逐一给出从源码出发的标准答案。这是从"会读源码"到"能讲系统"的一跳。

## Core idea

### 一、一张总图:入库 4 + 问答 3 + 系统横切 4

全部十八课可以压缩成一张图。三条横向主链(入库、问答),加一条纵向系统链:

```text
        ┌─────────── 系统实现(容器/Agent/Pipeline/记忆)───────────┐
        │ 0014 架构(容器+路由+引擎注册) │ 0015 Agent 引擎 │
        │ 0016 Chat Pipeline │ 0017 记忆                          │
        └────────────────────────────────────────────────────────┘
入库(离线,一次)
原始文档 → ①解析 0002 → ②切分+嵌入 0003 → ③索引 0004

问答(在线,每次)
用户提问 → ④检索 0005 → ⑤融合/重排 0006 → ⑥生成+引用 0007
        └─ 元数据 0008 · 评估 0009 · 高级 0010 · Graph 0011 · Agentic 0012 · 理论 0013
```

每个编号都对应该课文件名(如 `0005-hybrid-retrieval.md`),面试时你可以"指哪儿打哪儿"。

### 二、串讲口径一:被问"RAG 架构怎么讲"

**一句话版**:RAG = 先检索再生成。文档离线入库(解析→切分→嵌入→索引),用户提问在线问答(检索→融合重排→生成带引用)。

**两分钟版**(按 0001 课的四阶段递进讲):
- 为什么 RAG:LLM 四大短板(领域知识缺乏/信息过时/幻觉/数据安全),RAG 通过外部知识库补齐,不全量塞 prompt 因为 token 有限且噪声稀释注意力
- 流水线七环节:入库 4(解析/切分/嵌入/索引)+ 问答 3(检索/融合重排/生成)
- 现代演进:混合检索(关键词+向量双路)→ 重排 → Advanced(检索前中后优化)→ GraphRAG(跨文档综合)→ Agentic(自主决定查哪)
- 关键设计决策:混合检索双路互补、RRF 融合、MMR 去重、引用溯源(0005/0006/0007 课)

### 三、串讲口径二:被问"WeKnora 源码怎么讲"

**一句话版**:WeKnora 是腾讯开源的 Go RAG 引擎,核心是"可插拔引擎注册表 + 混合检索 + ReAct Agent"。

**源码抓手**(按 0014-0017 课):
- 架构:`internal/container/container.go` 的 `BuildContainer`(dig 依赖注入),`initRetrieveEngineRegistry` 注册七种检索引擎(PostgreSQL/SQLite/ES/OpenSearch/Qdrant/Weaviate/Milvus),每种实现同一 `RetrieveEngineService` 接口,加新后端 = 实现接口 + 注册一行
- Agent 引擎:`internal/agent/engine.go` 的 `Execute`→`executeLoop`(Next/Continue/Break 哨兵)→`runReActIteration`(Think/Analyze/Act/Observe),工具调用经 `act.go` 并行执行,`approval/gate.go` 审批
- Chat Pipeline:`internal/application/service/chat_pipeline/chat_pipeline.go` 十事件流式阶段,`merge.go` 的 merge 家族(expand/overlap/position)按坐标把碎片拼回完整上下文
- 记忆:`internal/application/service/memory/` 四段生命周期(异步提取→入库→巩固→召回),`ResolveScope` 用 tenantID+SubjectID 做安全隔离

### 四、串讲口径三:被问"生产实践怎么讲"

**一句话版**:混合检索是标配不是可选项,重排必上,引用必须可溯源,评估要指标化。

**生产实践四件套**:
- **检索质量**:混合检索(BM25 + 向量,RRF 融合)兜住"精确词漏了"和"语义漂移"两类失败;chunk-merge 不能误删文档中本来就重复的样板句(否则内容不可逆丢失)
- **安全**:SSRF 三道防线(请求前校验、禁重定向、结果缓存带白名单失效),WeKnora 的 `utils.ValidateURLForSSRF` + `_NoRedirectHandler` 是教科书实践
- **可解释**:引用溯源,`<ref>` 句柄在请求本地生成、模型摸不到真实全局 ID,防幻觉也防泄露
- **评估**:Precision/Recall/NDCG/MRR/MAP(检索侧)+ BLEU/ROUGE(生成侧),RAGAS/DeepEval 做自动化;改进遵循"模糊转精确"原则

### 五、串讲口径四:被问"系统级设计怎么讲"

**路径 A(功能,RAG 七步)**:0001 总览 → 0002 解析 → 0003 切分嵌入 → 0004 向量库 → 0005 混合检索 → 0006 重排 → 0007 生成引用(可再加 0008-0013 是升级与理论)。

**路径 B(工程,系统实现)**:0014 架构(容器/路由/引擎注册)→ 0015 Agent 引擎 → 0016 Chat Pipeline → 0017 记忆。"一条数据的一生":文档进来 → docparser 解析 → chunker 切分 → embedding 批量嵌入 → 存入向量库 → 用户提问 → 混合检索双路召回 → RRF 融合 → rerank 重排 → MMR 去重 → 组装上下文 → Agent 生成带引用。

## Worked example

**面试现场模拟**——面试官问:"你们 RAG 系统如果检索结果不准,你会从哪几个方向排查?"

**标准回答**(分层递进):
1. **先看召回还是排序**:候选集里有没有正确答案?没有 → 召回问题(切分太粗/嵌入模型不对/漏了关键词路);有但排不上去 → 排序问题(加重排/调 RRF 权重)
2. **再看查询侧**:用户问题是否被查询重写/扩展?有没有元数据可以缩小范围?(0008 课)
3. **再看数据侧**:解析有没有丢内容?chunk-merge 有没有误删?子块有没有独立 embedding?(0002/0003 课)
4. **最后量化**:用 NDCG@10/MRR 测排序,用 Recall 测召回,改完跑评测闭环看指标是否真升(0009/0013 课)

这套回答覆盖检索全链路,每一层都有源码/理论支撑,面试官追问任何一层你都能接住。

## Retrieval practice

1. 闭卷题:画出 WeKnora 的"入库 4 + 问答 3 + 系统实现 4"总图,标出每环节对应的课程编号和源码位置。
2. 迁移题:面试官问"你的 RAG 系统上线后怎么保证不胡说八道",你用哪几课的知识回答?按什么顺序讲?

<details>
<summary>Check answers</summary>

1. 入库:0002 解析(docparser)/0003 切分嵌入(chunker+embedding)/0004 索引(向量库);问答:0005 检索(混合双路)/0006 融合重排(RRF+rerank+MMR)/0007 生成引用(ReAct+ref);系统实现:0014 架构(container 注册表)/0015 Agent 引擎(executeLoop)/0016 Chat Pipeline(merge 家族)/0017 记忆(memory service)。
2. 顺序:① 引用溯源(0007)——每个结论可追溯到出处,这是第一道防线;② 评估指标化(0009/0013)——用 faithfulness/NDCG 持续监测;③ 检索质量兜底(0005/0006)——混合检索+重排让模型"有据可依";④ 高风险场景加 CRAG/Self-RAG 评分循环(0010)——检索质量不行就修正或拒绝回答。

</details>

## Try it

不看任何资料,在一张纸上画出"入库 4 + 问答 3 + 系统实现 4"总图,然后对着 0014 课的容器注册表部分,说出三种检索引擎的注册方式。能画出来、能说出来,这十八课就算真正吃透了。

## Source

- WeKnora 官方仓库:https://github.com/Tencent/WeKnora
- 本课程各课(0001-0017 + 0013 检索理论)
- 论文与资料清单:见站内"论文与资料"(20-rag-papers)

- [WeKnora 官方仓库](https://github.com/Tencent/WeKnora)
