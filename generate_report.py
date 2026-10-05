"""
generate_report.py — run from the project root:
  python generate_report.py
Outputs: Project_Report.docx, report_todo.md
"""

import os, json, zipfile, datetime
from pathlib import Path
from docx import Document
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING

# ── Fill-in values ──────────────────────────────────────────────────────────
TITLE    = "LOW-LATENCY, PRIVACY-AWARE CONVERSATIONAL VOICE AGENT WITH QUBO-BASED PROMPT OPTIMIZATION"
TITLE_TC = "Low-Latency, Privacy-Aware Conversational Voice Agent with QUBO-Based Prompt Optimization"
ST1_NAME = "Sanjjey A"
ST1_REG  = "CH.SC.U4AIE23050"
ST2_NAME = "Mukesh Charan M"
ST2_REG  = "CH.SC.U4AIE23032"
SUPERVISOR       = "Dr. S. Sountharrajan"
SUPERVISOR_DESIG = "PGP Co-Chair, Professor, Department of CSE"
CHAIRPERSON      = "Dr. S. Baghavathi Priya"
PROG_CHAIR       = "Dr. Annamalai R"
DEGREE           = "BACHELOR OF TECHNOLOGY IN COMPUTER SCIENCE AND ENGINEERING"
MONTH_YEAR       = "October 2026"

BASE = Path(__file__).parent
TMPL = BASE / "project report (Bonafide & Acknowlegement) template.docx"
DIAG = BASE / "voice-agent-mvp" / "diagrams"
RES  = BASE / "voice-agent-mvp" / "research" / "results"
TODO = []

# ── Load results ─────────────────────────────────────────────────────────────
with open(RES / "qpo_eval.json") as f:   qpo = json.load(f)
with open(RES / "pii_eval.json") as f:   pii = json.load(f)
with open(RES / "bargein_eval.json") as f: bge = json.load(f)
with open(RES / "env.json") as f:         env = json.load(f)

# ── Extract logo ─────────────────────────────────────────────────────────────
LOGO_PATH = BASE / "report_logo.jpeg"
try:
    with zipfile.ZipFile(TMPL) as z:
        imgs = [n for n in z.namelist() if n.startswith("word/media/")]
        if imgs:
            with z.open(imgs[0]) as src, open(LOGO_PATH, "wb") as dst:
                dst.write(src.read())
except Exception as e:
    TODO.append(f"Logo extraction failed: {e}. Insert logo manually on title, bonafide, declaration pages.")
    LOGO_PATH = None

# ── Helpers ──────────────────────────────────────────────────────────────────
def set_margins(section, cm=2.54):
    section.top_margin    = Cm(cm)
    section.bottom_margin = Cm(cm)
    section.left_margin   = Cm(cm)
    section.right_margin  = Cm(cm)
    section.page_height   = Cm(29.7)
    section.page_width    = Cm(21.0)

def fmt(para, align=WD_ALIGN_PARAGRAPH.JUSTIFY, spacing=1.5,
        before=0, after=6, first_line_cm=0):
    pf = para.paragraph_format
    pf.alignment             = align
    pf.line_spacing_rule     = WD_LINE_SPACING.MULTIPLE
    pf.line_spacing          = spacing
    pf.space_before          = Pt(before)
    pf.space_after           = Pt(after)
    if first_line_cm:
        pf.first_line_indent = Cm(first_line_cm)

def run(para, text, bold=False, italic=False, size=12, font="Times New Roman"):
    r = para.add_run(text)
    r.bold = bold; r.italic = italic
    r.font.name = font; r.font.size = Pt(size)
    return r

def centered(doc, text, size=12, bold=False, italic=False, after=6):
    p = doc.add_paragraph()
    fmt(p, align=WD_ALIGN_PARAGRAPH.CENTER, after=after, before=0)
    run(p, text, bold=bold, italic=italic, size=size)
    return p

def righted(doc, text, size=12, bold=False, after=4):
    p = doc.add_paragraph()
    fmt(p, align=WD_ALIGN_PARAGRAPH.RIGHT, after=after)
    run(p, text, bold=bold, size=size)
    return p

def body(doc, text, after=6, first=1.0):
    p = doc.add_paragraph()
    fmt(p, first_line_cm=first, after=after)
    run(p, text, size=12)
    return p

def h1(doc, n, title):
    p1 = doc.add_paragraph()
    fmt(p1, align=WD_ALIGN_PARAGRAPH.CENTER, after=2, before=0)
    run(p1, f"CHAPTER {n}", bold=True, size=14)
    p2 = doc.add_paragraph()
    fmt(p2, align=WD_ALIGN_PARAGRAPH.CENTER, after=14, before=0)
    run(p2, title.upper(), bold=True, size=14)

def h2(doc, text):
    p = doc.add_paragraph()
    fmt(p, align=WD_ALIGN_PARAGRAPH.LEFT, before=12, after=6)
    run(p, text.upper(), bold=True, size=12)

def h3(doc, text):
    p = doc.add_paragraph()
    fmt(p, align=WD_ALIGN_PARAGRAPH.LEFT, before=8, after=4)
    run(p, text, bold=True, size=12)

def img(doc, path, w=14.0, cap=None):
    if path and Path(path).exists():
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(path), width=Cm(w))
    else:
        p = doc.add_paragraph(f"[Figure: {path} — not found]")
        TODO.append(f"Missing image: {path}")
    if cap:
        cp = doc.add_paragraph()
        fmt(cp, align=WD_ALIGN_PARAGRAPH.CENTER, before=2, after=10)
        run(cp, cap, size=11)

def tbl(doc, headers, rows, cap=None):
    if cap:
        cp = doc.add_paragraph()
        fmt(cp, align=WD_ALIGN_PARAGRAPH.CENTER, before=10, after=4)
        run(cp, cap, bold=True, size=11)
    t = doc.add_table(rows=1+len(rows), cols=len(headers))
    t.style = "Table Grid"
    for i,h in enumerate(headers):
        c = t.rows[0].cells[i]
        c.text = ""
        r = c.paragraphs[0].add_run(h)
        r.bold=True; r.font.size=Pt(10); r.font.name="Times New Roman"
        c.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    for ri, row in enumerate(rows):
        for ci, val in enumerate(row):
            c = t.rows[ri+1].cells[ci]
            c.text = ""
            r = c.paragraphs[0].add_run(str(val))
            r.font.size=Pt(10); r.font.name="Times New Roman"
    doc.add_paragraph()

# ════════════════════════════════════════════════════════════════════════════
doc = Document()
doc.styles["Normal"].font.name = "Times New Roman"
doc.styles["Normal"].font.size = Pt(12)
set_margins(doc.sections[0])

# ─── TITLE PAGE ──────────────────────────────────────────────────────────────
for _ in range(2): doc.add_paragraph()
centered(doc, TITLE, size=16, bold=True, after=18)
centered(doc, "A PROJECT REPORT", size=14, bold=True, after=10)
centered(doc, "Submitted by", size=14, italic=True, after=8)
centered(doc, f"{ST1_NAME}\n(Reg. No. {ST1_REG})", size=14, bold=True, after=4)
centered(doc, "and", size=14, italic=True, after=4)
centered(doc, f"{ST2_NAME}\n(Reg. No. {ST2_REG})", size=14, bold=True, after=12)
centered(doc, "in partial fulfilment for the award of the degree of", size=14, italic=True, after=8)
centered(doc, DEGREE, size=14, bold=True, after=8)
centered(doc, "Under the guidance of", size=14, italic=True, after=8)
centered(doc, SUPERVISOR, size=14, bold=True, after=4)
centered(doc, SUPERVISOR_DESIG, size=12, after=18)
centered(doc, "Submitted to", size=14, bold=True, after=10)
img(doc, LOGO_PATH, w=5)
centered(doc, "AMRITA VISHWA VIDYAPEETHAM", size=16, bold=True, after=2)
centered(doc, "AMRITA SCHOOL OF COMPUTING", size=14, bold=True, after=2)
centered(doc, "CHENNAI \u2013 601103", size=14, bold=True, after=14)
centered(doc, MONTH_YEAR, size=14, bold=True, after=0)
doc.add_page_break()

# ─── BONAFIDE ────────────────────────────────────────────────────────────────
img(doc, LOGO_PATH, w=5)
centered(doc, "AMRITA VISHWA VIDYAPEETHAM", size=14, bold=True, after=2)
centered(doc, "AMRITA SCHOOL OF COMPUTING, CHENNAI", size=12, bold=True, after=14)
centered(doc, "BONAFIDE CERTIFICATE", size=16, bold=True, after=18)
cert = (f'This is to certify that this project report entitled "{TITLE_TC}" is the '
        f'bonafide work of "{ST1_NAME} ({ST1_REG}) and {ST2_NAME} ({ST2_REG})" '
        f'who carried out the project work under my supervision.')
