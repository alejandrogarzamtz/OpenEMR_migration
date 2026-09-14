from html.parser import HTMLParser
from io import BytesIO

from reportlab.lib.colors import HexColor
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate


class ReportTextParser(HTMLParser):
    def __init__(self):
        super().__init__();self.lines=[];self.current=[];self.kind="body";self.cells=[]
    def handle_starttag(self,tag,attrs):
        if tag in {"h1","h2"}:self.flush();self.kind=tag
        elif tag=="tr":self.flush();self.cells=[]
        elif tag in {"td","th"}:self.current=[]
        elif tag=="p":self.flush();self.kind="meta"
    def handle_data(self,data):
        value=" ".join(data.split())
        if value:self.current.append(value)
    def handle_endtag(self,tag):
        if tag in {"td","th"}:self.cells.append(" ".join(self.current));self.current=[]
        elif tag=="tr":
            if self.cells:self.lines.append(("row"," | ".join(self.cells)))
            self.cells=[]
        elif tag in {"h1","h2","p"}:self.flush();self.kind="body"
    def flush(self):
        value=" ".join(self.current).strip()
        if value:self.lines.append((self.kind,value))
        self.current=[]


def render_patient_report_pdf(html_document:str) -> bytes:
    parser=ReportTextParser();parser.feed(html_document);parser.flush()
    output=BytesIO();styles=getSampleStyleSheet()
    body=ParagraphStyle("ReportBody",parent=styles["BodyText"],fontName="Helvetica",fontSize=8.2,leading=10.2,spaceAfter=2,textColor=HexColor("#17201e"),alignment=TA_LEFT)
    row=ParagraphStyle("ReportRow",parent=body,fontName="Courier",fontSize=6.7,leading=8.4,borderColor=HexColor("#ccd7d3"),borderWidth=.35,borderPadding=3,spaceAfter=1)
    heading=ParagraphStyle("ReportHeading",parent=styles["Heading2"],fontName="Helvetica-Bold",fontSize=12,leading=14,textColor=HexColor("#176b5b"),spaceBefore=9,spaceAfter=4,keepWithNext=True)
    title=ParagraphStyle("ReportTitle",parent=styles["Title"],fontName="Helvetica-Bold",fontSize=18,textColor=HexColor("#17201e"),spaceAfter=8)
    meta=ParagraphStyle("ReportMeta",parent=body,fontSize=7,textColor=HexColor("#52615e"),spaceAfter=5)
    story=[]
    for kind,value in parser.lines:
        safe=value.replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")
        style=title if kind=="h1" else heading if kind=="h2" else meta if kind=="meta" else row if kind=="row" else body
        story.append(Paragraph(safe,style))
    def page(canvas,document):
        canvas.saveState();canvas.setFont("Helvetica",7);canvas.setFillColor(HexColor("#52615e"));canvas.drawString(16*mm,9*mm,"OpenRM patient report");canvas.drawRightString(LETTER[0]-16*mm,9*mm,f"Page {document.page}");canvas.restoreState()
    document=SimpleDocTemplate(output,pagesize=LETTER,rightMargin=14*mm,leftMargin=14*mm,topMargin=14*mm,bottomMargin=16*mm,title="OpenRM patient report",author="OpenRM")
    document.build(story,onFirstPage=page,onLaterPages=page)
    return output.getvalue()
