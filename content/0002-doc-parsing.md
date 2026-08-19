# 文档解析:原始文档怎么变成可检索的结构化文本

> **Outcome:** 学完你能说清文档解析的本质(Quality in, Quality out)、LangChain 文档加载器的分工,画出一张 WeKnora 七解析引擎的注册表,并指出 MinerU / PaddleOCR-VL 分别在处理哪一类文档、SSRF 防护挂在哪一层。

## Why this matters

RAG 的第一环就是吃进原始文档。反复强调一句:**"Quality in, Quality out"**——解析阶段丢了的信息,后面的切分、嵌入、检索再怎么优化也找不回来。企业知识库里绝大多数数据是 PDF、Word、PPT、Excel,尤其 PDF 又分"电子档"和"扫描档":电子档要还原版面与阅读顺序,扫描档本质上是一张张图片,必须先 OCR 才能进文本世界。这一环没处理好,后面全是"在垃圾上做检索"。WeKnora 把这一环做成了**七引擎可插拔注册表**——从 Go 原生解析到 MinerU / PaddleOCR-VL / 云端 OCR 全部可选,并且把网络解析的 SSRF 风险挡在了最前面。

## Core idea

### 一、文档解析的本质

文档解析的本质,是把**格式各异、版式多样、元素多种**的文档(段落、表格、标题、公式、多列、图片),转化为**阅读顺序正确的字符串信息**。输出错了顺序、丢了表格列,向量检索召回的就是"残次品文本"。

LangChain 用两件套解决"格式多"的问题:

- **BaseLoader 类**:定义"如何从某个数据源加载文档"。
- **Document 类**:统一描述不同类型文档的元数据(来源、页码等)。

`langchain_community` 基于 BaseLoader 扩展了 **160+ 种加载器**,覆盖本地文件、云端文件、数据库、Web 服务。PyPDF 加载器把多页 PDF 拆成独立单元并附带页码元数据。核心规律:**加载器 = 解析库的可复用封装**。

### 二、分格式差异:不是所有文件都值得上重型引擎

| **格式** | **处理难度** | **典型引擎** |
|----------|-------------|-------------|
| md / txt / csv / json | 极低,Go/Python 原生搞定 | simple(Go 原生,无外部依赖) |
| docx / xlsx / html / mhtml | 中,版面结构清晰 | builtin(DocReader) |
| PDF 电子档 | 高,需还原版面与阅读顺序 | MinerU / DocReader |
| PDF 扫描件、图片 | 最高,本质是 OCR | MinerU / PaddleOCR-VL |

WeKnora 源码里的 `internal/infrastructure/docparser/engine_registry.go` 说明了这个分档思想:engine 分为**本地注册引擎**与**远程引擎**两类,`EngineRegistration` 接口统一暴露 `Name / Description / FileTypes / CheckAvailable`。本地的 `FileTypes` 直接列它能吃什么格式,`CheckAvailable` 则决定它现在能不能用(比如 MinerU 要配好 endpoint 才 available)。

### 三、WeKnora 七引擎注册表:一份残缺却是真实的排兵布阵

`engine_registry.go` 的 `init()` 里注册了七个引擎(亲自去 WeKnora 源码 数一下,是七个):

```go
func init() {
    RegisterEngine(&builtinEngine{})         // DocReader,处理 docx/pdf/xlsx/html 等复杂格式
    RegisterEngine(&simpleEngine{})          // Go 原生处理 md/txt/csv/json,永远可用
    RegisterEngine(&weKnoraCloudEngine{})    // 腾讯云端 docreader,需 AppID 凭据
    RegisterEngine(&mineruEngine{})          // 自托管 MinerU,读本机/私有 HTTP 服务
    RegisterEngine(&mineruCloudEngine{})     // MinerU 云端 API
    RegisterEngine(&paddleOCRVLEngine{})     // 自托管 PaddleOCR-VL
    RegisterEngine(&paddleOCRVLCloudEngine{})// PaddleOCR-VL 云端
}
```

关键设计:**同一个格式可以多引擎可选**。PDF 既能被 builtin(DocReader) 解析,也能被 MinerU、PaddleOCR-VL 解析——引擎之间是"按可用性与配置择优",而不是写死一家的死代码。`simple` 引擎永远返回可用(`CheckAvailable` 恒 true),因为它没有外部依赖,md/txt 这种轻格式永远有兜底。

### 四、PDF / 扫描件:为什么 OCR 是单独一类

企业里 PDF 占数据的大头,而 2026 年的生产标准是:**电子档走版面解析,扫描档走 OCR**。

