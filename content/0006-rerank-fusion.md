# 多路融合与重排:从"能召回"到"排对位"

> **Outcome:** 学完你能说清"召回"和"排序"是两个问题,用 RRF 公式把多路检索结果融合成一个榜单,说清跨编码器重排模型为什么能把正确答案提到前排,并指出 WeKnora 源码里 RRF 融合、重排 provider、阈值过滤、MMR 去重每一段的落点。

## Why this matters

上一课(0005)解决了"漏召回":BM25 关键词路 + 向量路双管齐下,精确词和语义都能捞到。但混合检索会带来一个新问题——**两路结果怎么合成一个有序榜单?** 这就是本课要拆的"检索后优化"。即使检索已经能把所有相关结果都抓回来,如果它们排不对位,LLM 吃进去的前几个块还是错的。而 2026 年的生产共识是:**重排(Rerank)已经从"可选项"变成"标配"**——它是提升 RAG 回答质量单点性价比最高的环节之一。这一课把"融合"和"重排"当成两种不同的技术讲透。

## Core idea

### 一、为什么要融合:两条路的评分不可比

核心论断:**向量检索和关键词检索的相似度分数不在同一个量纲上**。pgvector 的余弦距离是 [-1,1] 的连续量,BM25 的分值受词频、文档长度影响极大。直接把两路的分数加权相加没有意义——你没法确定"向量 0.82" 和 "BM25 18.5" 谁更相关。

主流解法是 **RRF(Reciprocal Rank Fusion,倒数排名融合)**:不看原始分数,只看**排名位置**。公式:

```text
RRF(d) = Σ 权重 / (k + rank(d))

k          平滑常数(避免 rank=0 除零,典型值 60)
rank(d)    文档 d 在某一路检索中的名次(从 1 开始)
权重       该路检索的可调权重(可让向量/关键词不对称)
```

文档只要出现在某一路上就有分,出现在两路上则两个项相加——**跨两路都靠前的文档分数自然最高**。这正好补上 0001 课"订单 S12345 为什么没发货"里关键词漏、向量漂的互相兜底:两个死穴各被另一路压住,融合后正确块必然进前排。

### 二、为什么还要重排:融合只保证"在候选集里",不保证"排最前"

关键点是:RRF 或原始分数融合只是把多路结果整合,**真正"谁最贴合用户语义"要靠独立的精排模型**。融合阶段用的向量相似度是**双编码器(bi-encoder)**:查询和文档各自编码成一个向量再算相似度,速度快但对细粒度相关性不敏感。重排模型通常是**跨编码器(cross-encoder)**:把"查询+文档"拼接成一对输入让模型整体打分,能捕捉词与词之间的交互,相关性判断更准,但**慢且贵**,所以只能对候选集的 Top-N 精排,不能对整个库排。

|          |                                            |                                        |                                  |
|----------|--------------------------------------------|----------------------------------------|----------------------------------|
| **环节** | **输入/输出**                              | **典型模型**                          | **在 WeKnora 的位置**             |
| 融合     | 多路检索结果 → 一个融合榜单                 | RRF(无需模型,规则计算)                | `knowledgebase_search_fusion.go`   |
| 重排     | 融合后 Top-N 候选 → 相关性重新排序          | 跨编码器 / API reranker                | `chat_pipeline/rerank.go`          |
| 多样性   | 重排后 Top-K → 去冗余,保留互斥信息          | MMR(最大边际相关)                     | `chat_pipeline/rerank.go` 的 `applyMMR` |

### 三、WeKnora 的融合实现:RRF + 阈值 + 回退

源码里融合逻辑在 `internal/application/service/knowledgebase_search_fusion.go`:

- `classifyRetrievalResults(ctx, retrieveResults)` 先把多路返回按 `RetrieverType` 分成向量/关键词两类;
- `fuseOrDeduplicate(ctx, vectorResults, keywordResults, retrievalCfg)` 分流:关键词路为空则只做向量去重,反之亦然,两条都不空才走 RRF;
- `fuseWithRRF(ctx, …)` 是核心,公式注释写得很直白:`RRF score = vectorWeight/(k+vectorRank) + keywordWeight/(k+keywordRank)`,按 `ChunkID` 建排名 map、合并、`sortByScoreDesc` 排序;
- `deduplicateByScore` 用于单路场景,按 chunk 去重取最高分。

三个参数字段定义在 `internal/types/retrieval_config.go`:`RRFK`(平滑常数,默认 60)、`RRFVectorWeight`、`RRFKeywordWeight`(默认 0.7 / 0.3),通过 `GetEffectiveRRFK()`、`GetEffectiveRRFWeights()` 拿到带默认值的有效参数。

### 四、WeKnora 的重排实现:provider 注册 + 阈值过滤 + 组合分 + MMR

**provider 层** `internal/models/rerank/reranker.go` 定义 `Reranker` 接口(`Rerank(ctx, query, documents) ([]RankResult, error)`、`GetModelName`、`GetModelID`),`NewReranker` 按 provider 名路由到不同实现:阿里、智谱、Jina、NVIDIA、WeKnora 云、LKEAP、火山引擎、OpenAI 兼容(`newReranker` 的 switch)。`ConfigFromModel` 把 DB 里的模型配置映射成 `RerankerConfig`。

