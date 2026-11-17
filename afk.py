# -*- coding: utf-8 -*-
import ctypes
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import webbrowser
from datetime import datetime
from pathlib import Path

try:
    import msvcrt
except ImportError:
    msvcrt = None

SCRIPT_DIR = Path(__file__).resolve().parent
CONFIG_PATH = (Path.home() / "afk_config.json"
               if (Path.home() / "afk_config.json").exists()
               else SCRIPT_DIR / "afk_config.json")
STATE_DIR = CONFIG_PATH.parent
WATCH_LOG = STATE_DIR / "afk_watch.log"
WATCH_LOCK = STATE_DIR / "afk_watch.lock"
WATCH_PID = STATE_DIR / "afk_watch.pid"
REPO_DIR = SCRIPT_DIR / "afk-site"  # переопределяется init_runtime() из конфига
REPO_URL = ""
SITE_URL = ""
GH_LINK = ""
DEFAULT_FOLDER = Path.home() / "Documents" / "ObsidianNotes"
ASSET_EXT = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".pdf", ".mp3", ".mp4", ".webm"}
SKIP_DIRS = {".obsidian", ".trash", ".git", ".smart-connections", "node_modules"}
IDLE_SECONDS = 25  # публиковать только после 25 секунд без изменений (дописал — заливается)
POLL_SECONDS = 3   # как часто проверять файлы


class C:
    R = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    BG = "\033[44m"


def enable_console():
    if os.name == "nt":
        k = ctypes.windll.kernel32
        for hid in (-11, -12):
            h = k.GetStdHandle(hid)
            mode = ctypes.c_uint32()
            if k.GetConsoleMode(h, ctypes.byref(mode)):
                k.SetConsoleMode(h, mode.value | 0x0004)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def default_config():
    folders = []
    if DEFAULT_FOLDER.exists():
        folders.append(str(DEFAULT_FOLDER))
    return {"folders": folders, "state": {}, "history": []}


def load_config():
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, encoding="utf-8") as f:
                cfg = json.load(f)
            cfg.setdefault("folders", [])
            cfg.setdefault("state", {})
            cfg.setdefault("history", [])
            return cfg
        except Exception:
            pass
    cfg = default_config()
    save_config(cfg)
    return cfg


def save_config(cfg):
    tmp = CONFIG_PATH.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    tmp.replace(CONFIG_PATH)


def derive_site_url(repo_url):
    m = re.match(
        r"(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)"
        r"([^/]+)/([^/]+?)(?:\.git)?$",
        repo_url or "",
    )
    if not m:
        return ""
    user, repo = m.group(1), m.group(2)
    if repo.lower() == user.lower() + ".github.io":
        return f"https://{user.lower()}.github.io/"
    return f"https://{user.lower()}.github.io/{repo}/"


