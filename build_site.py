#!/usr/bin/env python3
"""Build the WeKnora RAG course as a standalone local documentation site."""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONTENT = ROOT / "content"
OUTPUT = ROOT / "_site"
REPOSITORY_URL = "https://github.com/9Ashwin/weknora-rag-course"

DOCS = [
    ("00-course-map.md", "课程地图", "四阶段学习路径:地基 → 流水线 → 进阶 → 系统深挖。", "导读"),
    ("20-rag-papers.md", "论文与资料", "经典论文 + 2026 最新 + 权威机构实践 + 面试用法。", "导读"),
    ("0001-rag-overview.md", "01 RAG 全景与选型", "四大短板、流水线七环节、按失败模式爬梯子。", "阶段一 地基"),
    ("0002-retrieval-theory-metrics.md", "02 检索理论与排序", "倒排索引、TF-IDF→BM25、TopK、NDCG/MRR/MAP、MMR。", "阶段一 地基"),
    ("0003-doc-parsing.md", "03 文档解析", "docparser 七引擎、MinerU/PaddleOCR-VL、SSRF 防护。", "阶段二 流水线"),
    ("0004-chunking-embedding.md", "04 切分与嵌入", "块的设计决定检索精度,六策略、批量嵌入池。", "阶段二 流水线"),
    ("0005-vector-db.md", "05 向量数据库", "四类向量库选型、pgvector HNSW、距离衡量。", "阶段二 流水线"),
    ("0006-hybrid-retrieval.md", "06 混合检索", "关键词(ParadeDB) + 向量(pgvector) 双路互补。", "阶段二 流水线"),
    ("0007-rerank-fusion.md", "07 融合与重排", "RRF 融合、跨编码器重排、MMR 去冗余。", "阶段二 流水线"),
    ("0008-generation-citation.md", "08 生成与引用溯源", "ReAct 编排、引用句柄、答案可核查。", "阶段二 流水线"),
    ("0009-metadata-query.md", "09 元数据与查询增强", "元数据过滤缩范围、LLM 查询重写与扩展。", "阶段二 流水线"),
    ("0010-evaluation.md", "10 评估与优化", "指标体检、评测闭环、改进原则。", "阶段二 流水线"),
    ("0011-advanced-modular.md", "11 Advanced 与 Modular", "检索前中后逐段优化、模块化编排、CRAG/Self-RAG。", "阶段三 进阶"),
    ("0012-graphrag.md", "12 GraphRAG", "知识图谱增强检索、跨文档综合、适用边界。", "阶段三 进阶"),
    ("0013-agentic-migrate.md", "13 Agentic RAG", "多智能体编排、ReAct 工具注册表、迁移落地。", "阶段三 进阶"),
    ("0014-weknora-architecture.md", "14 系统架构总览", "容器/依赖注入、路由、七引擎注册。", "阶段四 系统实现"),
    ("0015-agent-engine.md", "15 Agent 引擎", "ReAct 循环、工具调用、审批、结束判定。", "阶段四 系统实现"),
    ("0016-chat-pipeline.md", "16 Chat Pipeline", "检索→融合→生成全流程、merge 家族。", "阶段四 系统实现"),
    ("0017-memory-system.md", "17 Memory 长时记忆", "提取/巩固/搜索/作用域。", "阶段四 系统实现"),
    ("0018-full-system-review.md", "18 全系统串讲", "十八课一张图,面试话术。", "阶段四 系统实现"),
]



def page_name(filename: str) -> str:
    return f"{Path(filename).stem}.html"


