#!/usr/bin/env python3
import html
import json
import re
import sys
from pathlib import Path

import markdown
import yaml
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SRC = BASE_DIR / "thinking" / "20-项目" if (BASE_DIR / "thinking" / "20-项目").exists() else BASE_DIR / "20-项目"
OUT_ROOT = BASE_DIR / "dist"


def parse_frontmatter(raw: str) -> tuple[dict, str]:
    if raw.startswith("---"):
        parts = re.split(r"^---\s*$", raw, maxsplit=2, flags=re.MULTILINE)
        if len(parts) == 3:
            meta = yaml.safe_load(parts[1]) or {}
            return meta, parts[2].strip()
    return {}, raw.strip()


def clean_obsidian_syntax(text: str) -> str:
    text = re.sub(r"\[\[([^\x7c\]]+)\x7c([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\]]+)\]\]", r"\1", text)
    text = re.sub(r"^>\s*\[![^\]]+\]\s*(.*)$", r"> **\1**", text, flags=re.MULTILINE)
    return text


def split_sections_safely(md_text: str) -> list[str]:
    sections, buf = [], []
    in_code = False
    for line in md_text.splitlines():
        if line.strip().startswith("```"):
            in_code = not in_code
        if not in_code and line.strip() == "---":
            chunk = "\n".join(buf).strip()
            if chunk:
                sections.append(chunk)
            buf = []
        else:
            buf.append(line)
    last = "\n".join(buf).strip()
    if last:
        sections.append(last)
    return sections


def x_weighted_len(text: str) -> int:
    return sum(2 if ord(ch) > 127 else 1 for ch in text)


def render_xhs_cards(title: str, sections: list[str], tags: list[str], out_dir: Path) -> tuple[list[str], str]:
    """小红书：1080x1440 (3:4) 极简知识卡片 + 配文"""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("card_*.png"):
        old.unlink()

    cards = [f"# {title}\n\n{sections[0]}"] + sections[1:] if sections else [f"# {title}"]
    total = len(cards)
    rel_paths = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1080, "height": 1440}, device_scale_factor=2)

        for idx, sec in enumerate(cards, 1):
            body_html = markdown.markdown(sec, extensions=["extra", "fenced_code"])
            doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<link rel="stylesheet" href="[https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css](https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.css)">