def git_remote_origin():
    try:
        r = subprocess.run(
            ["git", "-C", str(REPO_DIR), "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def init_runtime():
    global REPO_DIR, REPO_URL, SITE_URL, GH_LINK
    cfg = load_config()
    REPO_DIR = Path(cfg.get("repo_dir") or SCRIPT_DIR / "afk-site")
    REPO_URL = cfg.get("repo_url") or git_remote_origin()
    SITE_URL = cfg.get("site_url") or derive_site_url(REPO_URL)
    GH_LINK = REPO_URL[:-4] if REPO_URL.endswith(".git") else REPO_URL
    return cfg


init_runtime()


def gh_anchor(cls, inner):
    if not GH_LINK:
        return ""
    cls_attr = f' class="{cls}"' if cls else ""
    return (f'<a{cls_attr} href="{GH_LINK}" target="_blank" rel="noopener" '
            f'aria-label="GitHub, откроется в новой вкладке">{inner}</a>')


def hash_file(path):
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def escape_html(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


WIKI = {}
ASSETS = {}


def url_for(site_path):
    p = str(site_path).replace("\\", "/")
    return SITE_URL + "/".join(urllib.parse.quote(seg) for seg in p.split("/"))


PAGE_FEATS = set()

CALLOUT_ICON = {
    "note": "📝", "abstract": "📋", "summary": "📋", "tldr": "📋",
    "info": "ℹ️", "todo": "☑️",
    "tip": "💡", "hint": "💡", "important": "💡",
    "success": "✅", "check": "✅", "done": "✅",
    "question": "❓", "help": "❓", "faq": "❓",
    "warning": "⚠️", "caution": "⚠️", "attention": "⚠️",
    "failure": "❌", "fail": "❌", "missing": "❌",
    "danger": "💥", "error": "💥", "bug": "🐞",
    "example": "📌", "quote": "❝", "cite": "❝",
}
CALLOUT_COLOR = {
    "note": "#3b82f6", "abstract": "#3b82f6", "summary": "#3b82f6",
    "tldr": "#3b82f6", "info": "#3b82f6", "todo": "#3b82f6",
    "tip": "#06b6d4", "hint": "#06b6d4", "important": "#06b6d4",
    "success": "#22c55e", "check": "#22c55e", "done": "#22c55e",
    "question": "#a855f7", "help": "#a855f7", "faq": "#a855f7",
    "warning": "#eab308", "caution": "#eab308", "attention": "#eab308",
    "failure": "#ef4444", "fail": "#ef4444", "missing": "#ef4444",
    "danger": "#ef4444", "error": "#ef4444", "bug": "#ef4444",
    "example": "#a855f7", "quote": "#71717a", "cite": "#71717a",
}


def inline_md(text):
    protected = []

    def keep(html):
        protected.append(html)
        return f"\x00{len(protected) - 1}\x00"

    def keep_math(m):
        PAGE_FEATS.add("katex")
        return keep(f'<span class="math-inline">\\({escape_html(m.group(1))}\\)</span>')

    text = re.sub(r"(?<!\\)\$(?!\$|\s)([^\$\n]+?)(?<!\s)\$", keep_math, text)
    text = re.sub(r"\\([\\`*_[\]{}()#+\-.!|<>~^&=+])",
                  lambda m: keep(escape_html(m.group(1))), text)
    html_re = (
        r"</?[A-Za-z][A-Za-z0-9-]*"
        r"(?:\s+[A-Za-z-]+(?:\s*=\s*(?:[^\s\"'=<>`]+|'[^']*'|\"[^\"]*\"))?)*"
        r"\s*/?>|<!--.*?-->"
    )
    text = re.sub(html_re, lambda m: keep(m.group(0)), text)

    def keep_code(m):
        return keep(f"<code>{escape_html(m.group(2))}</code>")

    text = re.sub(r"(?<!`)(`+)(?!`)(.+?)(?<!`)\1(?!`)", keep_code, text,
                  flags=re.S)

    text = escape_html(text)

    text = re.sub(r"\[\^([^\]\s]+)\]",
                  lambda m: keep(
                      f'<sup class="fnref"><a href="#fn-{escape_html(m.group(1))}">'
                      f"{escape_html(m.group(1))}</a></sup>"), text)

    text = re.sub(r"\*\*\*([^\n]+?)\*\*\*", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"\*\*([^\n]+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"___([^\n]+?)___", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"__([^\n]+?)__", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*\n<>]+?)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"(?<![\w*])_([^_\n<>]+)_(?![\w*])", r"<em>\1</em>", text)
    text = re.sub(r"~~([^~\n]+)~~", r"<del>\1</del>", text)
    text = re.sub(r"==([^=\n]+)==", r"<mark>\1</mark>", text)
    text = re.sub(r"^\*\*\*(?!\*)(.+)$", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"^\*\*(?!\*)(.+)$", r"<strong>\1</strong>", text)
    text = re.sub(r"^___(?!_)(.+)$", r"<strong><em>\1</em></strong>", text)
    text = re.sub(r"^__(?!_)(.+)$", r"<strong>\1</strong>", text)

    def img(m):
        alt, src, title = m.group(1), m.group(2), m.group(3)
        if src.startswith("<") and src.endswith(">"):
            src = src[1:-1]
        key = src.lstrip("./").lower()
        real = ASSETS.get(key) or ASSETS.get(Path(src).name.lower())
        href = url_for(real) if real else src
        t = f' title="{title}"' if title else ""
        return keep(f'<img src="{href}" alt="{alt}"{t}>')

    text = re.sub(r"!\[([^\]]*)\]\(\s*([^)\s]+)(?:\s+&quot;(.*?)&quot;)?\s*\)",
                  img, text)

    def wiki_img(m):
        parts = m.group(1).split("|")
        name = Path(parts[0]).name.lower()
        w = parts[1].strip() if len(parts) > 1 else ""
        real = ASSETS.get(name)
        if real:
            style = f' style="width:{escape_html(w)}px"' if w.isdigit() else ""
            return keep(f'<img src="{url_for(real)}" alt="{name}"{style}>')
        return keep(m.group(0))

    text = re.sub(r"!\[\[([^\]]+)\]\]", wiki_img, text)

    def link(m):
        href, title = m.group(2), m.group(3)
        if href.startswith("<") and href.endswith(">"):
            href = href[1:-1]
        t = f' title="{title}"' if title else ""
        return keep(f'<a href="{href}"{t} target="_blank" '
                    f'rel="noopener">{m.group(1)}</a>')

    text = re.sub(r"\[([^\]]+)\]\(\s*([^)\s]+)(?:\s+&quot;(.*?)&quot;)?\s*\)",
                  link, text)

    def wiki(m):
        body = m.group(1)
        alias = body.split("|", 1)
        target = alias[0].strip()
        label = alias[1].strip() if len(alias) > 1 else target
        page, _, frag = target.partition("#")
        frag = frag.strip()
        anchor = ""
        if frag and not frag.startswith("^"):
            anchor = "#" + slugify(frag)
        if page:
            dest = WIKI.get(Path(page).stem.lower())
            if dest:
                return keep(f'<a href="{url_for(dest)}{anchor}">'
                            f"{escape_html(label)}</a>")
            return keep(f'<span class="wl">{escape_html(label)}</span>')
        if frag and not frag.startswith("^"):
            return keep(f'<a href="{anchor}">{escape_html(label)}</a>')
        return keep(f'<span class="wl">{escape_html(label)}</span>')

    text = re.sub(r"\[\[([^\]]+)\]\]", wiki, text)

    def bare_url(m):
        url = re.sub(r"[.,;:!?]+$", "", m.group(1))
        return keep(f'<a href="{url}" target="_blank" rel="noopener">{url}</a>')

    text = re.sub(r"(?<![\w\"=/])(https?://[^\s<>\"')\]]+)", bare_url, text)

    text = re.sub(r"(?<![\w/])#([^\W\d][\w-]*)",
                  r'<span class="hashtag">#\1</span>', text)

    for i in range(len(protected) - 1, -1, -1):
        text = text.replace(f"\x00{i}\x00", protected[i])
    return text


LIST_ITEM_RE = re.compile(r"^(\s*)([-*+]|\d+\.)\s+(.*)$")


def render_list_block(block):
    first = LIST_ITEM_RE.match(block[0])
    base = len(first.group(1))
    ordered = first.group(2).endswith(".")
    items = []
    cur = None
    for ln in block:
        if not ln.strip():
            continue
        mm = LIST_ITEM_RE.match(ln)
        if mm and len(mm.group(1)) <= base:
            cur = {"text": [mm.group(3)], "sub": []}
            items.append(cur)
        elif mm:
            if cur is None:
                cur = {"text": [""], "sub": []}
                items.append(cur)
            cur["sub"].append(ln)
        elif cur is not None:
            cur["text"].append(ln.strip())
    parts = []
    for it in items:
        t0 = it["text"][0]
        tm = re.match(r"^\[([ xX])\]\s+(.*)$", t0)
        task = bool(tm)
        inner = inline_md(tm.group(2) if task else t0)
        for extra in it["text"][1:]:
            if extra.strip():
                inner += "<br>" + inline_md(extra)
        if it["sub"]:
            inner += render_list_block(it["sub"])
        if task:
            checked = " checked" if tm.group(1).lower() == "x" else ""
            parts.append(
                f'<li class="task"><input type="checkbox" disabled{checked}>'
                f"{inner}</li>"
            )
        else:
            parts.append(f"<li>{inner}</li>")
    tag = "ol" if ordered else "ul"
    start_attr = ""
    if ordered:
        num = re.match(r"^\s*(\d+)\.", block[0])
        if num and int(num.group(1)) != 1:
            start_attr = f' start="{int(num.group(1))}"'
    return f"<{tag}{start_attr}>{''.join(parts)}</{tag}>"


def md_to_html(md):
    md = md.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    props_html = ""
    if md.startswith("---\n"):
        end = md.find("\n---", 4)
        if end != -1:
            fm = md[4:end]
            md = md[end + 4:].lstrip("\n")
            rows = []
            for ln in fm.split("\n"):
                fmm = re.match(r"^([A-Za-zА-Яа-яЁё][\w -]*?)\s*:\s*(.*)$", ln)
                if fmm:
                    k = fmm.group(1)
                    v = fmm.group(2).strip().strip("\"'")
                    rows.append(
                        f'<div class="prop"><span class="prop-k">{escape_html(k)}</span>'
                        f'<span class="prop-v">{escape_html(v)}</span></div>'
                    )
            if rows:
                props_html = f'<div class="props">{"".join(rows)}</div>'
    fence_parts = re.split(r"(^```.*?^```)", md, flags=re.S | re.M)
    for j in range(0, len(fence_parts), 2):
        fence_parts[j] = re.sub(r"%%.*?%%", "", fence_parts[j], flags=re.S)
    md = "".join(fence_parts)
    math_blocks = []

    def _math_block(m):
        math_blocks.append(m.group(1).strip())
        return f"\n\x03B{len(math_blocks) - 1}\x03\n"

    md = re.sub(r"\$\$(.+?)\$\$", _math_block, md, flags=re.S)
    lines = md.split("\n")
    out = []
    fn_defs = []
    i = 0
    n = len(lines)

    def is_block_start(ln, nxt=""):
        return (
            ln.startswith("#")
            or ln.startswith(">")
            or ln.startswith("```")
            or re.match(r"^\s*([-*+]|\d+\.)\s+", ln)
            or re.match(r"^(-{3,}|\*{3,}|_{3,})\s*$", ln)
            or re.match(r"^\x03B\d+\x03$", ln)
            or re.match(r"^\[\^[^\]\s]+\]:", ln)
            or ("|" in ln and "-" in nxt
                and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", nxt))
        )

    def render_footnotes():
        if not fn_defs:
            return ""
        items = "".join(
            f'<p class="fn" id="fn-{escape_html(k)}"><b>[{escape_html(k)}]</b> '
            f"{inline_md(v)}</p>"
            for k, v in fn_defs
        )
        return f'<div class="footnotes"><hr>{items}</div>'

    while i < n:
        line = lines[i]
        mb = re.match(r"^\x03B(\d+)\x03$", line.strip())
        if mb:
            PAGE_FEATS.add("katex")
            out.append(f'<div class="math-block">\\['
                       f"{escape_html(math_blocks[int(mb.group(1))])}\\]</div>")
            i += 1
            continue
        if line.startswith("```"):
            lang = line[3:].strip()
            i += 1
            buf = []
            while i < n and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            code = escape_html(chr(10).join(buf))
            if lang == "mermaid":
                PAGE_FEATS.add("mermaid")
                out.append(f'<div class="mermaid">{code}</div>')
                continue
            cls = f' class="lang-{escape_html(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{code}</code></pre>")
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m:
            level = len(m.group(1))
            txt = m.group(2).rstrip(" #")
            out.append(f'<h{level} id="{slugify(txt)}">{inline_md(txt)}</h{level}>')
            i += 1
            continue
        if re.match(r"^(-{3,}|\*{3,}|_{3,})\s*$", line):
            out.append("<hr>")
            i += 1
            continue
        mfn = re.match(r"^\[\^([^\]\s]+)\]:\s*(.*)$", line)
        if mfn:
            fn_defs.append((mfn.group(1), mfn.group(2)))
            i += 1
            continue
        if line.startswith(">"):
            buf = []
            while i < n and lines[i].startswith(">"):
                buf.append(re.sub(r"^>\s?", "", lines[i]))
                i += 1
            cm = re.match(r"^\[!([A-Za-z0-9_-]+)\]([-+]?)\s*(.*)$", buf[0])
            if cm:
                ctype = cm.group(1).lower()
                marker = cm.group(2)
                ctitle = cm.group(3).strip() or ctype.capitalize()
                icon = CALLOUT_ICON.get(ctype, "📝")
                color = CALLOUT_COLOR.get(ctype, "#71717a")
                rest = buf[1:]
                inner = (md_to_html("\n".join(rest))
                         if any(s.strip() for s in rest) else "")
                attrs = (f'data-type="{escape_html(ctype)}" style="--c:{color}"')
                title_html = (f'<span class="callout-ic">{icon}</span>'
                              f'<span class="callout-name">{escape_html(ctitle)}</span>')
                if marker:
                    open_attr = " open" if marker == "+" else ""
                    out.append(
                        f'<details class="callout"{open_attr} {attrs}>'
                        f'<summary class="callout-title">{title_html}</summary>'
                        f'<div class="callout-content">{inner}</div></details>'
                    )
                else:
                    out.append(
                        f'<div class="callout" {attrs}>'
                        f'<div class="callout-title">{title_html}</div>'
                        f'<div class="callout-content">{inner}</div></div>'
                    )
                continue
            out.append("<blockquote>" + md_to_html("\n".join(buf)) + "</blockquote>")
            continue
        if (
            "|" in line
            and i + 1 < n
            and re.match(r"^\s*\|?[\s:|-]+\|?\s*$", lines[i + 1])
            and "-" in lines[i + 1]
        ):
            def split_row(row):
                row = row.strip().strip("|")
                return [c.strip() for c in row.split("|")]

            def cell_align(c):
                c = c.strip()
                if len(c) >= 2 and c.startswith(":") and c.endswith(":"):
                    return "center"
                if c.endswith(":"):
                    return "right"
                if c.startswith(":"):
                    return "left"
                return ""

            header = split_row(line)
            aligns = [cell_align(c) for c in split_row(lines[i + 1])]
            i += 2
            rows = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(split_row(lines[i]))
                i += 1

            def cell_html(tag, txt, k):
                a = aligns[k] if k < len(aligns) else ""
                style = f' style="text-align:{a}"' if a else ""
                return f"<{tag}{style}>{inline_md(txt)}</{tag}>"

            thead = "".join(cell_html("th", h, k) for k, h in enumerate(header))
            tbody = "".join(
                "<tr>" + "".join(cell_html("td", c, k) for k, c in enumerate(r))
                + "</tr>"
                for r in rows
            )
            out.append(f"<table><thead><tr>{thead}</tr></thead><tbody>{tbody}</tbody></table>")
            continue
        m = LIST_ITEM_RE.match(line)
        if m:
            base = len(m.group(1))
            first_ordered = m.group(2).endswith(".")
            block = [line]
            i += 1
            while i < n:
                ln = lines[i]
                if not ln.strip():
                    j = i + 1
                    if j < n:
                        nm = LIST_ITEM_RE.match(lines[j])
                        ind_j = len(lines[j]) - len(lines[j].lstrip())
                        if (nm and len(nm.group(1)) >= base) or ind_j >= base + 2:
                            block.append(ln)
                            i += 1
                            continue
                    break
                mm = LIST_ITEM_RE.match(ln)
                if mm:
                    if len(mm.group(1)) < base:
                        break
                    if (len(mm.group(1)) == base
                            and mm.group(2).endswith(".") != first_ordered):
                        break
                    block.append(ln)
                    i += 1
                    continue
                if len(ln) - len(ln.lstrip()) >= base + 2:
                    block.append(ln)
                    i += 1
                    continue
                break
            out.append(render_list_block(block))
            continue
        if re.match(r"^ {4,}\S", line):
            buf = []
            while i < n and (not lines[i].strip() or re.match(r"^ {4,}", lines[i])):
                buf.append(lines[i])
                i += 1
            while buf and not buf[-1].strip():
                buf.pop()
            code = "\n".join(l[4:] if l.startswith("    ") else l for l in buf)
            out.append("<pre><code>" + escape_html(code) + "</code></pre>")
            continue
        if not line.strip():
            i += 1
            continue
        buf = [line]
        i += 1
        while i < n and lines[i].strip() and not is_block_start(
                lines[i], lines[i + 1] if i + 1 < n else ""):
            buf.append(lines[i])
            i += 1
        out.append("<p>" + "<br>".join(inline_md(b) for b in buf) + "</p>")
    if props_html:
        out.insert(0, props_html)
    foot = render_footnotes()
    if foot:
        out.append(foot)
    return "\n".join(out)


def logo_svg(size=26, cls=""):
    gid = f"g{size}"
    classes = "logo" + (f" {cls}" if cls else "")
    return (
        f'<svg class="{classes}" width="{size}" height="{size}" viewBox="0 0 32 32" aria-hidden="true">'
        f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="#6366f1"/><stop offset="1" stop-color="#22d3ee"/>'
        f'</linearGradient></defs>'
        f'<rect width="32" height="32" rx="9" fill="url(#{gid})"/>'
        f'<g transform="translate(4 4)">'
        f'<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z" fill="#fff"/>'
        f'</g></svg>'
    )


FONT_LINK = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
             '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
             '<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400..700'
             '&family=Geist+Mono:wght@400..600&display=swap" rel="stylesheet">')

ICON_FILE = ('<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
             'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
             '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>'
             '<polyline points="14 2 14 8 20 8"/></svg>')

ICON_FOLDER = ('<svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
               'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
               '<path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg>')

ICON_SEARCH = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
               'stroke-width="2" stroke-linecap="round" aria-hidden="true">'
               '<circle cx="11" cy="11" r="7"/>'
               '<path d="m20.5 20.5-4.2-4.2"/></svg>')

ICON_GRID = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
             'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
             '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/>'
             '<rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/>'
             '<rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/>'
             '<rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/></svg>')

ICON_LIST = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
             'stroke-width="2" stroke-linecap="round" aria-hidden="true">'
             '<path d="M8.5 6H21M8.5 12H21M8.5 18H21"/>'
             '<circle cx="4" cy="6" r="1.3" fill="currentColor" stroke="none"/>'
             '<circle cx="4" cy="12" r="1.3" fill="currentColor" stroke="none"/>'
             '<circle cx="4" cy="18" r="1.3" fill="currentColor" stroke="none"/></svg>')

ICON_GITHUB = ('<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">'
               '<path d="M12 .5C5.73.5.99 5.24.99 11.5c0 4.86 3.15 8.98 7.52 10.43.55.1.75-.24.75-.53 '
               '0-.26-.01-.95-.01-1.84-3.06.66-3.71-1.48-3.71-1.48-.5-1.28-1.22-1.62-1.22-1.62-1-.68.08-.67.08-.67 '
               '1.11.08 1.69 1.14 1.69 1.14.98 1.69 2.57 1.2 3.2.92.1-.71.38-1.2.7-1.48-2.44-.28-5.01-1.22-5.01-5.44 '
               '0-1.2.43-2.18 1.13-2.95-.11-.28-.49-1.4.11-2.92 0 0 .92-.3 3.02 1.13a10.5 10.5 0 0 1 5.5 0c2.1-1.43 '
               '3.02-1.13 3.02-1.13.6 1.52.22 2.64.11 2.92.7.77 1.13 1.75 1.13 2.95 0 4.23-2.58 5.16-5.03 5.43.39.34 '
               '.74 1 .74 2.03 0 1.47-.01 2.65-.01 3.01 0 .29.2.64.76.53 4.36-1.46 7.51-5.57 7.51-10.43C23.01 5.24 '
               '18.27.5 12 .5z"/></svg>')

ICON_BELL = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
             'stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
             '<path d="M18 8a6 6 0 1 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/>'
             '<path d="M13.7 21a2 2 0 0 1-3.4 0"/></svg>')