def plain_text(source: str) -> str:
    text = re.sub(r"```.*?```", " ", source, flags=re.DOTALL)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    text = re.sub(r"!?(?:\[([^\]]*)\])\([^)]+\)", r"\1", text)
    text = re.sub(r"[#>*_|~-]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def reading_minutes(source: str) -> int:
    compact = re.sub(r"\s+", "", plain_text(source))
    return max(1, round(len(compact) / 550))


def last_updated(filename: str) -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--format=%cs", "--", f"content/{filename}"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() or date.today().isoformat()


def render_markdown(source: str) -> tuple[str, list[tuple[int, str, str]]]:
    source = re.sub(r"^#\s+.*?\n", "", source, count=1)
    source = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\.md(#[^)]+)?\)",
        lambda match: f"[{match.group(1)}]({page_name(match.group(2) + '.md')}{match.group(3) or ''})",
        source,
    )
    body = subprocess.run(
        ["pandoc", "--from", "gfm", "--to", "html5", "--wrap=none"],
        input=source,
        text=True,
        capture_output=True,
        check=True,
    ).stdout
    headings: list[tuple[int, str, str]] = []
    for level, attrs, label in re.findall(r"<h([23])([^>]*)>(.*?)</h\1>", body, re.DOTALL):
        id_match = re.search(r'id="([^"]+)"', attrs)
        if id_match:
            headings.append((int(level), id_match.group(1), re.sub(r"<[^>]+>", "", label)))
    return body, headings


def chapter_nav(active: str) -> str:
    groups = [("导读", "开始这里"), ("阶段一 地基", "懂原理"), ("阶段二 流水线", "会写 RAG"), ("阶段三 进阶", "懂现代形态"), ("阶段四 系统实现", "吃透源码")]
    sections = []
    for key, label in groups:
        links = []
        for filename, title, _, group in DOCS:
            if group != key:
                continue
            current = " is-current" if filename == active else ""
            links.append(f'<a class="chapter-link{current}" href="{page_name(filename)}">{html.escape(title)}</a>')
        sections.append(f'<section><div class="nav-label">{label}</div>{"".join(links)}</section>')
    return "".join(sections)


def toc_nav(headings: list[tuple[int, str, str]]) -> str:
    return "".join(
        f'<a class="toc-level-{level}" href="#{anchor}">{html.escape(label)}</a>'
        for level, anchor, label in headings
    )


def shell(title: str, body: str, *, page_class: str, description: str = "") -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{html.escape(description)}">
  <title>{html.escape(title)} · WeKnora RAG 课程</title>
  <script>document.documentElement.dataset.theme=localStorage.getItem('weknora-theme')||'light'</script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400&family=Noto+Serif+SC:wght@500;600;700&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="assets/style.css">
</head>
<body class="{page_class}">
<div class="site-tools" aria-label="站点工具">
  <button class="tool-button search-button" type="button" aria-label="搜索文档"><span>⌕</span><small>搜索</small></button>
  <button class="tool-button theme-button" type="button" aria-label="切换深色模式"><span aria-hidden="true">◐</span><small>主题</small></button>
</div>
{body}
<dialog class="search-dialog" aria-labelledby="search-title">
  <form method="dialog" class="search-panel">
    <header><div><span>SEARCH</span><h2 id="search-title">搜索课程</h2></div><button class="search-close" value="close" aria-label="关闭搜索">×</button></header>
    <label class="search-field"><span aria-hidden="true">⌕</span><input type="search" placeholder="输入检索、Agent、源码关键词…" autocomplete="off"></label>
    <div class="search-status">输入关键词，搜索全部 18 篇课程</div>
    <div class="search-results"></div>
    <footer><span><kbd>↑</kbd><kbd>↓</kbd> 选择</span><span><kbd>Enter</kbd> 打开</span><span><kbd>Esc</kbd> 关闭</span></footer>
  </form>
</dialog>
<script src="assets/site.js"></script>
</body>
</html>
"""


def build_home() -> None:
    groups = [("导读", "开始这里"), ("阶段一 地基", "懂原理"), ("阶段二 流水线", "会写 RAG"), ("阶段三 进阶", "懂现代形态"), ("阶段四 系统实现", "吃透源码")]
    sections = []
    for group, subtitle in groups:
        cards = []
        for filename, title, description, item_group in DOCS:
            if item_group != group:
                continue
            import re as _re
            _m = _re.match(r"(\d+)", Path(filename).stem)
            number = _m.group(1).lstrip("0") if _m else Path(filename).stem.split("-", 1)[0]
            cards.append(
                f'<a class="chapter-card chapter-card--flat" href="{page_name(filename)}">'
                f'<span class="chapter-copy">'
                f'<strong>{html.escape(title)}</strong><small>{html.escape(description)}</small></span>'
                '<span class="chapter-arrow" aria-hidden="true">→</span></a>'
            )
        sections.append(
            f'<section class="volume"><header><span>{group}</span><h2>{subtitle}</h2></header>{"".join(cards)}</section>'
        )
    body = f"""
<header class="hero">
  <div class="hero-art" aria-hidden="true"><span></span><span></span><span></span></div>
  <div class="hero-content">
    <div class="hero-badge">RAG 源码课程 · 18 课</div>
    <h1>WeKnora RAG<br><em>从源码系统学 RAG</em></h1>
    <p class="hero-subtitle">从腾讯开源 WeKnora 源码出发，逐环节拆解 RAG 流水线<br>与完整系统实现</p>
    <blockquote class="hero-quote">
      <p>RAG 的本质：不是把所有知识塞给模型，而是给它此刻最需要的几块。</p>
      <cite>you can outsource your thinking, but you cannot outsource your understanding</cite>
    </blockquote>
    <p class="hero-meta">18 课 · 四阶段学习路径 · 源码逐环节拆解</p>
    <a class="hero-cta" href="{page_name('00-course-map.md')}">开始阅读 <span>→</span></a>
  </div>
  <a class="scroll-hint" href="#contents"><span>目录</span><i></i></a>
</header>
<main id="contents" class="contents">
  <header class="contents-heading"><span>Contents</span><h2><span>从原理到源码</span><br><span>四阶段学透 RAG</span></h2><p>地基(懂原理)→ 流水线(会写 RAG)→ 进阶(懂现代形态)→ 系统深挖(吃透源码)。</p></header>
  {''.join(sections)}
</main>
<footer class="site-footer"><span>WeKnora RAG 课程</span><span>由本地 Markdown 构建</span></footer>
"""
    (OUTPUT / "index.html").write_text(shell("首页", body, page_class="home", description="从腾讯开源 WeKnora 源码系统学习 RAG 开发"), encoding="utf-8")


def build_articles() -> None:
    for index, (filename, title, description, group) in enumerate(DOCS):
        source = (CONTENT / filename).read_text(encoding="utf-8")
        article, headings = render_markdown(source)
        minutes = reading_minutes(source)
        updated = last_updated(filename)
        previous = DOCS[index - 1] if index else None
        following = DOCS[index + 1] if index + 1 < len(DOCS) else None
        prev_link = (
            f'<a class="pager-prev" href="{page_name(previous[0])}"><span>上一篇</span>{html.escape(previous[1])}</a>'
            if previous else "<span></span>"
        )
        next_link = (
            f'<a class="pager-next" href="{page_name(following[0])}"><span>下一篇</span>{html.escape(following[1])}</a>'
            if following else '<a class="pager-next" href="index.html"><span>阅读完成</span>返回目录</a>'
        )
        import re as _re
        _m = _re.match(r"(\d+)", Path(filename).stem)
        number = _m.group(1).lstrip("0") if _m else Path(filename).stem.split("-", 1)[0]
        body = f"""
<button class="mobile-menu" aria-label="打开章节导航" aria-expanded="false">目录</button>
<div class="reading-progress" aria-hidden="true"></div>
<div class="page-layout">
  <aside class="chapter-sidebar">
    <a class="brand" href="index.html"><span class="brand-mark">W</span><span>WeKnora RAG<small>源码课程</small></span></a>
    <nav class="chapter-nav">{chapter_nav(filename)}</nav>
  </aside>
  <main class="article-main">
    <article class="article">
      <header class="article-header"><div class="eyebrow">{group} · Chapter {number}</div><h1>{html.escape(title)}</h1><p>{html.escape(description)}</p><div class="article-meta"><span>约 {minutes} 分钟阅读</span><span>更新于 {updated}</span><a href="{REPOSITORY_URL}/edit/main/content/{filename}" target="_blank" rel="noreferrer">在 GitHub 编辑 ↗</a></div></header>
      <div class="article-body">{article}</div>
      <nav class="pager">{prev_link}{next_link}</nav>
    </article>
  </main>
  <aside class="toc-sidebar"><div class="toc-title">本页目录</div><nav>{toc_nav(headings)}</nav><a class="back-home" href="index.html">← 返回全书目录</a></aside>
</div>
"""
        output = shell(title, body, page_class="article-page", description=description)
        (OUTPUT / page_name(filename)).write_text(output, encoding="utf-8")


def build() -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)
    (OUTPUT / "assets").mkdir(parents=True)
    shutil.copy2(ROOT / "site_assets" / "style.css", OUTPUT / "assets" / "style.css")
    shutil.copy2(ROOT / "site_assets" / "site.js", OUTPUT / "assets" / "site.js")
    build_home()
    build_articles()
    search_index = []
    for filename, title, description, group in DOCS:
        source = (CONTENT / filename).read_text(encoding="utf-8")
        search_index.append(
            {
                "title": title,
                "description": description,
                "group": group,
                "url": page_name(filename),
                "content": plain_text(source),
            }
        )
    (OUTPUT / "assets" / "search.json").write_text(
        json.dumps(search_index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    print(f"Built {len(DOCS) + 1} pages in {OUTPUT}")


if __name__ == "__main__":
    build()
