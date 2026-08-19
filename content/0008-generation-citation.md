# 生成与引用溯源:让 LLM 基于片段作答,并交代出处

> **Outcome:** 学完你能说清生成环节"组合指令 + 提示词工程"的作用,理解引用溯源为什么是生产级 RAG 的硬要求,并指出 WeKnora 源码里 ReAct Agent 编排、prompt 组装、`<ref>`→`<kb>/<web>` 引用展开、流式引用安全每一段的落点。

## Why this matters

前面几课解决"检索到对的资料",这一课解决"拿这些资料拼出对的答案"。生成环节可以拆成两步:**组合指令**(把用户问题 + 检索片段拼成 prompt 喂给大模型)和**提示词工程**(设计好指令让模型乖乖基于片段作答、不瞎编)。而在 2026 年,单纯"答对"已经不够——金融、医疗、客服场景要求**每个论断都能追溯到来源**(引用溯源),这既是可信度问题,也是合规和数据安全问题。这一课把"生成流程"和 WeKnora 的"引用溯源 + ReAct Agent"拼成一张完整的地图。

## Core idea

### 一、生成流程:大模型是大脑,提示词是开关

核心观点:RAG 的生成不是"让模型自由发挥",而是**给它限定上下文让它做"阅读理解"**:把检索到的若干文本块 + 用户问题组合成指令,约束模型"只能依据给定内容回答"。提示词工程质量直接决定输出质量——同一个 LLM,给混乱的上下文就答得烂,给清晰的组织就答得准。这解释了为什么生成环节要严格区分 **system prompt(固定职责)** 和 **user prompt(本次问题)**。

生成侧的大模型选型也有讲究:通用大模型(闭源如通义、智谱、混元;开源可私有化如 Qwen、GLM)在 RAG 里当"大脑",性能直接决定整个系统上限;私有化场景优先开源模型以保住数据安全(呼应 0001 课 LLM 四短板的"数据安全")。

### 二、生产级生成:答案必须能溯源

"答得对"只是基础;2026 年的生产要求在此基础上加一条 **"答得可核查"**。实现引用溯源的关键设计决定是:**引用用的 ID 必须在请求本地生成、不可让模型摸到真实全局 ID**。原因有二:一是安全和合规,真实 chunk ID / 知识库 ID 不该出现在用户可见输出里;二是防幻觉——如果模型看到的是一串"c12""w3"这种简短句柄,它只能用上下文里真正出现过的句柄,无法编造一个不存在的来源。

### 三、WeKnora 的生成编排:ReAct Agent

生成层在 `internal/agent/`:它不只是单轮问答,而是一个 **ReAct(Reason+Act)Agent**,能自主决定"要不要再检索一次"。核心函数:

- `NewAgentEngine(...)` 构建引擎,`buildSystemPrompt(ctx)` 组装系统提示(拼入检索上下文、工具说明、引用协议);
- `Execute(...)` 入口,内部 `executeLoop(...)` 循环驱动,`runReActIteration(...)` 跑一轮"思考→行动→观察"(对应 `think.go` / `act.go` / `observe.go`),`finalize.go` 收尾;
- 工具由 `internal/agent/tools/` 提供(如 `knowledge_search.go`、`wiki_tools.go`),让 Agent 能按需再检索。

### 四、WeKnora 的引用溯源:句柄 + 协议 prompt + 展开器

引用机制落在 `internal/modelcontext/`,是这个 Agent 的"引用命脉"。整套设计围绕**请求级来源句柄**(request-local source handle)展开:

**句柄注册(sources.go)**:`sourceRegistry` 为一次回答维护四类句柄——`cN` 知识块 chunk、`dN` 文档、`bN` 知识库、`wN` 网页,由 `newSourceRegistry` 初始化。检索结果通过 `RegisterSearchResults` 批量注册,`RegisterChunk` / `RegisterDocument` / `RegisterWeb` 等把真实 ID 映射成短句柄。

**协议 prompt(citations.go)**:`sourceProtocolPrompt(citationsEnabled)` 把系统级引用规则注入 prompt。`citationEnabledProtocolPrompt` 明确要求:引用知识块用 `<ref id="cN"/>`、网页用 `<ref id="wN"/>`;**只能引用上下文里出现过的句柄**;`<ref/>` 内联在对应的论断同一行,不许在末尾集中堆引用。`citationDisabledProtocolPrompt` 则强制"本次不输出任何引用"。

**展开(citations.go)**:模型输出 `<ref id="cN"/>` 后,`ExpandText` 把它转成公开契约 `<kb doc="…" chunk_id="…"/>`(知识块)或 `<web url="…" title="…"/>`(网页);未知句柄**fail-closed 直接丢弃**。`CompactPublicCitations` 反向把历史轮次里的公开 `<kb>/<web>` 折叠回私有句柄,防止持久化 chunk ID 再次暴露给模型。

