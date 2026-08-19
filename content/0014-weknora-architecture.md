# WeKnora 系统架构总览:容器、依赖注入、路由与引擎注册

> **Outcome:** 学完你能说出 WeKnora 的进程是怎么"长"出来的:`BuildContainer` 用 dig 容器做依赖注入,把基础设施、外部服务、Repository、业务 Service 一层层 `Provide` 进去;检索引擎通过 `initRetrieveEngineRegistry` 按 `RETRIEVE_DRIVER` 环境变量注册进 `RetrieveEngineRegistry`,运行时再由 `EngineFactory` + `createEngineServiceFromStore` 按 `VectorStore.EngineType` 动态重建;HTTP 层由 `NewRouter` 用 gin 组装中间件和 `RegisterXxxRoutes`,把 URL 绑到 `internal/handler/` 的各个 Handler 上。

## Why this matters

前 13 课一直在讲 RAG 的"零件"(切分、嵌入、检索、重排),但零件怎么被组装成一个能跑的 HTTP 服务,才是最容易被忽略的一层。WeKnora 是一个 19.8k★ 的生产级项目,它不是把 `main()` 里几百行 `NewXxxService` 堆在一起,而是用了 **dig 依赖注入容器 + 引擎注册表 + 路由注册** 三件套来解耦。读懂这一课,你就拿到了整份代码的地图:之后看到任何一个 `NewXxxHandler`、任何一个业务 Service 被 `dig.Invoke` 取出来,都知道它在进程里处在哪一层。2026 年 Go 服务几乎都长这样,这一课等于给你一副"读任何 Go 后端的主线眼镜"。

## Core idea

### 一、三层骨架:Container → Router → Handler

WeKnora 的进程组装分成三层,顺序固定:

| 层 | 代码位置 | 职责 | 关键入口 |
|----|----------|------|----------|
| 组装层(容器) | `internal/container/container.go` | 用 dig 做依赖注入,把一切 `Provide` 进容器 | `BuildContainer`(108 行) |
| 路由层 | `internal/router/router.go` | 用 gin 建路由、挂中间件、把 URL 绑到 Handler | `NewRouter`(92 行) |
| 处理层 | `internal/handler/` | 一文件一个 HTTP Handler,接收 gin.Context | `NewXxxHandler`(system.go / knowledge.go / session/...) |

`container.go` 的 `BuildContainer` 是唯一入口,它从第 108 行一路注册到结尾:

```go
func BuildContainer(container *dig.Container) *dig.Container {
    must(container.Provide(config.LoadConfig))          // 配置
    must(container.Provide(initLangfuse))               // 可观测性
    must(container.Provide(initDatabase))               // GORM 数据库
    must(container.Provide(initRedisClient))            // Redis
    must(container.Provide(initAntsPool))               // 协程池
    must(container.Provide(initRetrieveEngineRegistry)) // 检索引擎注册表
    // …… 外部服务客户端、数十个 Repository、业务 Service 逐一 Provide
}
```

`must` 的作用是:任何一个 `Provide` 出错就直接 panic,保证进程"缺一个依赖就不启动",而不是带着半成品跑起来。

### 二、检索引擎注册表:一条 `RETRIEVE_DRIVER` 决定七条后端

`initRetrieveEngineRegistry`(1090 行)是第七章颗检索引擎的接线处。它先读逗号分隔的 `RETRIEVE_DRIVER` 环境变量,然后对每个启用的后端,用同一个 `retriever.NewKVHybridRetrieveEngine(...)` 包装各自的后端 Repository,再 `registry.Register` 进注册表:

```go
retrieveDriver:= strings.Split(os.Getenv("RETRIEVE_DRIVER"), ",")
if slices.Contains(retrieveDriver, "postgres") {
    postgresRepo:= postgresRepo.NewPostgresRetrieveEngineRepository(db)
    registry.Register(retriever.NewKVHybridRetrieveEngine(postgresRepo, types.PostgresRetrieverEngineType))
}
// sqlite / elasticsearch_v8 / elasticsearch_v7 / opensearch / qdrant / weaviate / milvus 同理
```