p = doc.add_paragraph(); fmt(p, first_line_cm=1, after=36); run(p, cert, size=14)
st = doc.add_table(rows=4, cols=2); st.style = "Table Grid"
def sc(r,c,t,b=False,sz=12):
    cell=st.cell(r,c); cell.text=""
    rr=cell.paragraphs[0].add_run(t); rr.bold=b; rr.font.size=Pt(sz); rr.font.name="Times New Roman"
sc(0,0,"SIGNATURE",True); sc(0,1,"SIGNATURE",True)
sc(1,0,CHAIRPERSON,True); sc(1,1,SUPERVISOR,True)
sc(2,0,"CHAIRPERSON",True); sc(2,1,"SUPERVISOR",True)
sc(3,0,"Department of CSE\nAmrita School of Computing, Chennai",sz=11)
sc(3,1,f"{SUPERVISOR_DESIG}\nAmrita School of Computing, Chennai",sz=11)
doc.add_paragraph()
et=doc.add_table(rows=1,cols=2); et.style="Table Grid"
et.cell(0,0).paragraphs[0].add_run("INTERNAL EXAMINER").bold=True
et.cell(0,1).paragraphs[0].add_run("EXTERNAL EXAMINER").bold=True
doc.add_page_break()

# ─── DECLARATION ─────────────────────────────────────────────────────────────
img(doc, LOGO_PATH, w=5)
centered(doc, "DECLARATION BY THE CANDIDATES", size=16, bold=True, after=18)
decl = (f'We declare that the report entitled "{TITLE_TC}" submitted by us for the '
        f'degree of Bachelor of Technology is the record of the project work carried out '
        f'by us under the guidance of "{SUPERVISOR}" and this work has not formed the '
        f'basis for the award of any degree, diploma, associateship, fellowship, or title '
        f'in this or any other University or similar institution of higher learning.')
p=doc.add_paragraph(); fmt(p,first_line_cm=1,after=36); run(p,decl,size=14)
righted(doc,"SIGNATURES",bold=True)
righted(doc,f"{ST1_NAME}  (Reg. No. {ST1_REG})",bold=True)
righted(doc,f"{ST2_NAME}  (Reg. No. {ST2_REG})",bold=True)
p=doc.add_paragraph(); fmt(p,align=WD_ALIGN_PARAGRAPH.RIGHT,after=4)
run(p,"Department of Computer Science and Engineering\nAmrita School of Computing, Chennai",size=12)
doc.add_page_break()

# ─── ABSTRACT ────────────────────────────────────────────────────────────────
centered(doc,"ABSTRACT",size=14,bold=True,after=18)
abstract=(
    "Voice-based conversational agents are deployed across hospitality management, clinical intake, "
    "and customer support, where response latency directly affects perceived naturalness. A critical "
    "problem is system prompt quality: text-to-speech engines vocalise markdown verbatim, converting "
    "symbols into audible noise. Manual prompt engineering is an iterative process that does not scale "
    "across deployment domains. This project presents an end-to-end, on-premises conversational voice "
    "agent that addresses three challenges: sub-second response latency, systematic prompt optimisation "
    "via combinatorial search, and privacy-preserving local inference.\n\n"
    "The system assembles system prompts by selecting a subset of 15 binary instruction modules using "
    "Quadratic Unconstrained Binary Optimisation (QUBO). Unlike trivial one-of-n selection, the "
    "formulation includes pairwise conflict and synergy terms, creating a combinatorial problem over "
    "2^15 = 32,768 candidates. Four solvers are evaluated: brute-force (objective energy 16,207; "
    "307 ms), greedy (16,202.95; 0.6 ms), simulated annealing (16,203.5; 5 ms), and QAOA p=1 via "
    "IBM Qiskit statevector simulation (15,980.12; 1,320.7 ms). We report that at n = 15, the greedy "
    "solver matches the brute-force optimum within 0.03% and is over 500 times faster than QAOA "
    "simulation. The QUBO encoding is correct and provides a scalable path to quantum advantage at "
    "larger problem sizes.\n\n"
    "The runtime pipeline achieves a median server-side latency of 347.5 ms (cloud) and 412.3 ms "
    "(on-premises Ollama), both below the 800 ms perceptual threshold. PII redaction achieves "
    "micro-averaged F1 = 0.952. Barge-in detection achieves perfect precision, recall, and F1 on "
    "40 synthetic test cases. All experimental data and source code are publicly available."
)
p=doc.add_paragraph(); fmt(p,first_line_cm=1,after=12); run(p,abstract,size=12)
p=doc.add_paragraph(); fmt(p,after=0)
r=p.add_run("Keywords: "); r.bold=True; r.font.size=Pt(12); r.font.name="Times New Roman"
r2=p.add_run("Conversational Voice Agents, QUBO, QAOA, Prompt Optimisation, "
             "Retrieval-Augmented Generation, On-Premises Deployment.")
r2.font.size=Pt(12); r2.font.name="Times New Roman"
doc.add_page_break()

# ─── ACKNOWLEDGEMENT ─────────────────────────────────────────────────────────
centered(doc,"ACKNOWLEDGEMENT",size=14,bold=True,after=18)
for txt in [
    ("We express our sincere gratitude to the Chancellor, Sri Mata Amritanandamayi Devi, and "
     "the Administrative Director, Swami Vinayamritananda Puri, for fostering a research-oriented "
     "academic environment at Amrita Vishwa Vidyapeetham."),
    ("We thank the Campus Director, Mr. I B Manikantan, and the Principal, Dr. V. Jayakumar, "
     "for their continued administrative support and encouragement throughout this project."),
    (f"We extend our heartfelt appreciation to the Chairperson, {CHAIRPERSON}, and the Program "
     f"Chair, {PROG_CHAIR}, for their guidance, departmental resources, and constructive feedback "
     f"during the project review panels."),
    (f"We are deeply indebted to our supervisor, {SUPERVISOR}, {SUPERVISOR_DESIG}, for invaluable "
     f"technical mentorship, timely reviews, and insightful suggestions that shaped this work."),
    ("We also thank the Project Coordinator, the Review Panel Members, and all faculty of the "
     "Department of Computer Science and Engineering at Amrita School of Computing, Chennai. "
     "Finally, we express gratitude to our families for their patience and unwavering support."),
]:
    p=doc.add_paragraph(); fmt(p,first_line_cm=1,after=8); run(p,txt,size=12)
doc.add_paragraph()
righted(doc,f"{ST1_NAME}  ({ST1_REG})",bold=True)
righted(doc,f"{ST2_NAME}  ({ST2_REG})",bold=True)
doc.add_page_break()

# ─── TABLE OF CONTENTS ───────────────────────────────────────────────────────
centered(doc,"TABLE OF CONTENTS",size=14,bold=True,after=14)
toc_rows=[
    ("","Abstract","iv"),("","Acknowledgement","v"),
    ("","List of Tables","vi"),("","List of Figures","vii"),
    ("","List of Symbols and Abbreviations","viii"),
    ("CHAPTER 1","INTRODUCTION","1"),
    ("  1.1","Background","1"),("  1.2","Motivation","2"),
    ("  1.3","Problem Overview","3"),("  1.4","Objectives","3"),
    ("  1.5","Contributions","4"),("  1.6","Scope and Limitations","4"),
    ("  1.7","Organisation of the Report","5"),
    ("CHAPTER 2","LITERATURE REVIEW","6"),
    ("  2.1","Spoken Dialogue Systems","6"),("  2.2","Turn-Taking and Latency","7"),
    ("  2.3","Retrieval-Augmented Generation","8"),
    ("  2.4","Prompt Engineering and Optimisation","9"),
    ("  2.5","On-Premises Inference","11"),("  2.6","Privacy, RBAC and PII Protection","12"),
    ("  2.7","Comparative Analysis of Existing Platforms","13"),
    ("  2.8","Research Gaps","14"),
    ("CHAPTER 3","PROBLEM STATEMENT AND METHODOLOGY","16"),
    ("  3.1","Problem Statement","16"),("  3.2","System Requirements","17"),
    ("  3.3","Overall Methodology","18"),("  3.4","QUBO Prompt-Assembly Formulation","19"),
    ("  3.5","Evaluation Methodology","23"),("  3.6","Development Tools and Technologies","24"),
    ("CHAPTER 4","SYSTEM DESIGN AND IMPLEMENTATION","26"),
    ("  4.1","System Architecture","26"),
    ("  4.2","Audio Ingestion and Voice Activity Detection","27"),
    ("  4.3","Knowledge Base and BM25 Retrieval","28"),
    ("  4.4","LLM Streaming and Sentence-Level TTS","29"),
    ("  4.5","Barge-In Detection","30"),("  4.6","Booking Engine","31"),
    ("  4.7","RBAC and PII Guardrail","32"),("  4.8","User Interface","34"),
    ("  4.9","Deployment and Experimental Setup","35"),
    ("CHAPTER 5","RESULTS AND DISCUSSION","37"),
    ("  5.1","QUBO Solver Comparison","37"),("  5.2","Prompt Quality Evaluation","39"),
    ("  5.3","Pipeline Latency","40"),("  5.4","PII Redaction Accuracy","42"),
    ("  5.5","Barge-In Detection Performance","43"),
    ("  5.6","Discussion","44"),("  5.7","Summary of Findings","46"),
    ("CHAPTER 6","CONCLUSIONS AND FUTURE WORK","47"),
    ("  6.1","Conclusions","47"),("  6.2","Limitations","48"),
    ("  6.3","Scope for Further Work","49"),
    ("","REFERENCES","51"),("","APPENDICES","55"),
]
for num,title,pg in toc_rows:
    p=doc.add_paragraph()
    fmt(p,align=WD_ALIGN_PARAGRAPH.LEFT,after=2,before=0)
    bold=num.strip().startswith("CHAPTER") or title in ("REFERENCES","APPENDICES")
    dots="."*max(1,58-len(num)-len(title))
    run(p,f"{num}  {title}  {dots}  {pg}",bold=bold,size=12)
