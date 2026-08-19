# Memory 长时记忆:跨会话的提取、巩固与检索作用域

> **Outcome:** 学完你能画出 WeKnora 长时记忆的四段生命周期(提取→入库→巩固→召回),说清记忆的"作用域"隔离模型为什么是安全的,讲出 Recall 在注入 prompt 时如何区分"常住记忆/兴趣/情境记忆",并指出每个阶段在 `internal/application/service/memory/` 下的真实函数名。

## Why this matters

前面 13 课讲的都是"知识库检索":文档一次性入库,问答时检索。但真实 Agent 的另一半记忆来自**对话本身**——用户今天说"我喜欢简约风",一周后应该还记得。WeKnora 用 `memory` 包实现这套**跨会话长时记忆**:不依赖任何单个 chat session,按"同一个主体(principal)在同一个工作空间"记忆。读源码你会发现它的工程含量极高:`service.go`(1302 行)+ `extract.go`(1154 行)+ `consolidate.go`(509 行)加起来近 3000 行,处理的根本不是"存一段话"这种玩具问题,而是**提取要不要收、何时放弃、怎么去重、常住记忆何时被忘记、怎么把几段话合并成一条**这些生产级难题。

## Core idea

### 一、四阶段生命周期与真实落点

```go
// service.go 顶部包注释
// Package memory implements cross-session long-term memory: what the system
// remembers about one principal inside one workspace, independently of any
// single chat session.
```

|          |                                |                                          |
|----------|--------------------------------|------------------------------------------|
| **阶段** | **做什么**                     | **真实函数**（`memory/` 包）            |
| 提取     | 从对话里异步蒸馏记忆           | `ScheduleExtraction` → `enqueueExtraction` → `Handle`（asynq 队列）→ `applyDecisions` |
| 入库     | 写一条 memory item，去重+容量控制 | `Remember` → `write`、`findContainedDuplicate`、`enforceCapacity` |
| 巩固     | 定期合并/淘汰陈旧记忆          | `consolidateIfDue` / `ConsolidateNow` → `reviewStore` → `mergeRedundant` / `demoteStaleTasks` |
| 召回     | 问答时注入 prompt              | `Recall` → `selectRecallWithTrace` |

提取不是同步做的:`ScheduleExtraction(ctx, sessionID, messageID, chatModelID)` 只负责把任务推进 asynq 队列(`enqueueExtraction`),真正的模型调用发生在 `Handle(ctx, t *asynq.Task)` 里——这是典型的**异步蒸馏**,避免每次对话都要等记忆模型。

### 二、作用域即安全模型(scope.go,42 行)

`memory/scope.go` 是整个包最小的文件,却是**隔离模型的核心**:

```go
// ResolveScope derives the memory space from the request context alone.
// 关键注释:Deriving rather than accepting a scope is the whole isolation model:
// there is no code path where a client-supplied id can select a memory space.
func ResolveScope(ctx context.Context) (interfaces.MemoryScope, error) {
	tenantID, ok:= types.TenantIDFromContext(ctx)...
	subjectID:= principal.StorageID()...
	return interfaces.MemoryScope{TenantID: tenantID, SubjectID: subjectID}, nil
}
```

记忆空间的 key 是 `(TenantID, SubjectID)`,且**只从请求上下文推导,绝不接受客户端传入的 id**——所以不存在"指定读某个人的记忆"这条代码路径,天然防越权。同一个人的记忆也不会跨工作空间泄漏(带 TenantID)。

### 三、Recall:三层记忆如何拼进 prompt(service.go:113)

`Recall(ctx, query)` 把记忆分成三类,注入策略完全不同:

|          |                                |                                       |
|----------|--------------------------------|---------------------------------------|
| **类别** | **含义**                       | **注入方式**                          |
| 常住记忆 resident | 长期成立的事实/偏好(standing)    | 全部进 block(`ListActiveResident`，上限 60) |
| 兴趣 interest | 用户长期关注的领域                | 按 query 挑最相关的注入(`selectResidentInterests`) |
| 情境记忆 situational | 单次的事实/任务(Fact/Task kinds) | 只取非 resident 的做向量/词法召回(`ListActiveByKinds`，上限 400) |

```go
residentItems, _:= s.repo.ListActiveResident(recallCtx, scope, 60)
standing, interests:= splitResidentInterests(residentItems)
selectedInterests, relevantInterests:= selectResidentInterests(query, interests,...)
block:= types.RenderMemoryBlock(blockItems)   // 常住 = 全量渲染成 block...
situational, _:= s.repo.ListActiveByKinds(recallCtx, scope,
	[]string{types.MemoryKindFact, types.MemoryKindTask}, 400)
matched, rankTrace:= s.selectRecallWithTrace(recallCtx, scope, cfg, query,
	candidates, types.MemoryRecallMaxItems, types.MemoryRecallRuneBudget)
prompt:= types.WrapMemoryForPrompt(block, types.RenderMemoryRecall(matched))
```