def slugify(s):
    s = re.sub(r"[^\w]+", "-", s.lower()).strip("-")
    return s or "folder"


def sidebar_html(back, folders, active=None, total=0, is_index=False):
    idx = back + "index.html"
    parts = []
    cls = "nav-item active" if is_index else "nav-item"
    parts.append(
        f'<a class="{cls}" href="{idx}"><span class="ico">{ICON_FILE}</span>'
        f'<span>Все заметки</span><span class="nav-count">{total}</span></a>'
    )
    if folders:
        parts.append('<div class="nav-label">Папки</div>')
    for name, cnt in folders:
        slug = slugify(name)
        href = f"#folder-{slug}" if is_index else f"{back}index.html#folder-{slug}"
        cls = "nav-item active" if active == name else "nav-item"
        parts.append(
            f'<a class="{cls}" href="{href}"><span class="ico">{ICON_FOLDER}</span>'
            f'<span>{escape_html(name)}</span><span class="nav-count">{cnt}</span></a>'
        )
    return (
        f'<aside class="sidebar">\n'
        f'<a class="brand" href="{idx}">'
        f'<img class="logo avatar" src="{back}avatar.jpg" alt="" aria-hidden="true" '
        f'width="22" height="22"><span>AFK Notes</span></a>\n'
        f'<label class="search">{ICON_SEARCH}'
        f'<input id="q" type="search" placeholder="Поиск заметок" '
        f'data-index="{idx}" autocomplete="off"><kbd>/</kbd></label>\n'
        f'<nav class="nav" aria-label="Навигация">\n'
        + "\n".join(parts)
        + '\n</nav>\n'
        f'<div class="side-foot">'
        f'{gh_anchor("", ICON_GITHUB + "<span>GitHub</span>")}\n'
        f'</div>\n'
        f'</aside>'
    )


SITE_JS = """
(function () {
  var q = document.getElementById('q');
  var cards = [].slice.call(document.querySelectorAll('.card'));
  var folders = [].slice.call(document.querySelectorAll('.folder'));
  var rcount = document.getElementById('rcount');
  var nores = document.getElementById('nores');
  var total = cards.length;
  function plural(n) {
    var a = n % 10, b = n % 100;
    if (a === 1 && b !== 11) return n + ' заметка';
    if (a >= 2 && a <= 4 && (b < 12 || b > 14)) return n + ' заметки';
    return n + ' заметок';
  }
  function apply(v) {
    v = (v || '').trim().toLowerCase();
    var shown = 0;
    cards.forEach(function (c) {
      var hay = (c.getAttribute('data-search') || c.textContent).toLowerCase();
      var ok = !v || hay.indexOf(v) !== -1;
      c.hidden = !ok;
      if (ok) shown++;
    });
    folders.forEach(function (f) {
      var any = [].slice.call(f.querySelectorAll('.card'))
        .some(function (c) { return !c.hidden; });
      f.hidden = !!v && !any;
    });
    if (rcount) rcount.textContent = v ? shown + ' из ' + total : plural(total);
    if (nores) nores.hidden = !(v && shown === 0 && total > 0);
  }
  if (q) {
    var init = new URLSearchParams(location.search).get('q');
    if (init) { q.value = init; apply(init); }
    q.addEventListener('input', function () {
      if (cards.length) apply(q.value);
    });
    q.addEventListener('keydown', function (e) {
      if (e.key === 'Enter') {
        e.preventDefault();
        if (!cards.length) {
          var base = q.getAttribute('data-index') || 'index.html';
          location.href = base + (q.value ? '?q=' + encodeURIComponent(q.value) : '');
        }
      } else if (e.key === 'Escape') {
        q.value = '';
        apply('');
        q.blur();
      }
    });
  }
  document.addEventListener('keydown', function (e) {
    if (e.key !== '/' || e.ctrlKey || e.metaKey || e.altKey) return;
    var t = document.activeElement;
    if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return;
    if (q) { e.preventDefault(); q.focus(); q.select(); }
  });
  var tgs = [].slice.call(document.querySelectorAll('.tg'));
  function setView(v) {
    [].slice.call(document.querySelectorAll('.cards')).forEach(function (el) {
      el.classList.toggle('list', v === 'list');
    });
    tgs.forEach(function (b) {
      b.setAttribute('aria-pressed',
        b.getAttribute('data-view') === v ? 'true' : 'false');
    });
    try { localStorage.setItem('afk-view', v); } catch (err) {}
  }
  if (tgs.length) {
    var saved = 'grid';
    try { saved = localStorage.getItem('afk-view') || 'grid'; } catch (err) {}
    setView(saved);
    tgs.forEach(function (b) {
      b.addEventListener('click', function () {
        setView(b.getAttribute('data-view'));
      });
    });
  }
})();
"""