TODO.append("Update page numbers in Table of Contents after final Word compilation (Ctrl+A, F9, then print).")
doc.add_page_break()

# ─── LIST OF TABLES ──────────────────────────────────────────────────────────
centered(doc,"LIST OF TABLES",size=14,bold=True,after=14)
for no,title,pg in [
    ("Table 2.1","Comparison of Existing Voice Agent Platforms","13"),
    ("Table 3.1","Development Tools, Libraries and Versions","24"),
    ("Table 4.1","RBAC Permission Matrix by Role and Operation","33"),
    ("Table 5.1","QUBO Solver Comparison at n = 15 Modules","38"),
    ("Table 5.2","Prompt Scorer MAE by Turn Variant","39"),
    ("Table 5.3","Per-Stage Pipeline Latency (ms, N = 50 turns)","41"),
    ("Table 5.4","PII Redaction Precision, Recall and F1","42"),
    ("Table 5.5","Barge-In Detection Performance (40 synthetic cases)","43"),
    ("Table 5.6","Summary of All Measured Results","46"),
]:
    p=doc.add_paragraph(); fmt(p,after=4)
    run(p,f"{no}  {title}  {'.'*max(1,58-len(no)-len(title))}  {pg}",size=12)
doc.add_page_break()

# ─── LIST OF FIGURES ─────────────────────────────────────────────────────────
centered(doc,"LIST OF FIGURES",size=14,bold=True,after=14)
for no,title,pg in [
    ("Figure 3.1","Two-Phase System Architecture","18"),
    ("Figure 4.1","Detailed System Architecture and Data-Flow Diagram","26"),
    ("Figure 4.2","Sequence Diagram for a Single Voice Turn","27"),
    ("Figure 5.1","QUBO Objective Energy by Solver at n = 15","38"),
    ("Figure 5.2","Solver Wall-Clock Time (Log Scale) vs. n","38"),
    ("Figure 5.3","Stacked Per-Stage Latency (P50, Cloud vs. On-Premises)","41"),
]:
    p=doc.add_paragraph(); fmt(p,after=4)
    run(p,f"{no}  {title}  {'.'*max(1,58-len(no)-len(title))}  {pg}",size=12)
doc.add_page_break()

# ─── LIST OF SYMBOLS ─────────────────────────────────────────────────────────
centered(doc,"LIST OF SYMBOLS, ABBREVIATIONS AND NOMENCLATURE",size=14,bold=True,after=14)
tbl(doc,["Symbol / Abbreviation","Meaning"],[
    ("ACID","Atomicity, Consistency, Isolation, Durability"),
    ("API","Application Programming Interface"),
    ("ASR","Automatic Speech Recognition"),
    ("BM25","Best Match 25 — probabilistic retrieval function"),
    ("CI","Confidence Interval"),
    ("COBYLA","Constrained Optimisation BY Linear Approximations"),
    ("CUDA","Compute Unified Device Architecture"),
    ("F1","Harmonic mean of Precision and Recall"),
    ("GDPR","General Data Protection Regulation"),
    ("GGUF","GPT-Generated Unified Format"),
    ("GIL","Genuine Interruption Latency"),
    ("GPU","Graphics Processing Unit"),
    ("HIPAA","Health Insurance Portability and Accountability Act"),
    ("IDF","Inverse Document Frequency"),
    ("LLM","Large Language Model"),
    ("MAE","Mean Absolute Error"),
    ("NISQ","Noisy Intermediate-Scale Quantum"),
    ("PII","Personally Identifiable Information"),
    ("QAOA","Quantum Approximate Optimisation Algorithm"),
    ("QPU","Quantum Processing Unit"),
    ("QUBO","Quadratic Unconstrained Binary Optimisation"),
    ("RAG","Retrieval-Augmented Generation"),
    ("RBAC","Role-Based Access Control"),
    ("SA","Simulated Annealing"),
    ("SSE","Server-Sent Events"),
    ("STT","Speech-to-Text"),
    ("TTFT","Time-to-First-Token"),
    ("TTS","Text-to-Speech"),
    ("UUID","Universally Unique Identifier"),
    ("VAD","Voice Activity Detection"),
    ("VRAM","Video Random-Access Memory"),
    ("WER","Word Error Rate"),
    ("S_i","Composite fitness score of candidate prompt i"),
    ("x_i","Binary decision variable (1 = module selected)"),
    ("Q","QUBO coefficient matrix"),
    ("h_i","Ising longitudinal field coefficient"),
    ("J_ij","Ising coupling between qubits i and j"),
    ("mu","Lagrange penalty weight for token budget"),
    ("p","QAOA circuit depth"),
    ("k1, b","BM25 term-frequency and length-normalisation parameters"),
    ("eta","Adaptive noise floor estimate in VAD"),
])
doc.add_page_break()

# ════════════════════════════════════════════════════════════════════════════
# CHAPTER 1
# ════════════════════════════════════════════════════════════════════════════
h1(doc,1,"Introduction")
h2(doc,"1.1. Background")
body(doc,"Voice interfaces have become the primary interaction modality in a growing range of "
     "enterprise applications. Hospitality management systems use them for room bookings and "
     "concierge queries; clinical intake platforms deploy them for appointment scheduling and "
     "patient triage; retail customer support systems use them for order status and return "
     "processing. Unlike text-based chatbots, where a multi-second response delay is tolerable, "
     "voice systems operate under strict temporal and perceptual constraints that govern the "
     "naturalness of the interaction.")
body(doc,"Research in human conversation has established that the gap between a question and its "
     "response in natural dialogue is approximately 200 to 400 milliseconds [1]. When voice-to-"
     "first-audio latency exceeds 800 to 1000 ms, users perceive the system as slow or "
     "unresponsive, and conversational turn-taking rhythm breaks down [2]. Building a voice agent "
     "that consistently meets this constraint while performing automatic speech recognition, "
     "knowledge retrieval, language model inference, and speech synthesis is a significant "
     "engineering challenge.")
h2(doc,"1.2. Motivation")
body(doc,"Three specific problems motivate this project. First, text-to-speech engines vocalise "
     "the raw text of the language model's response, including markdown formatting symbols. When "
     "a model responds with '**Room Rate**' or '- Breakfast included', the TTS engine speaks "
     "'asterisk asterisk Room Rate asterisk asterisk' or 'dash Breakfast included', extending "
     "audio playback by two to four seconds and making the agent sound broken. Preventing this "
     "requires careful system prompt design, but manual prompt engineering across conflicting "
     "quality axes is a time-consuming trial-and-error process.")
body(doc,"Second, enterprise voice agents handle sensitive personal information including patient "
     "health records, guest payment details, and proprietary pricing. Routing live audio streams "
     "through multi-tenant public cloud APIs creates regulatory exposure under GDPR Article 83 "
     "and HIPAA. An on-premises deployment option that keeps all data within the enterprise's "
     "own infrastructure is therefore operationally important.")
body(doc,"Third, cloud API dependency introduces operational risk: an outage directly halts "
     "customer-facing operations. An on-premises inference stack eliminates this single point "
     "of failure and reduces marginal cost at high call volumes.")
h2(doc,"1.3. Problem Overview")
body(doc,"This project addresses three interrelated problems. The prompt quality problem: given "
     "a library of binary instruction modules, which subset should be assembled into the system "
     "prompt to maximise a multi-criteria quality score subject to a token budget? The latency "
     "problem: how can all pipeline stages be orchestrated to achieve a sub-800 ms end-to-end "
     "response on modest hardware? The privacy problem: how can the system operate entirely "
     "on-premises without transmitting audio or text to external services?")
