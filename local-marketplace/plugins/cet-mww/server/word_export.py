"""Dependency-free Word reading edition, rebuilt from the canonical lexicon."""
from __future__ import annotations

from io import BytesIO
import json
from hashlib import sha256
from xml.etree.ElementTree import Element, SubElement, tostring
from zipfile import ZipFile, ZIP_DEFLATED, BadZipFile

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
XML = "http://www.w3.org/XML/1998/namespace"
V = "urn:schemas-microsoft-com:vml"
EXPORT_VERSION = "word-4-front-index"


def node(parent, tag, **attrs):
    return SubElement(parent, f"{{{W}}}{tag}", {f"{{{W}}}{k}": str(v) for k, v in attrs.items()})


def xml_bytes(element):
    return tostring(element, encoding="utf-8", xml_declaration=True)


def fingerprint(data):
    return EXPORT_VERSION + ":" + sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def run(parent, text, *, bold=False, italic=False, size=None, color=None, font=None):
    r = node(parent, "r")
    props = node(r, "rPr")
    if bold:
        node(props, "b")
    if italic:
        node(props, "i")
    if size:
        node(props, "sz", val=size)
    if color:
        node(props, "color", val=color)
    if font:
        node(props, "rFonts", ascii=font, hAnsi=font, eastAsia="Songti SC")
    for i, part in enumerate(str(text).split("\n")):
        if i:
            node(r, "br")
        t = node(r, "t")
        t.set(f"{{{XML}}}space", "preserve")
        t.text = part
    return r


def paragraph(parent, text="", style="Normal", *, keep=False, page=False):
    p = node(parent, "p")
    props = node(p, "pPr")
    node(props, "pStyle", val=style)
    if keep:
        node(props, "keepNext")
    if page:
        node(props, "pageBreakBefore")
    if text:
        run(p, text)
    return p


def link(p, text, anchor):
    h = node(p, "hyperlink", anchor=anchor, history="1")
    run(h, text, color="24546A")


def source_label(exam):
    if exam.get("category") == "未分类":
        return "未分类"
    level = "四级" if exam["level"] == "CET-4" else "六级"
    return f"{exam['year']}年{exam['month']}月{level}第{exam['set_number']}套"


def make_styles():
    styles = Element(f"{{{W}}}styles")
    defaults = node(styles, "docDefaults")
    rp = node(node(defaults, "rPrDefault"), "rPr")
    node(rp, "rFonts", ascii="Calibri", hAnsi="Calibri", eastAsia="Songti SC")
    node(rp, "sz", val="20")
    node(rp, "lang", val="en-US", eastAsia="zh-CN")
    specs = [
        ("Normal", "Normal", 20, False, 0, 50, None),
        ("Title", "Title", 38, True, 0, 80, None),
        ("Subtitle", "Subtitle", 18, False, 0, 90, None),
        ("Heading1", "Heading 1", 28, True, 160, 90, 0),
        ("Heading2", "Heading 2", 22, True, 160, 80, 1),
        ("Heading3", "Heading 3", 20, True, 90, 60, 2),
        ("Headword", "Word headword", 28, True, 160, 50, 2),
        ("Pronunciation", "Word pronunciation", 19, False, 0, 80, None),
        ("Gloss", "English gloss", 19, False, 0, 55, None),
        ("Example", "English example", 20, False, 25, 25, None),
        ("Translation", "Chinese translation", 20, False, 0, 55, None),
        ("Source", "Paper sources", 18, False, 55, 100, None),
        ("Index", "Paper word index", 20, False, 0, 100, None),
    ]
    for sid, name, size, bold, before, after, outline in specs:
        s = node(styles, "style", type="paragraph", styleId=sid)
        if sid == "Normal":
            s.set(f"{{{W}}}default", "1")
        node(s, "name", val=name)
        if sid != "Normal":
            node(s, "basedOn", val="Normal")
        node(s, "next", val="Normal")
        pp = node(s, "pPr")
        node(pp, "spacing", before=before, after=after, line="275", lineRule="auto")
        node(pp, "widowControl")
        if outline is not None:
            node(pp, "outlineLvl", val=outline)
            node(pp, "keepNext")
        if sid in {"Example", "Translation", "Gloss"}:
            node(pp, "ind", left="160")
        rp = node(s, "rPr")
        node(rp, "sz", val=size)
        node(rp, "color", val="000000" if sid not in {"Gloss", "Translation", "Source"} else "5A5A5A")
        if bold:
            node(rp, "b")
        if sid in {"Title", "Headword"}:
            node(rp, "rFonts", ascii="Georgia", hAnsi="Georgia", eastAsia="Songti SC")
    return xml_bytes(styles)