PAGE_CSS = """
:root { color-scheme: dark;
  --bg: #000; --panel: #0a0a0a; --panel2: #111;
  --border: #1f1f1f; --border2: #2e2e2e; --hover: #1a1a1a;
  --text: #ededed; --muted: #a1a1aa; --dim: #71717a;
  --font-body: 'Geist', 'Segoe UI', system-ui, -apple-system, sans-serif;
  --font-head: 'Geist', 'Segoe UI', system-ui, -apple-system, sans-serif;
  --font-mono: 'Geist Mono', 'DM Mono', Consolas, monospace; }
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: var(--bg); color: var(--text);
  font-family: var(--font-body); font-size: 0.875rem; line-height: 1.6;
  -webkit-font-smoothing: antialiased; }
::selection { background: #3f3f46; color: #fff; }
a { color: inherit; text-decoration: none; }
a:focus-visible, button:focus-visible, input:focus-visible {
  outline: 2px solid #fff; outline-offset: 2px; border-radius: 4px; }
[hidden] { display: none !important; }
::-webkit-scrollbar { width: 10px; height: 10px; }
::-webkit-scrollbar-track { background: var(--bg); }
::-webkit-scrollbar-thumb { background: #262626; border-radius: 6px;
  border: 2px solid var(--bg); }
::-webkit-scrollbar-thumb:hover { background: #3f3f46; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { animation: none !important; transition: none !important; } }

.skip { position: absolute; left: -9999px; top: 0; z-index: 100;
  background: #fff; color: #000; font-weight: 600;
  padding: 10px 16px; border-radius: 0 0 8px 0; }
.skip:focus { left: 0; top: 0; }

.app { display: grid; grid-template-columns: 240px minmax(0, 1fr);
  min-height: 100vh; }
.sidebar { position: sticky; top: 0; height: 100vh; overflow-y: auto;
  border-right: 1px solid var(--border); padding: 14px 12px 12px;
  display: flex; flex-direction: column; gap: 14px; background: var(--bg); }
.main-col { min-width: 0; display: flex; flex-direction: column; }

.brand { display: flex; align-items: center; gap: 8px; color: #fff;
  font-weight: 600; font-size: 0.875rem; letter-spacing: -0.01em;
  padding: 2px 6px 0; }
.brand .logo { border-radius: 7px; }
.brand .avatar { border-radius: 50%; object-fit: cover; display: block; }
.search { display: flex; align-items: center; gap: 8px; height: 34px;
  padding: 0 8px; border: 1px solid var(--border); border-radius: 8px;
  background: var(--panel); color: var(--dim); cursor: text; }
.search:focus-within { border-color: #3f3f46; }
.search svg { flex: none; width: 14px; height: 14px; }
.search input { flex: 1; min-width: 0; background: none; border: none;
  outline: none; color: var(--text); font: inherit; font-size: 0.8125rem; }
.search input::placeholder { color: var(--dim); }
.search input::-webkit-search-cancel-button { -webkit-appearance: none; }
.search kbd { font-family: var(--font-mono); font-size: 0.625rem; line-height: 1;
  border: 1px solid var(--border2); border-radius: 4px; padding: 3px 5px;
  color: var(--dim); background: var(--panel2); }
.nav { display: flex; flex-direction: column; gap: 1px; }
.nav-label { font-size: 0.6875rem; font-weight: 500; text-transform: uppercase;
  letter-spacing: 0.06em; color: var(--dim); padding: 8px 8px 4px; }
.nav-item { display: flex; align-items: center; gap: 8px; padding: 6px 8px;
  border-radius: 6px; color: var(--muted); font-size: 0.84375rem;
  font-weight: 500; transition: background .12s, color .12s; }
.nav-item:hover { background: var(--hover); color: var(--text); }
.nav-item.active { background: var(--hover); color: #fff; }
.nav-item .ico { display: flex; color: var(--dim); }
.nav-item.active .ico { color: var(--text); }
.nav-item svg { width: 15px; height: 15px; flex: none; }
.nav-count { margin-left: auto; font-size: 0.71875rem; color: var(--dim);
  font-variant-numeric: tabular-nums; }
.side-foot { margin-top: auto; border-top: 1px solid var(--border);
  padding-top: 10px; }
.side-foot a { display: flex; align-items: center; gap: 8px; padding: 6px 8px;
  border-radius: 6px; color: var(--muted); font-size: 0.8125rem;
  font-weight: 500; transition: background .12s, color .12s; }
.side-foot a:hover { background: var(--hover); color: var(--text); }
.side-foot svg { width: 15px; height: 15px; flex: none; }

.topbar { position: sticky; top: 0; z-index: 20; display: flex;
  align-items: center; gap: 12px; min-height: 52px; padding: 0 24px;
  border-bottom: 1px solid var(--border); background: var(--bg); }
.tb-title { font-size: 0.875rem; font-weight: 600; color: #fff; }
.crumbs { display: flex; align-items: center; gap: 8px; min-width: 0;
  font-size: 0.8125rem; }
.crumb { color: var(--muted); white-space: nowrap; }
.crumb:hover { color: var(--text); }
.crumb-sep { color: #3f3f46; }
.crumb-current { color: var(--text); font-weight: 500; overflow: hidden;
  text-overflow: ellipsis; white-space: nowrap; }
.tb-right { margin-left: auto; display: flex; align-items: center; gap: 12px;
  flex: none; }
.btn-ghost { display: inline-flex; align-items: center; gap: 6px;
  height: 32px; padding: 0 12px; border: 1px solid var(--border);
  border-radius: 8px; background: var(--panel); color: var(--text);
  font-size: 0.8125rem; font-weight: 500; white-space: nowrap;
  transition: border-color .12s, background .12s; }
.btn-ghost:hover { background: var(--panel2); border-color: #3f3f46; }
.tb-gh { display: inline-flex; align-items: center; justify-content: center;
  width: 32px; height: 32px; border: 1px solid var(--border);
  border-radius: 8px; background: var(--panel); color: var(--dim);
  transition: border-color .12s, background .12s, color .12s; }
.tb-gh:hover { background: var(--panel2); border-color: #3f3f46; color: var(--text); }
.tb-gh svg { width: 15px; height: 15px; }

main { flex: 1; width: 100%; max-width: 1120px; margin: 0 auto;
  padding: 28px 28px 90px; }
.page-head h1 { font-size: 1.375rem; font-weight: 600;
  letter-spacing: -0.02em; color: #fff; margin: 0 0 6px; }
.page-sub { color: var(--dim); font-size: 0.84375rem; margin: 0; }
.stats { display: flex; flex-wrap: wrap; gap: 6px 16px; color: var(--dim);
  font-size: 0.8125rem; margin-top: 8px; font-variant-numeric: tabular-nums; }
.stats b { color: var(--muted); font-weight: 500; }
.toolbar { display: flex; align-items: center; justify-content: space-between;
  gap: 12px; margin: 26px 0 14px; }
.result-count { color: var(--dim); font-size: 0.8125rem;
  font-variant-numeric: tabular-nums; }
.toggle { display: flex; border: 1px solid var(--border); border-radius: 8px;
  overflow: hidden; background: var(--panel); }
.tg { width: 34px; height: 30px; display: grid; place-items: center;
  background: none; border: none; color: var(--dim); cursor: pointer;
  padding: 0; }
.tg + .tg { border-left: 1px solid var(--border); }
.tg:hover { color: var(--text); }
.tg[aria-pressed="true"] { background: var(--hover); color: #fff; }
.tg svg { width: 15px; height: 15px; }

.folder { margin: 0 0 34px; scroll-margin-top: 68px; }
.folder-head { display: flex; align-items: center; gap: 10px;
  margin-bottom: 12px; }
.fi { width: 28px; height: 28px; border-radius: 7px; flex: none;
  background: var(--panel2); border: 1px solid var(--border2);
  display: flex; align-items: center; justify-content: center;
  color: var(--muted); }
.fi svg { width: 15px; height: 15px; }
.folder-head h2 { font-size: 0.875rem; font-weight: 600; color: #d4d4d8;
  margin: 0; }
.count { margin-left: auto; color: var(--dim); font-size: 0.78125rem;
  font-variant-numeric: tabular-nums; }
.cards { display: grid;
  grid-template-columns: repeat(auto-fill, minmax(270px, 1fr)); gap: 12px; }
.card { display: flex; flex-direction: column; gap: 10px; padding: 16px;
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 12px; color: inherit; min-width: 0;
  transition: border-color .15s, background .15s; }
.card:hover { border-color: #333; background: var(--panel2); }
.card-ic { width: 34px; height: 34px; border-radius: 8px; flex: none;
  background: var(--panel2); border: 1px solid var(--border2);
  display: flex; align-items: center; justify-content: center;
  color: var(--muted); }
.card-body { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
.card-title { font-size: 0.875rem; font-weight: 600; color: #fff;
  line-height: 1.35; overflow: hidden;
  display: -webkit-box; -webkit-line-clamp: 2;
  -webkit-box-orient: vertical; }
.card-path { font-family: var(--font-mono); font-size: 0.71875rem;
  color: var(--dim); word-break: break-all; }
.card-time { display: flex; justify-content: space-between; align-items: center;
  gap: 8px; border-top: 1px solid var(--border); padding-top: 10px;
  font-size: 0.78125rem; color: var(--dim);
  font-variant-numeric: tabular-nums; }
.card .arr { opacity: 0; transform: translateX(-4px); transition: .15s;
  color: var(--muted); }
.card:hover .arr { opacity: 1; transform: none; }

.cards.list { grid-template-columns: 1fr; gap: 8px; }
.cards.list .card { flex-direction: row; align-items: center; gap: 14px;
  padding: 12px 16px; }
.cards.list .card-body { flex: 1; }
.cards.list .card-time { border-top: none; padding-top: 0; flex: none; }
.cards.list .card-title { -webkit-line-clamp: 1; }

.empty { background: var(--panel); border: 1px dashed var(--border2);
  border-radius: 12px; padding: 56px 24px; text-align: center;
  color: var(--muted); }
.empty .ei { display: flex; justify-content: center; margin-bottom: 14px;
  color: var(--dim); }
.empty .ei svg { width: 22px; height: 22px; }
.empty p { margin: 0 auto; max-width: 380px; }

.np-date { color: var(--dim); font-size: 0.78125rem;
  font-variant-numeric: tabular-nums; }
.content { background: var(--panel); border: 1px solid var(--border);
  border-radius: 12px; padding: 8px 40px 40px; }
h1, h2, h3, h4, h5, h6 { line-height: 1.3; color: #fff;
  letter-spacing: -0.015em; font-family: var(--font-head);
  font-weight: 600; }
.content h1 { font-size: 1.875rem; margin: 26px 0 16px; border: none; }
.content h2 { font-size: 1.3125rem; margin: 34px 0 12px; border: none; }
.content h3 { font-size: 1.0625rem; margin: 26px 0 10px; }
.content h4, .content h5, .content h6 { font-size: 0.9375rem;
  margin: 20px 0 8px; }
.content p { margin: 12px 0; color: #d4d4d8; }
.content a { color: #fff; text-decoration: underline;
  text-decoration-color: #52525b; text-underline-offset: 2px; }
.content a:hover { text-decoration-color: #fff; }
.content ul, .content ol { padding-left: 24px; margin: 12px 0;
  color: #d4d4d8; }
.content li { margin: 6px 0; }
.content li.task { list-style: none; }
.content li.task input { margin-right: 6px; accent-color: #d4d4d8; }
.content code { background: #1a1a1a; color: #d4d4d8; padding: 2px 6px;
  border-radius: 5px; border: 1px solid var(--border);
  font-family: var(--font-mono); font-size: 0.86em; }
.content pre { background: #000; border: 1px solid var(--border);
  border-radius: 10px; padding: 16px 18px; overflow-x: auto; margin: 16px 0; }
.content pre code { background: none; border: none; color: #e4e4e7;
  padding: 0; font-size: 0.8125rem; line-height: 1.6; }
.content blockquote { margin: 18px 0; padding: 12px 18px;
  border-left: 3px solid #3f3f46; background: #0d0d0d;
  border-radius: 0 8px 8px 0; color: var(--muted); }
.content table { border-collapse: collapse; margin: 18px 0; width: 100%;
  display: block; overflow-x: auto; }
.content th, .content td { border: 1px solid var(--border2);
  padding: 8px 12px; text-align: left; font-size: 0.84375rem; }
.content th { background: #141414; color: #fff; font-weight: 600; }
.content td { color: #d4d4d8; }
.content tr:nth-child(2n) { background: rgba(255,255,255,.02); }
.content img { max-width: 100%; border-radius: 10px;
  border: 1px solid var(--border); display: block; margin: 18px 0; }
.content hr { border: none; height: 1px; margin: 30px 0;
  background: var(--border2); }
.content mark { background: #facc15; color: #111; padding: 0 5px;
  border-radius: 4px; }
.content .wl { color: var(--muted); border-bottom: 1px dashed #52525b; }
.content strong { color: #fff; }
.content .meta { color: var(--dim); font-size: 0.8125rem; }
.stat, .count, .card-time, .meta, .np-date, .nav-count, .stats {
  font-variant-numeric: tabular-nums; }

.content .hashtag { color: #818cf8; }
.content .callout { margin: 16px 0; border: 1px solid var(--border2);
  border-left: 3px solid var(--c, #71717a); border-radius: 8px;
  background: color-mix(in srgb, var(--c, #71717a) 8%, transparent); }
.content .callout-title { display: flex; align-items: center; gap: 8px;
  margin: 0; padding: 10px 14px; font-weight: 600; font-size: 0.875rem;
  color: var(--c, #d4d4d8); }
.content .callout-ic { line-height: 1; }
.content .callout-content { padding: 0 14px 12px; color: #d4d4d8; }
.content .callout-content > :first-child { margin-top: 0; }
.content .callout-content > :last-child { margin-bottom: 0; }
.content details.callout > summary { cursor: pointer; list-style: none; }
.content details.callout > summary::-webkit-details-marker { display: none; }
.content details.callout > summary::after { content: "\\203A"; margin-left: auto;
  color: var(--dim); font-weight: 400; transition: transform .15s; }
.content details.callout[open] > summary::after { transform: rotate(90deg); }
.content .props { border: 1px solid var(--border); border-radius: 8px;
  padding: 8px 0; margin: 4px 0 18px; background: var(--panel2); }
.content .prop { display: flex; gap: 12px; padding: 4px 14px;
  font-size: 0.8125rem; }
.content .prop-k { color: var(--dim); min-width: 110px; flex: none; }
.content .prop-v { color: #d4d4d8; word-break: break-word; }
.content .footnotes { border-top: 1px solid var(--border2);
  margin-top: 26px; padding-top: 10px; }
.content .footnotes .fn { font-size: 0.8125rem; color: var(--muted);
  margin: 8px 0; }
.content .footnotes .fn b { color: var(--dim); font-weight: 500;
  font-variant-numeric: tabular-nums; }
.content .fnref a { color: #818cf8; text-decoration: none; }
.content .math-block { margin: 18px 0; text-align: center; overflow-x: auto; }
.content .math-inline { font-family: var(--font-mono); }
.content .mermaid { margin: 18px 0; text-align: center;
  background: var(--panel2); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px; font-family: var(--font-mono);
  font-size: 0.8125rem; white-space: pre-wrap; }

@media (max-width: 820px) {
  .app { grid-template-columns: 1fr; }
  .sidebar { position: static; height: auto; border-right: none;
    border-bottom: 1px solid var(--border); }
  .side-foot { margin-top: 4px; }
  .nav { flex-direction: row; flex-wrap: wrap; }
  .nav-label { width: 100%; padding-top: 4px; }
  .nav-count { margin-left: 6px; }
  .topbar { padding: 0 16px; }
  main { padding: 20px 16px 70px; }
  .content { padding: 4px 18px 26px; }
  .cards { grid-template-columns: 1fr; }
}
"""