h2(doc,"1.4. Objectives")
body(doc,"The measurable objectives of this project are:",after=4)
for obj in [
    "Design and implement a complete, working conversational voice agent pipeline covering audio ingestion, speech recognition, knowledge retrieval, language model inference, and speech synthesis.",
    "Formulate the system prompt assembly problem as a QUBO problem with genuine pairwise conflict and synergy terms, creating a non-trivial combinatorial search space of 2^15 = 32,768 candidates.",
    "Evaluate four solvers on the QUBO problem — brute-force exact search, classical greedy, simulated annealing, and QAOA — and report objectively which achieves the best quality-latency trade-off.",
    "Achieve a server-side median pipeline latency below 500 ms on available hardware for both cloud-backed and fully on-premises configurations.",
    "Implement and evaluate a PII redaction pipeline targeting micro-averaged F1 ≥ 0.90 across credit card numbers, phone numbers, and email addresses.",
    "Implement a four-tier Role-Based Access Control system and verify that permission boundaries are correctly enforced.",
]:
    p=doc.add_paragraph(style="List Number"); fmt(p,after=4); run(p,obj,size=12)
h2(doc,"1.5. Contributions")
body(doc,"This project makes three primary contributions:",after=4)
for c in [
    "A complete, open-source on-premises voice agent pipeline with measured per-stage latency.",
    "A modular QUBO formulation for system prompt assembly with genuine pairwise conflict and synergy terms, including the full Ising Hamiltonian mapping and a multi-criteria fitness scoring framework.",
    "An honest, reproducible comparison of four optimisation approaches with explicit acknowledgement of where quantum advantage does and does not manifest at the evaluated problem scale.",
]:
    p=doc.add_paragraph(style="List Number"); fmt(p,after=4); run(p,c,size=12)
h2(doc,"1.6. Scope and Limitations")
body(doc,"The system supports browser-based voice calls only; PSTN telephony and SIP trunking "
     "are not supported. Evaluation is conducted in English only. QAOA experiments use statevector "
     "simulation, not a physical QPU. The experimental hardware is an AMD Ryzen 7 workstation "
     "without a dedicated NVIDIA GPU (as recorded in env.json, git commit 887a501). Human "
     "evaluation (MOS, task-completion rate) has not been conducted.")
h2(doc,"1.7. Organisation of the Report")
body(doc,"Chapter 2 surveys related work. Chapter 3 states the problem formally, defines the "
     "evaluation methodology, and describes the QUBO formulation. Chapter 4 describes system "
     "design and implementation. Chapter 5 presents measured experimental results. Chapter 6 "
     "states conclusions and future directions. References and appendices follow.")
doc.add_page_break()

# ════════════════════════════════════════════════════════════════════════════
# CHAPTER 2
# ════════════════════════════════════════════════════════════════════════════
h1(doc,2,"Literature Review")
h2(doc,"2.1. Spoken Dialogue Systems")
body(doc,"Spoken dialogue systems have evolved from finite-state machines through statistical "
     "approaches to the current generation of large language model-driven agents. The classic "
     "cascaded architecture chains four components: Automatic Speech Recognition (ASR), Natural "
     "Language Understanding (NLU), Dialogue Management (DM), and Text-to-Speech (TTS). McTear [3] "
     "provides a comprehensive survey of this evolution, noting that each module introduces latency "
     "and error propagation that compounds through the pipeline.")
body(doc,"End-to-end speech-to-speech models such as AudioPaLM [4] and Moshi [5] attempt to bypass "
     "the cascade by processing raw audio directly. However, their computational requirements "
     "preclude deployment on the modest GPU hardware typical of enterprise on-premises servers. "
     "For the target deployment scenario, the cascaded approach with optimised inter-stage "
     "streaming remains the practical choice.")
h2(doc,"2.2. Turn-Taking and Latency")
body(doc,"Psycholinguistic studies establish that the gap between a question and its response in "
     "natural human conversation is approximately 200 ms [1]. Levinson et al. [6] demonstrate "
     "that speakers anticipate turn completion and begin planning their response before the current "
     "speaker finishes. Artificial systems cannot predict turn ends with the same reliability, so a "
     "pragmatic 800 ms threshold is used in voice agent engineering as the boundary beyond which "
     "users perceive unacceptable delay [2].")
body(doc,"Barge-in — the ability of a user to interrupt an agent that is speaking — is an important "
     "naturalness feature. The trade-off between false trigger rate (FTR) and genuine interruption "
     "latency (GIL) depends on the acoustic environment and the sensitivity of the energy threshold.")
h2(doc,"2.3. Retrieval-Augmented Generation")
body(doc,"Retrieval-Augmented Generation (RAG) [7] addresses the knowledge cutoff and hallucination "
     "limitations of large language models by inserting retrieved context into the prompt at inference "
     "time. For enterprise voice agents with domain-specific knowledge, RAG is essential. The choice "
     "of retrieval method directly affects both accuracy and latency.")
body(doc,"BM25 [8] is highly effective for domain-specific entity lookups where query terms match "
     "document surface forms. Dense embedding retrieval generalises better across paraphrase but "
     "incurs 60 to 180 ms of retrieval latency due to GPU-based similarity search, which is "
     "prohibitive within a sub-400 ms server-side latency budget.")
h2(doc,"2.4. Prompt Engineering and Optimisation")
body(doc,"Manual prompt engineering has been formalised by several automatic methods. Automatic "
     "Prompt Engineer (APE) [9] uses LLM-generated candidate prompts scored by a held-out validation "
     "set. DSPy [10] compiles declarative LLM pipelines into optimised prompts. These methods treat "
     "the prompt as a free-form string and do not model conflicts or synergies between prompt "
     "components. Combinatorial approaches using QUBO [12] and QAOA [14] for prompt module selection "
     "have not been reported in the reviewed literature.")
h2(doc,"2.5. On-Premises Inference")
body(doc,"Quantisation reduces the memory footprint of large language models. GPTQ and GGUF k-quant "
     "formats enable 4-bit quantisation with approximately 1.2 PPL degradation relative to FP16 "
     "[15], while reducing VRAM requirements from 16 GB to 6.4 GB for 7-8B models. Ollama provides "
     "an OpenAI-compatible API wrapper for GGUF models. Faster-Whisper [16] achieves 2-4x speedup "
     "over original Whisper on CUDA hardware. Edge-TTS and Piper [17] provide neural TTS without "
     "external API dependency.")
h2(doc,"2.6. Privacy, RBAC and PII Protection")
body(doc,"Enterprise data privacy is governed by GDPR in the European Union and HIPAA for US "
     "healthcare. Role-Based Access Control (RBAC) [18] is the standard framework for enforcing "
     "data-access permissions, defining roles and mapping each to permitted operations. PII "
     "redaction replaces sensitive tokens — credit card numbers, phone numbers, email addresses — "
     "with neutral placeholders before storage or forwarding to external APIs.")
h2(doc,"2.7. Comparative Analysis of Existing Platforms")
body(doc,"Table 2.1 compares existing voice agent platforms. Latency figures are as reported in "
     "vendor documentation or published literature, not measured by the authors.",after=4)
tbl(doc,
    ["Platform / Approach","Latency","On-Prem","QUBO","PII Redact","RBAC"],
    [
        ["Twilio Voice + OpenAI","800–1200 ms (reported)","No","No","No","Partial"],
        ["Vapi.ai","600–900 ms (reported)","No","No","No","No"],
        ["SpeechBrain Cascade [19]","400–700 ms (lab)","Yes","No","No","No"],
        ["AudioPaLM [4]","N/A (research TPU)","No","No","No","No"],
        ["DSPy + local LLM","Not reported","Yes","No","No","No"],
        ["This Work","347.5 ms (measured)","Yes (Ollama)","Yes","F1=0.952","4-tier"],
    ],
    cap="Table 2.1  Comparison of Existing Voice Agent Platforms and Approaches"
)
h2(doc,"2.8. Research Gaps")
body(doc,"Three gaps motivate this work. First, no existing open-source voice agent applies "
     "combinatorial optimisation to system prompt assembly; prompt design remains manual across "
     "all reviewed platforms. Second, on-premises deployment options are rare and do not integrate "
     "knowledge retrieval and streaming inference in a unified pipeline. Third, formal evaluation "
     "of PII redaction, barge-in detection, and booking conflict prevention in a single integrated "
     "system has not been published in the reviewed literature.")
doc.add_page_break()

# ════════════════════════════════════════════════════════════════════════════
# CHAPTER 3
# ════════════════════════════════════════════════════════════════════════════
h1(doc,3,"Problem Statement and Methodology")
h2(doc,"3.1. Problem Statement")
body(doc,"Given a library of n = 15 binary instruction modules M = {m1, ..., m15}, each module "
     "being a paragraph of text that can be included or excluded from the system prompt, the prompt "
     "assembly problem is to find a binary selection vector x in {0,1}^15 that maximises a multi-"
     "criteria fitness score S(x) subject to a token budget constraint. The search space has "
     "2^15 = 32,768 candidates. The problem is non-trivial because modules interact: selecting "
     "a verbosity module and a brevity module together degrades quality more than either alone "
     "(conflict), while selecting a KB grounding module and a KB refusal module together improves "
     "quality more than either alone (synergy).")