**流水线层** `internal/application/service/chat_pipeline/rerank.go` 的 `PluginRerank.OnEvent`(响应 `CHUNK_RERANK` 事件)做完整编排:

1. 把候选 passage 组装成 `passages`,调 `rerankModel.Rerank`(用 `chatManage.RewriteQuery` 作为查询);
2. **阈值过滤**:只保留 `RelevanceScore >= chatManage.RerankThreshold` 的结果;剔光时回退 Top-1(`fallback_top1`);
3. **阈值降级**:一次调用全被阈值过滤掉且原阈值 > 0.3 时,用 `原阈值×0.7`(最低 0.3)重试一次(`threshold_degrade`);
4. **组合分**:`compositeScore = 0.6*modelScore + 0.3*baseScore + 0.1*sourceWeight`,把重排模型分数、原检索分数、来源权重(如 web_search 0.95)合成最终分;FAQ 块可叠加 `FAQScoreBoost`;
5. **MMR 去重**:`applyMMR` 用 Jaccard 相似度对已选块惩罚冗余(`lambda=0.7`),保证 Top-K 信息互斥;
6. rerank API 失败时**回退**到未重排的检索结果(`api_error_fallback`),保证管道仍能返回有用内容。

## Worked example

**案例一(订单场景)**:用户问"查订单 12345",关键词路精确命中"订单 12345 于 2023-08-15 在上海,客户不满意得分 0.9",向量路召回"12 开头的订单包装破损严重,相关与其它 0.8",两路分别得分但混合排序让期望结果落到第一、第四位。WeKnora 先 `fuseWithRRF` 把两路按排名融合,再 `applyMMR` 保证不冗余,正确块被提到前两,LLM 的答案质量立刻不同。

**案例二(2026 重排成为标配)**:某客服系统召回 Top-50,embedding 语义分把"激活码"漂移到"验证码"块上排在前面,正确答案埋在第 9 位。固定流水线里补一个 cross-encoder/API reranker(Cohere Rerank / Jina / BGE-reranker),把查询+候选对整体打分,正确答案抬到第 1 位——这个改动只动一层,一周上线,是"梯子中间最便宜的提升"。

**案例三(融合的代价要权衡)**:重排模型每次调用是"查询 × N 个候选"的拼接,又慢又贵。WeKnora 的取舍是:**重排只对融合后的候选集做,不扫整个库**;且用 `RerankTopK` 控制最终进入上下文的数量。2026 年的工程经验是候选数通常取 20–50,再大边际收益递减而延迟上升。

## Retrieval practice

1. 闭卷题:为什么向量检索和关键词检索的分数不能直接加?写出 RRF 公式,说明 `k`、`vectorWeight`、`keywordWeight` 各自的作用;为什么 RRF 之后还要单独上一路重排模型?
2. 迁移题:你的知识库同时开了关键词+向量两路,某用户高频问题答案正确但总排不进前三。按 WeKnora 的管线,你会先查哪几个配置项?如果重排 API 挂了,系统该怎么保证不白屏?

<details>
<summary>Check answers</summary>

1. 因为两路分数量纲不可比(向量是余弦距离、BM25 是词频统计分),直接相加无意义。RRF 只看排名不看分数:`RRF(d)=Σ 权重/(k+rank(d))`,`k` 是平滑常数(默认 60)防除零,两个 `weight` 控制两路的相对话语权(WeKnora 默认向量 0.7 / 关键词 0.3)。RRF 只整合排名,不判断"哪块最贴合查询语义"——双编码器向量对上细粒度相关性不敏感,所以要用跨编码器/API 重排模型对 Top-N 做精排。
2. 先查 `RerankThreshold`(是否阈值定太高把正确块过滤了)、`RerankTopK`(候选太少)、RRF 的 `vector/keyword weight` 是否失衡、以及重排模型是否配好。若重排 API 失败,WeKnora 有 `api_error_fallback`:直接把候选集 `SearchResult = candidatesToRerank` 原样返回,保证管道还能答。对应产品上应保留"降级到未重排结果"的兜底,而不是让请求失败。

</details>

## Try it

打开 WeKnora 源码的 `internal/application/service/chat_pipeline/rerank.go`,找到 `compositeScore` 那 0.6/0.3/0.1 的三段加权,把注释换成你自己的话;再对照 `knowledgebase_search_fusion.go` 的 `fuseWithRRF`,数一数"排名 map 建立→合并→排序"这三步在代码里的起止行。

## Source

- WeKnora 源码:`internal/application/service/knowledgebase_search_fusion.go`(fuseOrDeduplicate / fuseWithRRF)、`internal/application/service/chat_pipeline/rerank.go`(PluginRerank / compositeScore / applyMMR)、`internal/models/rerank/reranker.go`(Reranker 接口 / NewReranker)、`internal/types/retrieval_config.go`(RRF 参数)
- 2026 趋势:重排为生产标配;跨编码器与 API reranker(Cohere Rerank / Jina / BGE-reranker)取舍

- [An Analysis of Fusion Functions for Hybrid Retrieval](https://arxiv.org/abs/2210.11934)
- [Is ChatGPT Good at Search? (RANKGPT)](https://arxiv.org/abs/2304.09542)
- [Cohere Rerank 官方文档](https://cohere.com/rerank)