def section_properties(parent, columns=1, continuous=False):
    section = node(parent, "sectPr")
    for kind, rid in (("default", "rIdHeader"), ("first", "rIdFirstHeader")):
        ref = node(section, "headerReference", type=kind)
        ref.set(f"{{{R}}}id", "rIdBlankHeader" if columns == 1 else "rIdHeader")
    ref = node(section, "footerReference", type="default")
    ref.set(f"{{{R}}}id", "rIdFooter")
    node(section, "type", val="continuous" if continuous else "nextPage")
    node(section, "pgSz", w="12240", h="15840")
    node(section, "pgMar", top="900", right="1000", bottom="900", left="1000", header="400", footer="450", gutter="0")
    node(section, "cols", num=columns, space="480", equalWidth="1")
    return section


def make_divider_header(first_page=False):
    """A page-anchored blue rule in the gutter; native column rules are black."""
    header = Element(f"{{{W}}}hdr")
    p = paragraph(header)
    pp = p.find(f"{{{W}}}pPr")
    node(pp, "spacing", before="0", after="0", line="20", lineRule="exact")
    pict = node(node(p, "r"), "pict")
    top = 112 if first_page else 45
    line = SubElement(pict, f"{{{V}}}line", {
        "id": "CETGutterFirst" if first_page else "CETGutter",
        "style": f"position:absolute;margin-left:306pt;margin-top:{top}pt;z-index:-251654144;mso-position-horizontal-relative:page;mso-position-vertical-relative:page",
        "from": "0,0", "to": f"0,{747 - top}pt",
        "strokecolor": "#24546A", "strokeweight": "0.5pt",
    })
    SubElement(line, f"{{{V}}}stroke", {"endcap": "flat"})
    return xml_bytes(header)


def linked_heading(body, text, anchor, bookmark_id):
    p = paragraph(body, style="Heading1")
    node(p, "bookmarkStart", id=bookmark_id, name=anchor)
    run(p, text)
    node(p, "bookmarkEnd", id=bookmark_id)


def render_index(body, entries, anchors):
    linked_heading(body, "试卷目录", "paper_index", len(entries))
    paragraph(body, "点击词头跳转到后面的完整词条。", "Gloss")
    buckets = {}
    for e in entries:
        for exam in e.get("exam_sources", []) or [{"category": "未分类"}]:
            key = json.dumps(exam, sort_keys=True, ensure_ascii=False)
            buckets.setdefault(key, (exam, []))[1].append(e["headword"])
    order = lambda b: (b[0].get("level", "ZZZ"), b[0].get("year", 9999), b[0].get("month", 99), b[0].get("set_number", 99))
    previous = (None, None)
    for exam, words in sorted(buckets.values(), key=order):
        if exam.get("category") == "未分类":
            paragraph(body, "未分类", "Heading2")
        else:
            level, year = exam["level"], exam["year"]
            if level != previous[0]:
                paragraph(body, "CET 4 四级" if level == "CET-4" else "CET 6 六级", "Heading2")
            if (level, year) != previous:
                paragraph(body, str(year) + "年", "Heading3")
            paragraph(body, f"{exam['month']}月 第{exam['set_number']}套", "Normal", keep=True)
            previous = (level, year)
        p = paragraph(body, style="Index")
        for i, word in enumerate(words):
            if i:
                run(p, "   ·   ", color="888888")
            link(p, word, anchors[word])


def render_alphabet_index(body, entries, anchors):
    linked_heading(body, "字母索引", "alphabet_index", len(entries) + 1)
    groups = {}
    for e in entries:
        initial = e["headword"][:1].upper()
        groups.setdefault(initial, []).append(e["headword"])
    for initial, words in groups.items():
        p = paragraph(body, style="Index")
        run(p, initial + "   ", bold=True)
        for i, word in enumerate(words):
            if i:
                run(p, "   ·   ", color="888888")
            link(p, word, anchors[word])


