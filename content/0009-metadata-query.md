# 元数据过滤与查询增强:把"检索什么"变精确

> **Outcome:** 学完你能说清元数据为什么能让检索又快又准,分清四类元数据,掌握访问权限过滤的工程做法,理解"查询重写"与"查询扩展"两种查询增强手段的差异,并指出 WeKnora 源码里元数据过滤(`SearchTarget` 的 TagIDs/ScopeTagIDs/KnowledgeIDs)、LLM 查询重写(`PluginQueryUnderstand`)、本地查询扩展(`expandQueries`)各段的落点。

## Why this matters

前几课都在优化"在同一池子数据里怎么捞得准",这一课换一个角度:先**缩小池子**。如果整个知识库有 100 万条,用户问"前天的 CNET 新闻有哪些?",在全部数据里做语义检索既慢又可能召回日期不对的新闻;如果能先按"发布日期"这个元数据把范围缩到"前天",再在里面检索,又快又准。缩小池子的另一面是**摘要与翻译**两大利器:摘要让长文档先浓缩再入库,翻译解决跨语言检索。而让"用户的一句话"变成"适合检索的查询"是另一组能力——**Advanced RAG 检索前优化**就包含查询重写与扩展。这一课把"元数据过滤(缩小范围)"和"查询增强(改写问题)"两个维度合并。

## Core idea

### 一、元数据:数据的定语

元数据常被定义为"数据的数据",即描述其他数据的属性、特征、上下文的信息,一般分四类:

|          |                                            |                                        |
|----------|--------------------------------------------|----------------------------------------|
| **类型** | **含义**                                   | **例子**                              |
| 描述性   | 描述内容本身                               | 标题、作者、发布日期                   |
| 结构性   | 描述组织结构                               | 章节、表格行列                         |
| 管理性   | 管理与维护信息                             | 版权、存储位置、**访问权限**           |
| 参考性   | 描述关系                                   | 链接、引用、分类                       |

关键洞察:**企业 RAG 里使用频率最高的是"访问权限"这条管理性元数据**——系统只检索当前用户有权限看的数据,机制和传统 MIS 系统一致,通常要自定义(而不是像新闻来自 RSS API 那样自动带出)。保存上,给表加一个"权限"字段(如 `readnews`)即可实现按权限过滤。

### 二、查询增强:提问前先"把问题修好"

Advanced RAG 检索前优化的核心是**让用户粗糙的原问题变成适合检索的查询**。WeKnora 里做了两层,一层用 LLM(重写)、一层纯本地(扩展):

**查询重写(LLM,`query_understand.go`)**:`PluginQueryUnderstand.OnEvent`(响应 `QUERY_UNDERSTAND` 事件)用会话历史 + LLM 做意图分类和查询改写,输出 `queryUnderstandOutput`(含 `RewriteQuery`、`Intent`)。改写 prompt 可配置(`RewritePromptUser` / `RewritePromptSystem`)。多模态场景还会对图片做描述(`ImageDescription`)。重写解决"多轮对话指代不清"——用户上句说"A 公司",这句只说"他们的政策",需要结合历史猜出"他们=A 公司"。

**查询扩展(本地无 LLM,`query_expansion.go`)**:`runQueryExpansion` 在初次召回不足(`recall_low`)时触发,`expandQueries` 用纯规则生成查询变体,再对这些变体做**并发多路检索**(信号量上限 16,跨 query×search-target 扇出):去掉停用词(`extractKeywords`)、抽取引号短语(`extractPhrases`)、按分隔符切段取最长(`splitByDelimiters`)、去掉疑问词(什么/如何/怎么…`removeQuestionWords`)、中文用 jieba 分词(`tokenize` 里 `types.Jieba.CutForSearch`),最多 5 个变体。这层零成本,专攻关键词召回,正补上"复杂问题需要跨文档、带约束的检索"的缺口。

### 三、WeKnora 怎么把元数据变成检索约束

WeKnora 的元数据过滤通过 `SearchTarget`(见 `internal/types/chat_manage.go`)表达,核心三个字段:

- `TagIDs` / `ScopeTagIDs`:按标签(分类)过滤,Scope 表示约束范围;
- `KnowledgeIDs`:按具体文档过滤(partial KB 搜索);
- `KnowledgeBaseID`:限定知识库。

在 `chat_pipeline/search.go` 里,`SearchTarget` 被展开成 `SearchParams`(带着 `TagIDs`、`ScopeTagIDs`、`KnowledgeIDs`),再调用 `knowledgeBaseService.HybridSearch` 真正执行——过滤发生在检索 SQL 层面,而不是召回后再丢弃,所以能**减少计算量和噪声**。`query_expansion.go` 的扩展检索也复用同一套 `SearchParams`,同样带 `TagIDs` / `KnowledgeIDs` 约束,保证"扩展了查询但没越界知识库"。

