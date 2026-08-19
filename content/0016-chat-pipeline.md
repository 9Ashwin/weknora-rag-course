# Chat Pipeline 与流式:检索 → 融合 → 生成的全流程

> **Outcome:** 学完你能说清 WeKnora 一次 RAG 问答的 10 个事件阶段(`LOAD_HISTORY → MEMORY_RECALL → QUERY_UNDERSTAND → CHUNK_SEARCH_PARALLEL → CHUNK_RERANK → [WEB_FETCH] → CHUNK_MERGE → FILTER_TOP_K → [DATA_ANALYSIS] → INTO_CHAT_MESSAGE → CHAT_COMPLETION_STREAM`),并理解 `EventManager` 是怎么把 `PluginMerge`、`PluginFilterTopK`、`PluginChatCompletion` 等插件按事件"洋葱式"串起来的;尤其能拆开 `PluginMerge.OnEvent` 八步融合流程,以及其中 `classifyMerge` 的五种合并判定和坐标驱动的 `appendTrustedContent`。

## Why this matters

前两课讲了进程组装(0014)和生成层的心脏 ReAct(0015)。这一课补上中间被跳过的一大块:**从"检索出候选"到"LLM 出答案"之间,WeKnora 到底对片段做了什么**。它是 2026 年 Advanced RAG 里最容易被低估的一环:候选不是拿来就用,而是 去重 → 补历史 → 解析父块 → 按知识库/块类型分组 → 坐标重叠合并 → FAQ 填充 → 短上下文扩写 → 再合并 → 终去重 + 去部分重叠 → top-k 截断 才交给生成。这一路如果做不好,结果就是 LLM 拿到一堆重复、断裂、超长、"正确答案被埋在中间"的片段。而整个编排是 事件驱动 + 插件 的——这是 WeKnora 区别于"写死的 if-else 流水线"的架构精髓。

## Core idea

### 一、事件驱动的流水线:EventManager 与 PipelineBuilder

WeKnora 的问答不是一段写死的函数,而是一张**有序事件表**,每个阶段是一个 `types.EventType`。常量定义在 `internal/types/chat_manage.go`(270 行起):

```go
LOAD_HISTORY  EventType = "load_history"
QUERY_UNDERSTAND EventType = "query_understand"
CHUNK_SEARCH_PARALLEL EventType = "chunk_search_parallel"
CHUNK_RERANK   EventType = "chunk_rerank"
CHUNK_MERGE    EventType = "chunk_merge"
FILTER_TOP_K   EventType = "filter_top_k"
INTO_CHAT_MESSAGE EventType = "into_chat_message"
CHAT_COMPLETION_STREAM EventType = "chat_completion_stream"
```

流水线用 `PipelineBuilder`(chat_manage.go 288 行)按特性开关动态拼,`AddIf(cond,...)` 让"有无历史、是否联网、是否数据分析"可控:

```go
pipeline = types.NewPipelineBuilder().
    AddIf(hasHistory, types.LOAD_HISTORY).
    Add(types.MEMORY_RECALL).
    Add(types.QUERY_UNDERSTAND).
    Add(types.CHUNK_SEARCH_PARALLEL).
    Add(types.CHUNK_RERANK).
    AddIf(req.WebSearchEnabled, types.WEB_FETCH).
    Add(types.CHUNK_MERGE).
    Add(types.FILTER_TOP_K).
    AddIf(chatManage.DataAnalysisEnabled, types.DATA_ANALYSIS).
    Add(types.INTO_CHAT_MESSAGE).
    Add(types.CHAT_COMPLETION_STREAM).
    Build()
```

而执行这套事件的引擎是 `EventManager`(chat_pipeline.go)。每个插件实现 `Plugin` 接口(`ActivationEvents()` 声明自己关心哪些事件、`OnEvent(ctx, eventType, chatManage, next)` 处理),`EventManager.Register` 把插件按事件挂进 `handlers map`。多插件监听同一事件时,`buildHandler` 用 `next` 闭包把它们串成**洋葱链**——先来的处理完调 `next()` 接力,`Trigger(eventType, chatManage)` 从最外层点起。共享状态装在 `types.ChatManage` 里随事件传递(`SearchResult` → `RerankResult` → `MergeResult` → `ChatResponse` 逐级写进同一个结构)。

### 二、PluginMerge.OnEvent:融合的八步

`PluginMerge.OnEvent`(merge.go 44 行)是融合核心,它对 `chatManage.RerankResult`(没有就用按分数降序的 `SearchResult`)做八步处理,最终落到 `chatManage.MergeResult`:

