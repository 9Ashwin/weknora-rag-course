# Agentic RAG 与迁移落地:多智能体编排 + 把整套模式搬进客服平台

> **Outcome:** 学完你能说清 2026 年 Agentic RAG 的"协调器—专业检索 agent—验证—组装"模式,在企业级"多 agent 编排 + 治理"的代价与前提,在 WeKnora 源码里定位 ReAct 执行循环、工具注册表与 MCP 集成三个真实落点(并诚实区分它离"多 agent 主从"还差什么),最后结合 0008 的迁移思路,给客服平台画一条可分期落地的 Agentic 改造路线。

## Why this matters

本系列前 11 课都在拆"一次检索→生成"。但当任务复杂到**一次检索拿不够上下文、需要自主决定查哪、查几次、用哪个工具**时,就需要 Agentic RAG。前面课程已经埋了 Modular RAG 的"编排"概念,2026 年 Agentic RAG 把它推到极致:一个 master 协调器把查询分解给多个专业检索 agent,再验证、再组装。同时企业级落地绕不开"多 agent 编排 + 治理(权限/审批/可观测)"。这一课把理论落到 WeKnora 的真实源码,并接上 0008 的客服平台迁移线——这就是整套 RAG 模式的"出口"。

## Core idea

### 一、2026 年 Agentic RAG 的标准模式

```text
用户查询 → Master 协调器(理解意图、拆分任务)
  → 专业检索 agent A(知识库/向量)
  → 专业检索 agent B(数据库/图谱/工具,经 MCP)
  → 验证器(检查检索质量是否足够)
  → 组装器(合并多路结果 → 生成终答)
```

四个关键词:
- **Master 协调器**:拆解复杂问题,决定派给谁、按什么顺序
- **专业检索 agent**:每个 agent 一种工具/数据源,各司其职
- **验证**:检索结果要过质量关,不合格就再查(呼应 0010 的 CRAG/Self-RAG 思想)
- **组装**:多路上下文合并,统一生成

**企业级还要加"治理"**:权限控制(哪个 agent 能碰哪些数据)、审批门(高风险操作)、可观测(追踪每步为什么这么查)。否则多 agent 就是"不可控的失控编排"。

### 二、WeKnora 的真相:单 ReAct Agent + 工具编排,而非多 agent 主从

先给结论再给证据——WeKnora 是**一个 ReAct agent + 丰富的工具注册表 + MCP 集成**,不是"多个 agent 互相协调"。它用"一个大脑 + 多把工具"实现 Agentic 效果,真正的多 agent 协作是扩展方向。真实源码:

- **ReAct 执行循环**:`internal/agent/engine.go` 的 `AgentEngine`、`executeLoop`(约 360 行),`runReActIteration` 执行"think → analyze → act → observe"一步,`MaxIterations` 控制最多迭代轮数(engine.go:397 `for state.CurrentRound < e.config.MaxIterations`)
- **工具注册表**:`internal/agent/tools/` 是一个 `ToolRegistry`,专业"检索 agent"在这里体现为一堆工具:
  - `knowledge_search.go`(知识库检索 + rerankWithLLM / rerankThreshold)
  - `query_knowledge_graph.go`(图谱关系查询,0011)
  - `database_query.go`、`data_analysis.go`(结构化数据,可接 DuckDB)
  - `faq_snippet.go`、`grep_chunks.go`(细粒度片段检索)
- **MCP 集成(外部工具/数据源的插口)**:`internal/mcp-server/agent/`(MCPClient、manager、oauth),`internal/agent/tools/mcp_tool.go` 的 `MCPTool` 把 MCP 服务工具包成 agent 工具,`internal/agent/approval/gate.go` 提供"调用前人工审批门",`internal/agent/tools/scope_authorization.go` 做作用域授权——这就是上文说的**治理层**

所以 WeKnora 证明一件事:**"工具万能 + 治理到位" 的单一 agent,能覆盖大部分 Agentic RAG 的诉求;多 agent 退缩为"当单一大脑的上下文/权限撞墙时"的升级方案。**

### 三、2026 生产注意点(简短)

- master 协调器的拆解、验证、组装在单 agent 里就是"工具 + 多轮 ReAct + 阈值判断",先别急着上多进程 agent
- 双数据库/多系统的"专业 agent"在 WeKnora = 多个工具 + 多个 MCP 服务,而不是多套独立 agent 进程
- 没有审批门和权限作用域的多 agent,等于裸奔——`approval/gate.go` 和 `scope_authorization.go` 不是可选