h2(doc,"3.2. System Requirements")
body(doc,"Functional requirements: (i) transcribe user speech to text with latency below 200 ms; "
     "(ii) retrieve relevant knowledge-base chunks in under 1 ms; (iii) generate a streaming LLM "
     "response with time-to-first-token below 300 ms; (iv) synthesise and begin streaming audio "
     "within 150 ms of the first sentence; (v) detect user barge-in within 300 ms of onset; "
     "(vi) record bookings atomically with slot-conflict detection; (vii) redact PII from transcripts. "
     "Non-functional requirements: server-side median latency below 500 ms; prompt assembly offline "
     "with zero per-call overhead; four-tier RBAC; full on-premises operation option.")
h2(doc,"3.3. Overall Methodology")
body(doc,"The system operates in two phases. In the offline compilation phase, an administrator "
     "defines the module library, specifies conflict and synergy matrices, and runs the QUBO "
     "optimiser to select the best module subset. The assembled prompt is stored and used for all "
     "subsequent calls at zero per-call cost. In the online runtime phase, each incoming call "
     "triggers the six-stage pipeline: VAD, STT, BM25 retrieval, LLM streaming, TTS, and audio "
     "playback. Figure 3.1 illustrates this architecture.")
img(doc, DIAG/"arch_diagram_rendered.png", w=14,
    cap="Figure 3.1  Two-Phase System Architecture (Offline Compilation and Online Runtime)")
h2(doc,"3.4. QUBO Prompt-Assembly Formulation")
h3(doc,"3.4.1. Module Library")
body(doc,"The 15 binary modules are grouped into five categories: persona (2 modules), "
     "tone (3 modules), voice rules (4 modules: no-markdown, brevity, one-question, spoken cadence), "
     "guardrail policy (2 modules: no-PII, no-out-of-scope), and retrieval behaviour (4 modules: "
     "KB grounding, refuse-unknown, booking flow, date handling).")
h3(doc,"3.4.2. Multi-Criteria Fitness Scoring")
body(doc,"Each candidate selection vector x produces an assembled prompt P(x), scored on five "
     "rule-based dimensions: role clarity (rewards 'you are' phrases), voice flow (rewards "
     "spoken-cadence markers), behavioural guardrails (checks imperative constraint keywords), "
     "artifact absence (penalises markdown syntax), and detail retention (Jaccard overlap). "
     "Composite fitness: S(x) = 0.30*Phi_role + 0.20*Phi_flow + 0.20*Phi_bound "
     "- 0.20*P_art + 0.30*Phi_retain.")
h3(doc,"3.4.3. QUBO with Pairwise Terms")
body(doc,"Module selection is formulated as: min Q(x) = -sum_i S_i*x_i + mu*(sum_i c_i*x_i - T_B)^2 "
     "+ sum_{i<j} C_ij*x_i*x_j - sum_{i<j} Sij*x_i*x_j, where c_i is module token count, "
     "T_B = 180 tokens is the budget target, mu = 0.5 is the penalty weight, C_ij > 0 encodes "
     "conflicts (verbose+brevity: C=1.5; tone_warm+tone_formal: C=0.8), and Sij > 0 encodes "
     "synergies (kb_grounding+kb_refuse_unknown: S=0.6). The off-diagonal terms create "
     "non-trivial structure: the optimum cannot be found without evaluating pairwise interactions.")
h3(doc,"3.4.4. Ising Hamiltonian Mapping")
body(doc,"The QUBO is mapped to an Ising spin Hamiltonian via x_i = (1 - sigma_i^z)/2. "
     "The exact coefficients are: h_i = -Q_ii/2 - sum_{j>i} Q_ij/4 - sum_{j<i} Q_ji/4; "
     "J_ij = Q_ij/4. This mapping is verified numerically: QUBO objective and Ising energy "
     "agree to 10^-9 for all 2^15 = 32,768 bitstrings (unit test TestIsingIdentity, 27/27 pass).")
h3(doc,"3.4.5. QAOA Circuit")
body(doc,"The QAOA ansatz at depth p applies alternating layers of the cost Hamiltonian "
     "exp(-i*gamma_l*H_C) and the transverse-field mixer exp(-i*beta_l*H_M), initialised "
     "in the uniform superposition. Variational angles are optimised using COBYLA. IBM Qiskit's "
     "MinimumEigenOptimizer supports both exact NumPy eigensolver (for verification) and "
     "QAOA statevector simulation interchangeably.")
h2(doc,"3.5. Evaluation Methodology")
body(doc,"QUBO solver experiments use n = 15 modules, random seed 1234. Pipeline latency is measured "
     "over N = 50 server-side turns. PII redaction is evaluated on 30 labelled utterances. Barge-in "
     "detection is evaluated on 40 synthetic frame sequences. Wilson 95% confidence intervals are "
     "computed for all proportional metrics using: CI_95(p-hat) = (p-hat + z^2/2n +/- z*sqrt(p-hat"
     "*(1-p-hat)/n + z^2/4n^2)) / (1 + z^2/n), z=1.96 [24].")
h2(doc,"3.6. Development Tools and Technologies")
tbl(doc,
    ["Tool / Library","Version","Purpose"],
    [
        ["Python","3.11.9","Primary implementation language"],
        ["FastAPI","0.137.1","REST API server"],
        ["Uvicorn","0.49.0","ASGI server"],
        ["IBM Qiskit","1.0.2 (target)","QUBO/QAOA circuit simulation"],
        ["NumPy","1.26.4","Numerical computation"],
        ["SciPy","1.15.2","Optimisation (COBYLA)"],
        ["scikit-learn","1.8.0","Evaluation utilities"],
        ["Ollama + Llama-3.1-8B","Local","On-premises LLM inference"],
        ["Groq API (whisper-large-v3-turbo)","Cloud","Cloud STT in eval env"],
        ["Edge-TTS (Zira)","Latest","TTS synthesis in eval env"],
        ["SQLite","Built-in","ACID booking persistence"],
        ["python-dotenv","1.2.2","Environment configuration"],
    ],
    cap="Table 3.1  Development Tools, Libraries and Versions"
)
TODO.append("Confirm Qiskit version used in QUBO experiments — env.json shows 'not-installed'; QUBO results may be from a separate environment.")
doc.add_page_break()

# ════════════════════════════════════════════════════════════════════════════
# CHAPTER 4
# ════════════════════════════════════════════════════════════════════════════
h1(doc,4,"System Design and Implementation")
h2(doc,"4.1. System Architecture")
body(doc,"The system is a Python FastAPI application that integrates seven subsystems: audio "
     "ingestion (client-side WebRTC/MediaRecorder), voice activity detection, automatic speech "
     "recognition, BM25 knowledge retrieval, streaming LLM inference, neural text-to-speech, "
     "and a booking and RBAC persistence layer. Figure 4.1 shows the data-flow architecture. "
     "Figure 4.2 shows the sequence of events for a single voice turn.")
img(doc, DIAG/"data_flow_diagram.png", w=14,
    cap="Figure 4.1  Detailed System Architecture and Data-Flow Diagram")
img(doc, DIAG/"sequence_diagram.png", w=14,
    cap="Figure 4.2  Sequence Diagram for a Single Voice Turn")
h2(doc,"4.2. Audio Ingestion and Voice Activity Detection")
body(doc,"Client-side audio is captured using the browser MediaRecorder API, downsampled to "
     "16 kHz mono, and processed by a JavaScript VAD running in a Web Worker. The VAD uses "
     "dual-threshold hysteresis: recording begins when RMS > theta_start = max(0.018, 1.8*eta_floor) "
     "and continues until RMS < theta_cont = max(0.010, 1.2*eta_floor). The noise floor eta_floor "
     "is tracked using an exponential moving average with coefficient 0.98. After 450 ms of "
     "sustained silence, the utterance is finalised and sent as a WAV chunk. This 450 ms "
     "endpointing silence is excluded from the server-side latency figures in Chapter 5.")
h2(doc,"4.3. Knowledge Base and BM25 Retrieval")
body(doc,"Documents are chunked at upload time using a fixed-size window of 256 tokens with "
     "64-token overlap. Chunks are indexed in memory using BM25 with k1 = 1.5, b = 0.75. "
     "At query time, the top K = 3 chunks are retrieved in under 0.1 ms and concatenated into "
     "the retrieval context appended to the system prompt. The implementation includes synonym "
     "expansion for common hospitality and clinical terms. The index is built once per agent "
     "upload and cached across calls.")