**流式安全(citations.go)**:`citationStreamExpander` 在 SSE 流上处理增量文本,`Feed` 缓存未完成的 `<ref…` 前缀,等标签闭合后才展开——杜绝把"残缺的私有标签"推到客户端。`Flush` 在流末尾清空缓冲。

这套机制的回答是:**模型只跟"c12/w3"这种一次性的短句柄打交道,永远碰不到真实 ID;用户看到的永远是带文档标题和 chunk_id 的可验证引用。**

## Worked example

**案例一(指令组合)**:用户问"退款要多久到账"。Naive 做法把问题直接丢给 LLM,模型凭训练记忆答,可能过时甚至编造。RAG 的生成环节则是:检索到"退款通常在 3–5 个工作日到账…退款流程见 X 文档"的块 → 组合成指令"请仅依据以下资料回答:…[块1][块2]… 问题:退款要多久到账" → LLM 作答并附 `<ref id="c1"/>`。WeKnora 里这对应 `buildSystemPrompt` 拼上下文 + `OnEvent` 后的生成调用,引用经 `ExpandText` 变成可见出处。

**案例二(引用的安全边界)**:假设模型在回答里多写了一个 `<ref id="c99"/>`,但上下文里根本没出现 c99。WeKnora 的 `ExpandText` 查句柄表找不到,直接丢弃这段引用(而不是把用户答错来源)。同时 prompt 协议要求"只引用上下文出现过的句柄",双保险压住"编造来源"。

**案例三(Agentic 生成)**:用户问"对比我们和竞品的退款政策",单次检索拼不出答案。WeKnora 的 Agent 在 `runReActIteration` 里先检索本公司退款政策,发现缺竞品信息,再触发 `knowledge_search` 工具检索竞品文档,第二轮上下文合并后作答,两个来源各自带引用。这正是 0001 课 Agentic RAG 档位在生成层的落地。

## Retrieval practice

1. 闭卷题:为什么生产级 RAG 的引用要用"请求级短句柄(cN/wN)"而不是直接让模型输出真实 chunk ID?`ExpandText` 遇到未知句柄会怎样?
2. 迁移题:你的客服机器人要求"每个结论必须给出可点击的原文出处",但 LLM 经常把两段话的引用张冠李戴。你会从 prompt 协议、句柄机制、以及 Agent 工具哪些层面去修?

<details>
<summary>Check answers</summary>

1. 三个原因:安全和合规(真实 chunk/知识库 ID 不应暴露给用户或外部系统);防幻觉(模型只能用上下文里出现过的句柄,无法编造来源);状态隔离(句柄一次请求内有效,不跨请求复用)。`ExpandText` 对未知句柄 fail-closed,直接丢弃——宁可不给引用,也不给错误引用。
2. 张冠李戴通常源于两处:一是 prompt 没要求"引用内联在各论断同一行"(WeKnora 的 `citationEnabledProtocolPrompt` 明确禁止末尾堆引用);二是模型在多个来源共存时混淆归属。可在 prompt 协议里强化"每个 `<ref/>` 紧跟其支撑的句子";对高价值场景可用 groundedness/忠实度指标自动检测"句子与所引用块内容是否一致"(见 0010 课),不合格则触发重生成或提示用户;Agent 工具侧应保证每个检索结果带独立句柄,避免合并时串号。

</details>

## Try it

打开 WeKnora 源码的 `internal/modelcontext/citations.go`,搜 `<ref id="` 看句柄正则和 `ExpandText` 的分支;再打开 `internal/sources.go`(完整路径 `internal/modelcontext/sources.go`)看 `RegisterSearchResults` 怎么把 `types.SearchResult` 映射成 chunk 句柄。把"注册→引用→展开"三步在脑中走一遍。

## Source

- WeKnora 源码:`internal/agent/engine.go`(NewAgentEngine / executeLoop / runReActIteration)、`internal/agent/tools/`(knowledge_search.go)、`internal/modelcontext/citations.go`(sourceProtocolPrompt / CompactPublicCitations / ExpandText / citationStreamExpander)、`internal/modelcontext/sources.go`(sourceRegistry / RegisterSearchResults)
- 2026 生产要求:引用溯源为可信 RAG 硬指标,配合 groundedness 持续测量(见 0010 课)

## 对话模式与结构化数据

> 生成层还有两个核心设计问题:怎么组织对话、怎么让输出可解析。这一节把它们接到 WeKnora 生成层:模型上下文(modelcontext)机制、记忆与上下文管理、以及"让输出可解析"的落地。

### 一、对话模式的要点:三种角色与记忆

