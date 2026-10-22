#!/usr/bin/env python3
"""Export Markdown paper notes to a pleasant single-file HTML reader.

Install one Markdown parser if needed: pip install mistune>=3
MathJax CDN is used for math typesetting when internet is available.
"""
from __future__ import annotations

import argparse
from html import escape, unescape
from pathlib import Path
import re
import sys


def strip_frontmatter(markdown: str) -> tuple[str, dict[str, str]]:
    match = re.match(r"\A---\s*\n(.*?)\n---\s*\n", markdown, flags=re.S)
    if not match:
        return markdown, {}
    header: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep:
            header[key.strip()] = value.strip().strip('"').strip("'")
    return markdown[match.end():], header


def protected_math(text: str) -> tuple[str, dict[str, str]]:
    """Protect TeX delimiters from Markdown escape interpretation.

    Deliberately does not parse $inline$ since dollars are used for currency too.
    Prefer \\( ... \\) or \\[ ... \\] in authored notes.
    """
    store: dict[str, str] = {}
    pattern = re.compile(r"(?s)(?<!\\)(\\\[(?:.|\n)*?\\\]|\\\((?:.|\n)*?\\\)|\$\$(?:.|\n)*?\$\$)")
    def sub(m: re.Match[str]) -> str:
        key = f"PAPER_MATH_{len(store):05d}_PLACEHOLDER"
        store[key] = escape(m.group(0))
        return key
    return pattern.sub(sub, text), store


def md_to_html(markdown: str) -> str:
    try:
        import mistune
    except ImportError as e:
        raise RuntimeError("Please install mistune>=3: python -m pip install 'mistune>=3'") from e
    parse = mistune.create_markdown(escape=True, plugins=["table", "strikethrough", "url"])
    protected, math = protected_math(markdown)
    html = parse(protected)
    for key, expression in math.items():
        html = html.replace(key, expression)
    return html


def headings_with_toc(html: str) -> tuple[str, str]:
    counts: dict[str, int] = {}
    headings: list[str] = []
    def sub(m: re.Match[str]) -> str:
        level, body = int(m.group(1)), m.group(2)
        plain = unescape(re.sub(r"<[^>]+>", "", body)).strip()
        if not plain:
            plain = "section"
        base = re.sub(r"[^\w\u4e00-\u9fff-]+", "-", plain.lower()).strip("-_" ) or "section"
        counts[base] = counts.get(base, 0) + 1
        slug = base if counts[base] == 1 else f"{base}-{counts[base]}"
        headings.append(f'<a class="toc-h{level}" href="#{escape(slug, quote=True)}">{escape(plain)}</a>')
        return f'<h{level} id="{escape(slug, quote=True)}">{body}</h{level}>'
    html = re.sub(r"<h([1-4])>(.*?)</h\1>", sub, html, flags=re.S)
    return html, "\n".join(headings)