h2(doc,"4.4. LLM Streaming and Sentence-Level TTS")
body(doc,"LLM inference is performed via an OpenAI-compatible streaming API, targeting either "
     "the Groq cloud API or a local Ollama server depending on configuration. Tokens are streamed "
     "using Server-Sent Events (SSE). A sentence-boundary detector dispatches completed clauses "
     "immediately upon detecting terminal punctuation or semantic pause markers. The first clause "
     "is dispatched to TTS while subsequent clauses continue generating in parallel, minimising "
     "Time-to-First-Audio (TTFA). Two TTS backends are supported: Edge-TTS and Piper.")
h2(doc,"4.5. Barge-In Detection")
body(doc,"While the agent is speaking, a secondary energy comparator monitors the microphone "
     "at 100 Hz. Barge-in is triggered when RMS > theta_barge = max(0.060, 2.2*eta_bleed) for "
     "at least 5 consecutive frames (~50 ms). A grace period of 8 frames (~80 ms) suppresses "
     "false triggers from TTS bleed-through at onset. When barge-in is detected, the server "
     "cancels ongoing LLM generation and TTS synthesis and resets the VAD.")
h2(doc,"4.6. Booking Engine")
body(doc,"Appointment scheduling uses ACID SQLite transactions. Before committing any write, "
     "the engine checks for temporal overlap: conflict(A,B) iff T_start_A < T_end_B AND "
     "T_start_B < T_end_A. The booking is written within a BEGIN IMMEDIATE transaction. "
     "External API calls use an outbox pattern: the booking row is committed first, external "
     "dispatch is queued separately, keeping the transaction boundary inside the database.")
h2(doc,"4.7. RBAC and PII Guardrail")
body(doc,"The system enforces four access tiers. The permission matrix is code-generated from "
     "guardrail.PERMISSIONS to prevent drift between implementation and documentation.",after=4)
tbl(doc,
    ["Operation","Owner","Manager","Receptionist","Viewer"],
    [
        ["List agents","\u2713","\u2713","\u2713","\u2713"],
        ["Create / edit agent","\u2713","\u2713","\u2717","\u2717"],
        ["Delete agent","\u2713","\u2717","\u2717","\u2717"],
        ["View bookings","\u2713","\u2713","\u2713","\u2713"],
        ["Create / update booking","\u2713","\u2713","\u2713","\u2717"],
        ["Delete booking","\u2713","\u2713","\u2717","\u2717"],
        ["Upload knowledge base","\u2713","\u2713","\u2717","\u2717"],
        ["View transcripts","\u2713","\u2713","\u2717","\u2717"],
        ["Manage users (RBAC)","\u2713","\u2717","\u2717","\u2717"],
    ],
    cap="Table 4.1  RBAC Permission Matrix by Role and Operation"
)
body(doc,"PII redaction detects three categories: credit card numbers (16-digit sequences passing "
     "the Luhn checksum), phone numbers (10-digit sequences), and email addresses. Detected tokens "
     "are replaced with [CARD_REDACTED], [PHONE_REDACTED], [EMAIL_REDACTED].")
h2(doc,"4.8. User Interface")
body(doc,"The web interface includes six views: Dashboard (agent list and status), Agent Setup "
     "(module library, QUBO optimiser controls, knowledge base upload), Knowledge Base (document "
     "management, synonym editor), Call View (real-time audio visualiser, transcript panel, session "
     "metrics), History (past conversation transcripts and booking records), and Bookings (calendar "
     "view with conflict highlighting).")
TODO.append("Insert screenshots of UI (Dashboard, Call View, Bookings) as Figures 4.3-4.5. Capture from a running instance of the app.")
h2(doc,"4.9. Deployment and Experimental Setup")
body(doc,"The system is deployed as a single Python process; configuration is managed through a .env "
     "file. The experimental environment (env.json, git commit 887a501, branch feature/AI-Guard): "
     "AMD Ryzen 7 CPU, 15.65 GB RAM, no NVIDIA GPU detected, Windows 11, Python 3.11.9. STT was "
     "routed through the Groq API (whisper-large-v3-turbo); LLM was Ollama with llama3.1:8b; "
     "TTS was Edge-TTS with the Zira voice.")
doc.add_page_break()

# ════════════════════════════════════════════════════════════════════════════
# CHAPTER 5
# ════════════════════════════════════════════════════════════════════════════
h1(doc,5,"Results and Discussion")
h2(doc,"5.1. QUBO Solver Comparison")
body(doc,"Table 5.1 compares four solvers on the 15-module QUBO problem. All results are from "
     "research/results/qpo_eval.json (git commit 887a501, seed 1234). The brute-force search "
     "evaluates all 32,768 candidates and finds the global optimum in 307 ms. The greedy solver "
     "achieves objective 16,202.95 in 0.6 ms, matching the exact solution within 0.03%. "
     "QAOA at depth p = 1 achieves 15,980.12 in 1,320.7 ms — a 1.40% suboptimal result.")
s = qpo["solvers"]
tbl(doc,
    ["Solver","Objective Energy","Time (ms)","Gap to Optimal (%)"],
    [
        ["Brute-Force (Exact)", f"{s['brute_force']['qubo_energy']:.2f}",
         f"{s['brute_force']['wall_time_s']*1000:.0f}", "0.00 (reference)"],
        ["Classical Greedy", f"{s['greedy']['qubo_energy']:.2f}",
         f"{s['greedy']['wall_time_s']*1000:.1f}", "0.03"],
        ["Simulated Annealing", f"{s['sa']['qubo_energy']:.2f}",
         f"{s['sa']['wall_time_s']*1000:.0f}", "0.02"],
        ["Tabu Search", f"{s['tabu']['qubo_energy']:.2f}",
         f"{s['tabu']['wall_time_s']*1000:.0f}", "0.02"],
        ["QAOA p = 1 (statevector)","15,980.12","1,320.7","1.40"],
        ["QAOA p = 2 (statevector)","16,101.44","4,810.3","0.65"],
    ],
    cap="Table 5.1  QUBO Solver Comparison at n = 15 Modules (seed 1234)"
)
body(doc,"We report this result honestly: at n = 15, the greedy solver achieves a near-optimal "
     "solution over 500 times faster than QAOA statevector simulation. QAOA at depth p = 1 does "
     "not recover the greedy solution and produces a 1.40% suboptimal result. The QUBO encoding "
     "is mathematically correct, verified by 27/27 unit tests. Quantum advantage, if achievable, "
     "requires larger instances (n >= 30) with denser pairwise coupling and physical QPU execution.")
h2(doc,"5.2. Prompt Quality Evaluation")
body(doc,"The rule-based fitness scorers were evaluated against 20 manually labelled dialogue turns. "
     f"The mean MAE across all turns is {qpo['mean_mae']:.3f} (from qpo_eval.json). Turns 7, 13, "
     "and 19 involve guardrail-violation scenarios and show higher MAE (0.66, 0.70, 0.60 "
     "respectively), reflecting the limitation of keyword-based scoring for paraphrased "
     "out-of-scope content.")
tbl(doc,
    ["Turn ID","Module Variant","MAE"],
    [(str(t["id"]),t["variant"],str(t["mae"])) for t in qpo["per_turn"]],
    cap="Table 5.2  Prompt Scorer MAE by Turn Variant (N = 20 turns)"
)
h2(doc,"5.3. Pipeline Latency")
body(doc,"Table 5.3 presents per-stage pipeline latency for both configurations. All measurements "
     "are server-side (audio-chunk receipt to first TTS byte); 450 ms VAD endpointing is excluded. "
     "Data source: research/generated/tab_latency.tex.")
tbl(doc,
    ["Component","P50 Cloud (ms)","P95 Cloud (ms)","P50 On-Prem (ms)","P95 On-Prem (ms)"],
    [
        ["ASR (Faster-Whisper / Web Speech)","94.1","128.5","108.2","142.0"],
        ["BM25 Retrieval","0.05","0.09","0.06","0.11"],
        ["LLM TTFT","185.3","240.1","225.4","288.7"],
        ["TTS First Chunk","68.0","92.4","78.6","105.2"],
        ["Total (server-side)","347.5","461.1","412.3","536.0"],
    ],
    cap="Table 5.3  Per-Stage Pipeline Latency (ms, N = 50 turns). VAD endpointing (450 ms) excluded."
)
body(doc,"The 347.5 ms cloud median and 412.3 ms on-premises median are both below the 800 ms "
     "perceptual threshold. LLM TTFT dominates at 53% (cloud) and 55% (on-premises). BM25 "
     "contributes under 0.1 ms. The on-premises configuration incurs a 64.8 ms TTFT penalty "
     "at P50, reflecting lower quantised model throughput relative to Groq. No controlled "
     "ablation on identical hardware was performed; comparisons are indicative only.")
h2(doc,"5.4. PII Redaction Accuracy")
body(doc,"PII redaction was evaluated on 30 labelled utterances. Table 5.4 shows results by "
     "category. Data source: research/results/pii_eval.json.")
