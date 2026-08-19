# Agent 引擎深挖:ReAct 循环、工具调用、审批与结束判定

> **Outcome:** 学完你能画出 WeKnora `AgentEngine` 一趟回答的生命周期:`Execute` 建状态与 Langfuse span → `executeLoop` 用 `for state.CurrentRound < MaxIterations` 兜住循环,用 sentinel(`Next/Continue/Break`)控制跳转 → 每轮 `runReActIteration` 走 Think(1)→ Analyze(2)→ Act(3)→ Observe(4)四步,内部带空内容重试与卡死检测 → 工具调用在 `act.go` 里串行 `executeToolCalls`/并行 `executeToolCallsParallel` 执行 → 高分险工具经 `approval/gate.go` 的 `RequestAndWait` 等审批 → 结束由 `finalize.go` 的 `emitCompletionEvent` 发 `EventAgentComplete` 收尾。

## Why this matters

上一课讲了进程怎么组装,这一课钻进去看**生成层的引擎**。WeKnora 不是一次"检索→直接出答案",它有一个完整的 ReAct(Reason+Act)循环:模型先"想"(Think),决定要不要调工具(比如检索、查网页),工具执行结果再喂回去,循环到模型给出最终答案为止。这个循环是 2026 年 Agentic RAG 的核心心脏——**循环怎么兜底、怎么判定"该停了"、怎么处理高风险工具的审批**,直接决定一个 agent 是"可用的产品"还是"会失控的 demo"。读 744 行的 `engine.go`,你会看到这套循环工业级的边角处理:用户点"停止"怎么优雅退出、模型空转怎么重试、模型复读同样内容怎么判卡死。

## Core idea

### 一、Execute:一趟回答的入口与状态

`AgentEngine.Execute`(206 行)是入口。它依次做四件事:

1. `defer e.toolRegistry.Cleanup(ctx)`——不管成败都清理工具注册表;
2. 打开 Langfuse span `agent.execute`,把 `MaxIterations`、`ParallelToolCalls`、`WebSearchEnabled` 等配置打进 metadata,后面每一轮 LLM 调用和工具执行都挂在这个 span 下,可观测性成树;
3. 初始化 `AgentState`(`RoundSteps`、`KnowledgeRefs`、`IsComplete=false`、`CurrentRound=0`);
4. 组装 `systemPrompt`(`buildSystemPrompt`)、历史 `messages`(`buildMessagesWithLLMContext`)、工具定义 `tools`(`buildToolsForLLM`),然后 `executeLoop` 把整个循环跑掉。

```go
state:= &types.AgentState{RoundSteps: []types.AgentStep{}, KnowledgeRefs: []*types.SearchResult{}, IsComplete: false, CurrentRound: 0}
messages:= e.buildMessagesWithLLMContext(systemPrompt, query, sessionID, llmContext, imgs)
tools:= e.buildToolsForLLM()
_, err:= e.executeLoop(ctx, state, query, messages, tools, sessionID, messageID)
```

### 二、executeLoop:循环骨架与三种跳出

`executeLoop`(362 行)是循环主控,骨架如下:

```go
for state.CurrentRound < e.config.MaxIterations {
    select {
    case <-ctx.Done():   // 用户停止/超时——尽力抢救已有工具结果
        if totalTC:= countTotalToolCalls(state.RoundSteps); totalTC > 0 {
            _ = e.streamFinalAnswerToEventBus(ctx, query, state, sessionID)
            state.IsComplete = true
        }
        return state, ctx.Err()
    default:
    }
    outcome, iterErr:= e.runReActIteration(ctx, state, &messages, tools,...)
    switch outcome {
    case iterOutcomeContinue: continue loop // 空内容重试:不推进轮次
    case iterOutcomeBreak:    break loop     // 拿到最终答案/卡死
    case iterOutcomeNext:     state.CurrentRound++ // 本轮有工具调用,继续下一轮
    }
}
if !state.IsComplete && ctx.Err() == nil {
    e.handleMaxIterations(ctx, query, state, sessionID) // 到顶没答完,强制合成
}
```

关键设计:

- **sentinel 驱动**:用 `iterOutcome` 枚举(`Next=0 / Continue=1 / Break=2`)而不是裸 return,让 break/continue/next 跳转集中在 loop 一处,可读性强。
- **`iterateOutcomeContinue` 不推进 `CurrentRound`**:专门给"模型返回空内容 + stop"的兜底重试用,重试次数上限 `maxEmptyResponseRetries`,超了就回退成通用提示语,绝不让空的 `FinalAnswer` 漏给用户。
- **`EventAgentComplete` 恰好发一次**:用闭包 `emitCompletion()` + `completionEmitted` 位标记 + `defer`,保证正常结束、context 取消、迭代报错三条退出路径都不重不漏,并且用 `context.WithoutCancel` 保证取消时也能发出去。