用一句话串起来:**问题先进 `PluginQueryUnderstand` 被 LLM 改写成规范查询并确认元数据范围(`SearchTarget`),若召回不足再由 `expandQueries` 生成本地变体并发补召,所有检索都带着标签/文档/知识库的元数据约束执行。**

## Worked example

**案例一(日期元数据)**:用户问"前天 CNET 新闻有哪些?"。若没有元数据过滤,全库语义检索可能召回"任何时间的 CNET 新闻";按 `发布日期 = 前天` 过滤后,检索范围缩到一天,结果全对。WeKnora 里就是把"前天"这类约束映射进 `SearchTarget` 的过滤字段,而不是把"前天"当普通关键词去查内容。

**案例二(访问权限)**:员工 A 问"薪资政策",系统不能把所有薪资文档都喂给 LLM。权限元数据(如 `readnews` / `admin`)先行过滤:`SearchTarget` 只保留 A 有权限的文档,`HybridSearch` 在库层面就查不到无权内容——这正是 0001 课"数据安全"短板在企业落地的具体机制。

**案例三(查询扩展补召回)**:用户问"能退钱吗?流程是什么?"。初次混合检索召回不足,`runQueryExpansion` 触发,`removeQuestionWords` 去掉"能""吗"生成变体"退钱 流程",再并发补召;"退钱"命中"退款流程"文档。整个过程没调一次 LLM,零成本把遗漏捞回来。

## Retrieval practice

1. 闭卷题:四类元数据是什么?为什么"访问权限"在企业 RAG 里使用频率最高?查询重写与查询扩展的区别是什么?
2. 迁移题:你的知识库跨多个产品线(标签:手机、穿戴、家居),用户问"X200 的保修政策",还误带了上一轮的上下文。你会怎么设计"元数据过滤"和"查询重写"让它答准又不越界?

<details>
<summary>Check answers</summary>

1. 描述性(标题/作者/日期)、结构性(章节/行列)、管理性(版权/存储/访问权限)、参考性(链接/引用/分类)。访问权限最常用因为企业 RAG 必须只检索用户有权看的数据,且可复用 MIS 系统权限模块。查询重写(LLM)把原问题结合上下文改写成规范检索查询、消歧;查询扩展(可纯本地)生成查询变体扩大召回——一个管"问得更准",一个管"捞得更全"。
2. 元数据层:把用户权限 + "手机产品线"映射进 `SearchTarget` 的 `TagIDs` / `ScopeTagIDs`,`HybridSearch` 在库层面就排除无权限/无关产品线文档。查询重写层:`PluginQueryUnderstand` 结合上一轮上下文消歧(若上轮提到家电,本轮仍是"它"则需澄清或按标签约束到手机线),把"X200 的保修政策"改写成含产品型号的规范查询。扩展层:召回不足时用 `expandQueries` 生成"X200 保修"等变体,但变体检索仍带同样的 Tag/权限约束,保证不越界。

</details>

## Try it

打开 WeKnora 源码的 `internal/application/service/chat_pipeline/query_expansion.go`,数一数 `expandQueries` 里注明的 1–4 步生成了哪几类变体;再打开 `query_understand.go` 找 `RewritePromptUser` / `RewritePromptSystem` 怎么配。最后在 `search.go` 里看 `TagIDs` / `KnowledgeIDs` 怎么被塞进 `SearchParams` 传给 `HybridSearch`。

## Source


- WeKnora 源码:`internal/application/service/chat_pipeline/query_understand.go`(PluginQueryUnderstand)、`internal/application/service/chat_pipeline/query_expansion.go`(expandQueries / runQueryExpansion)、`internal/application/service/chat_pipeline/search.go`(SearchParams)、`internal/types/chat_manage.go`(SearchTarget 的 TagIDs/ScopeTagIDs/KnowledgeIDs)

## 摘要与翻译:RAG 两大利器

在元数据检索之后,还有 RAG 里另两个"基本操作"——**文本摘要**与**机器翻译**。它们一个解决"内容太多看不完、全量检索太慢",一个解决"语言不通检索不到",都能显著提升体验与效果。

### 一、为什么需要摘要:提用户体验 + 提检索效率

