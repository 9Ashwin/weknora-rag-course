# 评估与优化:用指标给 RAG 体检,再对症下药

> **Outcome:** 学完你能说清"先定业务目标 → 选指标 → 实测 → 迭代改检索"的评估闭环,区分检索类与生成类指标,掌握量化打分标准与"模糊转精确"改进原则,并指出 WeKnora 源码里 `metricCalculators` 十项指标的注册方式、`EvaluationService` 的评测闭环,以及检索配置参数这些"可调旋钮"的落点。

## Why this matters

前 8 课在"造系统",这一课是"给系统体检并持续修"。核心原则:**RAG 效果评估是搭建完成后的持续优化流程**,没有统一评估标准,就无法公平比较不同优化方法哪个有效。评估循环是"先找方向再改进":明确业务目标 → 找现成指标库(如 Ragas)→ 按指标实测 → 迭代改进并校准指标。2026 年,RAGas / DeepEval 这类框架已经标配十项指标,生产系统开始把 **groundedness(答案扎根于检索上下文/来源是否成立)** 做成持续测量,而不是上线前测一次就完事。这一课把"指标库 + 改进原则"和 WeKnora 的评估实现拼起来。

## Core idea

### 一、评估的两种方式与量化标准

评估方式分两种,对应两族指标:

- **评估方式**:大模型打分(快、可自动化、但受模型自身偏差影响)vs 人工打分(准、能抓细微幻觉、但慢而贵)。
- **评估指标**:CR 检索相关性(Context Relevancy)、AR 答案相关性(Answer Relevancy)、F 可信度(Faithfulness,查幻觉)。
- **打分标准**:Perfect=1.0、Acceptable=0.75、Missing=0.5、Incorrect=0。
- 场景还可扩展 **Top1 / Top3 / Top5 召回率** 等检索类指标。

### 二、Ragas 十项指标

推荐 Ragas(`docs.ragas.io`),理由:文档完备、专注 RAG 评测、支持与 11 种框架集成。其十项指标里最常用的几项:

|          |                                          |                                           |
|----------|------------------------------------------|-------------------------------------------|
| **指标** | **衡量什么**                             | **性质**                                 |
| 忠实度 Faithfulness | 答案所有声明能否从给定上下文中推断(查幻觉) | 生成类(有参考上下文)                     |
| 答案相关性 Answer Relevance | 答案与问题的相关、完整、无冗余 | 生成类 |
| 上下文查准率 Context Precision | 真实相关项是否排在顶部 | 检索类(排名) |
| 上下文利用率 Context Utilization | 是否利用了所有可用信息块(顺序无关) | 检索类 |
| 上下文查全率 Context Recall | 检索到的上下文与标注答案的一致程度 | 检索类 |

一句话:**检索类指标(Precision/Recall/MRR/NDCG/MAP)评估"捞得准不准、排得对不对",生成类指标(BLEU/ROUGE/Faithfulness/Answer Relevancy)评估"答得好不好、有没有幻觉"。**

### 三、改进原则:尽量把模糊检索转成精确检索

改进的核心原则:**尽量将"模糊检索"转化为"精确检索"**,而且强调是"尽量"而非绝对,从两个层面下手:

1. **用户交互层面提供精确信息**:在对话界面加模块标签栏,用户点"销售管理/生产管理"后提问,后台把该标签传下去缩小检索范围(呼应 0008 课的元数据/标签过滤);
2. **业务逻辑层面提供精确信息**:在业务规则里注入关键词等精确约束。

这直接对应 WeKnora 里 `SearchTarget` 的 `TagIDs` / `ScopeTagIDs`——把"用户交互给的标签"变成检索的精确约束,减少召回噪声。

### 四、WeKnora 的评估实现:十项指标 + 评测闭环

**指标注册(`internal/application/service/metric_hook.go`)**:`metricCalculators` 用一个切片声明了十项指标及其结果字段,`MetricList.Append(metricInput)` 遍历计算。字段全是真实函数名:

```go
// 检索类
metric.NewPrecisionMetric()      → RetrievalMetrics.Precision
metric.NewRecallMetric()         → RetrievalMetrics.Recall
metric.NewNDCGMetric(3)          → RetrievalMetrics.NDCG3
metric.NewNDCGMetric(10)         → RetrievalMetrics.NDCG10
metric.NewMRRMetric()            → RetrievalMetrics.MRR
metric.NewMAPMetric()            → RetrievalMetrics.MAP
// 生成类
metric.NewBLEUMetric(true, metric.BLEU1Gram)   → GenerationMetrics.BLEU1
metric.NewBLEUMetric(true, metric.BLEU2Gram)   → GenerationMetrics.BLEU2
metric.NewBLEUMetric(true, metric.BLEU4Gram)   → GenerationMetrics.BLEU4
metric.NewRougeMetric(true, "rouge-1", "f")    → GenerationMetrics.ROUGE1
metric.NewRougeMetric(true, "rouge-2", "f")    → GenerationMetrics.ROUGE2
metric.NewRougeMetric(true, "rouge-l", "f")    → GenerationMetrics.ROUGEL
```

各指标实现在 `internal/application/service/metric/`(`recall.go` 的 `RecallMetric.Compute` 用 `RetrievalGT`(ground truth)与 `RetrievalIDs`(预测)算分;`mrr.go`、`ndcg.go`、`map.go`、`bleu.go`、`rouge.go` 同理)。

**评测闭环(`internal/application/service/evaluation.go`)**:`EvaluationService` 用 `dataset`(语料 `corpus`、问题 `queries`、标准答案 `answers`、相关性 `qrels`/`arels`)驱动 `EvalDataset`(对某知识库跑评测集)与 `EvaluationResult`(取回结果)构成评估循环;`types/evaluation.go` 定义 `MetricInput` 的 `RetrievalGT` / `RetrievalIDs` 接口。这正好落地说的"先建评测集,再跑指标"。

**可调旋钮(检索配置)**:`internal/types/retrieval_config.go` 的 `RetrievalConfig` 把 RRF 参数(`RRFK` / `RRFVectorWeight` / `RRFKeywordWeight`)、TopK、阈值等暴露成可调配置——指标指出哪一环弱,就调对应的旋钮:召回低调 TopK/混合检索,精度低调阈值/重排,幻觉抬头查生成指标与提示词。

## Worked example

**案例一(查询扩展 + 评估)**:用户问"下面报告中涉及了哪几个行业的案例以及总结各自面临的挑战?"。单点向量查询只覆盖一个语义区域,容易漏。查询扩展指令让 LLM 生成 5 个变体问题,每个独立检索,再合并重排,覆盖不同语义区域。同时用 CR/AR/F 三项指标 + Perfect/Acceptable/Missing/Incorrect 打分标准给系统定量,判断优化是否真有效(这条检索优化正是 0008 课 WeKnora `expandQueries` 的动机)。

**案例二(交互层精确化)**:在对话页加"销售管理/生产管理/库存管理"标签栏,用户点标签再提问,后台把模块信息传给检索,把模糊的全库检索变成"只在该模块内检索"。WeKnora 里就是你点标签 → `SearchTarget` 带上 `TagIDs` → `HybridSearch` 在库层面缩小范围——精准、还省算力。

**案例三(2026 groundedness 持续测量)**:上线前测一次指标不够。生产系统用 RAGas/DeepEval 的忠实度/groundedness 指标,对**每一轮真实问答**持续打分(可挂在 langfuse 之类的 tracing 上),当某文档的 groundedness 连续走低,说明该文档经常被幻觉引用或检索到不相关内容——要么修文档、要么调检索权重、要么收紧重排阈值。WeKnora 的 `MetricList` + `EvaluationService` 就是把这种"按评测集反复跑十项指标并据结果调参"的能力内建到系统里。

## Retrieval practice