### 三、runReActIteration:一轮四步

每轮 `runReActIteration`(468 行)完整走 ReAct:

| 步 | 代码 | 干什么 |
|----|------|--------|
| 1 Think | `callLLMWithRetry(ctx, *messagesPtr, tools,...)` | 带重试地调 LLM(支持 function calling) |
| 2 Analyze | `analyzeResponse` | 判定 `verdict.isDone`:自然停止且无工具调用才算是最终答案 |
| 3 Act | `executeToolCalls` | 执行本轮所有工具调用 |
| 4 Observe | `appendToolResults` + 追加 `RoundSteps` | 把工具结果写回 messages,循环继续 |

每轮开头先 `estimateCurrentTokens` + `manageContextWindow` 做上下文窗口管理(超了就裁剪历史),再开一个 `agent.round.N` 的 Langfuse span。两个防御性细节值得记:

- **卡死检测**:若模型连续 `maxRepeatedResponseRounds` 轮返回相同内容且无工具调用,直接判 stuck,把 `response.Content` 当 `FinalAnswer`、`IsComplete=true`、`Break`。
- **用户中途停止**:若 LLM 流式期间 `ctx.Err()!=nil`,不把半截思考当最终答案,只把部分 thinking 保留成 `AgentStep` 就 `Break`,避免"重复卡片"污染消息内容。

### 四、act.go:工具的串并行执行与事件

`executeToolCalls`(act.go 217 行)是 Act 步的执行器:

```go
if e.config.ParallelToolCalls && n >= 2 {
    e.executeToolCallsParallel(ctx, response, step,...) // errgroup 并发,结果按下标回填保序
    return
}
for i, tc:= range response.ToolCalls {
    e.executeSingleToolCall(ctx, tc, i, step,...)       // 串行(默认)
}
```

单个工具由 `runToolCall`(356 行)负责:`NormalizeToolCallID` 规范化 ID → 解析参数 `tc.Function.Arguments` → 执行 → 记日志。每个工具结果都会 `eventBus.Emit` 两个事件:`EventAgentToolResult` 与 `EventAgentTool`(`AgentActionData` 带 ToolName/ToolInput/ToolOutput/Success/Duration),让前端能实时画出一棵"思考 + 工具调用"树。并行路径用 `errgroup.WithContext` 并发跑,但用 `results[i]=toolCall` 按下标回填,保证**顺序稳定**;失败也 best-effort,不取消兄弟工具。

### 五、approval/gate.go:高风险工具的人机审批闸

`internal/agent/approval/gate.go` 是审批闸。它不是所有工具都直接跑:

- `NeedsApproval(tenantID, serviceID, toolName)`(289 行)判断这个工具是否命中审批规则;
- `RequestAndWait(ctx, PendingRequest)`(309 行)把审批请求发出,阻塞等待人批;`RequestOAuthAndWait` 处理 OAuth 类授权;
- 审批决议经 `Resolve`(539 行)分发:本实例走 `deliverLocal`(638 行,Redis pubsub 订阅同一 channel),跨实例走 `resolveCrossInstance`(565 行),`runSubscriber`(212 行)后台跑一个订阅者循环接决议。

这层闸是 2026 年 agent 产品安全性的标配:agent 可以自主做低风险只读操作,但访问外部系统/写操作前必须停住等人工放行,避免"AI 自主干出事故"。

### 六、finalize.go:两种收尾

循环结束后按两条路收尾:

- 自然拿到答案:状态置 `IsComplete`,不进 `handleMaxIterations`。
- 到顶没答完:`handleMaxIterations`(160 行)调 `streamFinalAnswerToEventBus` 强制让 LLM 基于已有工具结果合成一段总结性答案,失败则回退 "Sorry, I was unable to generate a complete answer."

两条路最终都由 `emitCompletionEvent`(181 行)发 `EventAgentComplete` 收尾,payload 带 `FinalAnswer`、`KnowledgeRefs`、`AgentSteps`(`state.RoundSteps` 全量思考+工具历史,落进消息可回放)、`TotalDurationMs`——这就是前端"执行步骤树"和消息持久化的数据来源。

## Worked example