|         |                                  |                                     |
|---------|----------------------------------|-------------------------------------|
| **作用** | **机理**                         | **代价/边界**                       |
| 提升用户体验 | 摘要很短,用户先扫一眼有没有感兴趣内容,有则点开详情,无则跳过,省阅读时间 | 摘要若只覆盖关键内容、漏了次要部分,用户要找的知识恰好漏掉时系统答不了 |
| 提高检索效率 | 类比书的前言/目录:先在摘要里检索确认"有没有",有再返回详情,没有就跳过,避免全量反复扫 | 摘要检索有盲区,不能单独用,要和其它检索方法配合 |

摘要这种"先看摘要确定有没有、再进详情"的浏览路径,是最典型的用户体验优化手段(CNET 新闻简报就是靠它让用户快速判断"这条要不要看")。

### 二、摘要怎么实现:一条提示词,长文本先拆后合

**短文本摘要**只需一条提示词让 LLM 干活:

```python
构造文本摘要messages(输入字符串):
    {"role": "user", "content": f"请对以下文本进行摘要:\n\n{输入字符串}"}
```

**长文本摘要**因为大模型有输入长度上限,要"按长度分段 → 逐段摘要 → 把各段摘要拼接":

```python
def 对长文本进行摘要(输入文本):
    if len(输入文本) > 文本划分长度:
        文本list = 按长度划分文本(输入文本, 文本划分长度)
        文本摘要结果 = ''
        for 当前文本 in 文本list:
            当前文本摘要结果 = 文本摘要(当前文本)
            文本摘要结果 += 当前文本摘要结果 + '\n'
        return 文本摘要结果
    else:
        return 文本摘要(输入文本)
```

同时也要注意:粗糙的按长度切分可能把一句砍成两段病句。要不要精细化(按换行符/语义分段)取决于**业务对准确率的要求**和**投入资源是否划算**——案例只图"快速判断是否感兴趣",用最简办法就已达标。

### 三、翻译:跨语言检索的三类场景

只要"用户提问"和"入库知识"存在语言差,RAG 就需要机器翻译,归纳起来有三种情况:

|         |                                |                               |                                |
|---------|--------------------------------|-------------------------------|--------------------------------|
| **场景** | **例子**                       | **要翻译谁**                  | **处理位置**                   |
| 提问与入库不同语言 | 案例 2:CNET 新闻是英文,用户提问是中文 | 翻译入库知识(英→中)          | 入库前/检索时对知识翻译        |
| 入库知识多种语言 | 扩展新闻源到日文、中文 IT 新闻 | 把各语种知识统一成目标语言     | 入库前统一翻译后切块入库       |
| 用户多语言提问 | 旧金山多语种官方、旅游场景    | 先翻用户提问,再翻系统回答     | 检索前翻提问,生成后翻回答      |

实现仍是一条提示词(`构造英译中messages`:"请将以下文本翻译成中文")调 LLM;**长文本翻译**同样用"分段→逐段翻译→合并",与摘要同构。

### 四、WeKnora 对照:未内置,扩展方向

在 WeKnora 源码里 grep `summary` / `translate` 后确认:**WeKnora 未内置"文档入库前摘要"与"跨语言翻译"这两项能力**。搜到的 `summary` 类代码(`internal/application/service/chat_pipeline/rerank.go` 里的 `SummaryPassagePreviews`、`tracing/langfuse/retrieval_obs.go` 里的 `summarizeIndexHits`)都是**追踪/日志展示用的截断摘要**,不是生成式文档摘要;`translate` 命中的也只是错误信息 sentinel 的转换(`knowledgebase.go` 的 "translate retriever sentinels"),与跨语言无关。

因此这是 WeKnora 的**扩展方向**:

|         |                        |                                        |
|---------|------------------------|----------------------------------------|
| **能力** | **放在哪个环节**       | **扩展思路**                           |
| 文档摘要 | 入库前:对每个切块用 LLM 生成摘要写入元数据,检索时对摘要做混合检索,呼应本课 TagIDs/元数据过滤思路,也能让结果携带"摘要预览" | 扩展 chunking/ingest 管线,或检索后在 topK 候选上动态生成摘要给用户预览 |
| 跨语言翻译 | 入库前统一多语言知识→目标语言后再切块入向量库;或多语言用户场景翻译提问与回答 | 用课中"分段→翻译→合并"处理长文本,接入现有 `PluginQueryUnderstand` 查询改写或生成环节 |

一句话:**摘要与翻译都可以落在"入库前"或"检索后"两个节点,WeKnora 本身没做,但结构上(元数据、查询改写、生成管线)都给你留好了接缝**。

- [A Surprisingly Simple yet Effective Multi-Query Rewriting Method](https://arxiv.org/abs/2406.18960)