| 步 | 处理 | 说明 |
|----|------|------|
| 1 | `selectInputResults` | 首选重排结果,否则用按 score 降序的检索结果 |
| 2 | `dedup("dedup_summary")` | 初始去重(`removeDuplicateResults`) |
| 3 | `injectHistoryResults` | 把历史轮次里相关的引用并进来,再去重 |
| 4 | `resolveParentChunks` | 解析父块(子块合并回所属父亲) |
| 5 | `groupAndMergeCurrentContent` | 按知识库/块类型分组,合并坐标重叠的块(ParallelMap 并行) |
| 6 | `populateFAQAnswers` | 命中 FAQ 则填充标准答案 |
| 7 | `expandShortContextWithNeighbors` | 太短的上下文用相邻块扩写 |
| 7.5 | `groupAndMergeCurrentContent`(重复) | 扩写可能引入新重叠,再合并一次 |
| 8 | `dedup("final_dedup")` + `removePartialOverlaps` | 终去重,再消掉部分内容重叠 |

```go
searchResult:= p.selectInputResults(ctx, chatManage)
searchResult = p.dedup(ctx, "dedup_summary", searchResult)
searchResult = p.injectHistoryResults(ctx, chatManage, searchResult)
searchResult = p.resolveParentChunks(ctx, chatManage, searchResult)
mergedChunks:= p.groupAndMergeCurrentContent(ctx, searchResult)
mergedChunks = p.populateFAQAnswers(ctx, chatManage, mergedChunks)
mergedChunks = p.expandShortContextWithNeighbors(ctx, chatManage, mergedChunks)
mergedChunks = p.groupAndMergeCurrentContent(ctx, mergedChunks) // 扩写后再合并
mergedChunks = p.dedup(ctx, "final_dedup", mergedChunks)
mergedChunks = removePartialOverlaps(ctx, mergedChunks)
chatManage.MergeResult = mergedChunks
```

### 三、坐标驱动的合并:classifyMerge 五种判定

真正的片段"合体"逻辑在 `merge_overlap.go`。`mergeSequentialChunks`(17 行)把同一知识库里坐标连续/重叠的块叠成一个,核心是 `classifyMerge`(129 行)对相邻两块判五种情况:

| 判定 | 动作 |
|------|------|
| `mergeSeparate` | 不相邻,单独成组 |
| `mergeExtend` | 前块尾部与后块头部重叠,`appendTrustedContent` 按坐标拼接 |
| `mergeSubsume` | 后块完全包含在前块内(被"吞并"),不重复内容 |
| `mergeJoinDistinct` | 坐标贴近但不重叠(同一文档两块),用 `\n\n` 连接 |
| `mergeJoinText` | 文本层相接,同样 `JoinChunkContent` 连接 |

合并组策略:**保留更高分**,`lastIndex` 跟踪最远坐标。而拼接块正文用的是 `appendTrustedContent`(84 行)——它优先用坐标给的 `positionOverlap` 做**精确定位重叠**(`searchutil.AppendWithExactOverlap`),只有文字对不上(比如 HTML 实体/合成表头破坏了长度不变式)才回退到文本最长后缀匹配(`AppendWithOverlap`)。这保证了"坐标路径"优先,而不是靠猜文本,避免把重复的表行/日志当重叠丢内容——这正是 `merge_position_path_test.go` 等测试覆盖的边界。

### 四、扩写与 top-k:quality 的收尾两刀

- `expandShortContextWithNeighbors`(merge_expand.go 11 行):太短的命中块用 `fetchChunksIfMissing` 拉相邻块,靠 `mergeOrderedContent(prev, base, next, maxLen)` 拼出有上下文的片段。
- `PluginFilterTopK`(filter_top_k.go):对 `FILTER_TOP_K` 事件,在 `MergeResult` / `RerankResult` / `SearchResult` 里挑存在的那层,按确定性排序(`filter_top_k_test.go` 验证:先分数降序,再父/块类型做 tie-breaker)截到 `RerankTopK`。

### 五、生成与流式:PluginChatCompletion

最后 `PluginChatCompletion`(chat_completion.go)接管 `CHAT_COMPLETION_STREAM`:

```go
chatModel, opt, err:= prepareChatModel(ctx, p.modelService, chatManage)
chatMessages, modelContext:= prepareMessagesWithModelContext(ctx, chatManage)
chatMessages = modelContext.EncodeMessages(chatMessages)
ctx = withPromptCacheMetadata(ctx, chatModel, chatMessages, opt, "knowledge_qa")
chatResponse, err:= chatModel.Chat(ctx, chatMessages, opt) // 流式
modelContext.DecodeResponse(chatResponse)
chatManage.ChatResponse = chatResponse
```

它把 `MergeResult` 编进 prompt(`prepareMessagesWithModelContext` + `EncodeMessages`),加上 prompt cache 元数据,调 `chatModel.Chat` 流式出答案,响应再 `DecodeResponse` 解码回写 `chatManage.ChatResponse`,同步检查 `OrphanResourceHandles`(模型引用了不存在的资源句柄,记 warning)。至此 检索→融合→生成 全流程闭环。流式输出由 `agent_stream_handler.go` 等 handler 订阅事件总线,把每个阶段进度(`BeginRetrievalProgress`/`EndRetrievalProgress`,见 progress.go)实时推给前端。

## Worked example