| 后端 | 注册键(`RetrieverEngineType`) | 创建函数(`engine_factory.go`) |
|------|-------------------------------|-------------------------------|
| PostgreSQL | `PostgresRetrieverEngineType` | `createPostgresEngine` |
| SQLite | `SQLiteRetrieverEngineType` | `createSQLiteEngine` |
| Elasticsearch v8 | `ElasticsearchRetrieverEngineType` | `createElasticsearchV8Engine` |
| Elasticsearch v7 | `ElasticsearchRetrieverEngineType`(v7 专用 client) | `createElasticsearchV7Engine` |
| OpenSearch | `OpenSearchRetrieverEngineType` | `createOpenSearchEngine` |
| Qdrant | `QdrantRetrieverEngineType` | `createQdrantEngine` |
| Milvus | `MilvusRetrieverEngineType` | `createMilvusEngine` |
| Weaviate | `WeaviateRetrieverEngineType` | `createWeaviateEngine` |
| Doris / 腾讯向量库 | `Doris/TencentVectorDBRetrieverEngineType` | `createDorisEngine` 等 |

所有后端都实现了同一个 `interfaces.RetrieveEngineService` 接口——这就是"引擎注册"的可插拔设计:**调用方只认接口,不认具体后端**。

### 三、注册表与运行时工厂:双通道重建引擎

`registry.go` 的 `NewRetrieveEngineRegistry(repo, factory)` 返回的注册表内部有四个 map:

```go
return &RetrieveEngineRegistry{
    byEngineType: make(map[types.RetrieverEngineType]interfaces.RetrieveEngineService),
    byStoreID:    make(map[string]interfaces.RetrieveEngineService),
    storeGen:     make(map[string]uint64),
    failedUntil:  make(map[string]time.Time), // 构建失败的冷却
    repo:         repo,
    factory:      factory,
}
```

它回答两类问题:

1. **环境变量驱动的静态引擎**(启动时注册):查 `byEngineType`。`Register` 对同名类型会返回 "already registered" 错误。
2. **DB 里的向量库实例**(每个知识库配的 store):通过 `GetOrLoadByStoreID` 查 `byStoreID`;没命中就走 `factory`(即 `NewEngineFactory`)现场重建,重建失败进 `markBuildFailed` 冷却 `rebuildCooldown`,避免反复连一个挂掉的后端。

`engine_factory.go` 的 `createEngineServiceFromStore` 是对环境变量注册表的"运行时对应物":它 `switch store.EngineType`,把持久化的 `VectorStore.ConnectionConfig` 变成活的引擎,并且开头先过一层 `validateRuntimeVectorStoreAddresses` 做 **SSRF 校验**——它不信任任何存进 DB 的地址,这正是 2026 年云服务必须守的底线。

### 四、路由层:gin 中间件 + 路由组注册

`NewRouter`(92 行)返回一个 `*gin.Engine`,先把中间件按顺序 `Use` 上去(CORS、`RequestID`、`Language`、`Logger`、`Recovery`、`ErrorHandler`),然后注册各黑盒入口,最后把业务路由分给各个 `RegisterXxxRoutes`(如 `RegisterTenantRoutes`、`RegisterAuthRoutes`、`RegisterIMRoutes`、`RegisterEmbedPublicRoutes`):

```go
r:= gin.New()
r.Use(cors.New(...))                 // 注意注释:通配符 * 与 AllowCredentials 不能共存
r.Use(middleware.RequestID())
r.Use(middleware.Recovery())
r.GET("/health",...)                // 健康检查不过认证
if gin.Mode() != gin.ReleaseMode {
    r.GET("/swagger/*any", ginSwagger.WrapHandler(...)) // 生产关闭
}
```

一个值得记的细节:启动时 `r.SetTrustedProxies(trustedProxies())` 把受信代理收紧到前端 nginx 网段,防止伪造 `X-Forwarded-For` 绕过按 ClientIP 的限流——这是并发风险里容易漏的一环。

## Worked example

**案例一(读懂启动日志)**:部署时只开 Postgres + Redis,设 `RETRIEVE_DRIVER=postgres,sqlite`。启动日志依次出现 "Register postgres retrieve engine success"、"Register sqlite retrieve engine success"。请求进来后 `NewRouter` 建的 gin 路由匹配到 `/api/v1/knowledge/...`,命中 `handler.KnowledgeHandler`,从 dig 容器 `Invoke` 出 `KnowledgeService` 和 `RetrieveEngineRegistry`,按知识库配的 store 类型取引擎。整条链路不关心后端是 ES 还是 Milvus,因为接口一样。

