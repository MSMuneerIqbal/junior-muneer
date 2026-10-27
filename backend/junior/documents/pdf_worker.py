"""Private renderer entrypoint. Text is escaped; no supplied HTML/scripts/fonts/URLs are fetched."""
from html import escape
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit


def text(value):
    return escape(str(value))


def link(url, label):
    parts = urlsplit(str(url))
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.username or parts.password:
        return text(label)
    return f'<a href="{text(url)}">{text(label)}</a>'


def html_document(doc, sources, slide_mode, count):
    from junior.google.slides import slide_pages
    common = """*{box-sizing:border-box}body{margin:0;color:#162b45;font-family:Arial,'Noto Sans Arabic',sans-serif}
    h1,h2,p,li{unicode-bidi:plaintext}h1{font-size:27pt;line-height:1.2}h2{font-size:17pt;break-after:avoid}
    p,li{font-size:11pt;line-height:1.65;overflow-wrap:anywhere}p{white-space:pre-wrap;orphans:3;widows:3}
    a{color:#196ce6;text-decoration:none;overflow-wrap:anywhere}.refs{font-size:9pt;color:#516277}
    .source{break-inside:avoid}h1,h2{overflow-wrap:anywhere}body{-webkit-print-color-adjust:exact}"""
    if slide_mode:
        css = common + """@page{size:960px 540px;margin:0}.slide{width:960px;height:540px;padding:35px 48px;
        break-after:page;position:relative;overflow:hidden;background:#f8fafd}.slide:last-child{break-after:auto}
        .slide h1{font-size:30px;margin:0 0 22px;height:78px}.body{height:334px;overflow:hidden}
        .body p{font-size:23px;line-height:1.35;margin:0 0 16px}.cover{background:#162b45;color:white}
        .cover h1{height:130px;margin-top:45px;font-size:44px}.cover .body{height:190px}
        .cover .body p{font-size:27px;color:#cdddf1}.footer{position:absolute;bottom:18px;left:48px;
        right:48px;font-size:12px;color:#516277}.source-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px 28px}
        .source-grid p{font-size:16px}.page-number{float:right}.cover .footer{color:#bccce0}"""
        pages = slide_pages(doc, sources, count)
        catalog = {s["id"]: s for s in sources}
        content = []
        for i, page in enumerate(pages):
            cover = page["layout"] == "cover" and i == 0 and count > 1
            references = page["layout"] == "sources"
            body = "".join('<p>' + (link(page["links"][n], b) if references else text(
                (f"{n + 1}. " if page["layout"] == "steps" else "" if cover else "• ") + b)) + '</p>'
                for n, b in enumerate(page["bullets"]))
            cited = doc.slides[i].source_ids if i < len(doc.slides) else []
            footer = " ".join(link(catalog[n]["url"], f"[{n}]") for n in cited)
            content.append(f'<section class="slide {"cover" if cover else ""}"><h1 dir="auto">{text(page["title"])}</h1>'
                f'<div class="body {"source-grid" if references else ""}">{body}</div><div class="footer">'
                f'{footer}<span class="page-number">{i + 1} / {count}</span></div></section>')
        body = "".join(content)
    else:
        css = common + "@page{size:A4;margin:22mm 20mm}h1{border-bottom:3px solid #196ce6;padding-bottom:14px}"
        body = f'<h1 dir="auto">{text(doc.title)}</h1><p dir="auto">{text(doc.summary)}</p>'
        for section in doc.sections:
            body += f'<h2 dir="auto">{text(section.heading)}</h2><p dir="auto">{text(section.text)}</p>'
            body += '<p class="refs">Sources: ' + ", ".join(f"[{i}]" for i in section.source_ids) + '</p>'
        body += '<h2>Sources</h2>'
        for source in sources:
            body += f'<p class="source">[{source["id"]}] {text(source["title"])}<br>' + link(source["url"], source["url"]) + '</p>'
    return '<!doctype html><html><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src \'none\'; style-src \'unsafe-inline\'">' + f'<title>{text(doc.title)}</title><style>{css}</style></head><body>{body}</body></html>'


def main(folder):
    from playwright.sync_api import sync_playwright
    from junior.documents.schema import ResearchDocument, validate_document
    root = Path(folder)
    raw = (root / "input.json").read_bytes()
    if len(raw) > 500000:
        raise ValueError("Input exceeds print limit.")
    payload = json.loads(raw)
    doc = ResearchDocument.model_validate(payload["document"])
    sources, count = payload["sources"], payload["count"]
    slide_mode = payload["format"] == "slides_pdf"
    validate_document(doc, sources, payload["format"], count)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, timeout=20000,
            args=["--disable-background-networking", "--disable-component-update", "--no-first-run",
                  "--host-resolver-rules=MAP * ~NOTFOUND", "--disable-sync"])
        try:
            context = browser.new_context(java_script_enabled=False, offline=True, service_workers="block")
            context.route("**/*", lambda route: route.abort())
            page = context.new_page()
            page.set_content(html_document(doc, sources, slide_mode, count), wait_until="domcontentloaded", timeout=10000)
            if slide_mode:
                # Fixed internal layout check, never supplied JavaScript. Shrink dense text only to a readable minimum.
                fits = page.evaluate("""() => [...document.querySelectorAll('.slide')].every(s => {
                    const title=s.querySelector('h1'), b=s.querySelector('.body');
                    for(let n=0;n<10 && b.scrollHeight>b.clientHeight+1;n++)
                        b.querySelectorAll('p').forEach(p=>p.style.fontSize=Math.max(14,parseFloat(getComputedStyle(p).fontSize)-1)+'px');
                    for(let n=0;n<8 && title.scrollHeight>title.clientHeight+1;n++)
                        title.style.fontSize=Math.max(22,parseFloat(getComputedStyle(title).fontSize)-1)+'px';
                    return b.scrollHeight<=b.clientHeight+1 && title.scrollHeight<=title.clientHeight+1;
                })""")
                if not fits:
                    raise ValueError("Slide text does not fit at a readable size.")
            data = page.pdf(prefer_css_page_size=True, print_background=True)
            from io import BytesIO
            from pypdf import PdfReader
            actual = len(PdfReader(BytesIO(data)).pages)
            if actual > 100 or (slide_mode and actual != count):
                raise ValueError("Unexpected PDF page count.")
            (root / "output.pdf").write_bytes(data)
        finally:
            browser.close()


if __name__ == "__main__":
    if sys.stdin.readline().strip() != "junior-go":
        raise SystemExit(125)
    main(sys.argv[1])
