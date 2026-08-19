# RAG 高质量资料清单(论文 + 权威机构)

> 用途:WeKnora 课程各课的理论延伸阅读、面试谈资。按"经典必读 → 子方向 → 2026 最新 → 权威机构实践"四层组织。
> 论文统一给 arxiv ID,访问 `https://arxiv.org/abs/<ID>`;机构资料给官方链接。

## 一、经典必读(高引核心论文)

| 论文 | arxiv ID | 年份 | 引用 | 讲什么 |
|---|---|---|---|---|
| Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection | [2310.11511](https://arxiv.org/abs/2310.11511) | 2023 | 高引 | 自我反思:检索/生成/批评一体,训练模型自评检索是否必要、答案是否可靠 |
| Corrective Retrieval Augmented Generation (CRAG) | [2401.15884](https://arxiv.org/abs/2401.15884) | 2024 | 269 | 修正式检索:检索结果不靠谱时触发修正(知识精炼/重新检索),防幻觉的关键 |
| From Local to Global: A Graph RAG Approach to Query-Focused Summarization | [2404.16130](https://arxiv.org/abs/2404.16130) | 2024 | 1937 | 微软 GraphRAG:实体图 + 社区分层摘要,跨文档综合问答的基石 |
| Retrieval-Augmented Generation for Large Language Models: A Survey | [2312.10997](https://arxiv.org/abs/2312.10997) | 2023 | 极高引 | Gao 等经典综述:Naive/Advanced/Modular RAG 三分法,入门第一读 |
| RAG vs Fine-tuning: Pipelines, Tradeoffs, and a Case Study on Agriculture | [2401.08406](https://arxiv.org/abs/2401.08406) | 2024 | 高引 | RAG 与微调的系统对比,什么时候选哪个 |
| Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG | [2501.09136](https://arxiv.org/abs/2501.09136) | 2025 | 388 | Agentic RAG 综述:从单次检索到自主决策检索的范式演进 |

## 二、子方向经典论文

### 查询重写
- [2307.08803](https://arxiv.org/abs/2307.08803) Mixed-initiative Query Rewriting in Conversational Passage Retrieval(2023)— 对话检索里的人机混合主动重写
- [2406.18960](https://arxiv.org/abs/2406.18960) A Surprisingly Simple yet Effective Multi-Query Rewriting Method(2024)— 简单多查询重写胜过复杂基线
- [2112.08558](https://arxiv.org/abs/2112.08558) CONQRR: Conversational Query Rewriting for Retrieval with RL(2021)— 强化学习学查询重写,经典

### 重排(Reranking)
- [2304.09542](https://arxiv.org/abs/2304.09542) Is ChatGPT Good at Search? RANKGPT(2023)— 首个 LLM listwise 重排,里程碑
- [2212.10528](https://arxiv.org/abs/2212.10528) HYRR: Hybrid Infused Reranking for Passage Retrieval(2022)— 混合信号重排
- [2605.01664](https://arxiv.org/abs/2605.01664) A Hybrid Retrieval and Reranking Framework for Evidence-Grounded RAG(2026)— 证据型 RAG 混合检索+重排

### 混合检索(Dense + Sparse)
- [2508.01405](https://arxiv.org/abs/2508.01405) Balancing the Blend: Trade-offs in Hybrid Search(2025)— 混合检索权衡的系统实验
- [2412.03736](https://arxiv.org/abs/2412.03736) Domain-specific Question Answering with Hybrid Search(2024)— 领域 QA 混合检索应用
- [2304.12139](https://arxiv.org/abs/2304.12139) Anserini Gets Dense Retrieval(2023)— Lucene HNSW 集成工程实践

### 分块(Chunking)
- [2402.09760](https://arxiv.org/abs/2402.09760) Grounding Language Model with Chunking-Free In-Context Retrieval(2024)— 免分块检索,挑战传统范式
- [2504.19754](https://arxiv.org/abs/2504.19754) Reconstructing Context: Evaluating Advanced Chunking Strategies(2025)— 高级分块策略系统评估
- [2505.21700](https://arxiv.org/abs/2505.21700) Rethinking Chunk Size For Long-Document Retrieval(2025)— 长文档块大小影响

### RRF 融合
- [2210.11934](https://arxiv.org/abs/2210.11934) An Analysis of Fusion Functions for Hybrid Retrieval(2022)— RRF/Condorcet/Borda 对比,混合融合经典分析
- (RRF 原始论文:Cormack et al. 2009,不在 arxiv)

### 父子块 / Small-to-Big
- 无独立高引论文,是工程实践(LangChain Parent Document Retriever 等框架实现)

## 三、2026 最新论文(每个方向 3-4 篇,跟上研究前沿)

### 总体 RAG
- [2608.17536](https://arxiv.org/abs/2608.17536) CoAL-RAG:复杂度感知法律 RAG — 单一检索策略对简单问题过度推理、复杂问题检索不足
- [2608.16515](https://arxiv.org/abs/2608.16515) 当上下文误导:意图引导解码实现鲁棒 RAG — 外部证据也引入信任问题,抗误导
- [2608.16776](https://arxiv.org/abs/2608.16776) GRIP:信息受限前提下的接地推理 — 大容量编码器让查询主导状态,检索证据失效的修复

### Agentic RAG
- [2608.02011](https://arxiv.org/abs/2608.02011) 推理失败之前:Agentic RAG 的"证据前流程失败" — agent 在证据条件推理前就因检索片段错误失败
- [2608.08340](https://arxiv.org/abs/2608.08340) OpRAG:GPU 多阶段 RAG 工作流资源确定性运行时 — 统一预处理/嵌入/检索/生成阶段
- [2608.01913](https://arxiv.org/abs/2608.01913) 长时程搜索 agent 的搜索行为与失败模式诊断

### Hybrid 检索
- [2608.15851](https://arxiv.org/abs/2608.15851) 稠密扩张、稀疏锚定:混合检索的信道非对称查询扩展 — 改进固定 Top-L 融合
- [2608.07152](https://arxiv.org/abs/2608.07152) 无固定 Top-L 截断的精确自适应混合检索 — 避免截断信息丢失
- [2608.01450](https://arxiv.org/abs/2608.01450) 双曲空间实时混合检索用于边缘设备 RAG

### Graph RAG
- [2608.01269](https://arxiv.org/abs/2608.01269) ACE-GraphRAG:层级 GraphRAG 的 Agentic 上下文工程
- [2607.24861](https://arxiv.org/abs/2607.24861) HVM-GraphRAG:复杂文档全视图多模态图 RAG
- [2606.16409](https://arxiv.org/abs/2606.16409) PathRouter:在 Agentic Graph RAG 中对齐奖励与检索质量

### 评估
- [2608.03860](https://arxiv.org/abs/2608.03860) SciRet:科学 RAG 的算力感知检索与重排
- [2604.20763](https://arxiv.org/abs/2604.20763) 覆盖率而非平均值:可信检索评估的语义分层
- [2604.19047](https://arxiv.org/abs/2604.19047) RARE:高相似度语料的冗余感知检索评估

## 四、权威机构高质量资料(工程实践标准)

| 机构 | 资料 | 核心价值 |
|---|---|---|
| Anthropic | [Contextual Retrieval 官方博客](https://www.anthropic.com/engineering/contextual-retrieval) | **Contextual Embeddings + Contextual BM25:减少 49% 检索失败,加重排 67%**。官方数据,切分前加上下文是 2024 后最强实践 |
| Anthropic | [Claude Cookbook: Enhancing RAG with contextual retrieval](https://platform.claude.com/cookbook/capabilities-contextual-embeddings-guide) | 可跑代码实现(anthropic+voyage+cohere+elasticsearch) |
| Microsoft Research | [LazyGraphRAG: quality and cost](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost) | 免前置索引的 GraphRAG,成本和质量新标准,2025 已进 Azure |
| Microsoft Research | [Project GraphRAG](https://www.microsoft.com/en-us/research/project/graphrag) | GraphRAG 官方项目页:local/global search、BenchmarkQED 自动化基准 |
| Microsoft Research | [Moving to GraphRAG 1.0](https://www.microsoft.com/en-us/research/blog/moving-to-graphrag-1-0-streamlining-ergonomics-for-developers-and-users) | GraphRAG 1.0 工程化演进 |
| Pinecone | [Hybrid Search 官方文档](https://docs.pinecone.io/guides/search/hybrid-search) | 混合检索+去重+rerank 的完整生产代码,alpha 调参(1.0=纯稠密,0=纯稀疏) |
| Weaviate | [Hybrid search docs](https://weaviate.io/developers/weaviate/search/hybrid) | alpha 参数、融合实现 |
| RAGAS | [docs.ragas.io](https://docs.ragas.io) | Faithfulness/Answer Relevance/Context Relevance/Context Precision 等指标,LLM-as-judge 评估 |
| DeepEval | [deepeval.com](https://deepeval.com) | 开源 LLM 评估框架,faithfulness 用 LLM-as-judge |
| arXiv | [RAG Evaluation Survey (2504.14891)](https://arxiv.org/abs/2504.14891) | RAG 评估方法综述:传统统计指标 + LLM 时代方法 |

## 五、面试怎么用这份清单

- **被问 RAG 原理**:Gao Survey(2312.10997)的 Naive/Advanced/Modular 三分法 + Self-RAG/CRAG 的自我反思/修正机制
- **被问检索质量**:Anthropic Contextual Retrieval 的 49%/67% 官方数据 + RANKGPT listwise 重排 + RRF
- **被问 GraphRAG**:微软 GraphRAG(1937 引用)local→global + LazyGraphRAG 成本优化
- **被问评估**:RAGAS 四指标(faithfulness/answer relevance/context relevance/precision)+ 2026 语义分层新论文
- **被问前沿**:2026 最新论文每个方向报 1-2 篇名字 + 一句话贡献,显得持续跟进

## 五、补充方向(嵌入 / 向量库 / 长上下文 / 安全 / 上下文工程)

### 嵌入模型
- [2402.11573](https://arxiv.org/abs/2402.11573) BGE Landmark Embedding: A Chunking-Free Embedding Method For RAG — 免分块嵌入,配合长上下文 LLM
- [2506.00049](https://arxiv.org/abs/2506.00049) Rethinking Hybrid Retrieval: When Small Embeddings and LLM Re-ranking Beat Bigger Models — 小嵌入 + LLM 重排反超大模型的混合检索

### 向量数据库
- [2608.12812](https://arxiv.org/abs/2608.12812) A Comprehensive Empirical Evaluation of Vector Database Systems for ANN Search — 向量库系统性能/质量/资源权衡实证
- [2304.12139](https://arxiv.org/abs/2304.12139) Anserini Gets Dense Retrieval — Lucene HNSW 集成工程实践

### 长上下文 vs RAG
- [2608.07458](https://arxiv.org/abs/2608.07458) CoinRAG: Contextualized Information Nugget KV Cache Reuse for Long-Context RAG — 长上下文场景 RAG 的 KV 缓存复用

### RAG 安全(检索增强系统特有攻击面)
- [2606.19660](https://arxiv.org/abs/2606.19660) A Layered Security Framework Against Prompt Injection in RAG-Based Chatbots — RAG 提示注入分层防御
- [2606.26627](https://arxiv.org/abs/2606.26627) Agents That Know Too Much: A Data-Centric Survey of Privacy in LLM Agents — Agent 隐私数据调查

### 上下文工程(2026 前沿)
- [2210.03629](https://arxiv.org/abs/2210.03629) ReAct: Synergizing Reasoning and Acting in Language Models — Agent 范式奠基

### LLM Agent 安全(补充)
- [2407.19354](https://arxiv.org/abs/2407.19354) The Emerged Security and Privacy of LLM Agent: A Survey with Case Studies(CSUR 2025)— LLM Agent 安全与隐私综述,高引

### BM25 原始文献
- Integrating the Probabilistic Models BM25/BM25F into Lucene(2004,Robertson)— BM25 经典公式的工程化实现