def render_word(data):
    entries = sorted(data.get("entries", {}).values(), key=lambda e: e.get("headword", "").casefold())
    anchors = {e["headword"]: f"word_{i}" for i, e in enumerate(entries)}
    doc = Element(f"{{{W}}}document")
    body = node(doc, "body")
    paragraph(body, "四六级英语单词本", "Title")
    paragraph(body, "CET MY WORD WORLD    英汉学习词典", "Subtitle")
    paragraph(body, "目录", "Heading1")
    for text, anchor in (("试卷目录", "paper_index"), ("字母索引", "alphabet_index"), ("词条正文", "entry_body")):
        p = paragraph(body, style="Index")
        link(p, text, anchor)
    render_index(body, entries, anchors)
    render_alphabet_index(body, entries, anchors)
    # The front matter is full width. The dictionary starts on a new two-column page.
    p = paragraph(body)
    section_properties(p.find(f"{{{W}}}pPr"))
    linked_heading(body, "词条正文", "entry_body", len(entries) + 2)
    if not entries:
        paragraph(body, "暂无词条。查询第一个单词后，这里会自动更新。")
    for i, entry in enumerate(entries):
        word = entry["headword"]
        p = paragraph(body, style="Headword")
        node(p, "bookmarkStart", id=i, name=anchors[word])
        run(p, word)
        node(p, "bookmarkEnd", id=i)
        pos = entry.get("parts_of_speech", [])
        labels = {"adjective": "adj.", "noun": "n.", "verb": "v.", "adverb": "adv.", "noun phrase": "n. phrase", "verb phrase": "v. phrase"}
        metadata = [labels.get(g.get("pos", ""), g.get("pos", "")) for g in pos]
        ipa = entry.get("pronunciations", {})
        # Identical UK/US IPA is printed once to keep the entry compact.
        if ipa.get("uk"):
            metadata.append(("英美 " if ipa.get("uk") == ipa.get("us") else "英 ") + ipa["uk"])
        if ipa.get("us") and ipa.get("us") != ipa.get("uk"):
            metadata.append("美 " + ipa["us"])
        paragraph(body, "   ".join(filter(None, metadata)), "Pronunciation", keep=True)
        number = 0
        for group in pos:
            if len(pos) > 1:
                paragraph(body, group.get("pos", ""), "Heading3")
            for sense in group.get("senses", []):
                number += 1
                p = paragraph(body, keep=True)
                run(p, f"释义 {number}  ", bold=True, color="24546A")
                run(p, sense.get("zh", ""), bold=True)
                if sense.get("en"):
                    paragraph(body, sense["en"], "Gloss", keep=bool(sense.get("examples")))
                for example_index, example in enumerate(sense.get("examples", [])):
                    p = paragraph(body, style="Example", keep=bool(example.get("zh")))
                    if example_index == 0:
                        run(p, "例句  ", bold=True, size=18, color="24546A")
                    run(p, example.get("en", ""), italic=True)
                    if example.get("zh"):
                        paragraph(body, example["zh"], "Translation")
        if entry.get("collocations"):
            p = paragraph(body, keep=True)
            run(p, "常用搭配", bold=True, size=19)
            for item in entry["collocations"]:
                p = paragraph(body)
                if isinstance(item, dict):
                    run(p, item.get("en", ""), bold=True, size=20)
                    if item.get("zh"):
                        run(p, "   " + item["zh"], size=20)
                else:
                    run(p, item, size=20)
        for note in entry.get("cet_notes", []):
            p = paragraph(body)
            run(p, "考试用法  ", bold=True, size=19)
            run(p, note, size=19)
        paragraph(body, "来源  " + "；".join(source_label(s) for s in entry.get("exam_sources", [])) if entry.get("exam_sources") else "来源  未分类", "Source")
    section_properties(body, columns=2)
    footer = Element(f"{{{W}}}ftr")
    p = paragraph(footer)
    node(p.find(f"{{{W}}}pPr"), "jc", val="center")
    run(p, "CET MWW   ·   ", size=18, color="777777")
    field = node(p, "fldSimple", instr=" PAGE ")
    run(field, "1", size=18, color="777777")
    content_types = '''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/><Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/><Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/></Types>'''
    rels = '''<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/><Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/></Relationships>'''
    doc_rels = '''<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/><Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/></Relationships>'''
    core = f'''<?xml version="1.0"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>四六级英语单词本</dc:title><dc:creator>CET MWW</dc:creator><dc:identifier>{fingerprint(data)}</dc:identifier></cp:coreProperties>'''
    content_types = content_types.replace("</Types>", '''<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/><Override PartName="/word/header2.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/><Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/></Types>''')
    content_types = content_types.replace("</Types>", '''<Override PartName="/word/header-blank.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/></Types>''')
    doc_rels = doc_rels.replace("</Relationships>", '''<Relationship Id="rIdHeader" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/><Relationship Id="rIdFirstHeader" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header2.xml"/><Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/></Relationships>''')
    doc_rels = doc_rels.replace("</Relationships>", '''<Relationship Id="rIdBlankHeader" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header-blank.xml"/></Relationships>''')
    blank_header = Element(f"{{{W}}}hdr")
    paragraph(blank_header)
    settings = Element(f"{{{W}}}settings")
    node(settings, "view", val="print")
    compat = node(settings, "compat")
    node(compat, "compatSetting", name="compatibilityMode", uri="http://schemas.microsoft.com/office/word", val="15")
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        for path, content in {"[Content_Types].xml": content_types, "_rels/.rels": rels, "word/document.xml": xml_bytes(doc), "word/styles.xml": make_styles(), "word/_rels/document.xml.rels": doc_rels, "word/footer1.xml": xml_bytes(footer), "word/header1.xml": make_divider_header(), "word/header2.xml": make_divider_header(first_page=True), "word/header-blank.xml": xml_bytes(blank_header), "word/settings.xml": xml_bytes(settings), "docProps/core.xml": core}.items():
            archive.writestr(path, content)
    return output.getvalue()


def is_current(path, data):
    try:
        with ZipFile(path) as archive:
            return fingerprint(data).encode() in archive.read("docProps/core.xml")
    except (OSError, KeyError, ValueError, BadZipFile):
        return False
