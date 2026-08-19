# 切分与嵌入:把文本切成合适的块,再变成向量

> **Outcome:** 学完你能说清分块三要素(大小/重叠/拆分)、六种分块策略各适合什么场景,画出 WeKnora 的 Auto 分层分块诊断链,并指出嵌入批量池(`batch.go`)和并发封装(`wrapEmbeddingConcurrency`)在源码里的落点。

## Why this matters

解析完的是一整篇长文本——太长不能直接塞进向量检索。核心原则说得很直白:**分块策略和嵌入模型的选择,直接影响 RAG 的召回率和生成质量**。块太大,向量抓不住细节、计算贵;块太小,句子被切碎、语义断裂。而嵌入是怎么把"老婆饼""菠萝包"这种人类语言变成机器能比较的数字,是嵌入要解决的核心问题——Windows 字符串查找和 Unicode 编码都解决不了"形式相似但语义不同",只有把语义映射到向量空间才能算距离。这一课把"切多碎"和"怎么嵌入"两件事讲透,并落到 WeKnora 的 chunker 与 embedding 两个包的实现上。

## Core idea

### 一、分块三要素

任何分块策略都能拆成三个决定参数:

| **要素** | **含义** | **调参直觉** |
|----------|---------|-------------|
| **大小 (size)** | 每个块的最大字符数 | 越小越细粒度(情感分析),越大越保上下文(摘要/主题) |
| **重叠 (overlap)** | 相邻块之间重叠的字符数 | 防止关键句被切在边界上丢掉 |
| **拆分 (split)** | 按段落/分隔符/标记/语义确定块边界 | 决定边界"切在哪"是否语义自然 |

这三者的不同组合就派生出主流策略:

- **固定大小分块(Fixed Size)**:按字数硬切,简单粗糙。
- **重叠分块(Overlap)**:固定大小基础上带回退窗口,覆盖边界。
- **递归分块(Recursive)**:按层级分隔符(段落→句→词)从粗到细递归切,最常用。
- **文档特定分块(Document Specific)**:按 Markdown 标题、代码结构等特定语义切。
- **语义分块(Semantic)**:按语义边界切,块内语义最连贯(成本高)。
- **混合分块(Mix)**:多策略组合(如父子块)。

核心权衡:**块在"语义完整"和"颗粒度"之间的平衡**——块应保留核心语义且相对独立,让模型不依赖宽上下文也能检索准。

### 二、WeKnora 的 Auto 分块:按文档画像走分层策略

WeKnora 的分块不是让你裸调三个参数,而是提供 `strategy.go` 的 `SplitWithDiagnostics`——一个**带诊断的自动分层**机制。先看策略清单(`strategy.go` 顶部常量):

```go
StrategyAuto      = "auto"      // 用 profiler 画像自动选层
StrategyHeading   = "heading"   // 按标题/章节层级切(文档特定分块)
StrategyHeuristic = "heuristic" // 启发式边界切
StrategyRecursive = "recursive" // 递归分隔符切
StrategyLegacy    = "legacy"    // 老策略兜底
```

`splitter.go` 里定义了 `Chunk`、`SplitterConfig`(含 `ChunkSize` / `ChunkOverlap` / `Strategy`)和 `SplitText`。核心是 `SplitWithDiagnostics`(`strategy.go`):当用 `auto` 时,它先让 `profiler.go` 对文档画像(DocProfile:是否有标题层级、语言等),再根据画像**从高到低选 tier**,逐层尝试分块,`ValidateChunks` 校验结果,直到产出合规的块——这就是"按内容自适应"。

```go
// SplitWithDiagnostics(strategy.go): 画像 → 选层 → 尝试 → 校验回退
out, diag:= v.ValidateChunks(...) // 校验块大小是否达标...
```

关键文件分工:

- `profiler.go`:对文档画像,决定走哪一层(标题丰富 → heading,否则 → heuristic)。
- `heading_splitter.go`:按标题层级切,`splitByHeadingsImpl` 先找标题边界 `findHeadingBoundaries`,再把太小的块合并 `coalesceTinyChunks`,甚至给子块补"面包屑标题" `sectionBreadcrumbs`(让块自带章节上下文)。
- `heuristic_splitter.go`:`splitByHeuristicsImpl` 通过 `findHeuristicBoundaries` 按语言特征找边界,`applyOverlapAligned` 对齐重叠,遇到超长块 `appendOversizeBlock` 兜底。
- `strategy.go` 的 `SplitParentChild`:**父子块策略**——父块大(保上下文)、子块小(细检索),子块命中后能回指父块上下文,这正是"混合分块"里最常见的搭配。

### 三、嵌入的本质:把语义变成可比较的距离

用一个经典例子讲清嵌入为什么必要:老`婆饼`和`老婆`字符串前缀相同,`菠萝包`和`菠萝`也是——但它们是不同事物;`dog` 和 `log` 只差一个字母,意义完全不同。**Unicode 编码这类"约定数字"距离语义毫无关系**,用它比较纯属折腾。而**嵌入模型(Embedding)把文本映射进高维语义向量空间**,语义相近的文本向量距离就近。于是检索从"字符串等于"变成"向量距离最小":

1. 知识文本 → 嵌入模型 → 向量,存进向量库;
2. 用户问题 → 嵌入模型 → 查询向量;
3. 在向量库里找与查询向量距离最近的知识向量。