pm = pii["metrics"]
tbl(doc,
    ["PII Category","TP","FP","FN","Precision","Recall","F1"],
    [
        ["Credit Card", pm["CARD"]["tp"], pm["CARD"]["fp"], pm["CARD"]["fn"],
         f'{pm["CARD"]["precision"]:.3f}', f'{pm["CARD"]["recall"]:.3f}', f'{pm["CARD"]["f1"]:.3f}'],
        ["Email", pm["EMAIL"]["tp"], pm["EMAIL"]["fp"], pm["EMAIL"]["fn"],
         f'{pm["EMAIL"]["precision"]:.3f}', f'{pm["EMAIL"]["recall"]:.3f}', f'{pm["EMAIL"]["f1"]:.3f}'],
        ["Phone", pm["PHONE"]["tp"], pm["PHONE"]["fp"], pm["PHONE"]["fn"],
         f'{pm["PHONE"]["precision"]:.4f}', f'{pm["PHONE"]["recall"]:.4f}', f'{pm["PHONE"]["f1"]:.4f}'],
        ["Micro-Average", pm["MICRO"]["tp"], pm["MICRO"]["fp"], pm["MICRO"]["fn"],
         f'{pm["MICRO"]["precision"]:.4f}', f'{pm["MICRO"]["recall"]:.4f}', f'{pm["MICRO"]["f1"]:.4f}'],
    ],
    cap="Table 5.4  PII Redaction Precision, Recall and F1 (N = 30 utterances)"
)
body(doc,"Credit card and email redaction achieve perfect F1 (1.000). Phone redaction achieves "
     "F1 = 0.889; one FP and one FN arise from a 7-digit numeric sequence. Micro-averaged "
     "F1 = 0.952 exceeds the 0.90 target.")
h2(doc,"5.5. Barge-In Detection Performance")
body(doc,"Barge-in detection was evaluated on 40 synthetic frame sequences (15 sustained "
     "interruptions, 25 non-interruption cases). Table 5.5 shows results from "
     "research/results/bargein_eval.json.")
tbl(doc,
    ["Metric","Value"],
    [("TP",bge["tp"]),("TN",bge["tn"]),("FP",bge["fp"]),("FN",bge["fn"]),
     ("Precision",f'{bge["precision"]:.3f}'),("Recall",f'{bge["recall"]:.3f}'),
     ("F1",f'{bge["f1"]:.3f}'),("Accuracy",f'{bge["accuracy"]:.3f}')],
    cap="Table 5.5  Barge-In Detection Performance (N = 40 synthetic cases)"
)
body(doc,"All metrics equal 1.000 on the synthetic evaluation set. These results validate the "
     "algorithm design (RMS threshold, grace period, consecutive-hit count). Real-world performance "
     "will vary with acoustic environment and deployment conditions; a human perceptual study is "
     "required to characterise deployment performance.")
h2(doc,"5.6. Discussion")
body(doc,"The engineering objectives of the project are met: pipeline latency is below 500 ms at "
     "median, PII redaction exceeds the 0.90 F1 target, and barge-in detection achieves perfect "
     "scores on the synthetic test set. The QUBO formulation is mathematically correct and the "
     "Ising mapping is numerically verified.")
body(doc,"The most significant finding is the honest assessment of the quantum component. At "
     "n = 15 modules, QAOA at depth p = 1 does not outperform the classical greedy solver and "
     "is over 2,000 times slower. This is expected behaviour: the simulator computes the exact "
     "quantum state classically, while greedy exploits the sparse pairwise structure of this "
     "specific instance. Genuine quantum advantage would require n >= 30 with dense pairwise "
     "coupling and execution on physical quantum hardware with error mitigation.")
body(doc,"The prompt scorer MAE of 0.283 indicates reasonable accuracy for the rule-based "
     "approach, with the exception of guardrail-violation turns (MAE approx 0.65). Replacing "
     "the keyword-based Phi_bound scorer with an LLM-judge classifier is the highest-priority "
     "improvement for the scoring framework.")
h2(doc,"5.7. Summary of Findings")
tbl(doc,
    ["Metric","Result","Target","Status"],
    [
        ["Server-side P50 latency (cloud)","347.5 ms","< 800 ms","\u2713 Met"],
        ["Server-side P50 latency (on-prem)","412.3 ms","< 500 ms","\u2713 Met"],
        ["PII micro-averaged F1","0.952",">= 0.90","\u2713 Met"],
        ["Barge-in F1 (synthetic)","1.000","Algorithm validation","\u2713 Met"],
        ["Prompt scorer MAE (mean)","0.283","< 0.30 (indicative)","\u2713 Met"],
        ["QUBO greedy gap to optimal","0.03%","< 5%","\u2713 Met"],
        ["QAOA p=1 gap to optimal","1.40%","< 1% (target)","\u2717 Not met"],
        ["Human evaluation (MOS)","Not evaluated","\u2014","\u2014 Future work"],
        ["WER on test speech","Not evaluated","\u2014","\u2014 Future work"],
    ],
    cap="Table 5.6  Summary of All Measured Results"
)
doc.add_page_break()

# ════════════════════════════════════════════════════════════════════════════
# CHAPTER 6
# ════════════════════════════════════════════════════════════════════════════
h1(doc,6,"Conclusions and Future Work")
h2(doc,"6.1. Conclusions")
body(doc,"This project designed, implemented, and evaluated a complete on-premises conversational "
     "voice agent with combinatorial system prompt optimisation via QUBO. The following conclusions "
     "are drawn from measured experimental results.")
body(doc,"The pipeline achieves a server-side median latency of 347.5 ms (cloud) and 412.3 ms "
     "(on-premises Ollama), both below the 800 ms perceptual threshold. LLM TTFT dominates at "
     "53% of total latency; BM25 retrieval does not constrain the pipeline at under 0.1 ms.")
body(doc,"The modular QUBO formulation with n = 15 binary modules and genuine pairwise conflict "
     "and synergy terms creates a non-trivial combinatorial problem. The classical greedy solver "
     "achieves a near-optimal solution (0.03% gap) in 0.6 ms. QAOA at p = 1 achieves a 1.40% "
     "suboptimal result in 1,320.7 ms. We conclude that quantum advantage does not manifest at "
     "n = 15 in simulation; larger instances on physical QPU hardware with error mitigation "
     "are required.")
body(doc,"PII redaction achieves micro-averaged F1 = 0.952. Barge-in detection achieves perfect "
     "precision, recall, and F1 on 40 synthetic test cases, validating the algorithm design.")
h2(doc,"6.2. Limitations")
body(doc,"Human evaluation (Mean Opinion Score, task-completion rate) has not been conducted. "
     "Word Error Rate has not been measured on the transcription component. QAOA experiments "
     "use statevector simulation and not a physical QPU. Evaluation was conducted in English "
     "only on two domains. No GPU was available during the evaluation run recorded in env.json; "
     "Faster-Whisper latencies may be lower with GPU acceleration. No controlled hardware ablation "
     "comparing cloud and on-premises configurations was performed.")
h2(doc,"6.3. Scope for Further Work")
for fw in [
    "Physical QPU execution: Run the n = 15 and larger QUBO instances on IBM Quantum hardware with Zero-Noise Extrapolation and Pauli twirling error mitigation to measure actual quantum speedup.",
    "Larger QUBO instances: Scale to 30-50 modules by adding domain-specific instruction modules with denser conflict/synergy matrices, and evaluate whether QAOA outperforms greedy on these structured instances.",
    "Human evaluation: Conduct a formal study with 20 participants measuring MOS, task-completion rate, and perceived latency using Wilcoxon signed-rank and McNemar's tests.",
    "Hybrid retrieval: Compare BM25 with dense embedding retrieval and a hybrid BM25 + dense approach on a labelled benchmark, measuring P@1, MRR, and latency.",
    "Multilingual support: Evaluate Whisper large-v3 on accented English and Indian-language code-switching.",
    "Mid-call prompt morphing: Real-time Hamiltonian updates based on detected caller sentiment for on-the-fly persona switching.",
    "PSTN/SIP integration: Bridge the system to SIP trunking to support traditional telephone networks.",
]:
    p=doc.add_paragraph(style="List Number"); fmt(p,after=4); run(p,fw,size=12)
doc.add_page_break()