**案例一(一轮带检索的正常回答)**:用户问"今年公司离职率多少"。Round-1 Think 返回一个 tool_call `search_knowledge(离职率)`,无纯文本结尾 → `analyzeResponse` 判 `isDone=false` → Act 执行检索,Observe 把结果 append 回 messages → `Next`,`CurrentRound=1`。Round-2 Think 基于检索结果返回纯文本且无工具调用 → `verdict.isDone=true` → `FinalAnswer` 设定、`IsComplete=true`、`Break`。`emitCompletionEvent` 连同 `KnowledgeRefs` 发 `EventAgentComplete`,前端整棵树收尾。

**案例二(模型空转兜底)**:弱模型在 Think 步只返回 `stop` 且 content 为空。`analyzeResponse` 给 `verdict.emptyContent=true`,`emptyRetries++`,若 `<= maxEmptyResponseRetries` 就塞一句 "Please provide your complete answer now as plain text." 并 `Continue`(不推进轮次)再试;重试耗尽则 `FinalAnswer="I'm sorry, I was unable to generate a response."` 并 `Break`。用户永远不会收到空白答案。

**案例三(高风险工具审批挂起)**:agent 想调一个会写外部数据库的 MCP 工具。`NeedsApproval` 命中 → `RequestAndWait` 把 `PendingRequest` 发出,该轮阻塞等待;管理员批/拒后 `Resolve` 经 Redis pubsub 把 `Decision` 分发给 `runSubscriber` → `RequestAndWait` 醒过来按决议执行或放弃。全程 agent 不越权。

## Retrieval practice

1. 闭卷题:`executeLoop` 里 `iterOutcome` 三取值含义?`iterOutcomeContinue` 为何不推进 `CurrentRound`?`analyzeResponse` 判 `isDone` 的充分条件是什么?
2. 迁移题:你的客服 agent 用 `for` 循环 + `break` 写死,结果模型常空转/复读。按 WeKnora 的做法要加哪三个防御机制,分别对应哪几个函数/常量?

<details>
<summary>Check answers</summary>

1. `Next`(0):本轮执行了工具调用,`state.CurrentRound++` 后继续循环;`Continue`(1):空内容重试,不推进轮次、原地再跑一轮;`Break`(2):拿到最终答案、卡死、或上下文取消,退出循环。`Continue` 不推进轮次是为了给空内容重试留"复活"机会而不消耗迭代预算。`analyzeResponse` 判 `isDone` 的充分条件是:模型自然停止(`FinishReason=stop`)且本轮没有工具调用(`len(ToolCalls)==0`)——只有这种情况才算最终答案;只要调了工具就还得循环。
2. 三个防御:(a) 空内容重试——对应 `emptyRetries`/`maxEmptyResponseRetries` 与 `iterOutcomeContinue`,空 stop 就 nudge 一句再试;(b) 卡死检测——对应 `consecutiveSameContent`/`maxRepeatedResponseRounds`,连续同内容无工具调用就主动 `Break` 并当最终答案;(c) 最大迭代兜底——对应 `e.config.MaxIterations` 与 `handleMaxIterations`,到顶没答完就基于已有工具结果 `streamFinalAnswerToEventBus` 强合成,再不行回退通用提示语。

</details>

## Try it

打开 WeKnora 源码的 `internal/agent/engine.go`,按顺序读 `Execute`(206)→ `executeLoop`(362)→ `runReActIteration`(468),把一轮四步(Think/Analyze/Act/Observe)在代码里圈出来;再跳到 `internal/agent/act.go` 对比 `executeToolCalls`(217)与 `executeToolCallsParallel`(242)的执行策略;最后读 `internal/agent/finalize.go` 的 `emitCompletionEvent`,看 `EventAgentComplete` 带走了哪些字段。

## Source

- WeKnora 源码的 `internal/agent/engine.go`(`Execute` 206、`executeLoop` 362、`iterOutcome` 451、`runReActIteration` 468、`handleMaxIterations` 位于 finalize.go 160)
- WeKnora 源码的 `internal/agent/act.go`(`executeToolCalls` 217、`executeToolCallsParallel` 242、`executeSingleToolCall` 310、`runToolCall` 356)
- WeKnora 源码的 `internal/agent/finalize.go`(`streamFinalAnswerToEventBus` 27、`handleMaxIterations` 160、`emitCompletionEvent` 181)
- WeKnora 源码的 `internal/agent/approval/gate.go`(`NewGate` 189、`NeedsApproval` 289、`RequestAndWait` 309、`Resolve` 539)

- [WeKnora 官方仓库](https://github.com/Tencent/WeKnora)
- [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)