注意一个精妙设计:`used`(注入的)和 `matched`(单条召回的)是**两个集合**——兴趣是因为容量有空余才搭车进来的,属于背景,不该每次都在聊天时间线上报告。代码注释原话:"What was injected and what is reported are deliberately not the same set." 召回全程用 langfuse 打 span(`memory.recall`),`rankTrace.Mode` 暴露这次是词法命中还是向量命中。

### 四、巩固:合并冗余、淘汰过期(consolidate.go)

`reviewStore` 是巩固主流程,顺序很讲究:
1. **先过期**:`ExpireOverdue` 把过期的任务归档——过期的记忆不该成为合并候选;
2. **全量读**:注释强调"the whole store, not a page of it"——怕的是两个都旧的重复永远碰不上;
3. **聚类合并**:`clusterSimilar` → `mergeRedundant`,用 Jaccard(`jaccardSets`)算 token 重叠分组,再 `callConsolidationModel` 合并;
4. **降级陈旧任务**:`demoteStaleTasks`。

它有两套时钟:`consolidateIfDue`(每日维护,间隔一天)vs `ConsolidateNow`(用户点按钮强制,间隔仅让按钮不能连点),避免两种调用互相静默。

## Worked example

**场景**:用户在会话里连续说"我公司在上海""我们主要做跨境电商""下周二想要一份竞品分析"。

- 每轮对话结束,`ScheduleExtraction` 把 `(sessionID, messageID)` 入队,延时 `cfg.ExtractDelay()`,subject 行先 `EnsureSubject` 建好。
- asynq worker `Handle` 取到任务 → `collectSegments` 攒对话片段 → `buildExtractionPrompt` → `callExtractionModel` → `parseExtractionResponse` → `applyDecisions` 决定每条是收成 fact 还是 task,还是**丢弃**。
- 一周后再开新会话问"我们在哪办公",`Recall` 从上下文解析出同一个 `(TenantID, SubjectID)`,`ListActiveResident` 把"公司在上海"这条常住事实渲染进 block,注入新 prompt——**这个会话从未见过上一会话,但记忆带过来了**。

## Retrieval practice

1. 闭卷题:`ResolveScope` 为什么是安全模型的核心?它为什么不从请求参数里拿 scope?
2. 迁移题:如果两个用户共享同一个公开 workspace(同一 TenantID),A 的"我喜欢蓝色"会不会泄漏给 B 的问答?为什么?要隔离到"每个 Agent/每个应用"各自记忆,你会改动哪一层?

<details>
<summary>Check answers</summary>

1. 因为 scope 只从请求上下文里的 `principal.StorageID()` 推导,客户端无法指定去读别人的记忆空间——"没有一条代码路径能让客户端选择记忆空间",所以不用逐端点审计越权。带 TenantID + SubjectID 双 key,既隔离租户又隔离同一租户内的主体。
2. 不会。同一 TenantID 下,`SubjectID = principal.StorageID()`,不同用户是不同 principal,记忆空间天然不同。若要让"每个 Agent/应用"各自记忆,作用域需要再加一维(例如在 `MemoryScope` 增加 agent/app 维度,并在 `ResolveScope` 里从上下文带上该维度)——`scope.go` 的 `ResolveScope` 就是你要改的落点。

</details>

## Try it

打开 `internal/application/service/memory/recall_trace.go`,看 `rankTrace` 记录了哪些字段(`LexicalHits`/`VectorHits`/`VectorSkipReason`/`Mode`),再回看 `Recall` 结尾传给 langfuse 的 Summary,理解为什么"词法命中 vs 向量命中"对运营排障有用。

## Source

- WeKnora 源码的 `internal/application/service/memory/`:`service.go`(Recall/Remember/write/ListResident)、`extract.go`(ScheduleExtraction/Handle/applyDecisions)、`consolidate.go`(reviewStore/mergeRedundant/demoteStaleTasks)、`scope.go`(ResolveScope)、`search.go`(SearchMemory/MemoryAvailable)、`recall_trace.go`
- 类型与常量:WeKnora 源码的 `internal/types/memory.go`(MemoryItem/MemoryKind/Resident)、`internal/types/interfaces/` 下的 MemoryService 接口

- [WeKnora 官方仓库](https://github.com/Tencent/WeKnora)
