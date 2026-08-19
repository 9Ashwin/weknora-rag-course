# 混合检索:关键词 + 向量双路,让精确词和语义都不漏

> **Outcome:** 学完你能说清为什么单一向量检索会漏精确词、单一关键词检索会丢语义上下文,画出 WeKnora 的 `CompositeRetrieveEngine` 按 `RetrieverType` 路由的多路召回结构,并指出 ParadeDB `|||`(关键词)与 pgvector `<=>`(向量)在源码里的落点。

## Why this matters

一个核心事实:**向量检索并非万能**。搜"订单 12345"、搜"伊隆·马斯克"、搜只有几个字母的缩写"RAG/LLM",向量检索常失准——因为向量检索擅长的是"语义相近",而命中和编号这类**精确词**要靠关键词;反过来,关键词检索拿到精确行,却给不出"订单相关的广泛上下文"。**单一检索路线的死穴,正好被另一条路补上**。这就是混合检索(多路召回)存在的意义。放到业务现实里:用户懒得输入公司全名,只说"广州神机妙算的款项",系统也得模糊查到——这正是 0005 课向量相似度补上的能力。这一课把"多路召回 + 混合检索"讲透,并落到 WeKnora 用 ParadeDB 全文搜索 + pgvector 余弦距离 + 按类型路由的 `CompositeRetrieveEngine` 实现。

## Core idea

### 一、为什么需要混合检索

两条单一路线的盲区正好互补:

| **路线** | **擅长** | **盲区** |
|---------|---------|---------|
| 关键词检索(KM25/全文) | 精确匹配(产品名/姓名/编号/代码)、少量字符、低频词 | 给不出查询相关的广泛上下文 |
| 向量检索 | 语义相近召回、同义词/改述 | 精确词会"漂移"、编号/缩写易失准 |

一个经典案例:用户问"订单 12345",关键词检索能精确命中"12345"这条记录,但没有相关上下文;语义匹配能理解"订单""配送"等关联词,却对具体订单号翻车。**混合检索先用关键词路定位精确信息,再用向量路扩展语义上下文**(比如"12 开头的订单、包装破损严重"),既拿到精确详情,又拿到额外有用信息。

混合检索的首要目标很朴素:**确保最相关的结果出现在候选列表里**——两路都召回,宁可多不能漏,排序交给重排。(重排在下一课,这里只确立"多路召回"。)

### 二、模糊检索的另一种讲法

业务案例给"为什么需要混合"补了视角:实战案例只支持**精确检索**——输入完整公司名"广州神机妙算有限公司"能查到,省略成"广州神机妙算"就查不到。**现实里用户几乎不会输全名**,所以必须支持模糊检索。模糊检索怎么做?三步:

1. 把知识编码成向量并保存(0004 课的嵌入 → 0005 课的向量库);
2. 把用户问题编码成向量;
3. 算两者相似度,取距离最小者(0005 课的四种距离)。

**关键词路保精确(全名/编号),向量路保模糊(简写/同义/改述)**——两条腿一起,业务才能"又准又不怕用户偷懒"。

### 三、WeKnora 的多路召回:`CompositeRetrieveEngine` 按类型路由

WeKnora 的检索不是写死的单路,而是**组合引擎按 `RetrieverType` 分派**。`internal/types/retriever.go` 里定义了检索类型:

```go
type RetrieverType string
const (
    KeywordsRetrieverType RetrieverType = "keywords"  // 关键词路
    VectorRetrieverType   RetrieverType = "vector"    // 向量路
    WebSearchRetrieverType RetrieverType = "websearch" // 联网路
)
```

`internal/application/service/retriever/composite.go` 的 `CompositeRetrieveEngine.Retrieve` 会对每个检索参数**并发分派给支持该 `RetrieverType` 的引擎**,再把结果合并(`concurrentRetrieve`):

```go
// composite.go
for _, engineInfo:= range c.engineInfos {
    if slices.Contains(engineInfo.retrieverType, param.RetrieverType) {
        result, err:= engineInfo.retrieveEngine.Retrieve(ctx, param)
        // 结果 append 进 results;mutex 保护
    }
}
```

`concurrentRetrieve` 用 `sync.WaitGroup` + goroutine 让"关键词路"和"向量路"**并行跑**——多路召回在一个请求里并发完成,而不是串行两遍。上层 `KeywordsVectorHybridRetrieveEngineService`(`keywords_vector_hybrid_indexer.go`)则负责"关键词+向量混合"索引入库:入库时若向量检索开启,就 `embedder.Embed` / 批量 `batchEmbedWithBackoff` 生成向量与文本一起存,再调用底层仓库 `Save` / `BatchSave`。

### 四、两路的引擎:ParadeDB `|||` 与 pgvector `<=>`

WeKnora 主线的混合检索,落地在 `postgres/repository.go`,一条 SQL 里同时出现两种运算符:

```sql
-- 关键词路:ParadeDB 全文搜索的 ||| 运算符(匹配任意 token)
content ||| ?          -- repository.go:199  "Use ParadeDB's ||| operator"

-- 向量路:pgvector 余弦距离 <=>(包一层 halfvec 表达式索引以命中 HNSW)
embedding::halfvec(%[1]d) <=> $1::halfvec(%[1]d) as distance
ORDER BY embedding::halfvec(%[1]d) <=> $1::halfvec(%[1]d)  -- repository.go:384-387
```

- **`|||`(ParadeDB BM25 全文搜索)**承担关键词/精确匹配路,对应 `KeywordsRetrieverType`;
- **`<=>`(pgvector 余弦距离)**承担语义/模糊匹配路,对应 `VectorRetrieverType`。

两路都声明在 `Support()` 里(`KeywordsRetrieverType, VectorRetrieverType`)。**这就是 2026 年企业级 RAG"关键词 + 向量双路"的标准做法**:关键词路兜住精确词,向量路兜住语义与模糊,`CompositeRetrieveEngine` 按类型并发路由,两路结果合并后再交给下一课的重排去排序。

## Worked example

**案例(回到 0001 课的企业客服):**用户分别问两种问题,看两路如何分工:

1. **"X200 激活码怎么弄?"**——纯向量检索容易把"激活码"漂移到"验证码"的块上。关键词路用 `|||` 精确命中"激活码"(`keywords` 路),向量路补上"激活码"相关操作流程(`vector` 路),`CompositeRetrieveEngine.Retrieve` 对这两种 `RetrieverType` 并发召回,两路结果都进候选。
2. **"广州神机妙算的款项到账了吗?"**(,省略了"有限公司")——关键词路按"广州神机妙算"找不到全名记录,但向量路能把问题向量和"广州神机妙算有限公司"的文档向量算余弦距离,按语义命中。**关键词路兜精确、向量路兜偷懒的简写**。

两路合并后进入重排(0007 课),由 rerank 决定"哪个块最该放最前"。这就是混合检索闭环:**CompositeRetrieveEngine 并发多路召回 → 合并 → 交给重排**。

## Retrieval practice

1. 闭卷题:混合检索为什么是 2026 年 RAG 的标配?`CompositeRetrieveEngine.Retrieve` 是怎么做到"多路并发召回"的?
2. 迁移题:你的电商知识库,用户问"S12345 包裹怎么还没到"——关键词路和向量路各自会召回什么?如果只开向量路,可能漏掉什么?

<details>
<summary>Check answers</summary>

1. 因为单一检索路线有死穴:纯向量漏精确词(订单号/编号/缩写会漂移),纯关键词给不出语义上下文与模糊改述。混合检索让两路互补,先保证"最相关结果进候选列表",排序留给重排。`CompositeRetrieveEngine.Retrieve` 对每个 `RetrieveParams` 里指定的 `RetrieverType`(`keywords`/`vector`),用 `slices.Contains` 找到支持它的引擎并调用,`concurrentRetrieve` 用 `sync.WaitGroup` + goroutine 让多路并行执行,结果经 `mutex` 安全 append 合并。
2. 关键词路(`|||`):精确命中"S12345"这条订单记录(编号/异常状态),但可能缺语义上下文;向量路(`<=>`):把"包裹怎么还没到"的语义映射到"物流/派送延迟"相关块,能给上下文,但对 S12345 这个精确编号容易飘。只开向量路,很可能漏掉"含 S12345 编号但那段的语义不贴问题"的精确记录——这正是需要双路召回补上的盲区。

</details>

## Try it

打开 WeKnora 源码的 `internal/application/service/retriever/composite.go`,读 `Retrieve` + `concurrentRetrieve`,确认多路并发合并的写法。再打开 `internal/types/retriever.go` 找 `KeywordsRetrieverType` / `VectorRetrieverType` 常量,最后在 `postgres/repository.go` 里定位 `|||`(≈199 行)和 `<=>`(≈370-387 行)的 SQL。

## Source

- WeKnora 源码的 `internal/application/service/retriever/`:`composite.go`(CompositeRetrieveEngine.Retrieve / concurrentRetrieve)、`keywords_vector_hybrid_indexer.go`(KeywordsVectorHybridRetrieveEngineService 混合索引入库)。`internal/types/retriever.go`(RetrieverType 常量)
- WeKnora 源码的 `internal/application/repository/retriever/postgres/repository.go`:ParadeDB `|||`(≈199 行)、pgvector `<=>` halfvec 表达式索引(≈370-387 行)

- [Balancing the Blend: Trade-offs in Hybrid Search](https://arxiv.org/abs/2508.01405)
- [ParadeDB(全文检索引擎)](https://github.com/paradedb/paradedb)