几乎所有的 RAG 应用本质上都是通过"对话模式"交互的——哪怕看起来不是对话的应用(比如返回结构化数据的工具调用),底层仍是"用户问一句、AI 答一句"的对话。在对话模式里有三种角色,以及一个贯穿始终的概念——记忆。

| 概念 | 要点 | 对照 WeKnora 生成层落点 |
| --- | --- | --- |
| **user / assistant** | 对话的两个基本角色,即用户与 AI | `internal/agent/observe.go` 的 `buildMessagesWithLLMContext` 拼出 `[]chat.Message`,用户本轮问题以 `user` 角色追加在末尾 |
| **system(可选)** | OpenAI 从 GPT3.5 起新增,用于设定助理行为;很多非 OpenAI 模型不支持,故课程对话模型默认不用 system | WeKnora 反而**必用** system:`buildSystemPrompt(ctx)` 拼出唯一的 system 消息,承载检索上下文、工具说明、引用协议与记忆块(`engine.go` 第 277 行 `buildMessagesWithLLMContext` 首个消息就是 system) |
| **记忆 memory** | 多轮对话中 AI 靠**之前的话**推断省略的信息(如"还剩多少"能补全"客户A/款项/到账");记忆有上限,不同模型不同 | 每次会话历史由调用方按轮次从 DB 重建(`engine.go` 注释:"history is rebuilt from the DB once per turn")注入 `llmContext`;当上下文窗口逼近上限时由 `internal/agent/memory/consolidator.go` 触发**LLM 总结压缩**(见下) |
| **RAG = 好记性不如烂笔头** | 用外部知识库这个"烂笔头"代替记忆:检索相关片段塞进对话再让模型生成 | 检索结果经 `RegisterSearchResults` 注册成短句柄后,`RenderUserTurnContent` 调用 `buildRuntimeContextBlock` 把绑定知识库/文档拼进当前 user 轮,再经 `CompactKnownText` 压成模型可读形式(`observe.go` 507–560 行) |

**上下文管理的两条 WeKnora 工程实践,正好回答"一万次对话超记忆上限怎么办"的经典难题:**

1. **总结压缩(面向长期记忆)**:"摘要记忆 / 混合记忆"在 WeKnora 落地为 `agentmemory.Consolidator`——当 token 数超过 `MaxContextTokens × threshold`(默认 0.5)时,用 LLM 把较早的消息总结成一段紧凑摘要,保留关键事实与工具结果;总结失败(最多重试 3 次)则回退为原始归档。这跟"切片→逐段归纳→持久化"的经典做法同构。
2. **脱敏注入历史(面向短期上下文)**:历史进了上下文后,`buildMessagesWithLLMContext` 会 **丢弃历史里的 system 消息**,并把上一轮的检索(KB)工具结果按需脱敏——`RedactRetrievalHistory` 为假时调用 `redactHistoryKBResults` 抹掉旧检索块,防止模型复用**已被改库"过期"的检索数据**。这也是为什么记忆块(`memoryPrompt`)要被 append 进 system prompt 而非单独一条消息:否则从第二轮起会被静默丢掉(`engine_memory_test.go` 测试专门守护这一点)。

> 一个反直觉但重要的点:通用对话场景常因"很多模型不支持 system"而默认不用它;WeKnora 因为面向受控 Agent 场景,反而把**协议、记忆、上下文全压进唯一的 system 消息**。这说明 system 角色的适用性取决于你是否能控制模型接入面。

### 二、返回结构化数据:为什么 LLM 输出要结构化、怎么可解析

结构化输出的核心痛点:**程序只能识别结构化数据,识别不了人类语言**;且 AI 一次只能返回一个结果。业界给出由易到难的五级结构化梯度——全部通过"在 user 的 content 里声明返回格式"实现:

| 输出类型 | 适用场景 | 做法示例 | WeKnora 生成层对应机制 |
| --- | --- | --- | --- |
| 布尔值 | 判断题 | `"请以布尔值格式返回答案:…"` → `false` | 协议性布尔/枚举常写在 system 协议里(如 `citationEnabledProtocolPrompt`) |
| 整数 | 选择题 | 给 1.点心 2.水果 3.菜肴,`"请以整数格式返回正确选项"` → `1` | 工具参数里限制 `enum` + `type:"integer"`,让模型输出选项索引 |
| 浮点数 | 开放性数值 | `"请以浮点数格式返回按米计算的答案:…"` → `2.26` | 工具参数 schema 约束 `type:"number"` |
| 数组 | 可变参数 | 返回多个名字供 `greet_many(*names)` | 工具参数 `type:"array"`(如一次检索多个 chunk 句柄) |
| JSON | 复杂结构 | 在 prompt 里贴 JSON Schema 示例,要求严格按结构返回 | **HandleTable + DecodeToolCalls**:模型输出 JSON 的 tool-call 参数,`Registry.DecodeToolCalls` 把参数里的短句柄解析回真实持久值 |

