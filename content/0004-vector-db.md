# 向量数据库:把向量存起来,并快速算相似度

> **Outcome:** 学完你能说清四类向量数据库的划分、为什么最终选了 pgvector,画出一张 WeKnora 多后端向量库的注册地图,并解释 pgvector 的 HNSW 索引为什么要在检索代码里做 ef_search 调优。

## Why this matters

解析、分块、嵌入之后,我们手里是一堆高维向量。但**每次查询都重算一遍全部文档的向量是明显不合理的**——必须先把向量"存起来",检索时才能用它快算相似度。这一课讲的就是"存哪、怎么存、怎么快"。向量数据库的价值是语义相似性搜索,业界实践给出的结论是:**装了 pgvector 插件的 PostgreSQL 是最稳妥的选择**。检索核心是 L1/L2/负内积/余弦四种距离。落到 WeKnora,就是 `internal/application/repository/retriever/` 下十种后端 + pgvector HNSW 的精细调优。

## Core idea

### 一、为什么需要向量数据库

课程里把数据库按用途分清楚了:

| **数据库** | **擅长** | **类比场景** |
|-----------|---------|-------------|
| 键值数据库 | 按键精准定位 | 按书名找一本书 |
| 文档数据库 | 复杂的结构化信息 | 查书的具体章节/作者简介 |
| 图数据库 | 复杂的关系数据 | 作者合作网络、书籍推荐关系 |
| **向量数据库** | **语义相似性搜索** | 找"与某本书内容相似的书籍" |

传统数据库存的是精确值,而**向量的价值在于语义**——文字/图像/语音/视频这些多模态、非结构化数据,只有在向量表示下才能算"语义相不相似"。向量数据库的核心能力就是:**基于向量之间的相似性,快速、精确地定位语义最相关的数据**。

业界把向量数据库按"是否开源 × 是否专用"分成四类:

| **类别** | **例子** |
|---------|---------|
| 开源专用 | Chroma、Vespa、LanceDB、Marqo、Qdrant、Milvus |
| 开源但支持向量搜索 | OpenSearch、PostgreSQL、ClickHouse、Cassandra |
| 商用专用 | Weaviate、Pinecone |
| 商用但支持向量搜索 | Elasticsearch、Redis、Rockset、SingleStore |

### 二、选型:踩坑经验 → pgvector

团队实践过的工具有 Faiss、Milvus、PostgreSQL,最终在掉坑无数次后**锁定了装了 pgvector 插件的 PostgreSQL**,并稳定运行 12 个月。理由落在工程现实:

- **PostgreSQL 本身不支持向量**,但 +pgvector 插件后就变成能存、能检的向量数据库;
- 相比专用向量库,pgvector 最大的优势是**不用多养一套基础设施**——向量和数据元数据在同一个库里,事务、备份、权限全复用现成能力;
- 部署极简:`docker pull pgvector/pgvector:pg16` 即可拉起,还能和现有 Postgres 业务表共存。

这也是 WeKnora 默认/主力走 PostgreSQL(pgvector)的根本原因——**在"足够好用"和"运维成本"之间,pgvector 是平衡点**。

### 三、检索核心:算距离

向量检索的本质是算"距离",核心有四种:

| **距离** | **定义** | **直觉** |
|---------|---------|---------|
| L1(曼哈顿) | 各维度绝对差之和 | 只能沿坐标轴走,无斜穿 |
| L2(欧几里得) | 各维度差平方和开根 | 空间中的直线距离 |
| 负内积 | -Σ(x·y) | 依赖向量模长 |
| **余弦距离** | 1 - 夹角余弦 | **只看方向/语义,不受模长影响**,RAG 最常用 |

在 RAG 里最常用的是**余弦距离**:它对向量做了归一化,更贴合"语义方向相不相似",而不是"长度相不相似"。(WeKnora 主线就用余弦,见 0005 课的 `<=>`。)

### 四、WeKnora 的多后端向量库地图

WeKnora 把向量库做成了**可插拔多后端**,`internal/application/repository/retriever/` 下能看到这些目录:

```text
doris  elasticsearch  milvus  neo4j  opensearch  postgres
qdrant  sqlite  tencentvectordb  weaviate
```

每一种后端都实现同一套 `RetrieveEngineRepository` 接口,并声明自己支持的检索类型。例如 postgres 仓库显式声明:

```go
// postgres/repository.go
func (g *pgRepository) Support() []types.RetrieverType {
    return []types.RetrieverType{types.KeywordsRetrieverType, types.VectorRetrieverType}
}
```

(sqlite、milvus 同样各自实现 `Support()`。)这就是"注册表 + 统一接口"的多后端设计(与 0001 课 `container.go` 的 `initRetrieveEngineRegistry` 呼应):**业务代码不关心底层是 Postgres 还是 Milvus,只面向接口调用**。