<script defer src="[https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js](https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/katex.min.js)"></script>
<script defer src="[https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js](https://cdn.jsdelivr.net/npm/katex@0.16.11/dist/contrib/auto-render.min.js)"
  onload="renderMathInElement(document.body, {{delimiters:[{{left:'$$',right:'$$',display:true}},{{left:'$',right:'$',display:false}}]}});"></script>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    width: 1080px; height: 1440px; padding: 96px 88px 80px;
    background: #FAF9F6; color: #18181B;
    font-family: "PingFang SC", "Hiragino Sans GB", "Noto Sans CJK SC", -apple-system, sans-serif;
    display: flex; flex-direction: column; justify-content: space-between;
  }}
  .content {{ font-size: 34px; line-height: 1.75; letter-spacing: 0.02em; }}
  h1 {{ font-size: 54px; line-height: 1.3; font-weight: 800; margin-bottom: 44px; letter-spacing: -0.02em; }}
  h2 {{ font-size: 42px; line-height: 1.35; font-weight: 700; margin-bottom: 32px; color: #111; border-left: 8px solid #18181B; padding-left: 22px; }}
  p {{ margin-bottom: 28px; color: #27272A; }}
  ul, ol {{ margin: 0 0 28px 36px; }}
  li {{ margin-bottom: 18px; }}
  strong {{ color: #000; font-weight: 700; background: linear-gradient(transparent 62%, #E4E4E7 62%); }}
  blockquote {{ border-left: 6px solid #71717A; padding-left: 24px; color: #52525B; margin: 24px 0; }}
  code {{ font-family: "SF Mono", Menlo, monospace; font-size: 28px; background: #F4F4F5; padding: 4px 10px; border-radius: 6px; }}
  pre {{ background: #18181B; color: #F4F4F5; padding: 28px; border-radius: 14px; font-size: 24px; line-height: 1.5; overflow: hidden; margin-bottom: 28px; }}
  pre code {{ background: none; color: inherit; padding: 0; }}
  .footer {{
    display: flex; justify-content: space-between; align-items: center;
    border-top: 2px solid #E4E4E7; padding-top: 24px; font-size: 24px; color: #71717A;
  }}
</style></head>
<body>
  <div class="content">{body_html}</div>
  <div class="footer"><span>{html.escape(title)}</span><span>{idx} / {total}</span></div>
</body></html>"""
            page.set_content(doc, wait_until="networkidle")
            fname = f"card_{idx:02d}.png"
            page.screenshot(path=str(out_dir / fname))
            rel_paths.append(f"xhs/{fname}")

        browser.close()

    tag_str = " ".join(f"#{t.lstrip('#')}" for t in tags) if tags else "#深度思考 #系统架构 #方法论"
    plain_intro = re.sub(r"[#*>`\-]", "", sections[0]).strip() if sections else ""
    caption = f"{title}\n\n{plain_intro}\n\n{tag_str}"
    (out_dir / "caption.txt").write_text(caption + "\n", encoding="utf-8")
    return rel_paths, caption


def render_wechat_html(title: str, clean_md: str, out_file: Path) -> str:
    """微信公众号：内联 CSS 富文本 HTML，返回纯正文片段供复制"""
    merged_md = re.sub(r"^\s*---\s*$", "", clean_md, flags=re.MULTILINE)
    raw_html = markdown.markdown(merged_md, extensions=["extra", "fenced_code", "tables"])

    styles = {
        "h2": "font-size:19px;font-weight:700;color:#111;margin:32px 0 14px;padding-left:12px;border-left:4px solid #111;line-height:1.4;",
        "h3": "font-size:17px;font-weight:700;color:#222;margin:24px 0 10px;",
        "p": "font-size:15px;line-height:1.85;color:#2c2c2c;margin:0 0 18px;letter-spacing:0.4px;",
        "ul": "margin:0 0 18px;padding-left:22px;color:#2c2c2c;font-size:15px;line-height:1.85;",
        "ol": "margin:0 0 18px;padding-left:22px;color:#2c2c2c;font-size:15px;line-height:1.85;",
        "li": "margin-bottom:8px;",
        "blockquote": "margin:20px 0;padding:12px 16px;background:#f7f7f8;border-left:3px solid #888;color:#555;font-size:14px;line-height:1.75;",
        "pre": "background:#1e1e1e;color:#d4d4d4;padding:14px;border-radius:6px;font-size:13px;line-height:1.5;overflow-x:auto;margin:18px 0;",
        "code": "font-family:Menlo,Monaco,monospace;background:#f2f2f3;padding:2px 5px;border-radius:3px;font-size:13px;",
        "strong": "font-weight:700;color:#000;",
    }
    for tag, css in styles.items():
        raw_html = re.sub(rf"<{tag}(\b[^>]*)>", rf'<{tag}\1 style="{css}">', raw_html)
    raw_html = re.sub(r"(<pre[^>]*>)\s*<code[^>]*>", r"\1<code>", raw_html)

    wrapper = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title></head>
<body style="max-width:680px;margin:40px auto;padding:0 20px;font-family:-apple-system,BlinkMacSystemFont,'PingFang SC',sans-serif;">
  <h1 style="font-size:22px;font-weight:700;color:#111;margin-bottom:24px;line-height:1.4;">{html.escape(title)}</h1>
  {raw_html}
</body></html>"""
    out_file.write_text(wrapper, encoding="utf-8")
    return raw_html


def render_medium_md(title: str, clean_md: str, out_file: Path) -> str:
    """Medium：标准纯净 Markdown"""
    merged_md = re.sub(r"^\s*---\s*$", "\n* * *\n", clean_md, flags=re.MULTILINE)
    full_md = f"# {title}\n\n{merged_md}"
    out_file.write_text(full_md + "\n", encoding="utf-8")
    return full_md


def render_x_article(title: str, clean_md: str, sections: list[str], tags: list[str], out_dir: Path) -> tuple[str, str]:
    """X Articles：语义化 HTML 正文 + 280 字符安全线内的时间线引流短推"""
    out_dir.mkdir(parents=True, exist_ok=True)
    body_html = markdown.markdown(clean_md, extensions=["extra", "fenced_code", "tables"])

    article_doc = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{html.escape(title)}</title></head>
<body style="max-width:680px;margin:40px auto;padding:0 20px;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#0f1419;line-height:1.75;">
  {body_html}
</body></html>"""
    (out_dir / "article.html").write_text(article_doc, encoding="utf-8")

    intro = re.sub(r"[#*>`\-]", "", sections[0]).strip() if sections else ""
    tag_str = " ".join(f"#{t.lstrip('#')}" for t in tags[:3]) if tags else ""
    teaser = f"{title}\n\n{intro}"
    acc, w = [], 0
    for ch in teaser:
        cw = 2 if ord(ch) > 127 else 1
        if w + cw > 230:
            acc.append("…")
            break
        acc.append(ch)
        w += cw
    teaser_final = "".join(acc) + (f"\n\n{tag_str}" if tag_str else "")
    (out_dir / "teaser.txt").write_text(teaser_final + "\n", encoding="utf-8")
    return body_html, teaser_final


def render_preview_dashboard(
    title: str,
    cards: list[str],
    xhs_caption: str,
    wechat_body_html: str,
    medium_md: str,
    x_body_html: str,
    x_teaser: str,
    out_file: Path,
):
    """生成单页四端聚合展示与一键复制工作台"""
    payload = {
        "title": title,
        "cards": cards,
        "xhsCaption": xhs_caption,
        "wechatHtml": wechat_body_html,
        "mediumMd": medium_md,
        "mediumHtml": markdown.markdown(medium_md, extensions=["extra", "fenced_code", "tables"]),
        "xHtml": x_body_html,
        "xTeaser": x_teaser,
        "xTeaserWeight": x_weighted_len(x_teaser),
    }
    safe_json = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")

    dashboard = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · 四端发布预览台</title>
<style>
  :root {{
    --bg: #F4F5F7; --card: #FFFFFF; --border: #E4E7EC; --text: #101828;
    --muted: #667085; --primary: #111827; --primary-hover: #374151;
    --accent-bg: #F9FAFB; --radius: 14px;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Segoe UI", sans-serif;
    line-height: 1.6; padding-bottom: 60px;
  }}
  header {{
    position: sticky; top: 0; z-index: 50;
    background: rgba(255,255,255,0.9); backdrop-filter: blur(12px);
    border-bottom: 1px solid var(--border); padding: 14px 28px;
    display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 12px;
  }}
  .title-wrap {{ display: flex; align-items: center; gap: 12px; min-width: 0; }}
  .title-wrap h1 {{ font-size: 17px; font-weight: 700; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 520px; }}
  .controls {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }}
  button {{
    border: 1px solid var(--border); background: #fff; color: var(--text);
    padding: 7px 13px; border-radius: 8px; font-size: 13px; font-weight: 600;
    cursor: pointer; transition: all 0.15s ease; display: inline-flex; align-items: center; gap: 5px;
  }}
  button:hover {{ background: #F3F4F6; border-color: #D0D5DD; }}
  button.primary {{ background: var(--primary); color: #fff; border-color: var(--primary); }}
  button.primary:hover {{ background: var(--primary-hover); }}
  button.active {{ background: #EEF2FF; color: #3730A3; border-color: #C7D2FE; }}

  .grid {{
    max-width: 1560px; margin: 24px auto; padding: 0 24px;
    display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 22px;
  }}
  .grid.single-col {{ grid-template-columns: minmax(0, 820px); justify-content: center; }}
  @media (max-width: 1024px) {{ .grid {{ grid-template-columns: 1fr; }} }}

  .panel {{
    background: var(--card); border: 1px solid var(--border); border-radius: var(--radius);
    display: flex; flex-direction: column; overflow: hidden;
    box-shadow: 0 1px 3px rgba(16,24,40,0.04);
  }}
  .panel.hidden {{ display: none; }}
  .panel-head {{
    padding: 14px 18px; border-bottom: 1px solid var(--border); background: var(--accent-bg);
    display: flex; justify-content: space-between; align-items: center; gap: 10px; flex-wrap: wrap;
  }}
  .platform-badge {{ display: flex; align-items: center; gap: 8px; font-weight: 700; font-size: 15px; }}
  .dot {{ width: 9px; height: 9px; border-radius: 50%; display: inline-block; }}
  .panel-actions {{ display: flex; gap: 8px; flex-wrap: wrap; }}
  .panel-body {{ padding: 20px; overflow-y: auto; max-height: 680px; }}

  /* 小红书画廊 */
  .xhs-strip {{
    display: flex; gap: 14px; overflow-x: auto; padding-bottom: 12px; margin-bottom: 16px;
    border-bottom: 1px dashed var(--border);
  }}
  .xhs-card-item {{ flex: 0 0 190px; position: relative; cursor: zoom-in; }}
  .xhs-card-item img {{
    width: 100%; aspect-ratio: 3 / 4; object-fit: cover; border-radius: 10px;
    border: 1px solid var(--border); display: block; transition: transform 0.15s;
  }}
  .xhs-card-item img:hover {{ transform: translateY(-2px); }}
  .xhs-card-item span {{
    position: absolute; bottom: 8px; right: 8px; background: rgba(0,0,0,0.65);
    color: #fff; font-size: 11px; padding: 2px 7px; border-radius: 6px;
  }}
  .caption-box {{
    background: #F9FAFB; border: 1px solid var(--border); border-radius: 10px;
    padding: 14px; font-size: 14px; white-space: pre-wrap; color: #344054;
  }}

  /* X 引流短推 */
  .teaser-box {{
    background: #F0F9FF; border: 1px solid #BAE6FD; border-radius: 10px;
    padding: 14px; margin-bottom: 18px;
  }}
  .teaser-meta {{ display: flex; justify-content: space-between; font-size: 12px; color: #0369A1; font-weight: 600; margin-bottom: 6px; }}
  .teaser-text {{ font-size: 14px; white-space: pre-wrap; color: #0C4A6E; }}

  /* X 与 Medium 正文排版 */
  .rich-preview h1 {{ font-size: 22px; margin-bottom: 16px; }}
  .rich-preview h2 {{ font-size: 18px; margin: 24px 0 10px; }}
  .rich-preview p {{ margin-bottom: 14px; font-size: 15px; line-height: 1.75; }}
  .rich-preview ul, .rich-preview ol {{ margin: 0 0 14px 22px; font-size: 15px; }}
  .rich-preview li {{ margin-bottom: 6px; }}
  .rich-preview blockquote {{ border-left: 3px solid #CBD5E1; padding-left: 14px; color: #475569; margin: 14px 0; }}
  .rich-preview pre {{ background: #1E293B; color: #F8FAFC; padding: 12px; border-radius: 8px; overflow-x: auto; font-size: 13px; margin-bottom: 14px; }}
  .rich-preview hr {{ border: none; border-top: 1px solid #E2E8F0; margin: 22px 0; }}
  .raw-md {{
    font-family: "SF Mono", Menlo, monospace; font-size: 13px; line-height: 1.65;
    white-space: pre-wrap; background: #F8FAFC; padding: 16px; border-radius: 10px; border: 1px solid var(--border);
  }}

  /* 大图预览遮罩 */
  .lightbox {{
    position: fixed; inset: 0; background: rgba(0,0,0,0.82); z-index: 100;
    display: none; justify-content: center; align-items: center; padding: 24px; cursor: zoom-out;
  }}
  .lightbox.open {{ display: flex; }}
  .lightbox img {{ max-height: 92vh; max-width: 92vw; border-radius: 12px; box-shadow: 0 20px 50px rgba(0,0,0,0.5); }}

  .toast {{
    position: fixed; bottom: 24px; right: 24px; background: #111827; color: #fff;
    padding: 10px 18px; border-radius: 10px; font-size: 14px; font-weight: 600;
    opacity: 0; transform: translateY(10px); transition: all 0.2s; pointer-events: none; z-index: 200;
  }}
  .toast.show {{ opacity: 1; transform: translateY(0); }}
</style>
</head>
<body>

<header>
  <div class="title-wrap">
    <h1 id="doc-title"></h1>
    <button onclick="copyPlain(DATA.title, '标题已复制')">复制标题</button>
  </div>
  <div class="controls">
    <button class="active" data-filter="all" onclick="setFilter('all', this)">全部四端 (2×2)</button>
    <button data-filter="xhs" onclick="setFilter('xhs', this)">小红书</button>
    <button data-filter="wechat" onclick="setFilter('wechat', this)">微信公众号</button>
    <button data-filter="x" onclick="setFilter('x', this)">X Articles</button>
    <button data-filter="medium" onclick="setFilter('medium', this)">Medium</button>
  </div>
</header>

<main class="grid" id="grid">
  <!-- 1. 小红书 -->
  <section class="panel" data-panel="xhs">
    <div class="panel-head">
      <div class="platform-badge"><span class="dot" style="background:#FF2442;"></span>小红书 · 3:4 卡片与配文</div>
      <div class="panel-actions">
        <button class="primary" onclick="copyPlain(DATA.xhsCaption, '小红书配文已复制')">一键复制配文</button>
      </div>
    </div>
    <div class="panel-body">
      <div class="xhs-strip" id="xhs-strip"></div>
      <div class="caption-box" id="xhs-caption"></div>
    </div>
  </section>

  <!-- 2. 微信公众号 -->
  <section class="panel" data-panel="wechat">
    <div class="panel-head">
      <div class="platform-badge"><span class="dot" style="background:#07C160;"></span>微信公众号 · 内联样式富文本</div>
      <div class="panel-actions">
        <button class="primary" onclick="copyRich(DATA.wechatHtml, DATA.mediumMd, '公众号富文本已复制，可直接粘贴至后台')">一键复制富文本</button>
      </div>
    </div>
    <div class="panel-body" id="wechat-preview"></div>
  </section>

  <!-- 3. X Articles -->
  <section class="panel" data-panel="x">
    <div class="panel-head">
      <div class="platform-badge"><span class="dot" style="background:#0F1419;"></span>X (Twitter) · 长文与引流短推</div>
      <div class="panel-actions">
        <button onclick="copyPlain(DATA.xTeaser, '时间线引流短推已复制')">复制引流短推</button>
        <button class="primary" onclick="copyRich(DATA.xHtml, DATA.mediumMd, 'X 长文富文本已复制')">复制长文富文本</button>
      </div>
    </div>
    <div class="panel-body">
      <div class="teaser-box">
        <div class="teaser-meta"><span>时间线引流推文 (Teaser)</span><span id="teaser-count"></span></div>
        <div class="teaser-text" id="x-teaser"></div>
      </div>
      <div class="rich-preview" id="x-preview"></div>
    </div>
  </section>

  <!-- 4. Medium -->
  <section class="panel" data-panel="medium">
    <div class="panel-head">
      <div class="platform-badge"><span class="dot" style="background:#1A8917;"></span>Medium · 纯净 Markdown</div>
      <div class="panel-actions">
        <button onclick="toggleMediumView()" id="med-toggle">查看源码</button>
        <button class="primary" onclick="copyPlain(DATA.mediumMd, 'Medium Markdown 已复制')">一键复制 Markdown</button>
      </div>
    </div>
    <div class="panel-body">
      <div class="rich-preview" id="medium-preview"></div>
      <pre class="raw-md" id="medium-raw" style="display:none;"></pre>
    </div>
  </section>
</main>

<div class="lightbox" id="lightbox" onclick="this.classList.remove('open')"><img id="lightbox-img" src="" alt=""></div>
<div class="toast" id="toast"></div>

<script id="payload" type="application/json">{safe_json}</script>
<script>
const DATA = JSON.parse(document.getElementById('payload').textContent);

document.getElementById('doc-title').textContent = DATA.title;
document.getElementById('xhs-caption').textContent = DATA.xhsCaption;
document.getElementById('wechat-preview').innerHTML = DATA.wechatHtml;
document.getElementById('x-teaser').textContent = DATA.xTeaser;
document.getElementById('teaser-count').textContent = DATA.xTeaserWeight + ' / 280 权重字符';
document.getElementById('x-preview').innerHTML = DATA.xHtml;
document.getElementById('medium-preview').innerHTML = DATA.mediumHtml;
document.getElementById('medium-raw').textContent = DATA.mediumMd;

const strip = document.getElementById('xhs-strip');
DATA.cards.forEach((src, i) => {{
  const div = document.createElement('div');
  div.className = 'xhs-card-item';
  div.innerHTML = `<img src="${{src}}" alt="card ${{i+1}}"><span>${{i+1}} / ${{DATA.cards.length}}</span>`;
  div.onclick = () => {{
    document.getElementById('lightbox-img').src = src;
    document.getElementById('lightbox').classList.add('open');
  }};
  strip.appendChild(div);
}});

function showToast(msg) {{
  const t = document.getElementById('toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(window._toastTimer);
  window._toastTimer = setTimeout(() => t.classList.remove('show'), 2200);
}}

async function copyPlain(text, msg) {{
  try {{
    await navigator.clipboard.writeText(text);
    showToast(msg);
  }} catch (e) {{
    const ta = document.createElement('textarea');
    ta.value = text;
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showToast(msg);
  }}
}}

async function copyRich(htmlStr, plainStr, msg) {{
  try {{
    const item = new ClipboardItem({{
      'text/html': new Blob([htmlStr], {{ type: 'text/html' }}),
      'text/plain': new Blob([plainStr], {{ type: 'text/plain' }})
    }});
    await navigator.clipboard.write([item]);
    showToast(msg);
  }} catch (e) {{
    const box = document.createElement('div');
    box.contentEditable = true;
    box.style.position = 'fixed';
    box.style.left = '-9999px';
    box.innerHTML = htmlStr;
    document.body.appendChild(box);
    const range = document.createRange();
    range.selectNodeContents(box);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
    document.execCommand('copy');
    sel.removeAllRanges();
    document.body.removeChild(box);
    showToast(msg);
  }}
}}

function setFilter(key, btn) {{
  document.querySelectorAll('.controls button').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const grid = document.getElementById('grid');
  const panels = document.querySelectorAll('.panel');
  if (key === 'all') {{
    grid.classList.remove('single-col');
    panels.forEach(p => p.classList.remove('hidden'));
  }} else {{
    grid.classList.add('single-col');
    panels.forEach(p => p.classList.toggle('hidden', p.dataset.panel !== key));
  }}
}}

let showRaw = false;
function toggleMediumView() {{
  showRaw = !showRaw;
  document.getElementById('medium-preview').style.display = showRaw ? 'none' : 'block';
  document.getElementById('medium-raw').style.display = showRaw ? 'block' : 'none';
  document.getElementById('med-toggle').textContent = showRaw ? '渲染预览' : '查看源码';
}}
</script>
</body>
</html>"""
    out_file.write_text(dashboard, encoding="utf-8")


def update_root_index():
    """在 dist/index.html 生成所有已转化文章的总导航入口"""
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    items = []
    for sub in sorted(OUT_ROOT.iterdir()):
        preview = sub / "preview.html"
        if sub.is_dir() and preview.exists():
            items.append(f'<li><a href="{html.escape(sub.name)}/preview.html">{html.escape(sub.name)}</a></li>')

    index_html = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>四端发布总览</title>
<style>
  body {{ max-width: 680px; margin: 60px auto; padding: 0 20px; font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", sans-serif; color: #111; }}
  h1 {{ font-size: 24px; margin-bottom: 24px; }}
  ul {{ list-style: none; padding: 0; }}
  li {{ margin-bottom: 12px; }}
  a {{ display: block; padding: 14px 18px; border: 1px solid #E5E7EB; border-radius: 10px; text-decoration: none; color: #111; font-weight: 600; }}
  a:hover {{ background: #F9FAFB; border-color: #111; }}
</style></head>
<body><h1>四端内容分发预览台</h1><ul>{"".join(items) if items else "<li>暂无生成记录</li>"}</ul></body></html>"""
    (OUT_ROOT / "index.html").write_text(index_html, encoding="utf-8")


def process_file(md_path: Path) -> Path:
    raw = md_path.read_text(encoding="utf-8")
    meta, body = parse_frontmatter(raw)
    title = str(meta.get("title") or md_path.stem).strip()
    tags = meta.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",") if t.strip()]

    clean_md = clean_obsidian_syntax(body)
    sections = split_sections_safely(clean_md)

    target_dir = OUT_ROOT / md_path.stem
    target_dir.mkdir(parents=True, exist_ok=True)

    cards, xhs_caption = render_xhs_cards(title, sections, tags, target_dir / "xhs")
    wechat_body = render_wechat_html(title, clean_md, target_dir / "wechat.html")
    medium_md = render_medium_md(title, clean_md, target_dir / "medium.md")
    x_body, x_teaser = render_x_article(title, clean_md, sections, tags, target_dir / "x")

    preview_path = target_dir / "preview.html"
    render_preview_dashboard(
        title=title,
        cards=cards,
        xhs_caption=xhs_caption,
        wechat_body_html=wechat_body,
        medium_md=medium_md,
        x_body_html=x_body,
        x_teaser=x_teaser,
        out_file=preview_path,
    )
    print(f"[OK] 预览网页已生成: {preview_path}")
    return preview_path


def main():
    if len(sys.argv) > 1:
        files = [Path(arg).resolve() for arg in sys.argv[1:]]
    else:
        if not DEFAULT_SRC.exists():
            print(f"未找到目录: {DEFAULT_SRC}，请传入具体 .md 文件路径")
            sys.exit(1)
        files = sorted(DEFAULT_SRC.glob("*.md"))

    for f in files:
        if f.is_file() and f.suffix == ".md":
            process_file(f)
    update_root_index()


if __name__ == "__main__":
    main()
