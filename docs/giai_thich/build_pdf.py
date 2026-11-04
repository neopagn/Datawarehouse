"""Build docs/giai_thich_tu_dau.pdf from bao_cao.html with headless Edge, then add the table of
contents page numbers, footer page numbers and PDF bookmarks.

Run:  python docs/giai_thich/build_pdf.py
"""
import html
import os
import re
import site
import subprocess
import sys
import tempfile

sys.path.append(site.getusersitepackages())
import fitz

sys.stdout.reconfigure(encoding="utf-8")
HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "bao_cao.html")
OUT = os.path.join(HERE, "..", "giai_thich_tu_dau.pdf")
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
HEADING = re.compile(r'<h([23]) id="([^"]+)"([^>]*)>(.*?)</h\1>', re.S)


def plain(text):
    return html.unescape(re.sub(r"<[^>]+>", "", text)).strip()


def toc_html(entries, pages):
    rows = []
    for level, hid, title in entries:
        num = pages.get(hid, "")
        rows.append(f'<div class="l{level}"><a href="#{hid}">{html.escape(title)}</a>'
                    f'<span class="dots"></span><span>{num}</span></div>')
    return '<div class="toc">' + "".join(rows) + "</div>"


def print_pdf(source_html, path):
    with tempfile.TemporaryDirectory() as profile:
        page = os.path.join(HERE, "_build.html")
        with open(page, "w", encoding="utf-8") as f:
            f.write(source_html)
        subprocess.run([EDGE, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                        f"--user-data-dir={profile}", f"--print-to-pdf={path}",
                        "file:///" + page.replace(os.sep, "/")],
                       check=True, timeout=180, capture_output=True)
        os.remove(page)


source = open(SRC, encoding="utf-8").read()
entries = [(int(m[1]), m[2], plain(m[4])) for m in HEADING.finditer(source) if "data-notoc" not in m[3]]
tmp = os.path.join(tempfile.gettempdir(), "co4031_pass.pdf")

# pass 1 finds where each heading lands, pass 2 prints the numbers into the contents page
print_pdf(source.replace("<!--TOC-->", toc_html(entries, {})), tmp)
doc = fitz.open(tmp)
pages = {}
for i, page in enumerate(doc):
    for link in page.get_links():
        name = link.get("nameddest") or link.get("to_name")
        if name:
            pages.setdefault(name, None)
names = doc.resolve_names()
for hid, dest in names.items():
    pages[hid] = dest["page"] + 1
missing = [e[1] for e in entries if not pages.get(e[1])]
if missing:
    raise SystemExit(f"headings without a page: {missing}")
doc.close()

print_pdf(source.replace("<!--TOC-->", toc_html(entries, pages)), tmp)
doc = fitz.open(tmp)
names = doc.resolve_names()
for level, hid, _ in entries:
    if names[hid]["page"] + 1 != pages[hid]:
        raise SystemExit(f"contents page changed the layout at {hid}")

for i, page in enumerate(doc):
    if i == 0:
        continue
    label = str(i + 1)
    width = fitz.get_text_length(label, fontname="helv", fontsize=9.5)
    # the schema page is landscape, so position each number from its own page size
    page.insert_text(((page.rect.width - width) / 2, page.rect.height - 28), label,
                     fontname="helv", fontsize=9.5, color=(0.32, 0.38, 0.43))

doc.set_toc([[level - 1, title, pages[hid]] for level, hid, title in entries])
doc.set_metadata({"title": "Giải thích từ đầu: Phân tích và Thiết kế Kho dữ liệu OULAD", "subject": "CO4031 HK261"})
doc.save(os.path.abspath(OUT), garbage=3, deflate=True)
print("pages:", len(doc), " size_kb:", os.path.getsize(OUT) // 1024)