**案例一(碎片重组的价值)**:知识库把一篇文章切成 200 字的块,检索命中第 3、4 块(坐标相接),另命中一块 80 字短块。`groupAndMergeCurrentContent` 把 3、4 块用 `mergeExtend`+坐标重叠拼成连续段落;短块过 `expandShortContextWithNeighbors` 拉第 2 块扩写成有上下文的一段;`FILTER_TOP_K` 最后只留分数最高的若干段给 LLM。结果:模型拿到**连续、自足、去重**的上下文,而不是三条断裂的碎片——回答质量和引用完整性的差距就在这里。

**案例二(事件插件的可组合性)**:关掉联网搜索,`AddIf(req.WebSearchEnabled, WEB_FETCH)` 不把 `WEB_FETCH` 加进流水线;开数据分析才 `AddIf(..., DATA_ANALYSIS)`。同一套 `PluginMerge`、`PluginChatCompletion` 代码不用改,纯靠构建流水线时事件表不同,就切出"纯知识库问答"vs"联网+RAG+分析"两种模式——事件驱动把 feature flag 变成了"少贴/多贴几张事件贴纸"。

**案例三(重复和部分重叠的清理)**:BM25 与向量两路召回同一段落的不同偏移切片。`dedup` 按 ID 去重抓不住它们(ID 不同),`removePartialOverlaps` 专门扫内容级部分重叠并消掉,保证同一段内容进 prompt 前只出现一份,不浪费 token、不误导模型重复读。

## Retrieval practice

1. 闭卷题:按顺序写出一次"带历史、带联网、带数据分析"的 RAG 流式问答会触发哪些 `EventType`?`PluginMerge.OnEvent` 八步里的"7.5 步"为何要重复跑 `groupAndMergeCurrentContent`?
2. 迁移题:你的检索系统两个召回源常返回同一段落的偏移切片,导致 prompt 重复。你会把 `removePartialOverlaps` 加在哪个环节之前,用什么判定"部分重叠"而不是误删两个独立但相似的块?

<details>
<summary>Check answers</summary>

1. `LOAD_HISTORY → MEMORY_RECALL → QUERY_UNDERSTAND → CHUNK_SEARCH_PARALLEL → CHUNK_RERANK → WEB_FETCH → CHUNK_MERGE → FILTER_TOP_K → DATA_ANALYSIS → INTO_CHAT_MESSAGE → CHAT_COMPLETION_STREAM`。第 7.5 步重复合并是因为第 7 步 `expandShortContextWithNeighbors` 在扩写时可能引入新的坐标重叠(拉进的相邻块与已合并块再次相接),所以扩写后必须再 `groupAndMergeCurrentContent` 一次,把新引入的重叠也并掉,最后才做终去重。
2. 放在 `FILTER_TOP_K` 之前、紧随 `CHUNK_MERGE` 之后(即 OnEvent 的 step 8),此时既有合并后的骨干又有被去掉的短块。判定"部分重叠":先在内容层面做归一化(去空白/HTML 实体/大小写),再用最长公共子串/后缀匹配计算重叠长度占比,超阈值(并满足坐标相近)才判为重叠并保留较长或分数较高者;对"相似但独立"的块,要靠坐标区间不重叠 + 重叠占比不足来放行,避免误删。

</details>

## Try it

打开 WeKnora 源码的 `internal/types/chat_manage.go` 先看事件常量表(270 行)和 `PipelineBuilder` 的 `Add/AddIf`;再到 WeKnora 源码的 `internal/application/service/session_knowledge_qa.go`(187 行起)看真实流水线怎么按特性开关拼;然后读 `chat_pipeline/merge.go` 的 `OnEvent` 八步、`merge_overlap.go` 的 `classifyMerge`、`merge_expand.go` 的 `expandShortContextWithNeighbors`,对照本课表格标注每步。

## Source

- WeKnora 源码的 `internal/types/chat_manage.go`(`EventType` 常量 270、`PipelineBuilder` 288、`Pipeline` map 320)
- WeKnora 源码的 `internal/application/service/chat_pipeline/chat_pipeline.go`(`EventManager.Register`/`buildHandler`/`Trigger`、`PluginError`)
- WeKnora 源码的 `internal/application/service/chat_pipeline/merge.go`(`PluginMerge.OnEvent` 44、`selectInputResults` 101)
- WeKnora 源码的 `internal/application/service/chat_pipeline/merge_overlap.go`(`mergeSequentialChunks` 17、`appendTrustedContent` 84、`classifyMerge` 129)、`merge_expand.go`(`expandShortContextWithNeighbors` 11)、`filter_top_k.go`(PluginFilterTopK)
- WeKnora 源码的 `internal/application/service/chat_pipeline/chat_completion.go`(`PluginChatCompletion.OnEvent` 33)、`progress.go`(Begin/EndRetrievalProgress)
- WeKnora 源码的 `internal/application/service/session_knowledge_qa.go`(动态流水线组装 187 行起)

- [WeKnora 官方仓库](https://github.com/Tencent/WeKnora)