1. 闭卷题:检索类与生成类指标分别衡量什么?各举两个 WeKnora 里真实存在的指标函数。四档打分标准是什么?
2. 迁移题:你的 RAG 上线后 MRR 和 Recall 都高,但 Faithfulness/groundedness 持续偏低(答案常引用不存在的来源)。按"模糊转精确"原则和本课的可调旋钮思路,你优先从哪几个环节入手排查?

<details>
<summary>Check answers</summary>

1. 检索类指标评估"捞得准、排得对":`NewRecallMetric`(Recall)、`NewPrecisionMetric`(Precision)、`NewMRRMetric`(MRR)、`NewNDCGMetric(3/10)`、`NewMAPMetric`。生成类指标评估"答得好、没幻觉":`NewBLEUMetric`(BLEU1/2/4)、`NewRougeMetric`(rouge-1/2/l)、另有 Faithfulness / Answer Relevancy(CR/AR/F)。四档:Perfect=1.0、Acceptable=0.75、Missing=0.5、Incorrect=0。
2. 优先查三个方向:① 检索层——看检索到的上下文里是否混入大量不相关块(查 `Context Precision`),若混入,收紧重排阈值 `RerankThreshold`、提高 `RerankTopK` 提升候选质量,或调 RRF 权重;② 生成层——查提示词是否强约束"只依据给定上下文作答"(呼应 0007 课的引用协议 prompt),未强约束则幻觉会高;③ 数据层——被频繁误引的文档本身质量差(数据质量差,很难靠检索救回来),考虑清洗那张文档或从索引中剔除。衡量手段:对问题集反复跑 `EvaluationService` 的 `EvalDataset`,对比调参前后十项指标。

</details>

## Try it

打开 WeKnora 源码的 `internal/application/service/metric_hook.go`,数一数 `metricCalculators` 里声明了几项检索、几项生成指标;再打开 `internal/application/service/metric/recall.go`,看 `RecallMetric.Compute` 怎么用 `RetrievalGT` 和 `RetrievalIDs` 算分。最后打开 `internal/types/retrieval_config.go`,列出现在能调的检索旋钮。

## Source

- WeKnora 源码:`internal/application/service/metric_hook.go`(metricCalculators / MetricList.Append)、`internal/application/service/metric/`(recall.go 等十项指标实现)、`internal/application/service/evaluation.go`(EvaluationService / EvalDataset)、`internal/types/evaluation.go`(MetricInput)、`internal/types/retrieval_config.go`(可调参数)
- 2026 演进:RAGas(`docs.ragas.io`)/ DeepEval 十项指标,groundedness 持续测量接入 tracing(langfuse `retrieval_obs.go`)

## 持续优化、框架借鉴与规范化

评估闭环之外还有三个收尾主题:**持续优化**(细化检索优化的两种手段)、**框架借鉴**(怎么向 LangChain/LlamaIndex 等成熟框架"偷师")、**规范化**(把代码做成工程产物),正好是"找到方向 → 借力别人 → 做成规范产物"三步。

### 一、持续优化:让"模糊"尽量变"精确"

核心原则是**尽量将模糊检索转化为精确检索**,但注意是"尽量"而非绝对——完全转化做不到,只能从多个层面提高转化率。具体落地两种方法:

|         |                                     |                                     | WeKnora 对应                    |
|---------|-------------------------------------|-------------------------------------|---------------------------------|
| **层面** | **做法**                            | **效果**                            | **落点**                        |
| 用户交互层面 | 对话界面加模块标签栏(销售/生产/库存…),用户点标签再提问,把 module 传后端缩小检索范围 | 把全库模糊检索变成"只在该模块内检索",且不影响提问体验 | `SearchTarget` 的 `TagIDs`/`ScopeTagIDs`(0008 课已述) |
| 业务逻辑层面 | 在业务规则里注入关键词等精确约束(以关键词为例展开) | 用业务已知的精确信息缩小候选 | 查询重写 prompt / 检索约束       |