STYLE = """
:root{color-scheme:light dark;--bg:#fff;--fg:#192232;--muted:#657083;--line:#e5e8ed;--accent:#3068b4;--soft:#f5f7fa;--code:#eff3f9}
@media(prefers-color-scheme:dark){:root{--bg:#131820;--fg:#edf2fa;--muted:#a8b5ca;--line:#394253;--accent:#93bdff;--soft:#1c2330;--code:#202939}}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.8 system-ui,-apple-system,"Segoe UI","Noto Sans SC",sans-serif}
a{color:var(--accent);text-decoration:none}a:hover{text-decoration:underline} .layout{display:grid;grid-template-columns:260px minmax(0,820px);gap:50px;max-width:1230px;margin:0 auto;padding:30px}
aside{height:calc(100vh - 60px);position:sticky;top:30px;overflow:auto;border-right:1px solid var(--line);padding:10px 24px 20px 0}aside h2{font-size:1rem;margin:0 0 16px}nav a{display:block;color:var(--muted);font-size:.87rem;line-height:1.4;padding:7px 0}nav a:hover{color:var(--accent)}nav .toc-h3,nav .toc-h4{padding-left:15px}
main{min-width:0;padding:18px 0 80px}header{border-bottom:1px solid var(--line);margin-bottom:30px;padding-bottom:12px}.eyebrow{color:var(--muted);font-size:.8rem;text-transform:uppercase;letter-spacing:.12em}
h1{line-height:1.3;font-size:2rem}h2{margin-top:2.5rem;border-bottom:1px solid var(--line);padding-bottom:.3em}h3{margin-top:2rem}h1,h2,h3,h4{line-height:1.4;scroll-margin-top:20px}
p,li{overflow-wrap:anywhere}blockquote{border-left:4px solid var(--accent);background:var(--soft);padding:10px 18px;margin:24px 0}blockquote p{margin:0}
pre{border:1px solid var(--line);border-radius:10px;padding:18px;overflow-x:auto;background:var(--code);line-height:1.55}code{font:0.88em/1.6 ui-monospace,SFMono-Regular,Consolas,monospace}p code,li code{background:var(--code);padding:.12em .4em;border-radius:4px}
table{display:block;width:100%;overflow-x:auto;border-collapse:collapse;margin:22px 0}th,td{padding:10px 12px;border:1px solid var(--line);text-align:left;vertical-align:top}th{background:var(--soft)}img{max-width:100%;height:auto;border-radius:8px}hr{border:0;border-top:1px solid var(--line);margin:36px 0}
.meta{color:var(--muted);font-size:.9rem}.jump{display:none}.formula-note{color:var(--muted)}
@media(max-width:850px){.layout{display:block;padding:15px 20px}aside{position:static;height:auto;border-right:0;border-bottom:1px solid var(--line);padding:0 0 15px}nav{max-height:240px;overflow:auto}main{padding-top:10px}h1{font-size:1.65rem}}
@media print{body{font-size:11pt;color:#111;background:white}.layout{display:block;padding:0;max-width:none}aside{display:none}main{padding:0}a{color:#111}pre{white-space:pre-wrap}h2,h3{break-after:avoid}table{overflow:visible}tr{break-inside:avoid}}
"""


def build_html(markdown: str, fallback_title: str) -> str:
    markdown, meta = strip_frontmatter(markdown)
    article, toc = headings_with_toc(md_to_html(markdown))
    first = re.search(r"^#\s+(.+)$", markdown, re.M)
    title = meta.get("title") or (first.group(1) if first else fallback_title)
    meta_label = " · ".join(f"{escape(k)}: {escape(meta[k])}" for k in ("year", "arxiv", "version", "status") if meta.get(k))
    return f'''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(title)}</title><style>{STYLE}</style>
<script>window.MathJax={{tex:{{inlineMath:[["\\\\(","\\\\)"]],displayMath:[["\\\\[","\\\\]"],["$$","$$"]]}}}};</script>
<script defer src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-chtml.js"></script></head>
<body><div class="layout"><aside><h2>阅读目录</h2><nav aria-label="文章目录">{toc}</nav></aside>
<main id="content"><header><div class="eyebrow">AI Paper Deep Dive · 研究笔记</div><div class="meta">{meta_label}</div></header>
<article>{article}</article><hr><p class="meta">公式排版使用 MathJax（联网后加载）；离线时可能显示原始 LaTeX。导出自 Markdown 原稿。</p></main></div></body></html>'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Create a navigable HTML reader from AI paper Markdown notes")
    parser.add_argument("markdown", type=Path, help="Input UTF-8 Markdown file")
    parser.add_argument("--output", "-o", type=Path, help="Output HTML file (defaults to same name)")
    args = parser.parse_args()
    out = args.output or args.markdown.with_suffix(".html")
    if not args.markdown.is_file():
        parser.error(f"Input file not found: {args.markdown}")
    raw = args.markdown.read_text(encoding="utf-8")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build_html(raw, args.markdown.stem), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