def page_html(title, body, site_path, folder="", mtime="", folders=None):
    depth = site_path.count("/")
    back = "../" * depth
    slug = slugify(folder) if folder else ""
    crumbs = [f'<a class="crumb" href="{back}index.html">Все заметки</a>']
    if folder:
        crumbs.append('<span class="crumb-sep" aria-hidden="true">/</span>')
        crumbs.append(
            f'<a class="crumb" href="{back}index.html#folder-{slug}">'
            f'{escape_html(folder)}</a>'
        )
    crumbs.append('<span class="crumb-sep" aria-hidden="true">/</span>')
    crumbs.append(f'<span class="crumb-current">{escape_html(title)}</span>')
    date = f'<span class="np-date">{escape_html(mtime)}</span>' if mtime else ""
    folders = folders or []
    total = sum(c for _, c in folders)
    extra_head = ""
    extra_js = ""
    if "katex" in PAGE_FEATS:
        extra_head = ('<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/'
                      'katex@0.16/dist/katex.min.css" crossorigin="anonymous">')
        extra_js += (
            '<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16/dist/'
            'katex.min.js" crossorigin="anonymous"></script>\n'
            '<script defer src="https://cdn.jsdelivr.net/npm/katex@0.16/dist/'
            'contrib/auto-render.min.js" crossorigin="anonymous"></script>\n'
            '<script>window.addEventListener("load",function(){var el='
            'document.querySelector(".content");'
            'if(el&&window.renderMathInElement)renderMathInElement(el,'
            '{delimiters:[{left:"\\\\[",right:"\\\\]",display:!0},'
            '{left:"\\\\(",right:"\\\\)",display:!1}]});});</script>'
        )
    if "mermaid" in PAGE_FEATS:
        extra_js += (
            '<script type="module">import mermaid from "https://cdn.jsdelivr.net/'
            'npm/mermaid@11/dist/mermaid.esm.min.mjs";'
            'mermaid.initialize({startOnLoad:!0,theme:"dark"});</script>'
        )
    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape_html(title)}</title>
{FONT_LINK}
<link rel="icon" href="{back}favicon.svg" type="image/svg+xml">
{extra_head}
<style>{PAGE_CSS}</style>
</head>
<body>
<a class="skip" href="#content">Перейти к содержимому</a>
<div class="app">
{sidebar_html(back, folders, folder, total, False)}
<div class="main-col">
<header class="topbar">
<nav class="crumbs" aria-label="Хлебные крошки">{''.join(crumbs)}</nav>
<span class="tb-right">{date}{gh_anchor("tb-gh", ICON_GITHUB)}<a class="btn-ghost" href="{back}index.html">&larr; Все заметки</a></span>
</header>
<main id="content">
<article class="content">
{body}
</article>
</main>
</div>
</div>
{extra_js}
<script>{SITE_JS}</script>
</body>
</html>
"""


def plural_notes(n):
    if n % 10 == 1 and n % 100 != 11:
        w = "заметка"
    elif 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        w = "заметки"
    else:
        w = "заметок"
    return f"{n} {w}"


def build_index(cfg, notes, folder_names):
    groups = {}
    for note in notes:
        groups.setdefault(note["folder"], []).append(note)
    folders_sorted = sorted(groups)
    folders_html = []
    for folder in folders_sorted:
        items = sorted(groups[folder], key=lambda x: x["title"].lower())
        slug = slugify(folder)
        cards = []
        for it in items:
            hay = escape_html(f'{it["title"]} {it["rel"]} {folder}')
            cards.append(
                f'<a class="card" href="{url_for(it["site"])}" data-search="{hay}">'
                f'<span class="card-ic">{ICON_FILE}</span>'
                f'<span class="card-body">'
                f'<span class="card-title">{escape_html(it["title"])}</span>'
                f'<span class="card-path">{escape_html(it["rel"])}</span>'
                f'</span>'
                f'<span class="card-time"><span>{escape_html(it["mtime"])}</span>'
                f'<span class="arr" aria-hidden="true">&rarr;</span></span></a>'
            )
        folders_html.append(
            f'<section class="folder" id="folder-{slug}" aria-labelledby="fh-{slug}">'
            f'<div class="folder-head">'
            f'<span class="fi">{ICON_FOLDER}</span>'
            f'<h2 id="fh-{slug}">{escape_html(folder)}</h2>'
            f'<span class="count">{plural_notes(len(items))}</span>'
            f'</div><div class="cards">{"".join(cards)}</div></section>'
        )
    empty = ('<div class="empty"><div class="ei">' + ICON_BELL + '</div>'
             '<p>Пока нет заметок. Добавь папку в afk.py '
             'и сохрани файл в Obsidian.</p></div>' if not notes else "")
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    side_folders = [(f, len(groups[f])) for f in folders_sorted]
    body = f"""