实现细节(标签栏方案):前端在表单顶部加 `nav-tabs` 模块标签 + `<input type="hidden" name="module" value="{{module}}">`;后端 `views.py` 用 `request.GET['module']` 取到模块号,据此把检索范围缩到对应模块——和 WeKnora 把"标签"映射进 `SearchTarget` 后 `HybridSearch` 库里缩范围的机制是同一件事。

### 二、框架借鉴:向 LangChain / LlamaIndex 取长补短

核心观点极具启发性:**不用框架 ≠ 不能借鉴框架**。入门常用 LangChain,但发现不支持微信流式、百度文心、大量中国特有场景后逐渐自己实现,最后框架占比极低;一个常见规律是——"RAG 项目做得越久,框架定制化比例就越高",没有一个框架能覆盖现实工作 20% 的需求。所以正确姿势不是整体套用,而是**把优秀特性整合进自己的项目**。同时给出了标准化四步:

| 步骤 | 做什么                                   | 实例(LlamaIndex)                                       |
|------|------------------------------------------|---------------------------------------------------------|
| 1 明确问题与目标 | 说清项目痛点与想要什么                   | 按换行符分割粒度过大 → 检索准确率低、喂给 LLM 的 token 过多成本高,想要"粒度适中"的分割 |
| 2 寻找工具或参考 | 浏览各家官网找能解决的工具               | 在 LlamaIndex 官网找到 `SentenceWindowNodeParser`(句子窗口节点解析器):每 5 句一个窗口滑动切分,粒度适中 |
| 3 找到对应源代码 | 定位该特性的源码                         | 看 LlamaIndex 里 SentenceWindowNodeParser 的实现        |
| 4 整合进自己项目 | 把思路/代码搬进自己的 RAG                | 在自己的分割逻辑里实现类似滑动窗口,兼顾准确率与控制成本   |

这套四步法对 WeKnora 同样适用:当你觉得分块、重排、查询扩展某处不对劲,就去 LangChain/LlamaIndex 的源码找对应组件的设计,再对照本仓库 `WeKnora 源码` 的 retriever / rerank / query_expansion 看能不能吸收。

### 三、规范化:把教学代码做成工程代码

**教学代码为了好懂,用了中文函数名/变量名、几乎不用类、没有单元测试、没套设计模式,这不符合实际工作规范**。规范化要用 AI 编程助手一步步来,**不能指望 AI 一步到位**(好比"请生成抖音全部代码"这个笑话)。要点如下:

| 规范化项 | 做法                                       | 注意                                        |
|----------|--------------------------------------------|---------------------------------------------|
| 命名中→英 | 选中函数右键"生成优化建议",AI 把函数名/参数名/变量名改成英文并补中文注释 | AI 建议非 100% 准确,需人工复核;若没主动改,可追加"请将函数名和变量名改为规范化的英文" |
| 封装成类 | 把散落函数收进类、抽象公共逻辑             | 结合业务边界,避免过度设计                   |
| 边界验证 | 补入参校验、异常处理、类型转换一致(AI 建议四类:类型转换不一致/异常处理缺失/代码可读性/性能考虑) | 用 AI 的四类建议当检查清单                   |
| 单元测试 | 选中函数右键让 AI 添加单元测试用例         | 覆盖正常/异常/边界分支                       |
| 设计模式 | 按需应用工厂、策略、观察者等模式           | 以可维护、可测试为准,别为模式而模式         |

一句话串起来:**从交互和业务两个层面把检索变精确**,**借用框架但不依赖、去读它源码吸收优秀设计**,**最后用 AI 助手把代码规范化成工程级产物**——评估闭环("体检→改")因此落到真正的生产质量。

- [Retrieval Augmented Generation Evaluation in the Era of LLMs: A Comprehensive Survey](https://arxiv.org/abs/2504.14891)
- [RAGAS 官方文档](https://docs.ragas.io)
