# WeKnora RAG 课程:从源码系统学 RAG

一套从腾讯开源项目 [WeKnora](https://github.com/Tencent/WeKnora)(19.8k★)源码出发的 RAG 系统学习课程。18 课,四阶段递进,从原理到源码逐环节拆解,每课都带闭卷检索练习和源码阅读指引。

**在线课程**:https://9ashwin.github.io/weknora-rag-course/

## 课程结构

| 阶段 | 目标 | 课程 |
|---|---|---|
| 阶段一 · 地基 | 懂原理 | 01 RAG 全景与选型 / 02 检索理论与排序(倒排索引、TF-IDF→BM25、TopK、NDCG/MRR/MAP、MMR) |
| 阶段二 · 流水线 | 会写 RAG | 03 文档解析 → 04 切分与嵌入 → 05 向量数据库 → 06 混合检索 → 07 融合与重排 → 08 生成与引用溯源 → 09 元数据与查询增强 → 10 评估与优化 |
| 阶段三 · 进阶 | 懂现代形态 | 11 Advanced 与 Modular RAG / 12 GraphRAG / 13 Agentic RAG |
| 阶段四 · 系统实现 | 吃透源码 | 14 系统架构 → 15 Agent 引擎 → 16 Chat Pipeline → 17 Memory → 18 全系统串讲 |

另附:课程地图(学习路径) + 论文与资料清单(经典论文 + 2026 最新 + 权威机构实践)。

## 为什么用源码学 RAG

- **真实生产实现**:WeKnora 是微信对话开放平台的核心 RAG 引擎,不是 toy demo
- **可插拔架构**:七种检索引擎注册、混合检索(ParadeDB + pgvector)、RRF 融合、MMR 去重、引用溯源、Agent 编排——现代 RAG 该有的都有
- **理论与实践对照**:每课先把概念讲透,再指到真实源码文件/函数,最后给闭卷检索题检验

## 本地预览

需要 Python 3 和 Pandoc:

```bash
python3 build_site.py
python3 -m http.server 4173 --directory _site
```

打开 <http://127.0.0.1:4173/>。

## 目录结构

```text
content/       Markdown 源文档(18 课 + 课程地图 + 论文清单)
site_assets/   网站样式与交互
build_site.py  静态站点生成器
_site/         构建产物
```

推送到 `main` 后,GitHub Actions 自动构建并部署 GitHub Pages。

## 参考

- WeKnora 官方仓库:https://github.com/Tencent/WeKnora
- 论文与资料清单(站内 20-rag-papers):经典 RAG 论文、2026 最新论文、Anthropic/Microsoft/Pinecone/RAGAS 等权威实践

## License

MIT