### 五、pgvector HNSW 的调优细节(最难也最值钱)

WeKnora 不只用 pgvector,还把 HNSW 索引调得很讲究。关键点都在 `postgres/repository.go`:

- **索引是表达式索引**:注释明确说"HNSW index is built on the EXPRESSION",检索 SQL 里必须 `embedding::halfvec(%d) <=> $1::halfvec(%d)` 两边都 cast 成 halfvec,**这是让 HNSW 索引被用起来的唯一方式**(`repository.go:370-371`)。
- **ef_search 必须手动抬高**:HNSW 默认 `ef_search=40`,远小于内部 `expandedTopK`(最多 1000)的候选预算,所以代码里 `SET LOCAL hnsw.ef_search = %d` 动态设值,否则 HNSW 只返回 40 个候选,外层再按 `knowledge_base_id` 后过滤时容易"候选都不够"。
- **iterative_scan 回退**:旧版 pgvector 没有 `hnsw.iterative_scan`,代码用字符串匹配 `"hnsw.ef_search"` / `"hnsw.iterative_scan"` 做版本兼容回退。
- **存储估算**:仓库里 `calculateIndexStorageSize` 把"内容 + 半精度向量(每维 2B)+ 元数据 + HNSW 索引开销(~2×向量大小)"加起来估算存储,便于容量规划。

这些细节说明:**"选对向量库"只是第一步,"把索引参数调到能真正用上"才是生产级差距**。文档量大时,HNSW 的候选预算与后过滤的匹配度,直接决定召回质量和延迟。

## Worked example

**案例(检索演示 + WeKnora 的 HNSW)**:

用户输入"我想吃一个老婆饼",库里正好没有"老婆饼",要从另外四个事物里挑一个最相近的填空。系统把"我想吃一个老婆饼"经嵌入变成查询向量,再把四个候选的向量都算余弦距离,选中距离最近的"菠萝包"返回——这单靠**键值/文档数据库做不到**,因为"相近"是语义概念,只有向量+距离才能量。

放到 WeKnora 里,这一步落在 pgvector:`embedding::halfvec(n) <=> $1::halfvec(n) ORDER BY distance` 走表达式 HNSW 索引,`ef_search` 被抬到候选预算匹配,再按知识库维度后过滤。**语义距离是引擎,HNSW 是让它在百万级向量上别变慢的油门**。

## Retrieval practice

1. 闭卷题:把向量数据库分成哪四类?最终选了哪个方案,核心理由是什么?
2. 迁移题:团队已有稳定的业务 PostgreSQL,新上线 RAG,向量库该选专用向量库(如 Milvus)还是 pgvector?多后端设计(WeKnora 的 retriever 目录)给你留了什么退路?

<details>
<summary>Check answers</summary>

1. ①开源专用(Chroma/Vespa/LanceDB/Qdrant/Milvus)②开源且支持向量搜索(OpenSearch/PostgreSQL/ClickHouse)③商用专用(Weaviate/Pinecone)④商用且支持向量搜索(Elasticsearch/Redis)。选**装了 pgvector 插件的 PostgreSQL**,理由:已有 Postgres 基础上零新增基础设施,向量与数据同库,事务/备份/权限复用,部署简单(`docker pull pgvector/pgvector:pg16`)。
2. 有稳定业务 Postgres、向量量级中等时优先 pgvector——省一套基建,和业务表同库。规模过大或需要专用性能特性时再上 Milvus/Qdrant。WeKnora 的多后端注册表(`retriever/` 下 postgres/milvus/qdrant/weaviate 等目录 + 统一 `Support()` 接口)意味着**切换后端可以不改上层检索逻辑**,只换注册的引擎,这就是设计上留的退路。

</details>

## Try it

打开 WeKnora 源码的 `internal/application/repository/retriever/`,数一下有几种后端目录,再看 `postgres/repository.go` 的 `Support()` 和 `estimateSize`(HNSW 开销估算)。重点读 `postgres/repository.go` 里 `hnsw.ef_search` / `hnsw.iterative_scan` 的 `SET LOCAL` 片段,理解"为什么必须调 ef_search"。

## Source

- WeKnora 源码的 `internal/application/repository/retriever/`:postgres / sqlite / milvus / qdrant / weaviate 等多后端;`postgres/repository.go`(Support()、HNSW 表达式索引、`hnsw.ef_search` / `hnsw.iterative_scan` 调优、`calculateIndexStorageSize`)

- [pgvector 官方文档](https://github.com/pgvector/pgvector)
- [HNSW 论文: Efficient and robust approximate nearest neighbor search using Hierarchical Navigable Small World graphs](https://arxiv.org/abs/1603.09320)
