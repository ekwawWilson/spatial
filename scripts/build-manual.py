#!/usr/bin/env python3
"""Builds the user guide into one printable page: docs/manual/user-manual.html.

    python3 scripts/build-manual.py

Open the result in a browser and print it, or save it as PDF from the print
dialog. Uses only the standard library: it understands the Markdown the
guides are written in (headings, paragraphs, lists, tables, code, bold,
italics, links).
"""

import html
import re
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
USER = ROOT / "docs" / "user"
OUT = ROOT / "docs" / "manual" / "user-manual.html"

# Chapters in reading order: (file, part). Operations guides are for administrators.
CHAPTERS = [
    ("signing-in.md", "Getting started"),
    ("projects-and-layers.md", "Getting started"),
    ("coordinate-systems.md", "Getting started"),
    ("basemaps.md", "Getting started"),
    ("import-export.md", "Building the plan's data"),
    ("editing-and-boundaries.md", "Building the plan's data"),
    ("imagery.md", "Building the plan's data"),
    ("readiness-checklist.md", "Building the plan's data"),
    ("relationships.md", "Building the plan's data"),
    ("field-app.md", "Working in the field"),
    ("field-sync.md", "Working in the field"),
    ("project-files.md", "Keeping work safe"),
    ("audit-log.md", "Keeping work safe"),
    ("members.md", "Administration"),
    ("system-admin.md", "Administration"),
    ("../ops/data-protection.md", "Administration"),
]


def inline(text: str) -> str:
    text = html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<![*\w])\*([^*\n]+)\*(?![*\w])", r"<em>\1</em>", text)
    # Links between guides become plain text (they are all in this one page);
    # outside links keep their address.
    text = re.sub(r"\[([^\]]+)\]\((https?://[^)]+)\)", r'<a href="\2">\1</a>', text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    return text


def cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def convert(markdown: str, slug: str) -> str:
    out: list[str] = []
    lines = markdown.split("\n")
    i = 0
    paragraph: list[str] = []
    list_kind = ""

    def flush() -> None:
        nonlocal list_kind
        if paragraph:
            out.append("<p>" + inline(" ".join(paragraph)) + "</p>")
            paragraph.clear()
        if list_kind:
            out.append(f"</{list_kind}>")
            list_kind = ""

    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            flush()
            block = []
            i += 1
            while i < len(lines) and not lines[i].startswith("```"):
                block.append(lines[i])
                i += 1
            out.append("<pre>" + html.escape("\n".join(block)) + "</pre>")
        elif line.startswith("#"):
            flush()
            level = len(line) - len(line.lstrip("#"))
            title = inline(line.lstrip("#").strip())
            # A guide's own title becomes a chapter (h2); the rest move down one.
            tag = f"h{min(level + 1, 5)}"
            anchor = f' id="{slug}"' if level == 1 else ""
            out.append(f"<{tag}{anchor}>{title}</{tag}>")
        elif line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()):
            flush()
            out.append("<table><thead><tr>" + "".join(f"<th>{inline(c)}</th>" for c in cells(line)) + "</tr></thead><tbody>")
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                out.append("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in cells(lines[i])) + "</tr>")
                i += 1
            out.append("</tbody></table>")
            continue
        elif re.match(r"^\s*(-|\d+\.)\s+", line):
            kind = "ol" if re.match(r"^\s*\d+\.", line) else "ul"
            if paragraph:
                out.append("<p>" + inline(" ".join(paragraph)) + "</p>")
                paragraph.clear()
            if list_kind != kind:
                if list_kind:
                    out.append(f"</{list_kind}>")
                out.append(f"<{kind}>")
                list_kind = kind
            item = re.sub(r"^\s*(-|\d+\.)\s+", "", line)
            item = re.sub(r"^\[ \]\s*", "☐ ", item)
            out.append(f"<li>{inline(item)}</li>")
        elif not line.strip():
            flush()
        elif list_kind and line.startswith("  "):
            # A wrapped list item.
            out[-1] = out[-1][:-5] + " " + inline(line.strip()) + "</li>"
        else:
            if list_kind:
                out.append(f"</{list_kind}>")
                list_kind = ""
            paragraph.append(line.strip())
        i += 1
    flush()
    return "\n".join(out)


STYLE = """
body { font-family: Georgia, 'Times New Roman', serif; line-height: 1.5; max-width: 46rem; margin: 2rem auto; padding: 0 1rem; color: #1d2521; }
h1 { font-size: 2.2rem; margin-top: 4rem; }
h2 { font-size: 1.6rem; border-bottom: 2px solid #1f6f4a; padding-bottom: .2rem; margin-top: 3rem; page-break-before: always; }
h3 { font-size: 1.2rem; margin-top: 1.6rem; }
h4, h5 { font-size: 1.05rem; }
.part { font: 600 .8rem/1 Arial, sans-serif; letter-spacing: .08em; text-transform: uppercase; color: #1f6f4a; margin-top: 3rem; }
table { border-collapse: collapse; width: 100%; margin: .8rem 0; font-size: .92rem; }
th, td { border: 1px solid #c8cfca; padding: .35rem .5rem; text-align: left; vertical-align: top; }
th { background: #eef3ef; }
code, pre { font-family: Consolas, 'Courier New', monospace; font-size: .88rem; background: #f3f5f3; }
code { padding: 0 .2rem; }
pre { padding: .6rem .8rem; overflow-x: auto; white-space: pre-wrap; }
.toc li { margin: .15rem 0; }
.toc a { color: inherit; text-decoration: none; }
.cover { text-align: center; margin: 6rem 0 4rem; }
.cover p { color: #5f6b65; }
@media print { body { margin: 0; max-width: none; } a { color: inherit; text-decoration: none; } h2 { page-break-before: always; } tr, pre { page-break-inside: avoid; } }
"""


def main() -> None:
    body: list[str] = []
    toc: list[str] = []
    part = ""
    for name, chapter_part in CHAPTERS:
        path = (USER / name).resolve()
        text = path.read_text(encoding="utf-8")
        slug = path.stem
        title = next(line.lstrip("# ").strip() for line in text.split("\n") if line.startswith("# "))
        if chapter_part != part:
            part = chapter_part
            toc.append(f'</ul><p class="part">{html.escape(part)}</p><ul>')
        toc.append(f'<li><a href="#{slug}">{html.escape(title)}</a></li>')
        body.append(convert(text, slug))
    page = f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Community Planning GIS Platform: User Manual</title>
<style>{STYLE}</style>
</head>
<body>
<div class="cover">
<h1>Community Planning GIS Platform</h1>
<p>User manual</p>
<p>{date.today():%B %Y}</p>
</div>
<h3>Contents</h3>
<div class="toc"><ul>
{chr(10).join(toc)}
</ul></div>
{chr(10).join(body)}
</body>
</html>
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(page, encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {len(CHAPTERS)} chapters, {len(page) // 1024} KB")


if __name__ == "__main__":
    main()
