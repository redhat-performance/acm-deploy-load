# PDF Generation Patterns (reportlab)

Code patterns for generating professional sizing report PDFs using reportlab.

## Document Setup

```python
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table,
    TableStyle, PageBreak,
)
from reportlab.platypus.tableofcontents import TableOfContents

class SizingDoc(BaseDocTemplate):
    """Document template that auto-populates table of contents from H1 headings."""
    def afterFlowable(self, flowable):
        if isinstance(flowable, Paragraph) and flowable.style.name == "H1":
            text = flowable.getPlainText()
            key = "s_" + str(hash(text) & 0xFFFFFFFF)
            self.canv.bookmarkPage(key)
            self.notify("TOCEntry", (0, text, self.page, key))

margin = 0.6 * inch
frame = Frame(margin, margin, letter[0] - 2 * margin, letter[1] - 2 * margin, id="normal")
doc = SizingDoc(
    output_path,
    pagesize=letter,
    pageTemplates=[PageTemplate(id="default", frames=[frame])],
)
```

## Styles

```python
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name="TitleCustom", parent=styles["Title"],
                          fontSize=16, spaceAfter=6))
styles.add(ParagraphStyle(name="H1", parent=styles["Heading1"],
                          fontSize=13, spaceAfter=4, spaceBefore=12))
styles.add(ParagraphStyle(name="H2", parent=styles["Heading2"],
                          fontSize=11, spaceAfter=4, spaceBefore=8))
styles.add(ParagraphStyle(name="BodyCustom", parent=styles["BodyText"],
                          fontSize=9, spaceAfter=4, leading=12))
styles.add(ParagraphStyle(name="BoldBody", parent=styles["BodyText"],
                          fontSize=9, spaceAfter=4, leading=12,
                          fontName="Helvetica-Bold"))
styles.add(ParagraphStyle(name="SmallBody", parent=styles["BodyText"],
                          fontSize=8, spaceAfter=3, leading=10))
styles.add(ParagraphStyle(name="SmallBodyWhite", parent=styles["BodyText"],
                          fontSize=8, spaceAfter=3, leading=10,
                          textColor=colors.white, fontName="Helvetica-Bold"))
```

## Color Scheme

```python
HEADER_BG = colors.HexColor("#2c3e50")   # Dark blue-gray table headers
HEADER_FG = colors.white
ALT_ROW = colors.HexColor("#ecf0f1")     # Light gray alternating rows
HIGHLIGHT_BG = colors.HexColor("#eaf2e3") # Light green for highlighted rows
WARN_BG = colors.HexColor("#f9e4e4")     # Light red for warning rows
```

## Table Helper

```python
def make_table(headers, rows, col_widths=None, highlight_last=False,
               highlight_rows=None, warn_rows=None):
    """Create a styled table with header row and optional highlighting."""
    data = [headers] + rows
    style_cmds = [
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), HEADER_FG),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for i in range(1, len(data)):
        if i % 2 == 0:
            style_cmds.append(("BACKGROUND", (0, i), (-1, i), ALT_ROW))
    if highlight_last:
        style_cmds.append(("BACKGROUND", (0, len(data)-1), (-1, len(data)-1), HIGHLIGHT_BG))
        style_cmds.append(("FONTNAME", (0, len(data)-1), (-1, len(data)-1), "Helvetica-Bold"))
    if highlight_rows:
        for r in highlight_rows:
            ri = r + 1
            style_cmds.append(("BACKGROUND", (0, ri), (-1, ri), HIGHLIGHT_BG))
            style_cmds.append(("FONTNAME", (0, ri), (-1, ri), "Helvetica-Bold"))
    if warn_rows:
        for r in warn_rows:
            ri = r + 1
            style_cmds.append(("BACKGROUND", (0, ri), (-1, ri), WARN_BG))
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle(style_cmds))
    return t
```

## Multi-line Header Cells

Use Paragraph with `<br/>` for multi-line table headers:

```python
headers = [
    "Phase",
    Paragraph("CPU P95<br/>(cores)", styles["SmallBodyWhite"]),
    Paragraph("Mem Max<br/>(GiB)", styles["SmallBodyWhite"]),
]
```

## Page Structure

```python
story = []

# Title
story.append(Paragraph("Report Title", styles["TitleCustom"]))
story.append(Spacer(1, 8))

# Table of Contents
toc = TableOfContents()
toc.levelStyles = [
    ParagraphStyle(name="TOC1", fontSize=9, leftIndent=20,
                   spaceBefore=2, spaceAfter=1, fontName="Helvetica"),
]
story.append(Paragraph("Contents", styles["H2"]))
story.append(toc)

# Sections (H1 headings auto-populate TOC)
story.append(Paragraph("Section Title", styles["H1"]))
story.append(Paragraph("Body text here.", styles["BodyCustom"]))

# Bullet points
items = ["First point", "Second point"]
for item in items:
    story.append(Paragraph("• " + item, styles["BodyCustom"]))

# Tables
story.append(make_table(
    ["Col A", "Col B", "Col C"],
    [["row1a", "row1b", "row1c"],
     ["row2a", "row2b", "row2c"]],
    col_widths=[2.0*inch, 2.0*inch, 2.0*inch],
))

# Page breaks between major sections
story.append(PageBreak())

# Build
doc.multiBuild(story)
```

## Usable Page Width

Letter page (8.5") with 0.6" margins on each side = 7.3" usable width.
Keep total col_widths under 7.3 inches.