<div class="page-head">
<h1>Заметки</h1>
<p class="page-sub">Из Obsidian — публикуются автоматически, как только сохранил файл</p>
<div class="stats"><span><b>{plural_notes(len(notes))}</b></span><span><b>{len(groups)}</b> папок</span></div>
</div>
<div class="toolbar">
<span class="result-count" id="rcount">{plural_notes(len(notes))}</span>
<div class="toggle" role="group" aria-label="Вид отображения">
<button type="button" class="tg" data-view="grid" aria-pressed="true" aria-label="Сетка">{ICON_GRID}</button>
<button type="button" class="tg" data-view="list" aria-pressed="false" aria-label="Список">{ICON_LIST}</button>
</div>
</div>
{empty}
{"".join(folders_html)}
<div class="empty" id="nores" hidden><div class="ei">{ICON_BELL}</div>
<p>Ничего не найдено. Попробуй другой запрос.</p></div>
"""
    html = f"""<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AFK Notes</title>
{FONT_LINK}
<link rel="icon" href="favicon.svg" type="image/svg+xml">
<style>{PAGE_CSS}</style>
</head>
<body>
<a class="skip" href="#content">Перейти к содержимому</a>
<div class="app">
{sidebar_html("", side_folders, None, len(notes), True)}
<div class="main-col">
<header class="topbar">
<span class="tb-title">Все заметки</span>
<span class="tb-right"><span class="np-date">обновлено {now}</span>{gh_anchor("tb-gh", ICON_GITHUB)}</span>
</header>
<main id="content">
{body}
</main>
</div>
</div>
<script>{SITE_JS}</script>
</body>
</html>
"""
    index_path = REPO_DIR / "index.html"
    old = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    if old != html:
        index_path.write_text(html, encoding="utf-8")
        return True
    return False


def folder_display_names(folders):
    names = {}
    used = set()
    for f in folders:
        base = Path(f).name or "vault"
        name = base
        k = 2
        while name.lower() in used:
            name = f"{base}_{k}"
            k += 1
        used.add(name.lower())
        names[f] = name
    return names


def git(*args, cwd=None):
    return subprocess.run(
        ["git"] + list(args),
        cwd=str(cwd or REPO_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        creationflags=0x08000000 if os.name == "nt" else 0,
    )


def ensure_repo():
    if not (REPO_DIR / ".git").exists():
        if not REPO_URL:
            return False, "Репозиторий не задан — запусти: py afk.py --setup"
        REPO_DIR.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            ["git", "clone", REPO_URL, str(REPO_DIR)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        if r.returncode != 0:
            return False, r.stderr.strip()
    return True, ""


def collect_files(cfg):
    found = []
    for folder in cfg["folders"]:
        root = Path(folder)
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            try:
                rel = path.relative_to(root)
            except ValueError:
                continue
            if any(part in SKIP_DIRS or part.startswith(".") for part in rel.parts):
                continue
            if path.suffix.lower() not in ASSET_EXT and path.suffix.lower() != ".md":
                continue
            found.append((folder, path, rel))
    return found


def publish(cfg, quiet=False, dry_run=False):
    ok, err = ensure_repo()
    if not ok:
        return [], f"Ошибка репозитория: {err}"

    files = collect_files(cfg)
    folder_names = folder_display_names(cfg["folders"])
    folder_counts = {}
    for folder, path, rel in files:
        if path.suffix.lower() == ".md":
            name = folder_names[folder]
            folder_counts[name] = folder_counts.get(name, 0) + 1
    folders_list = sorted(folder_counts.items())
    state = cfg["state"]
    changes = []

    stems = {}
    for folder, path, rel in files:
        if path.suffix.lower() == ".md":
            stems[path.stem.lower()] = None
    for folder, path, rel in files:
        if path.suffix.lower() == ".md":
            site = Path("notes") / folder_names[folder] / rel.with_suffix(".html")
            stems[path.stem.lower()] = str(site)

    global WIKI, ASSETS
    WIKI = stems
    ASSETS = {}
    for folder, path, rel in files:
        if path.suffix.lower() in ASSET_EXT:
            site = Path("notes") / folder_names[folder] / rel
            ASSETS[str(rel).replace("\\", "/").lower()] = str(site)
            ASSETS[path.name.lower()] = str(site)

    seen = set()
    notes = []
    for folder, path, rel in files:
        key = str(path.resolve())
        seen.add(key)
        ext = path.suffix.lower()
        if ext == ".md":
            site = Path("notes") / folder_names[folder] / rel.with_suffix(".html")
        else:
            site = Path("notes") / folder_names[folder] / rel
        h = hash_file(path)
        old = state.get(key)
        if old and old.get("hash") == h and (REPO_DIR / site).exists():
            if ext == ".md":
                notes.append(
                    {"folder": folder_names[folder], "site": str(site).replace("\\", "/"),
                     "title": old.get("title", path.stem), "rel": str(rel).replace("\\", "/"),
                     "mtime": old.get("mtime", "")}
                )
            continue
        dest = REPO_DIR / site
        if not dry_run:
            dest.parent.mkdir(parents=True, exist_ok=True)
            if ext == ".md":
                text = path.read_text(encoding="utf-8", errors="replace").lstrip("﻿")
                title = path.stem
                for ln in text.split("\n"):
                    mm = re.match(r"^#\s+(.+)$", ln.strip())
                    if mm:
                        title = mm.group(1).strip()
                        break
                PAGE_FEATS.clear()
                body = md_to_html(text)
                mtime = datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
                dest.write_text(page_html(title, body, str(site).replace("\\", "/"),
                                          folder_names[folder], mtime,
                                          folders=folders_list), encoding="utf-8")
                state[key] = {"hash": h, "site": str(site).replace("\\", "/"),
                              "title": title, "mtime": mtime}
                notes.append({"folder": folder_names[folder], "site": str(site).replace("\\", "/"),
                              "title": title, "rel": str(rel).replace("\\", "/"), "mtime": mtime})
            else:
                shutil.copy2(path, dest)
                state[key] = {"hash": h, "site": str(site).replace("\\", "/"), "mtime": ""}
        kind = "new" if not old else "upd"
        changes.append((kind, str(rel).replace("\\", "/"), folder_names[folder]))

    for key in list(state.keys()):
        if key in seen:
            continue
        p = Path(key)
        root = None
        for f in cfg["folders"]:
            base = str(Path(f).resolve())
            if str(p) == base or str(p).startswith(base + os.sep):
                root = Path(f)
                break
        if root is not None and not root.exists():
            continue
        entry = state.pop(key)
        site_file = REPO_DIR / entry.get("site", "")
        if site_file.exists():
            site_file.unlink()
        changes.append(("del", entry.get("site", key), ""))

    if dry_run:
        return changes, ""

    build_index_from_state(cfg, folder_names)

    git("add", "-A")
    st = git("status", "--porcelain")
    committed = False
    if st.stdout.strip():
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        git("commit", "-m", f"publish {now} ({len(changes)} files)")
        committed = True
    if changes and committed:
        entry = {
            "time": datetime.now().isoformat(timespec="seconds"),
            "files": [c[1] for c in changes],
            "commit": git("rev-parse", "--short", "HEAD").stdout.strip(),
            "count": len(changes),
        }
        cfg["history"].insert(0, entry)
        cfg["history"] = cfg["history"][:100]
    if changes or committed:
        save_config(cfg)
    ahead = git("rev-list", "--count", "@{u}..HEAD")
    n_ahead = 0
    if ahead.returncode == 0 and ahead.stdout.strip().isdigit():
        n_ahead = int(ahead.stdout.strip())
    if n_ahead > 0:
        r = git("push", "origin", "main")
        if r.returncode != 0:
            git("pull", "--rebase", "origin", "main")
            r = git("push", "origin", "main")
        if r.returncode != 0:
            return changes, f"Push failed: {(r.stderr or r.stdout).strip()}"
    if changes and committed:
        commit = git("rev-parse", "--short", "HEAD").stdout.strip()
        return changes, f"OK commit {commit} -> {SITE_URL}"
    if changes:
        return changes, f"OK (git без различий) -> {SITE_URL}"
    if n_ahead > 0:
        return changes, f"OK push -> {SITE_URL}"
    return changes, None


def build_index_from_state(cfg, folder_names):
    notes = []
    for key, entry in cfg["state"].items():
        site = entry.get("site", "")
        if not site.startswith("notes/") or not site.endswith(".html"):
            continue
        parts = site.split("/")
        if len(parts) < 3:
            continue
        notes.append(
            {"folder": parts[1], "site": site,
             "title": entry.get("title", Path(site).stem),
             "rel": "/".join(parts[2:]), "mtime": entry.get("mtime", "")}
        )
    build_index(cfg, notes, folder_names)


def print_header():
    print(f"{C.BG}{C.WHITE}{C.BOLD}  AFK  ->  GitHub Pages  {C.R}  {C.DIM}{SITE_URL}{C.R}")
    print()


def print_menu(cfg):
    folders = cfg["folders"]
    last = cfg["history"][0] if cfg["history"] else None
    print(f"  {C.CYAN}1{C.R}) Папки        {C.DIM}[{len(folders)} подключено]{C.R}")
    print(f"  {C.CYAN}2{C.R}) Опубликовать сейчас")
    print(f"  {C.CYAN}3{C.R}) Авто-режим    {C.DIM}(следить за сохранениями){C.R}")
    print(f"  {C.CYAN}4{C.R}) История пушей {C.DIM}[{len(cfg['history'])} записей]{C.R}")
    print(f"  {C.CYAN}5{C.R}) Открыть сайт в браузере")
    print(f"  {C.CYAN}6{C.R}) Статус")
    wpid = watch_status()
    if wpid:
        print(f"  {C.CYAN}7{C.R}) Фоновый режим  {C.GREEN}вкл (pid {wpid}){C.R}")
    else:
        print(f"  {C.CYAN}7{C.R}) Фоновый режим  {C.DIM}выкл{C.R}")
    print(f"  {C.RED}0{C.R}) Выход")
    if last:
        t = last["time"].replace("T", " ")
        print(f"\n  {C.DIM}Последний пуш: {t} — {last['count']} файл(ов), commit {last['commit']}{C.R}")
    print()


def show_folders(cfg):
    while True:
        print(f"\n{C.BOLD}Папки для публикации{C.R}")
        if not cfg["folders"]:
            print(f"  {C.DIM}(нет папок){C.R}")
        for i, f in enumerate(cfg["folders"], 1):
            exists = Path(f).exists()
            mark = f"{C.GREEN}OK{C.R}" if exists else f"{C.RED}НЕТ{C.R}"
            count = 0
            if exists:
                count = sum(1 for _ in Path(f).rglob("*.md"))
            print(f"  {C.CYAN}{i}{C.R}) [{mark}] {f}  {C.DIM}({count} md){C.R}")
        print(f"\n  {C.CYAN}a{C.R}) Добавить папку")
        print(f"  {C.CYAN}r{C.R}) Удалить папку")
        print(f"  {C.CYAN}0{C.R}) Назад")
        choice = input(f"\n{C.BOLD}> {C.R}").strip().lower()
        if choice == "0":
            return
        elif choice == "a":
            path = input("Путь к папке: ").strip().strip('"')
            if not path:
                continue
            p = Path(path)
            if not p.exists():
                print(f"  {C.RED}Папка не существует: {path}{C.R}")
                continue
            if path in cfg["folders"]:
                print(f"  {C.YELLOW}Уже добавлена{C.R}")
                continue
            cfg["folders"].append(str(p))
            save_config(cfg)
            print(f"  {C.GREEN}Добавлена: {p}{C.R}")
        elif choice == "r":
            if not cfg["folders"]:
                continue
            idx = input("Номер папки: ").strip()
            try:
                i = int(idx) - 1
                removed = cfg["folders"].pop(i)
                for key in list(cfg["state"].keys()):
                    if str(key).startswith(str(Path(removed).resolve()) + os.sep) or str(key) == str(Path(removed).resolve()):
                        entry = cfg["state"].pop(key)
                        sf = REPO_DIR / entry.get("site", "")
                        if sf.exists():
                            sf.unlink()
                save_config(cfg)
                print(f"  {C.YELLOW}Удалена: {removed}{C.R}")
                print(f"  {C.DIM}Опубликованная копия на сайте будет убрана при следующей публикации.{C.R}")
            except (ValueError, IndexError):
                print(f"  {C.RED}Неверный номер{C.R}")


def do_publish(cfg):
    print(f"\n  {C.DIM}Сканирую...{C.R}")
    changes, msg = publish(cfg)
    if not changes:
        print(f"  {C.GREEN}Изменений нет — всё уже опубликовано.{C.R}")
        return
    for kind, rel, folder in changes:
        if kind == "new":
            print(f"  {C.GREEN}+ новая{C.R}  {folder}/{rel}")
        elif kind == "upd":
            print(f"  {C.YELLOW}~ изменена{C.R} {folder}/{rel}")
        else:
            print(f"  {C.RED}- удалена{C.R} {rel}")
    if msg:
        color = C.GREEN if msg.startswith("OK") else C.RED
        print(f"\n  {color}{msg}{C.R}")


def files_sig(cfg):
    sig = {}
    for _folder, path, _rel in collect_files(cfg):
        try:
            st = path.stat()
            sig[str(path)] = (st.st_mtime_ns, st.st_size)
        except OSError:
            pass
    return sig


def iter_debounced_publish():
    """Публикация только после IDLE_SECONDS без изменений файлов.

    Yields: ("wait", None, msg) — начали ждать;
            ("pub", changes, msg) — после тишины опубликовано;
            ("err", None, msg) — ошибка.
    """
    last_sig = None
    last_change = time.time() - IDLE_SECONDS
    while True:
        try:
            cfg = load_config()
            sig = files_sig(cfg)
            now = time.time()
            if last_sig is None:
                last_sig = sig
            if sig != last_sig:
                fresh = last_change is None
                last_sig = sig
                last_change = now
                if fresh:
                    yield "wait", None, f"change detected, waiting {IDLE_SECONDS}s before publish"
            elif last_change is not None and now - last_change >= IDLE_SECONDS:
                changes, msg = publish(cfg, quiet=True)
                failed = bool(msg) and not str(msg).startswith("OK")
                last_change = now if failed else None
                if changes or msg:
                    yield "pub", changes, msg
        except Exception as e:
            last_change = time.time()
            yield "err", None, f"ERROR {type(e).__name__}: {e}"
        time.sleep(POLL_SECONDS)


def auto_mode(cfg):
    print(f"\n  {C.GREEN}Авто-режим включён.{C.R}  Публикация после {IDLE_SECONDS} сек тишины. {C.DIM}Ctrl+C — выход в меню.{C.R}\n")
    try:
        for ev, changes, msg in iter_debounced_publish():
            now = datetime.now().strftime("%H:%M:%S")
            if ev == "wait":
                print(f"  {now} {C.DIM}изменения обнаружены, жду {IDLE_SECONDS}с…{C.R}")
            elif ev == "pub":
                for kind, rel, folder in changes or []:
                    sign = f"{C.GREEN}+{C.R}" if kind == "new" else (f"{C.YELLOW}~{C.R}" if kind == "upd" else f"{C.RED}-{C.R}")
                    print(f"  {now} {sign} {folder + '/' if folder else ''}{rel}")
                if msg:
                    color = C.GREEN if msg.startswith("OK") else C.RED
                    print(f"  {now} {color}{msg}{C.R}")
            elif ev == "err":
                print(f"  {now} {C.RED}{msg}{C.R}")
    except KeyboardInterrupt:
        print(f"\n  {C.YELLOW}Авто-режим остановлен.{C.R}")


def log_watch(msg):
    try:
        if WATCH_LOG.exists() and WATCH_LOG.stat().st_size > 1_000_000:
            old = SCRIPT_DIR / "afk_watch.old.log"
            if old.exists():
                old.unlink()
            WATCH_LOG.replace(old)
        with open(WATCH_LOG, "a", encoding="utf-8") as f:
            f.write(f"{datetime.now().isoformat(timespec='seconds')} {msg}\n")
    except Exception:
        pass


def acquire_watch_lock():
    if msvcrt is None:
        return None
    try:
        f = open(WATCH_LOCK, "a+")
    except OSError:
        return None
    try:
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close()
        return None
    return f


def read_watch_pid():
    try:
        return int(WATCH_PID.read_text(encoding="utf-8").strip())
    except Exception:
        return None


def pid_alive(pid):
    try:
        r = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=10,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        return str(pid) in (r.stdout or "") and "No tasks" not in (r.stdout or "")
    except Exception:
        return False


def watch_status():
    pid = read_watch_pid()
    if pid and pid_alive(pid):
        return pid
    return None


def stop_watch():
    pid = read_watch_pid()
    if not pid:
        return False, "Фоновый режим не запущен."
    if not pid_alive(pid):
        try:
            WATCH_PID.unlink()
        except OSError:
            pass
        return False, "Найден устаревший pid, файлы очищены."
    try:
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/F"],
            capture_output=True, text=True, timeout=10,
            creationflags=0x08000000 if os.name == "nt" else 0,
        )
        time.sleep(0.5)
    except Exception as e:
        return False, f"Ошибка остановки: {e}"
    for p in (WATCH_PID, WATCH_LOCK):
        try:
            p.unlink()
        except OSError:
            pass
    log_watch(f"stopped (pid {pid})")
    return True, f"Фоновый режим остановлен (pid {pid})."


def start_watch_hidden():
    if watch_status():
        return False, f"Уже запущен (pid {watch_status()})."
    exe = Path(sys.executable)
    if exe.name.lower() == "python.exe":
        pw = exe.with_name("pythonw.exe")
        if pw.exists():
            exe = pw
    flags = 0x00000008 | 0x08000000  # DETACHED_PROCESS | CREATE_NO_WINDOW
    try:
        subprocess.Popen(
            [str(exe), str(Path(__file__).resolve()), "--watch"],
            cwd=str(SCRIPT_DIR),
            creationflags=flags,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
        )
    except Exception as e:
        return False, f"Ошибка запуска: {e}"
    for _ in range(20):
        time.sleep(0.25)
        pid = watch_status()
        if pid:
            return True, f"Фоновый режим запущен (pid {pid})."
    return False, "Процесс не поднялся — смотри afk_watch.log."


def watch_mode():
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")
    lock_f = acquire_watch_lock()
    if lock_f is None:
        log_watch("already running, exit")
        return 1
    try:
        WATCH_PID.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass
    log_watch(f"started pid={os.getpid()} (idle={IDLE_SECONDS}s)")
    try:
        for ev, changes, msg in iter_debounced_publish():
            if ev == "pub":
                for kind, rel, folder in changes or []:
                    log_watch(f"{kind} {folder + '/' if folder else ''}{rel}")
                if msg:
                    log_watch(msg)
            else:
                log_watch(msg)
    except KeyboardInterrupt:
        log_watch("stopped by keyboard")
    finally:
        try:
            lock_f.close()
        except Exception:
            pass
        for p in (WATCH_PID,):
            try:
                p.unlink()
            except OSError:
                pass
    return 0


def show_history(cfg):
    print(f"\n{C.BOLD}История публикаций{C.R}")
    if not cfg["history"]:
        print(f"  {C.DIM}Пока пусто.{C.R}")
    for e in cfg["history"][:30]:
        t = e["time"].replace("T", " ")
        print(f"\n  {C.CYAN}{t}{C.R}  {C.GREEN}{e['count']} файл(ов){C.R}  {C.DIM}commit {e['commit']}{C.R}")
        for f in e["files"][:8]:
            print(f"      {C.DIM}-{f}{C.R}")
        if len(e["files"]) > 8:
            print(f"      {C.DIM}... и ещё {len(e['files']) - 8}{C.R}")
    input(f"\n{C.DIM}Enter — назад{C.R}")


def show_status(cfg):
    print(f"\n{C.BOLD}Статус{C.R}")
    print(f"  Сайт:        {C.CYAN}{SITE_URL}{C.R}")
    print(f"  Репозиторий: {C.DIM}{REPO_DIR}{C.R}")
    print(f"  Конфиг:      {C.DIM}{CONFIG_PATH}{C.R}")
    print(f"  Папок:       {len(cfg['folders'])}")
    print(f"  Файлов в state: {len(cfg['state'])}")
    md = sum(1 for v in cfg["state"].values() if v.get("site", "").endswith(".html"))
    print(f"  Заметок опубликовано: {md}")
    if (REPO_DIR / ".git").exists():
        status = git("status", "-sb").stdout.strip().split("\n")[0]
        print(f"  Git: {C.DIM}{status}{C.R}")
    wpid = watch_status()
    if wpid:
        print(f"  Фоновый режим: {C.GREEN}вкл (pid {wpid}){C.R}  {C.DIM}лог: {WATCH_LOG}{C.R}")
    else:
        print(f"  Фоновый режим: {C.DIM}выкл{C.R}  {C.DIM}запуск: py afk.py --watch{C.R}")
    if WATCH_LOG.exists():
        lines = WATCH_LOG.read_text(encoding="utf-8", errors="replace").splitlines()
        if lines:
            print(f"  {C.DIM}Лог (последний): {lines[-1]}{C.R}")
    input(f"\n{C.DIM}Enter — назад{C.R}")


def ask(prompt, default=""):
    try:
        v = input(prompt).strip()
        return v or default
    except EOFError:
        return default


def ask_yn(prompt, default=False):
    hint = "[Y/n]" if default else "[y/N]"
    v = ask(f"{prompt} {hint} ").lower()
    if not v:
        return default
    return v in ("y", "yes", "д", "да")


def ok_line(text):
    print(f"  {C.GREEN}✓{C.R} {text}")


def bad_line(text):
    print(f"  {C.RED}✗{C.R} {text}")


def info_line(text):
    print(f"  {C.DIM}·{C.R} {text}")


def try_winget(pkg_id, title):
    if not shutil.which("winget"):
        bad_line(f"{title}: winget не найден — установи вручную и повтори --setup")
        return False
    print(f"  {C.CYAN}→{C.R} Устанавливаю {title}...")
    try:
        r = subprocess.run(
            ["winget", "install", "--id", pkg_id, "-e",
             "--accept-source-agreements", "--accept-package-agreements"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=600,
        )
    except Exception as e:
        bad_line(f"Ошибка установки {title}: {e}")
        return False
    if r.returncode == 0:
        ok_line(f"{title} установлен")
        info_line("перезапусти терминал и повтори: py afk.py --setup")
        return True
    bad_line(f"{title}: установка не удалась — {r.stderr.strip()[:200]}")
    return False


def gh_login_user():
    try:
        r = subprocess.run(
            ["gh", "auth", "status"], capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=20,
        )
        if r.returncode != 0:
            return None
        text = re.sub(r"\x1b\[[0-9;]*m", "", (r.stdout or "") + (r.stderr or ""))
        m = re.search(r"(?:as|account)\s+(\S+)", text)
        return m.group(1) if m else None
    except Exception:
        return None


def setup_mode():
    print(f"\n  {C.BOLD}AFK Notes — настройка{C.R}")
    print(f"  {C.DIM}конфиг: {CONFIG_PATH}{C.R}\n")

    print(f"{C.BOLD}1. Git{C.R}")
    git_ok = shutil.which("git") is not None
    if git_ok:
        try:
            v = subprocess.run(["git", "--version"], capture_output=True,
                               text=True, timeout=10).stdout.strip()
        except Exception:
            v = "git"
        ok_line(v)
    else:
        bad_line("Git не установлен")
        if ask_yn("  Установить Git сейчас?"):
            try_winget("Git.Git", "Git")
            git_ok = shutil.which("git") is not None

    print(f"\n{C.BOLD}2. GitHub CLI (gh){C.R}")
    gh_ok = shutil.which("gh") is not None
    if gh_ok:
        ok_line("gh установлен")
    else:
        bad_line("GitHub CLI не установлен — нужен, чтобы создавать репозитории")
        if ask_yn("  Установить GitHub CLI сейчас?"):
            try_winget("GitHub.cli", "GitHub CLI")
            gh_ok = shutil.which("gh") is not None

    print(f"\n{C.BOLD}3. Доступ к GitHub{C.R}")
    gh_user = gh_login_user() if gh_ok else None
    if gh_user:
        ok_line(f"авторизован как {gh_user}")
    elif gh_ok:
        bad_line("не авторизован")
        if ask_yn("  Запустить вход gh auth login?"):
            try:
                subprocess.call(["gh", "auth", "login", "--hostname", "github.com",
                                 "--git-protocol", "https", "--web"])
            except Exception:
                pass
            gh_user = gh_login_user()
            if gh_user:
                ok_line(f"авторизован как {gh_user}")
            else:
                bad_line("вход не завершён — создание репозитория будет недоступно")
    else:
        bad_line("gh не установлен — пропускаю")

    print(f"\n{C.BOLD}4. Папки заметок{C.R}")
    cfg = load_config()
    if cfg["folders"]:
        ok_line(f"{len(cfg['folders'])} папок в конфиге")
        for fp in cfg["folders"]:
            mark = C.GREEN if Path(fp).exists() else C.RED
            print(f"    {mark}•{C.R} {fp}")
    else:
        bad_line("папки не заданы")
        while True:
            p = ask("  Путь к папке с заметками (Enter — пропустить): ")
            if not p:
                break
            if Path(p).exists():
                cfg["folders"].append(str(Path(p).resolve()))
                ok_line(f"добавлена: {p}")
            else:
                bad_line("папка не найдена, попробуй ещё")
        save_config(cfg)

    print(f"\n{C.BOLD}5. Репозиторий{C.R}")
    repo_exists = (REPO_DIR / ".git").exists()
    if repo_exists:
        r = git("ls-remote", "--heads", "origin")
        if r.returncode == 0:
            ok_line(f"клон найден: {REPO_DIR}")
            ok_line(f"origin доступен: {REPO_URL or git_remote_origin()}")
        else:
            bad_line(f"origin недоступен: {(r.stderr or r.stdout).strip()[:200]}")
        cfg = load_config()
        changed = False
        for key, val in (("repo_dir", str(REPO_DIR)),
                         ("repo_url", REPO_URL or git_remote_origin()),
                         ("site_url", SITE_URL),
                         ("gh_link", GH_LINK)):
            if val and cfg.get(key) != val:
                cfg[key] = val
                changed = True
        if changed:
            save_config(cfg)
            ok_line("недостающие параметры дописаны в конфиг")
    elif REPO_URL and git_ok:
        info_line(f"клонирую {REPO_URL} ...")
        good, err = ensure_repo()
        if good:
            ok_line(f"клонирован: {REPO_DIR}")
        else:
            bad_line(f"клон не удался: {err}")
    elif gh_ok and gh_user and git_ok:
        print(f"  {C.DIM}репозитория ещё нет — создам новый{C.R}")
        name = ask(f"  Имя репозитория [{gh_user}.github.io]: ",
                   default=f"{gh_user}.github.io")
        r = subprocess.run(
            ["gh", "repo", "create", name, "--public",
             "--description", "AFK Notes"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=60,
        )
        if r.returncode != 0 and "already exists" not in (r.stderr or ""):
            bad_line(f"создание не удалось: {(r.stderr or r.stdout).strip()[:200]}")
        else:
            REPO_URL_NEW = f"https://github.com/{gh_user}/{name}.git"
            ok_line(f"репозиторий создан: github.com/{gh_user}/{name}")
            r2 = subprocess.run(
                ["git", "clone", REPO_URL_NEW, str(REPO_DIR)],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace",
                creationflags=0x08000000 if os.name == "nt" else 0,
            )
            if r2.returncode == 0:
                ok_line(f"клонирован: {REPO_DIR}")
                cfg = load_config()
                cfg["repo_dir"] = str(REPO_DIR)
                cfg["repo_url"] = REPO_URL_NEW
                site = derive_site_url(REPO_URL_NEW)
                cfg["site_url"] = site
                cfg["gh_link"] = REPO_URL_NEW[:-4]
                save_config(cfg)
                init_runtime()
                info_line("первый запуск публикации...")
                changes, msg = publish(cfg)
                if msg and msg.startswith("OK"):
                    ok_line(msg)
                elif msg:
                    info_line(msg)
                if gh_ok:
                    owner, repo_name = gh_user, name
                    pr = subprocess.run(
                        ["gh", "api", "-X", "POST",
                         f"repos/{owner}/{repo_name}/pages",
                         "-f", "source[branch]=main", "-f", "source[path]=/"],
                        capture_output=True, text=True, encoding="utf-8",
                        errors="replace", timeout=30,
                    )
                    if pr.returncode == 0 or "already exists" in (pr.stderr or ""):
                        ok_line("GitHub Pages включён")
                    else:
                        info_line(f"Pages: {(pr.stderr or pr.stdout).strip()[:120]}")
            else:
                bad_line(f"клон не удался: {r2.stderr.strip()[:200]}")
    else:
        bad_line("нет git/gh или нет доступа к GitHub — повтори настройку позже")
        info_line("команда: py afk.py --setup")

    print(f"\n{C.BOLD}6. Синхронизация{C.R}")
    if (REPO_DIR / ".git").exists():
        if watch_status():
            ok_line(f"уже запущена (pid {watch_status()})")
        else:
            good, msg = start_watch_hidden()
            (ok_line if good else bad_line)(msg)
    else:
        bad_line("репозиторий не готов — синхронизация не запущена")

    print(f"\n  {C.BOLD}Готово.{C.R}")
    if SITE_URL:
        print(f"  Сайт: {C.CYAN}{SITE_URL}{C.R}")
    print()
    return 0 if (REPO_DIR / ".git").exists() else 1


def main():
    args = sys.argv[1:]
    if args and args[0] in ("--setup", "-setup", "setup"):
        enable_console()
        sys.exit(setup_mode())
    if args and args[0] in ("--watch", "-watch"):
        enable_console()
        sys.exit(watch_mode())
    if args and args[0] in ("--stop", "-stop"):
        enable_console()
        ok, msg = stop_watch()
        print(msg)
        sys.exit(0 if ok else 1)
    enable_console()
    if args and args[0] in ("--once", "-once"):
        cfg = load_config()
        changes, msg = publish(cfg)
        for c in changes:
            print(c)
        if msg:
            print(msg)
        return
    cfg = load_config()
    while True:
        os.system("cls" if os.name == "nt" else "clear")
        print_header()
        print_menu(cfg)
        choice = input(f"{C.BOLD}Выбор> {C.R}").strip()
        if choice == "1":
            show_folders(cfg)
        elif choice == "2":
            do_publish(cfg)
            input(f"\n{C.DIM}Enter — продолжить{C.R}")
        elif choice == "3":
            auto_mode(cfg)
        elif choice == "4":
            show_history(cfg)
        elif choice == "5":
            webbrowser.open(SITE_URL)
        elif choice == "6":
            show_status(cfg)
        elif choice == "7":
            if watch_status():
                ok, msg = stop_watch()
            else:
                ok, msg = start_watch_hidden()
            color = C.GREEN if ok else C.YELLOW
            print(f"\n  {color}{msg}{C.R}")
            input(f"\n{C.DIM}Enter — продолжить{C.R}")
        elif choice == "0":
            print(f"\n  {C.DIM}Пока!{C.R}\n")
            break


if __name__ == "__main__":
    main()