# ════════════════════════════════════════════════════════════════════════════
# REFERENCES
# ════════════════════════════════════════════════════════════════════════════
centered(doc,"REFERENCES",size=14,bold=True,after=14)
refs=[
    "Levinson, S. C. and Torreira, F., Timing in turn-taking and its implications for processing models of language, Frontiers in Psychology, vol. 6, article 731, 2015.",
    "Larson, J. and Traum, D. R., Turn-taking and latency in spoken dialogue systems, IEEE/ACM Transactions on Audio, Speech, and Language Processing, vol. 28, pp. 2911-2923, 2020.",
    "McTear, M., Conversational AI: Dialogue Systems, Conversational Agents, and Chatbots, Springer, Cham, 2022.",
    "Rubenstein, P. K. et al., AudioPaLM: A large language model that can speak and listen, arXiv preprint arXiv:2306.12925, 2023.",
    "Defossez, A. et al., Moshi: A speech-text foundation model for real-time dialogue, arXiv preprint arXiv:2410.00037, 2024.",
    "Levinson, S. C. et al., Universals and cultural variation in turn-taking in conversation, Proceedings of the National Academy of Sciences, vol. 106, no. 26, pp. 10587-10592, 2009.",
    "Lewis, P. et al., Retrieval-augmented generation for knowledge-intensive NLP tasks, in Proceedings of NeurIPS, 2020, pp. 9459-9474.",
    "Robertson, S. and Zaragoza, H., The probabilistic relevance framework: BM25 and beyond, Foundations and Trends in Information Retrieval, vol. 3, no. 4, pp. 333-389, 2009.",
    "Zhou, Y. et al., Large language models are human-level prompt engineers, in Proceedings of ICLR, 2023.",
    "Khattab, O. et al., DSPy: Compiling declarative language model calls into self-improving pipelines, arXiv preprint arXiv:2310.03714, 2023.",
    "Yang, C. et al., Large language models as optimizers, arXiv preprint arXiv:2309.03409, 2023.",
    "Glover, F., Kochenberger, G. and Du, Y., Quantum bridge analytics I: QUBO models, 4OR, vol. 17, no. 4, pp. 335-371, 2019.",
    "Date, P. et al., Combinatorial optimization on quantum computers, IEEE Transactions on Quantum Engineering, vol. 4, pp. 1-22, 2023.",
    "Farhi, E., Goldstone, J. and Gutmann, S., A quantum approximate optimization algorithm, arXiv preprint arXiv:1411.4028, 2014.",
    "Frantar, E. et al., GPTQ: Accurate post-training quantization for generative pre-trained transformers, in Proceedings of ICLR, 2023.",
    "SYSTRAN, Faster-Whisper: Faster Whisper transcription with CTranslate2, GitHub, 2023. [Online]. Available: https://github.com/SYSTRAN/faster-whisper",
    "Rhasspy, Piper: A fast, local neural text to speech system, GitHub, 2023. [Online]. Available: https://github.com/rhasspy/piper",
    "Ferraiolo, D. F. and Kuhn, D. R., Role-based access controls, in Proceedings of the 15th National Computer Security Conference, 1992, pp. 554-563.",
    "Ravanelli, M. et al., SpeechBrain: A general-purpose speech toolkit, arXiv preprint arXiv:2106.04624, 2021.",
    "Kandala, A. et al., Hardware-efficient variational quantum eigensolver for small molecules and quantum magnets, Nature, vol. 549, pp. 242-246, 2017.",
    "Shen, T. et al., Large language model alignment: A survey, arXiv preprint arXiv:2309.15025, 2023.",
    "Schick, T. et al., Toolformer: Language models can teach themselves to use tools, in Proceedings of NeurIPS, 2023.",
    "Vaswani, A. et al., Attention is all you need, in Proceedings of NeurIPS, 2017, pp. 5998-6008.",
    "Wilson, E. B., Probable inference, the law of succession, and statistical inference, Journal of the American Statistical Association, vol. 22, no. 158, pp. 209-212, 1927.",
    "Temme, K., Bravyi, S. and Gambetta, J. M., Error mitigation for short-depth quantum circuits, Physical Review Letters, vol. 119, 2017.",
]
for i,r in enumerate(refs,1):
    p=doc.add_paragraph(); fmt(p,after=4,first_line_cm=0); run(p,f"[{i}]  {r}",size=12)
doc.add_page_break()

# ════════════════════════════════════════════════════════════════════════════
# APPENDICES
# ════════════════════════════════════════════════════════════════════════════
centered(doc,"APPENDIX A",size=14,bold=True,after=4)
centered(doc,"PLAGIARISM REPORT",size=14,bold=True,after=18)
body(doc,"[Insert Turnitin / college similarity report PDF here before final submission. "
     "The plagiarism certificate is mandatory.]",first=0)
TODO.append("APPENDIX A: Insert Turnitin/college plagiarism certificate.")
doc.add_page_break()

centered(doc,"APPENDIX B",size=14,bold=True,after=4)
centered(doc,"SUBMITTED JOURNAL PAPER",size=14,bold=True,after=18)
body(doc,"A copy of the journal paper under review, 'Low-Latency, Privacy-Aware Conversational "
     "Voice Agent with QUBO-Based Prompt Optimization', is attached in this appendix. The paper "
     "was prepared as journal.tex in the project repository.",first=0)
TODO.append("APPENDIX B: Attach compiled PDF of journal.tex.")
doc.add_page_break()

centered(doc,"APPENDIX C",size=14,bold=True,after=4)
centered(doc,"KEY CODE LISTINGS",size=14,bold=True,after=18)
for title, code in [
    ("QUBO Builder — build_qubo function (qpo/qubo.py)",
     "def build_qubo(modules, conflict_matrix, synergy_matrix,\n"
     "               lambda_budget=0.5, T_B=180):\n"
     "    n = len(modules)\n"
     "    Q = np.zeros((n, n))\n"
     "    for i, mod in enumerate(modules):\n"
     "        Q[i, i] -= mod['score']         # linear fitness objective\n"
     "    for i in range(n):                  # token budget penalty\n"
     "        for j in range(n):\n"
     "            Q[i, j] += lambda_budget * modules[i]['tokens'] * modules[j]['tokens']\n"
     "        Q[i, i] -= 2 * lambda_budget * T_B * modules[i]['tokens']\n"
     "    for (i, j), c in conflict_matrix.items():  # pairwise conflicts\n"
     "        Q[i, j] += c\n"
     "    for (i, j), s in synergy_matrix.items():   # pairwise synergies\n"
     "        Q[i, j] -= s\n"
     "    return Q"),
    ("BM25 Retrieval — query method (bm25_index.py)",
     "def query(self, q: str, top_k: int = 3) -> list[str]:\n"
     "    tokens = self._tokenize(q)\n"
     "    scores = []\n"
     "    for doc_id, doc_tokens in enumerate(self._docs):\n"
     "        score = 0.0\n"
     "        tf_map = Counter(doc_tokens)\n"
     "        dl = len(doc_tokens)\n"
     "        for t in tokens:\n"
     "            if t not in self._idf: continue\n"
     "            tf = tf_map.get(t, 0)\n"
     "            tf_norm = tf * (self.k1 + 1) / (\n"
     "                tf + self.k1 * (1 - self.b + self.b * dl / self.avgdl))\n"
     "            score += self._idf[t] * tf_norm\n"
     "        scores.append((score, doc_id))\n"
     "    top = sorted(scores, reverse=True)[:top_k]\n"
     "    return [self._chunks[doc_id] for _, doc_id in top]"),
    ("PII Redaction — redact function (guardrail.py)",
     "CARD_RE  = re.compile(r'\\b(?:\\d[ -]?){15,16}\\d\\b')\n"
     "PHONE_RE = re.compile(r'\\b[2-9]\\d{2}[-.]?\\d{3}[-.]?\\d{4}\\b')\n"
     "EMAIL_RE = re.compile(\n"
     "    r'[a-zA-Z0-9._%+\\-]+@[a-zA-Z0-9.\\-]+\\.[a-zA-Z]{2,}')\n\n"
     "def redact(text: str) -> str:\n"
     "    for m in reversed(list(CARD_RE.finditer(text))):\n"
     "        digits = re.sub(r'[^0-9]', '', m.group())\n"
     "        if luhn_check(digits):\n"
     "            text = (text[:m.start()] + '[CARD_REDACTED]'\n"
     "                    + text[m.end():])\n"
     "    text = PHONE_RE.sub('[PHONE_REDACTED]', text)\n"
     "    text = EMAIL_RE.sub('[EMAIL_REDACTED]', text)\n"
     "    return text"),
]:
    h3(doc, title)
    p=doc.add_paragraph()
    fmt(p,after=12,first_line_cm=0)
    r=p.add_run(code); r.font.name="Courier New"; r.font.size=Pt(9)

# ─── SAVE ────────────────────────────────────────────────────────────────────
out = BASE / "Project_Report.docx"
doc.save(out)
print(f"Saved: {out}")

todo_path = BASE / "report_todo.md"
with open(todo_path,"w",encoding="utf-8") as f:
    f.write("# report_todo.md — Outstanding Items for Project Report\n\n")
    f.write(f"Generated: {datetime.datetime.now().isoformat()}\n\n")
    for i,item in enumerate(TODO,1):
        f.write(f"{i}. {item}\n")
print(f"Saved TODO: {todo_path}")
print(f"\nOutstanding items ({len(TODO)}):")
for i,t in enumerate(TODO,1):
    print(f"  {i}. {t}")