**案例二(动态重建的价值)**:租户在 UI 新建了配 Qdrant 的知识库,但启动时 `RETRIEVE_DRIVER` 没开 qdrant。`byEngineType` 没有 Qdrant,于是走 `GetOrLoadByStoreID` 的缺失分支,`factory`(NewEngineFactory)按 `EngineType=QdrantRetrieverEngineType` 调 `createQdrantEngine` 现造一个。这让**运行期新增向量库不需要重启进程**,是注册表 + 工厂双通道的价值。

**案例三(SSRF 防到源码层)**:`validateRuntimeVectorStoreAddresses` 对每个 store 的连接地址调 `utils.ValidateURLForSSRF(endpoint)` 再放行。攻击者哪怕注入自己控制的 IP 进 VectorStore 行,也会在这里被拦——注册表是最后一道闸。

## Retrieval practice

1. 闭卷题:`BuildContainer` 里多个 `dig.Container.Provide` 各自注册什么?`initRetrieveEngineRegistry` 靠哪个环境变量决定注册哪几个后端?`Register` 对重复类型返回什么?
2. 迁移题:团队要接入全新向量库 Pinecone。按注册表模式,需动哪几个文件、哪几个函数才能"一键可选"而不改一堆调用方?

<details>
<summary>Check answers</summary>

1. `Provide` 依次注册:基础设施(配置 `config.LoadConfig`、`initLangfuse`、`initDatabase`、`initRedisClient`、`initAntsPool`)、检索引擎注册表 `initRetrieveEngineRegistry`、外部服务客户端(repo/Redis/neo4j/ollama/DuckDB 等)、数十个 Repository、业务 Service;最后把需要启动的协程(Scheduler、Housekeeping 等)在 `Invoke` 里跑起来。`initRetrieveEngineRegistry` 按逗号分隔的 `RETRIEVE_DRIVER` 环境变量逐个注册。`Register` 对已注册类型返回 `"repository type %s already registered"` 错误,防止重复注册。
2. 三处:(a) `engine_factory.go` 加一个 `createPineconeEngine(store)`,并在 `createEngineServiceFromStore` 的 `switch store.EngineType` 里加 `case types.PineconeRetrieverEngineType`;(b) `types` 里加 `PineconeRetrieverEngineType` 常量;(c) `container.go` 的 `initRetrieveEngineRegistry` 里加 `if slices.Contains(retrieveDriver, "pinecone") {... registry.Register(NewKVHybridRetrieveEngine(pineconeRepo,...)) }`。调用方(CompositeRetrieveEngine、上层 Service)只依赖 `RetrieveEngineService` 接口,完全不用动——这就是注册表解耦的意义。

</details>

## Try it

打开 WeKnora 源码的 `internal/container/container.go`,先看 `BuildContainer`(108 行起)把整段注册顺序读一遍,数一数它注册了多少个 Repository;再跳到 `initRetrieveEngineRegistry`(1090 行)把 `RETRIEVE_DRIVER` 支持的每个后端注册块对照本课的表格;最后打开 `internal/router/router.go` 的 `NewRouter`,看中间件注册顺序。

## Source

- WeKnora 源码的 `internal/container/container.go`(`BuildContainer` 108 行、`initRetrieveEngineRegistry` 1090 行、`loadDBStoresIntoRegistry` 1407 行、`must` 512 行)
- WeKnora 源码的 `internal/container/engine_factory.go`(`NewEngineFactory` 46 行、`createEngineServiceFromStore` 56 行、`validateRuntimeVectorStoreAddresses` 94 行、各 `createXxxEngine`)
- WeKnora 源码的 `internal/application/service/retriever/registry.go`(`NewRetrieveEngineRegistry` 122 行、`Register` 139 行)
- WeKnora 源码的 `internal/router/router.go`(`NewRouter` 92 行、`trustedProxies` 305 行);`internal/router/routes_*.go`(RegisterTenantRoutes / RegisterAuthRoutes 等)
- WeKnora 源码的 `internal/handler/*.go`(system.go / knowledge.go / session/handler.go 等各 `NewXxxHandler`)

- [WeKnora 官方仓库](https://github.com/Tencent/WeKnora)