**"让输出可解析"在 WeKnora 的三个具体落点:**

1. **协议 prompt 声明格式**:`internal/modelcontext/` 的 `sourceProtocolPrompt`(由 `citationEnabledProtocolPrompt` + `citationDisabledProtocolPrompt` 组成)把"引用必须用 `<ref id="cN"/>`"这种**带严格结构的输出格式**注入 system 协议——模型必须按声明产出一个可解析的、带引用标记的结构化文本,而不是自由发挥。
2. **HandleTable:结构化句柄表**:`handles.go` 的 `HandleTable`(底层 `handleTable`)是"持久值 ↔ 请求级短句柄"的双向映射,如 `c000`(前缀 c、宽 3、从 0 起)、`ref-N`(前缀 ref-、从 1 起)。`Register` 把持久值登记成短句柄,`Resolve` 把模型输出的句柄解析回持久值。这就是"检索结果结构化入 prompt、拿到可解析输出"的幕后结构。
3. **DecodeToolCalls:解析并回填**:模型返回的 tool-call 是 JSON 参数串(包含短句柄),`registry.go` 的 `DecodeToolCalls` 逐个把 `resources` / `sources` 里的句柄 **resolved 回真实 ID**(`UnresolvedHandles` 追回没解析成功的孤儿句柄,并用 `jsonEquivalent` 对比解析前后是否变化,给出 `ArgumentResolution*` 状态)。一句话:**模型永远只接触短句柄,程序拿到的永远是解析回真实值的结构化参数**。

> "在 content 里声明格式"是**做得到但不稳**的软约束;WeKnora 的 protocol prompt + HandleTable + `DecodeToolCalls` 是**声明格式 + 状态机解码 + fail-closed 校验**的硬管线——这正是"程序能解析"和"程序解析出的东西是对的"的分水岭。

### 三、组装全景:把"对话模式 + 结构化"接起来

WeKnora 生成层一次请求的完整链路,正好把"对话 + 记忆"与"结构化输出"扣在一起:

`buildSystemPrompt` 拼 system(协议+记忆+上下文)→ `buildMessagesWithLLMContext` 注入脱敏历史 + 当前 user 问题(`RenderUserTurnContent` 里 `CompactKnownText` 把绑定知识库/文档压成短句柄)→ `runReActIteration` 跑"思考→行动→观察",模型按协议输出**带 `<ref/>` 的结构化文本 / JSON 工具调用**→ `observe.go` 的 `DecodeToolCalls` 把短句柄解析回真实 ID → `finalize.go` 收尾,`citationStreamExpander` 在流上把 `<ref id="cN"/>` 安全展开成 `<kb>/<web>` 公开引用。

| 概念 | WeKnora 文件/函数 | 一句话作用 |
| --- | --- | --- |
| 对话模式(user/assistant) | `internal/agent/observe.go` `buildMessagesWithLLMContext` | 拼消息序列:system + 脱敏历史 + 当前 user 轮 |
| 记忆/上下文管理 | `internal/agent/memory/consolidator.go`、`internal/agent/engine.go` `buildSystemPrompt` | 超阈值用 LLM 总结压缩;记忆块 append 进 system 防止被历史丢弃 |
| 检索知识塞进对话(RAG) | `observe.go` `RenderUserTurnContent`/`buildRuntimeContextBlock` + `CompactKnownText` | 把绑定知识库/文档/近期 chunk 注册并压成短句柄后拼入本轮 |
| 结构化输出声明 | `internal/modelcontext/citations.go` `sourceProtocolPrompt` | 把 `<ref/>` 引用等严格输出协议注入 system |
| 结构化可解析(句柄表/解码) | `internal/modelcontext/handles.go` `HandleTable` + `registry.go` `DecodeToolCalls`/`jsonEquivalent` | 短句柄 ↔ 持久值映射;解析 JSON 参数并回填真实 ID、标记未解析句柄 |

## Source(扩展)

- WeKnora 源码(扩展):`internal/agent/observe.go`(buildMessagesWithLLMContext / RenderUserTurnContent / buildRuntimeContextBlock / redactHistoryKBResults)、`internal/agent/memory/consolidator.go`(Consolidator 总结压缩)、`internal/modelcontext/handles.go`(HandleTable)、`internal/modelcontext/registry.go`(DecodeToolCalls / jsonEquivalent / resourceHandleProtocolPrompt)、`internal/agent/engine_memory_test.go`(记忆须入 system 的守卫测试)

- [Anthropic: Enhancing RAG with Contextual Retrieval](https://www.anthropic.com/engineering/contextual-retrieval)
