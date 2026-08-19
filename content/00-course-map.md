# WeKnora RAG 课程地图(四阶段)

从腾讯开源 Go 实现(WeKnora 19.8k★)系统学会 RAG 开发并吃透整个系统。理论骨架来自 RAG/检索/存储公开课程,实战对象是 WeKnora 源码,并补 2026 年生产实践。

**学习路径四阶段:地基(懂原理)→ 流水线(会写 RAG)→ 进阶(懂现代形态)→ 系统实现(吃透源码)。** 编号是章节号,阅读顺序按本地图分组走。

---

## 阶段一 · 地基:为什么 + 检索理论

> 学完能:说清 RAG 为什么存在、流水线怎么运转,以及检索的底层理论(倒排/BM25/TopK/评估指标/MMR)。

- [01 · RAG 全景与架构选型](0001-rag-overview.html) — 四大短板、流水线七环节、按失败模式爬梯子(Naive→Hybrid→Advanced→GraphRAG→Agentic)
- [02 · 检索理论与排序](0013-retrieval-theory-metrics.html) — 倒排索引、TF-IDF→BM25、精准/非精准 TopK、NDCG/MRR/MAP、MMR

## 阶段二 · 流水线:逐环节学 RAG 七环(理论 + 源码对照)

> 学完能:独立写出一条 RAG 流水线,每环知道 WeKnora 怎么实现。

- [03 · 文档解析](0002-doc-parsing.html) — 解析质量是检索质量的上限,docparser 七引擎、SSRF 防护
- [04 · 切分与嵌入](0003-chunking-embedding.html) — 块的设计决定检索精度,六策略、批量嵌入池
- [05 · 向量数据库](0004-vector-db.html) — 四类向量库选型、pgvector HNSW、距离衡量
- [06 · 混合检索](0005-hybrid-retrieval.html) — 关键词(ParadeDB)+ 向量(pgvector)双路互补
- [07 · 融合与重排](0006-rerank-fusion.html) — RRF 融合、跨编码器重排、MMR 去冗余
- [08 · 生成与引用溯源](0007-generation-citation.html) — ReAct 编排、引用句柄、答案可核查
- [09 · 元数据与查询增强](0008-metadata-query.html) — 元数据过滤缩范围、LLM 查询重写与扩展
- [10 · 评估与优化](0009-evaluation.html) — 指标体检、评测闭环、改进原则

## 阶段三 · 进阶:现代化形态

> 学完能:说清 Advanced RAG 的优化维度、GraphRAG 的适用边界、Agentic RAG 的编排模式。

- [11 · Advanced 与 Modular RAG](0010-advanced-modular.html) — 检索前中后逐段优化、模块化编排、CRAG/Self-RAG
- [12 · GraphRAG](0011-graphrag.html) — 知识图谱增强检索、跨文档综合、适用边界
- [13 · Agentic RAG](0012-agentic-migrate.html) — 多智能体编排、ReAct 工具注册表、迁移落地

## 阶段四 · 系统实现:吃透 WeKnora 本体

> 学完能:从"会用 RAG"到"懂整个系统"——架构、Agent 引擎、Chat Pipeline、记忆都能讲源码,面试有弹药。

- [14 · 系统架构总览](0014-weknora-architecture.html) — 容器/依赖注入、路由、引擎注册
- [15 · Agent 引擎](0015-agent-engine.html) — ReAct 循环、工具调用、审批、结束判定
- [16 · Chat Pipeline](0016-chat-pipeline.html) — 检索→融合→生成全流程、merge 家族
- [17 · Memory 长时记忆](0017-memory-system.html) — 提取/巩固/搜索/作用域
- [18 · 全系统串讲](0018-full-system-review.html) — 十八课一张图,面试话术