- **MinerU**(`mineru_converter.go` / `mineru_cloud_converter.go`):擅长 PDF 的版面还原、双栏、表格、公式识别,输出接近"阅读顺序正确"的 Markdown。
- **PaddleOCR-VL**(`paddleocr_vl_converter.go` / `paddleocr_vl_cloud_converter.go`):针对扫描件与图片的 OCR-VL(视觉语言模型),把图里的文字认出来再转文本。

二者都支持**自托管 + 云端**两种形态,这正是"能私有化就别上云"的企业数据安全诉求。

### 五、SSRF 防护:解析远程 URL 的安全红线

当解析器要**主动去拉取远程文档/图片 URL**时,最大的安全漏洞是 SSRF(服务器请求伪造):攻击者可以诱导服务去访问内网 `127.0.0.1`、云元数据接口(`169.254.169.254`)。WeKnora 在这一层做得很硬:

```go
// internal/infrastructure/docparser/mineru_converter.go
client:= utils.NewSSRFSafeHTTPClient(utils.SSRFSafeHTTPClientConfig{...})
if err:= utils.ValidateURLForSSRF(rawURL); err != nil {
    return fmt.Errorf("MinerU URL blocked by SSRF check: %v", err)
}
```

`mineru_converter_ssrf_test.go` 里就有针对性测试:`PingMinerU("http://127.0.0.1:8080")` 必须返回 false 且报错含 "SSRF"。**解析环节能点外部 URL,所以解析环节必须做 URL 校验**——这是安全兜底,不是可选项。

## 从 0 到 1 搭建 RAG:完整选型

从 0 到 1 搭建这一讲是本系列**唯一给出完整可运行代码**的章节:用一整套热门开源库,把"解析 → 分块 → 嵌入 → 存储 → 检索 → 生成"六步串成了一个完整 RAG 应用。看清这套选型,再用 WeKnora 对照,就能理解"手写 RAG 流水线"与"企业级 RAG 产品"在每一环上是怎么分道扬镳的。

### 完整技术栈选型表

| 环节 | 选型 | 一句话说明(为什么选它) | 替代方案 |
|------|-----------|----------------------|---------|
| 框架 | **LangChain** | 专为 LLM 应用设计的全覆盖框架,Loader/Splitter/VectorStore 随手即用,把"搭 RAG"从搭积木变成写配置 | LlamaIndex、RAGFlow、自研流水线 |
| 解析 | **pypdf**(经 PyPDFLoader 封装) | 轻量纯 Python 的 PDF 文本提取,`extract_images=False` 只取文字,零依赖上手快 | PyMuPDF、Unstructured、MinerU(版面还原更强) |
| 分块 | **RecursiveCharacterTextSplitter** | LangChain 默认分割器,按"双换行→单换行→标点→字符"的**层次化分隔符**切,尽量保住段落/句子等自然边界;课里 chunk_size=512、overlap=128(按字符非 token) | CharacterTextSplitter(简单固定长度)、按语义/表格切分 |
| 嵌入 | **bge-small-zh-v1.5**(智源 BAAI) | 中文小模型,向量维度 512、最大输入 512,token,体积小(约 95.8M)却对中文检索精度高,`normalize_embeddings=True` 配合余弦检索 | bge-m3、text-embedding-v3、m3e、OpenAI embedding(维度更高更贵) |
| 向量库 | **Faiss**(faiss-cpu) | Facebook AI 开源的相似度搜索引擎,`IndexFlatIP`(内积=余弦)内存索引,稳定高效适合教学/单机 | Chroma、Milvus、pgvector、Weaviate(面向生产/分布式) |
| 生成 | **通义千问 Qwen**(dashscope API) | 阿里云超大规模 LLM,云端 API 开箱即用,注册含 100 万 token 免费额度 | 其它云 API、本地开源 LLM(Ollama/vLLM 自托管) |

### 选型 vs WeKnora 实现:逐环节对照