## Worked example

**案例(迁移:客服平台收到复杂工单,参考 0008 思路)**——单一 agent + 多工具即可落地 Agentic:

```text
客户"发票金额对不上,订单也还没发货,咋办"
→ ReAct agent(协调器):
  第 1 步  knowledge_search:查"发票金额不符"政策(0010/0005 混合检索)
  第 2 步  database_query(经 MCP):查订单状态与发票明细
  第 3 步  query_knowledge_graph:查"订单—发票—物流"关系路径
  第 4 步  合并两路结果 → 生成"先解释差额,再给发货进度"的终答 + 引用
  (process 中途被 approval.gate 拦下时,等用户确认再继续)
```

对照 WeKnora:第 1/3 步是它内置工具,第 2 步是 MCP 接的工单系统,第 4 步是 `finalize.go` 的组装生成。**这就是"协调器拆解→专业检索→验证→组装"在 WeKnora 里的真实形态**——无需新造多 agent 框架。

**治理例子**:坐席手动发起高危操作(如删知识库)时,`MCPTool` 前的 `approval/gate.go` 弹人工审批;跨部门数据访问由 `scope_authorization` 拦截。对比 0008 里"人工审核的知识仍是最高可信度来源"——治理换不来质量,但锁得住边界。

## Retrieval practice

1. 闭卷题:2026 Agentic RAG 的四段式模式是什么?WeKnora 用哪种形态实现它(单选 agent / 多 agent 主从)?证据在哪几个文件?
2. 迁移题:你的客服平台有知识库、工单系统、物流系统三套数据。按本课思路,你会把它落成"多 agent 主从"还是"单一 agent + 多工具 + 多 MCP"?给出分期落地(Phase 1/2/3)并指出治理点。

<details>
<summary>Check answers</summary>

1. Master 协调器(拆解)→ 专业检索 agent(各自查)→ 验证器(质量把关)→ 组装器(合并生成)。WeKnora 是**单一 ReAct agent + 工具编排 + MCP 集成**,证据:`internal/agent/engine.go`(executeLoop / runReActIteration / MaxIterations)、`internal/agent/tools/`(ToolRegistry:knowledge_search / query_knowledge_graph / database_query 等)、`internal/agent/tools/mcp_tool.go` + `internal/mcp-server/agent/`、以及治理层 `internal/agent/approval/gate.go`、`internal/agent/tools/scope_authorization.go`。多 agent 主从是扩展方向,源码暂无。
2. 优先**单一 agent + 多工具 + 多 MCP**,因为三套数据在 WeKnora 里就是三个工具/服务,无需 multi-process。Phase 1:开 `knowledge_search` + `faq_snippet`,让 agent 答 FAQ;Phase 2:接工单/物流 MCP(`database_query` / 自定义 MCPService),做"跨系统把事实拉齐"的多轮 ReAct;Phase 3:加图谱工具做关系推理 + 语义缓存省成本。治理:所有写操作(改单/删库)过 `approval/gate.go` 人工审批,跨部门数据用 `scope_authorization` 限权,全程走 Langfuse 追踪(observability)。

</details>

## Try it

打开 WeKnora 源码的 `internal/agent/engine.go` 的 `executeLoop` 与 `runReActIteration`,数一数一个 ReAct 回合拆成哪几步;再打开 WeKnora 源码的 `internal/agent/tools/mcp_tool.go` 的 `MCPTool`,看它如何把外部 MCP 服务包装成 agent 工具,以及 `approval/gate.go` 插在调用前的哪一环。

## Source

- 2026 Agentic RAG 趋势:master 协调器分解→专业检索 agent→验证→组装;企业级多 agent 编排 + 治理(How to Build RAG Systems in 2026: 8 Architecture Patterns)
- WeKnora 源码的 `internal/agent/engine.go`(executeLoop / runReActIteration / MaxIterations)、`internal/agent/tools/`、`internal/agent/tools/mcp_tool.go`、`internal/mcp-server/agent/`、`internal/agent/approval/gate.go`、`internal/agent/tools/scope_authorization.go`

- [Agentic Retrieval-Augmented Generation: A Survey on Agentic RAG](https://arxiv.org/abs/2501.09136)