后面 0004 课会讲"怎么算距离"(L1/L2/余弦),这一课只需要确立:**嵌入是"人类语言 → 机器向量"的翻译层,向量空间里距离 ≈ 语义差异**。

### 四、WeKnora 的嵌入层:Provider 切换 + 批量池 + 并发封装

`internal/models/embedding/` 定义了统一的 `Embedder` 接口和一个清晰的装饰器链:

```go
// embedder.go
type Embedder interface {
    Embed(ctx context.Context, text string) ([]float32, error)
    BatchEmbed(ctx context.Context, texts []string) ([][]float32, error)
}
type EmbedderPooler interface {
    BatchEmbedWithPool(ctx context.Context, model Embedder, texts []string) ([][]float32, error)
}
```

- **多 Provider**:`openai.go`、`zhipu.go`、`volcengine.go`、`gemini.go`、`ollama.go`、`jina.go`、`nvidia.go`、`aliyun.go` 等几十个文件,对应不同嵌入服务;`NewEmbedder(config,...)` 按配置建实例。
- **批量池(`batch.go`)**:`batchEmbedder` 用 `ants.Pool` 协程池,`BatchEmbedWithPool` 把一批 chunk 提交到协程池并行嵌入,再收集结果——文档量大时这是吞吐的关键。
- **并发封装(`concurrency_wrapper.go`)**:`wrapEmbeddingConcurrency(e, config.MaxConcurrency)` 给每个 Embedder 套上并发上限,防止瞬时打爆嵌入 API 的 QPS 配额。
- **可观测性装饰器**:`embedder.go` 里 `NewEmbedder` 把调试(`debugEmbedder`)和埋点(`langfuseEmbedder`)也作为装饰器套在外层。

这样一个 embedder 被包成"限流 → 批量 → 可观测"的多层洋葱,让嵌入既能并发快跑,又不超配额、可追踪。对应到混合检索实现(`keywords_vector_hybrid_indexer.go`)里,`BatchIndex` 先 `batchEmbedWithBackoff` 批量嵌入 + 指数退避重试,再按 `batchSize` 分批落库。

## Worked example

**案例(分块困境 + WeKnora 的 Auto 解法)**:一份企业操作手册,有清晰的 Markdown 标题层级,每节 2~3 段。若用固定大小切,可能把"退款流程"的关键句从"退款政策"小节里切断,导致检索"能退钱吗"时块不完整。

WeKnora 的处理:

1. `SplitWithDiagnostics` 让 `profiler.go` 识别到"标题层级丰富" → 画像命中 heading 层;
2. `heading_splitter` 按标题切,每节成一块,块内自带完整段落;
3. 对过小的块执行 `coalesceTinyChunks` 合并,防止产生无信息量碎块;
4. 若某块还要更细(知识量大),切父子块——父块保上下文,子块细检索,命中子块能回指父块。

嵌入侧:这批块进 `BatchEmbedWithPool`,由 `ants.Pool` 并发向量化,同时 `MaxConcurrency` 限制并发数避免打爆嵌入 API;"退款"和"退货"因为语义相近,在向量空间里天然靠拢。最终"能退钱吗"能召回"退款流程"块——**前提是分块保住了语义完整**。

## Retrieval practice

1. 闭卷题:分块三要素是哪三个?固定大小分块和文档特定分块(按标题)各自最大的风险是什么?
2. 迁移题:你的知识库要索引一份"产品说明书",正文用大段无标题的叙述写,另一份是带目录结构的操作手册。两份文档 WeKnora 的 Auto 分块大概会分别落到哪个 splitter?为什么?

<details>
<summary>Check answers</summary>

1. 大小(size)、重叠(overlap)、拆分(split,决定边界位置)。固定大小分块最怕把关键句/语义边界硬生生切断,导致块语义不完整;文档特定分块(按标题)最怕文档本身没有清晰结构(如无标题的叙述文),标题做不了边界,产出块可能过大或切不到点。
2. 无标题叙述的操作说明书 → profiler 画像不到标题层级,落到 heuristic_splitter(启发式按语言/标点特征找边界);带目录的操作手册 → 命中 heading_splitter(按标题层级切,必要时合并小块、补面包屑标题)。判断依据:Auto 分块先用 profiler 画像选层,再决定用哪个 splitter。

</details>

## Try it

打开 WeKnora 源码的 `internal/infrastructure/chunker/strategy.go`,读 `SplitWithDiagnostics`,把 `SplitterConfig.Strategy` 从 `auto` 改成 `heading` / `heuristic`,对比 `Diagnostics` 的 `SelectedTier` 和输出块数。再打开 `internal/models/embedding/batch.go` 的 `BatchEmbedWithPool`,数一数 `ants.Pool` 提交任务的写法。

## Source

- WeKnora 源码的 `internal/infrastructure/chunker/`:`strategy.go`(Auto/诊断分层)、`splitter.go`(Chunk/SplitterConfig)、`heading_splitter.go`、`heuristic_splitter.go`、`profiler.go`(画像)
- WeKnora 源码的 `internal/models/embedding/`:`embedder.go`(Embedder 接口 + 装饰器链)、`batch.go`(ants 批量池)、`concurrency_wrapper.go`(并发限流)

- [Grounding Language Model with Chunking-Free In-Context Retrieval](https://arxiv.org/abs/2402.09760)
- [Reconstructing Context: Evaluating Advanced Chunking Strategies for RAG](https://arxiv.org/abs/2504.19754)