| 环节 | (手写 / LangChain) | WeKnora 对应组件 | 差异点(为什么 WeKnora 更"生产级") |
|------|------------------------------|-----------------|----------------------------------|
| 解析 | pypdf(PyPDFLoader)单引擎 | **docparser 七引擎注册表**(simple / builtin / MinerU / PaddleOCR-VL × 本地/云端) | 只能吃 PDF 文本;WeKnora 按格式择优、扫描件走 OCR-VL、远程解析带 SSRF 校验 |
| 分块 | RecursiveCharacterTextSplitter(512/128) | **chunker**(切分器,配置化) | 常数写死在代码里;WeKnora 把 chunk 大小/重叠做成可配置项,且可针对不同文档形态调整 |
| 嵌入 | 循环逐个 `embedding_model.encode()`,bge-small-zh-v1.5 | **embedding 批量池**(批量向量化后端) | 单条串行编码,慢;WeKnora 走批量池,可横向扩展、并发处理 |
| 向量库 | Faiss 纯内存 `IndexFlatIP` | **pgvector**(基于 PostgreSQL) | Faiss 内存索引重启即失、单机;pgvector 落库持久化、可查询可治理,契合企业数据资产管理 |
| 生成 | Qwen 云端 API + 手写 Prompt 模板 | **ReAct agent**(检索 + 工具调用 + 推理循环) | 是一次"检索→拼 Prompt→生成"单程;WeKnora 用 ReAct agent 让模型边思考边调用检索,多轮迭代、回答更可解释 |
| 环境 | Python venv + `pip install langchain... pypdf... faiss-cpu... dashscope` | 服务化部署 + 配置中心 | 依赖版本靠手装,易漂移;WeKnora 面向容器化/可运维 |

**对照结论**:上手方案的价值是用最少依赖把 RAG 五段式流程跑通、让人理解每一环在干什么;WeKnora 则是把同一套流程"产品化、服务化、安全化"——解析从单引擎变多引擎择优,向量库从内存变持久化数据库,生成从单程拼 Prompt 变 ReAct 智能体。**选型对每环都有替代方案,没有银弹;理解"为什么这样选"比记住某个库名更重要。**

## Worked example

**案例(一次"从扫描 PDF 到可检索文本"的完整路由)**:公司有一批老合同,是扫描版 PDF(本质是图片)。

1. `simple` 引擎吃不下扫描 PDF → 被过滤掉;
2. 系统发现 `mineru_endpoint` 已配置,且文档含扫描页 → 命中 **MinerU** 引擎;
3. MinerU 去拉文档时,URL 先过 `ValidateURLForSSRF`,若有人把文档地址换成本地路径 `file://` 或 `127.0.0.1`,直接被拒;
4. MinerU 输出阅读顺序正确的 Markdown + 表格 → 进入下一环:切分。

对比:如果这批合同只是纯文本 `txt`,连 MinerU 都不用起,`simple` 引擎零依赖在本地就切好了——**不是越重的引擎越好,是按格式选最合适的兜底**。这正是 WeKnora 用七引擎注册表而不是写死一个解析器的原因。

## Retrieval practice

1. 闭卷题:为什么说"Quality in, Quality out"?电子档 PDF 和扫描版 PDF 在解析环节的差别在哪?
2. 迁移题:你的知识库要接入一份带大量表格的年度财报 PDF 和一批合同扫描件,分别该选 WeKnora 的哪类引擎?如果这些文档都来自用户上传的外部 URL,还要补什么安全检查?

<details>
<summary>Check answers</summary>

1. 解析阶段丢的信息不可逆,后面的检索全是在残次品文本上工作,所以"高质量解析"决定 RAG 最终效果(Quality in, Quality out)。电子档 PDF 靠版面解析(还原段落/表格/标题/阅读顺序),扫描版 PDF 本质是图片,必须靠 OCR(MinerU / PaddleOCR-VL)先把图转成文本,再走解析。
2. 财报 PDF(带表格)选 MinerU 或 builtin(DocReader),因为它版面结构复杂、要还原表格与阅读顺序;合同扫描件选 PaddleOCR-VL 或 MinerU 的 OCR/扫描支持。外部 URL 一律先过 SSRF 校验(`ValidateURLForSSRF`),拒绝 loopback(127.0.0.1)与云元数据地址,避免服务被用来探测内网。

</details>

## Try it

打开 WeKnora 源码的 `internal/infrastructure/docparser/engine_registry.go`,数一数 `init()` 里注册了几个引擎,再看每个引擎的 `FileTypes()` 声明了哪些格式。然后打开 `mineru_converter_ssrf_test.go`,跑一遍 SSRF 用例,确认 `127.0.0.1` 被拒绝。

## Source

- WeKnora 源码的 `internal/infrastructure/docparser/`:`engine_registry.go`(七引擎注册)、`mineru_converter.go`(SSRF 校验 + MinerU)、`paddleocr_vl_converter.go`(OCR-VL)、`mineru_converter_ssrf_test.go`(SSRF 单测)
- 安全基线参考:SSRF Prevention Cheat Sheet(OWASP)

- [WeKnora docparser 源码](https://github.com/Tencent/WeKnora/tree/main/internal/infrastructure/docparser)
- [OWASP SSRF Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Server_Side_Request_Forgery_Prevention_Cheat_Sheet.html)
- [MinerU 文档解析工具](https://github.com/opendatalab/MinerU)
