# Project Report Generation Spec (Amrita School of Computing, Chennai)

**Goal:** Generate the final-year B.Tech project report as one Word file, `Project_Report.docx` (and a PDF copy), following the college "Format for Preparation of Project Report" exactly, reusing the supplied `project_report__Bonafide___Acknowlegement__template.docx` for the Bonafide and Acknowledgement pages.

**Inputs available to the agent**
- College format rules (summarised in Section 2 below; source is the scanned pages).
- `project_report__Bonafide___Acknowlegement__template.docx` (logo image `word/media/image1.jpeg`, Bonafide text, Acknowledgement text).
- The project repo (`voice-agent-mvp/`), `research/results/*`, `research/generated/*`, `research/figures/*`, and the final journal paper `.tex`.
- `memory/voice-agent-studio.md`, `runtime-appliance-spec.md`, `diagrams/*.png`.

**Golden rules**
1. Every number, table and figure must come from `research/results/` or `research/figures/`. Never invent results. If a result does not exist, write "not evaluated" or omit the claim.
2. The report must describe what the code really does (see the audit in `IMPLEMENTATION_PLAN.md`). Do not describe Docker, theta_words barge-in, ACID transactions, etc. unless the code and measurements exist.
3. Report text must be original prose (not copy-pasted from the journal paper) because the college requires a plagiarism report. Reuse facts and numbers, rewrite sentences. The journal paper may be cited as a reference ("our paper under review") if applicable.
4. Placeholders marked `{{...}}` in this file must be filled from the "Fill-in values" table (Section 1). If a value is still unknown, leave the placeholder visible in yellow highlight and list it in `report_todo.md`.

---

## 1. Fill-in values

| Placeholder | Value |
|---|---|
| `{{TITLE}}` | Low-Latency, Privacy-Aware Conversational Voice Agent with QUBO-Based Prompt Optimization (confirm final title; must match the journal paper) |
| `{{STUDENT_1}}` | Sanjjey Arumugam |
| `{{REG_1}}` | CH.EN.U4CSE23{{xxx}} (ask user; template shows `CH.EN.U4CSE23xxx`; the scanned specimen shows `CH.EN.U4AIE200xx`, so use the department code printed on the user's ID) |
| `{{STUDENT_2}}` | Mukesh Charan |
| `{{REG_2}}` | CH.EN.U4CSE23{{xxx}} |
| `{{SUPERVISOR}}` | {{Dr./Mr./Ms. name}} (ask user) |
| `{{SUPERVISOR_DESIG}}` | {{e.g. Assistant/Associate Professor}}, Department of CSE |
| `{{CHAIRPERSON}}` | Dr. S. Baghavathi Priya (from the template acknowledgement) |
| `{{PROGRAM_CHAIR}}` | Dr. Annamalai R (from the template) |
| `{{DEGREE}}` | BACHELOR OF TECHNOLOGY IN COMPUTER SCIENCE AND ENGINEERING |
| `{{MONTH_YEAR}}` | November 2026 (matches the specimen; confirm with user) |

Note: the scanned declaration says "Bachelor of Technology" in Specimen 3 but "Bachelor of Engineering" in Appendix 3. Use **Bachelor of Technology** (matches the degree on the title page).

Two students: use plural forms ("Candidates", "us", "our", "who carried out") on the Bonafide, Declaration and Acknowledgement. The template is written for one student, so adapt the wording and list both names and register numbers.

---

## 2. College formatting rules (apply strictly)

### 2.1 Page
- A4 (210 x 297 mm), margins **2.54 cm (1") on all four sides**. The supplied template uses different margins (about 1.9-2.0 cm and 2.4-2.9 cm top); **override to 1" everywhere**.
- Font: **Times New Roman** throughout.

### 2.2 Text styles
| Element | Style |
|---|---|
| Chapter heading ("CHAPTER 2") and chapter title | TNR 14 pt, ALL CAPS, bold, centred |
| Division heading (e.g. 2.1 INTRODUCTION) | TNR 12 pt, ALL CAPS, bold, left |
| Sub-division heading (e.g. 2.1.1 Types Of Straight-Line Mechanisms) | TNR 12 pt, Capitalize Each Word, bold, left |
| Running text | TNR 12 pt, sentence case, justified |
| Paragraph | first line indented 1 cm; justified; **1.5 line spacing** |
| Table of Contents text | TNR 12 pt, 1.5 spacing |

Illustrative example from the college: `CHAPTER 2` / `PROBLEM BACKGROUND` / `2.1. INTRODUCTION` / `2.1.1. Types of Straight-Line Mechanisms`.

Implementation: define Word styles `Heading 1` (chapter: number line + title line), `Heading 2` (division), `Heading 3` (sub-division), `Body Text`, `Caption`, `Reference`, and tie the TOC to them so the Table of Contents is auto-generated.

### 2.3 Numbering
- Preliminary pages (Title, Bonafide, Declaration, Abstract, Acknowledgement, TOC, Lists): the scanned text says "Arabic numerals", but **all specimen pages show lower-case roman numerals (i, ii, iii, iv, v, vi, vii, viii, ix)** centred at the bottom. Follow the specimens: roman for preliminaries, then restart at **1** in Chapter 1 with Arabic numerals. (Title page = i, no number printed is acceptable; Cover page is the same as Title page and is not counted separately.)
- Tables and figures: numbered by chapter, `Figure 3.4` = 4th figure in Chapter 3; caption below figures, above tables; "Table x.y" uses identical rules.
- Equations: numbered serially, restarting each chapter and appendix, e.g. `(4.2)`.

### 2.4 References
- Alphabetical by first author's surname. Authors first, then title (journal/book title in italics), edition, publisher, year. Examples given by the college:
  1. `Abbaszadeh-Mir, Y., Mayer, J., Cloutier, G. and Fortin, C., Theory and Simulation for the Identification of the Link Geometric Errors for a Five-axis Machine Tool Using a Telescoping Magnetic Ball-bar, International Journal of Production Research, vol. 40 (18), pp. 4781-4797, 2002.`
  2. `Shigley, J. E. and Uicker Jr., J. J., Theory of Machines and Mechanisms, Second Edition, McGraw Hill, 1996.`
- Numbered list; in-text citations as `[n]` matching the alphabetical list number.
- **Every reference must be verified** to exist (see J5 in the implementation plan). Do not include references you cannot confirm.

### 2.5 Binding / policy
- Final PDF must be print-ready for flexible-cover binding on thick white art paper.
- Plagiarism report is mandatory and goes in the Appendices.

---

## 3. Order of contents (exactly this order)

1. **Title Page** (Specimen 1 / Appendix 1)
2. **Cover Page** (identical to Title Page; same content, comes first physically; page i)
3. **Bonafide Certificate** (Specimen 2 / Appendix 2) - from the supplied docx
4. **Declaration by the Candidate** (Specimen 3 / Appendix 3)
5. **Abstract** (Specimen 4)
6. **Acknowledgement** (Specimen 5) - from the supplied docx
7. **Table of Contents** (Specimen 6)
8. **List of Tables** (Specimen 7)
9. **List of Figures** (Specimen 8)
10. **List of Symbols, Abbreviations and Nomenclature** (Specimen 9)
11. **Chapters 1-6** (Section 4)
12. **References**
13. **Appendices** (plagiarism report, copy of published/submitted papers, certificates, code listings, extra tables)

Page-number convention: Abstract = iv, Acknowledgement = v, TOC = vi, List of Tables = vii, List of Figures = viii, Symbols = ix (as in the specimens, which treat Title=i, Bonafide=ii, Declaration=iii).

---

## 4. Page-by-page templates

### 4.1 Title / Cover page (Appendix 1, Specimen 1)
All text Times New Roman, bold unless stated, centred, 1.5 spacing. Top to bottom:
1. `{{TITLE}}` - **18 pt**, ALL CAPS
2. `A PROJECT REPORT` - 14 pt
3. *Submitted by* - 14 pt italic
4. `STUDENT NAME(S)` then `(Reg. No. ...)` for each student - 14 pt
5. *in partial fulfillment for the award of the degree of* - 14 pt italic
6. `BACHELOR OF TECHNOLOGY IN COMPUTER SCIENCE AND ENGINEERING` - 14 pt
7. *Under the guidance of* - italic
8. `{{SUPERVISOR}}` - 14 pt
9. *Submitted to* - bold
10. **Amrita Vishwa Vidyapeetham logo** (extract `word/media/image1.jpeg` from the template docx; verify it is the logo and not the "School of Computing" lockup; the Bonafide/Declaration pages use the "AMRITA VISHWA VIDYAPEETHAM + SCHOOL OF COMPUTING CHENNAI" lockup, the Title page uses the plain AMRITA logo. If only one image exists, use it everywhere and flag in `report_todo.md`.)
11. `AMRITA VISHWA VIDYAPEETHAM` / `AMRITA SCHOOL OF COMPUTING` / `CHENNAI - 601103` - 16 pt
12. `{{MONTH_YEAR}}` - 14 pt
13. Roman page number `i` at bottom (optional on this page)

### 4.2 Bonafide Certificate (Appendix 2, Specimen 2)
Start from the supplied docx page 1 (preserve its layout and logo). Adapt:
- Header: logo + "SCHOOL OF COMPUTING CHENNAI" lockup, then `BONAFIDE CERTIFICATE` (16 pt bold, centred).
- Body (14 pt, 1.5 spacing): "This is to certify that this project report entitled **"{{TITLE}}"** is the bonafide work of **"{{STUDENT_1}} ({{REG_1}}) and {{STUDENT_2}} ({{REG_2}})"** who carried out the project work under my supervision."
- Signature block, two columns, 12 pt bold labels:
  - Left: `SIGNATURE`, `{{CHAIRPERSON}}`, `CHAIRPERSON`, Department of CSE, Amrita School of Computing, Chennai.
  - Right: `SIGNATURE`, `{{SUPERVISOR}}`, `SUPERVISOR`, {{designation}}, Dept. of CSE, Amrita School of Computing, Chennai.
- Bottom row: `INTERNAL EXAMINER` (left) and `EXTERNAL EXAMINER` (right), 14 pt bold.
- Implement the two columns with tab stops or a borderless table, never space padding.

### 4.3 Declaration by the Candidate (Appendix 3, Specimen 3)
- Logo lockup, then `DECLARATION BY THE CANDIDATE` (16 pt bold, centred).
- Body 14 pt, 1.5 spacing, justified: "We declare that the report entitled **"{{TITLE}}"** submitted by us for the degree of Bachelor of Technology is the record of the project work carried out by us under the guidance of **"{{SUPERVISOR}}"** and this work has not formed the basis for the award of any degree, diploma, associateship, fellowship, titled in this or any other University or other similar institution of higher learning."
- Right-aligned: `SIGNATURE` (12 bold), then for each student `NAME` and `Reg. No.` (bold), then the department address line `Department of Computer Science and Engineering, Amrita School of Computing, Chennai`.

### 4.4 Abstract (Specimen 4)
- Heading `ABSTRACT` centred, bold. One page, justified, 12 pt, ~250-300 words (a single paragraph, optionally two).
- Must contain: problem (sub-second voice agents, markdown pollution, privacy), approach (modular QUBO prompt assembly, streaming pipeline with BM25 retrieval, role-based PII shielding, on-prem option), measured results (only numbers from `research/results/`), and the honest outcome about quantum vs classical solvers.
- Followed by `Keywords:` line (bold label): Conversational Voice Agents, QUBO, QAOA, Prompt Optimization, Retrieval-Augmented Generation, On-Premises Deployment.

### 4.5 Acknowledgement (Specimen 5)
Use the paragraphs from the supplied docx, adapted to two students ("we", "our", "us") with:
- Chancellor Sri Mata Amritanandamayi Devi; Administrative Director Swami Vinayamritananda Puri; Campus Director Mr. I B Manikantan; Principal Dr. V. Jayakumar; Chairperson Dr. S. Baghavathi Priya; Program Chair Dr. Annamalai R; supervisor `{{SUPERVISOR}}`; Project Coordinator, Review Panel Members and faculty.
- Keep the template's bold names. Close with, right aligned and bold:
  `{{STUDENT_1}} ({{REG_1}})` and `{{STUDENT_2}} ({{REG_2}})`.
- Keep it to one page.

### 4.6 Table of Contents (Specimen 6)
- Heading `TABLE OF CONTENTS`, columns: `CHAPTER NO.` | `TITLE` | `PAGE NO.`
- First list the front matter without chapter numbers: Abstract (iv), List of Tables, List of Figures, List of Symbols and Abbreviations (roman pages). Then each chapter number in bold with chapter title in caps, divisions (1.1) and sub-divisions (1.1.1) indented, dot leaders to page numbers. Then References and Appendices.
- Auto-generate with a Word TOC field (levels 1-3), TNR 12, 1.5 spacing, then update fields and verify page numbers via PDF render.

### 4.7 List of Tables (Specimen 7) and List of Figures (Specimen 8)
- Columns: `TABLE NO.` / `FIGURE NO.` | `TITLE` | `PAGE NO.` Use Word caption-based lists (`TOC \c "Table"` and `TOC \c "Figure"`) so they stay in sync.
- Caption style: `Table 5.3 Latency by pipeline stage (ms)`.

### 4.8 List of Symbols, Abbreviations and Nomenclature (Specimen 9)
Two-column list `ABBR - Meaning`, alphabetical. Include at least: ASR, STT, TTS, LLM, TTFT, TTFA, VAD, RAG, BM25, IDF, QUBO, QAOA, VQE, COBYLA, SA, NISQ, QPU, RBAC, PII, ACID, SSE, WSS, TLS, API, REST, SQLite, GPU, VRAM, CUDA, INT8, GGUF, Q4_K_M, WER, MRR, P@1, FTR, GIL, CI, GDPR, HIPAA, PCI-DSS, Docker, UUID. Symbols: `S_i` fitness of candidate i; `x_i` binary decision variable; `Q` QUBO matrix; `h_i`, `J_ij` Ising field and coupling; `lambda`, `mu` penalty weights; `p` QAOA depth; `k1`, `b` BM25 parameters; `theta` barge-in threshold(s) as actually implemented. Only list items that appear in the report.

---

## 5. Chapter structure and content

Target length: 60-90 pages of body text at 1.5 spacing. Each chapter starts on a new page. Chapter heading format:

```
CHAPTER 3            (14 pt bold caps, centred)
PROBLEM STATEMENT AND METHODOLOGY   (14 pt bold caps, centred)
3.1. INTRODUCTION    (12 pt bold caps, left)
3.1.1. Scope Of The Method   (12 pt bold, capitalize each word, left)
```

### Chapter 1: Introduction (6-8 pages)
- 1.1 BACKGROUND: shift to voice interfaces; enterprise uses (hospitality, clinic).
- 1.2 MOTIVATION: latency (turn-taking 200-400 ms; cite Levinson & Torreira 2015 / Stivers et al. 2009 after verifying), markdown/preamble pollution in TTS, data privacy and cost.
- 1.3 PROBLEM OVERVIEW: three challenges (latency, prompt compliance, privacy/on-prem).
- 1.4 OBJECTIVES: a numbered list of 5-6 measurable objectives.
- 1.5 CONTRIBUTIONS: exactly the 3 in the journal paper.
- 1.6 SCOPE AND LIMITATIONS: browser-based calls, no PSTN telephony, English focus, small GPU.
- 1.7 ORGANISATION OF THE REPORT.

### Chapter 2: Literature Review / Problem Background (10-12 pages)
- 2.1 Spoken dialogue systems (cascaded vs speech-to-speech).
- 2.2 Turn-taking, latency and barge-in.
- 2.3 Retrieval-augmented generation: BM25 vs dense retrieval.
- 2.4 Prompt engineering and automatic prompt optimization (APE, DSPy, OPRO) and combinatorial/quantum optimization (QUBO, QAOA).
- 2.5 On-premises inference: quantization, Ollama/vLLM, Faster-Whisper, Piper.
- 2.6 Privacy, RBAC and PII protection.
- 2.7 Comparative table (**Table 2.1**) of existing platforms and approaches; latency figures labelled "as reported in literature/vendor documentation", not measured by us.
- 2.8 RESEARCH GAPS identified.

### Chapter 3: Problem Statement and Methodology (8-10 pages)
- 3.1 PROBLEM STATEMENT (formal).
- 3.2 SYSTEM REQUIREMENTS: functional and non-functional (latency target, voice-rule compliance, privacy, role isolation).
- 3.3 OVERALL METHODOLOGY: offline compilation phase vs online runtime phase (Figure 3.1, reuse `diagrams/architecture` and `workflow` images).
- 3.4 QUBO PROMPT-ASSEMBLY FORMULATION: modules, conflict/synergy matrices, token budget, QUBO to Ising mapping with the **corrected** coefficients (h_i = (S_i + lambda)/2 - (lambda/2)(n-1); J_ij = lambda/2), QAOA circuit, classical baselines. Show a small worked example (n = 4) with the actual Q matrix produced by the code.
- 3.5 EVALUATION METHODOLOGY: datasets, metrics, hardware, seeds, statistical tests.
- 3.6 DEVELOPMENT TOOLS AND TECHNOLOGIES (**Table 3.1**: FastAPI, SQLite, Qiskit, Faster-Whisper, Edge-TTS/Piper, Ollama, Groq, etc. with versions from `env.json`).

### Chapter 4: System Design, Implementation and Experimental Setup (14-18 pages)
- 4.1 ARCHITECTURE (Figure 4.1; reuse `diagrams/*`); data-flow diagram (Figure 4.2); sequence diagram (Figure 4.3).
- 4.2 AUDIO INGESTION: VAD (`vad-processor.js`, hysteresis), STT options (Groq Whisper vs local Faster-Whisper), endpointing.
- 4.3 KNOWLEDGE BASE AND RETRIEVAL: chunking, tokenization, synonyms, cached BM25 index.
- 4.4 LLM STREAMING AND SENTENCE-LEVEL TTS: `/chat_stream`, SSE, sentence chunking, TTS options.
- 4.5 BARGE-IN: the method actually implemented (energy threshold with adaptive speaker-bleed estimate, grace period, consecutive-hit count).
- 4.6 BOOKING ENGINE: validation rules, conflict detection, transaction and outbox pattern, ICS generation, webhook.
- 4.7 RBAC AND PII GUARDRAIL: **Table 4.x** permission matrix generated from `guardrail.PERMISSIONS`; redaction pipeline.
- 4.8 GOOGLE WORKSPACE INTEGRATION (brief): Calendar/Meet, Sheets, Docs ingestion, sandbox mode.
- 4.9 USER INTERFACE: screenshots (Dashboard, Agent setup, Knowledge, Call, History, Bookings). **Capture real screenshots**; if the app cannot be run, leave a labelled placeholder box and list it in `report_todo.md`.
- 4.10 ON-PREMISES DEPLOYMENT (only if Phase H was built): container topology, hardening, network isolation. Otherwise replace with "Deployment with Ollama on a local GPU" and describe only what exists.
- 4.11 EXPERIMENTAL SETUP: hardware table, model versions, dataset sizes, scripts to reproduce.

### Chapter 5: Results and Discussion (14-18 pages)
All content generated from `research/results/*`. Suggested sections (drop any without data):
- 5.1 QUBO SOLVER SCALING: gap-to-optimum and time vs n (Figures 5.1-5.2; Table 5.1). State plainly whether QAOA matched classical solvers.
- 5.2 PROMPT QUALITY: voice-rule violation rate, detail retention, guardrail compliance for each method with 95% CIs (Table 5.2).
- 5.3 LATENCY: per-stage decomposition, naive-cascade baseline, ablation (Tables 5.3-5.4; CDF Figure 5.3; stacked bar Figure 5.4).
- 5.4 RETRIEVAL: P@1, MRR, latency for BM25 vs dense vs BM25-no-synonyms (Table 5.5).
- 5.5 SPEECH RECOGNITION: WER overall and by accent subset.
- 5.6 BARGE-IN: false-trigger rate vs genuine-interrupt latency trade-off.
- 5.7 BOOKING AND PII CORRECTNESS: conflict-detection tests, concurrency test, PII precision/recall/F1.
- 5.8 CONCURRENCY AND RESOURCE USE (and air-gap verification if Phase H done).
- 5.9 DISCUSSION: what worked, what did not, comparison with literature, threats to validity.
- 5.10 SUMMARY OF FINDINGS (short table).

### Chapter 6: Conclusions and Scope for Further Work (3-4 pages)
- 6.1 CONCLUSIONS: restate only measured results; answer each objective from 1.4.
- 6.2 LIMITATIONS.
- 6.3 SCOPE FOR FURTHER WORK: real QPU runs with error mitigation, hybrid BM25 + dense retrieval, multilingual/Indic-language support, PSTN/SIP telephony integration, full-duplex speech-to-speech, federated fine-tuning.

### References
Alphabetical, college style (Section 2.4). 25-40 entries, all verified.

### Appendices
- Appendix A: Plagiarism report (placeholder page: "Insert Turnitin/college similarity report PDF here").
- Appendix B: Copy of the journal paper (PDF) and submission acknowledgement / certificates if any.
- Appendix C: Key code listings (QUBO builder, BM25 class, booking transaction, guardrail regex) in 9-10 pt Courier New in a bordered box, max ~6 pages.
- Appendix D: Full API endpoint list; configuration (`.env.example` without secrets); evaluation prompt sets.
- Appendix E: Additional result tables; Docker compose (if built).

---

## 6. Figures and tables to include

Reuse from the repo (`voice-agent-mvp/diagrams/`): `arch_diagram_rendered.png`, `data_flow_diagram.png`, `sequence_diagram.png`; render the `.html` diagrams to PNG if needed. Create from `research/figures/`: QUBO gap/time plots, latency CDF, stacked latency bar, retrieval comparison, barge-in trade-off. All figures: min 300 dpi, width <= 15.9 cm, caption below, referenced in text ("Figure 5.3 shows ..."). Tables: caption above, TNR 10-11 pt inside tables is acceptable, header row bold.

---

## 7. Generation procedure (for the agent)

1. Read `/mnt/skills/public/docx/SKILL.md` (or the docx tooling in your environment) first.
2. Unzip the template docx; copy the logo; reuse Bonafide and Acknowledgement XML as the basis, then fix margins to 1" and fonts to TNR.
3. Build `Project_Report.docx` with the `docx` npm library (or python-docx) using three sections:
   - Section A: front matter (roman page numbering, lowercase `i`),
   - Section B: chapters (Arabic numbering restarting at 1),
   - Section C: references and appendices (continue Arabic).
4. Write chapter text in `report/chapters/ch1.md ... ch6.md` first (markdown, with `{{FIG:id}}` and `{{TAB:id}}` markers), then convert to docx programmatically so text edits stay easy. Number figures/tables per chapter automatically.
5. Insert Word fields for TOC, List of Tables, List of Figures; update fields; convert to PDF (`soffice` wrapper from the skill) and check page numbers.
6. **Verification checklist (render to images and look at pages):**
   - [ ] A4, margins 2.54 cm, TNR everywhere
   - [ ] Chapter headings 14 pt bold caps centred; divisions 12 pt caps bold left; sub-divisions capitalize-each-word bold
   - [ ] Body justified, 1.5 spacing, 1 cm first-line indent
   - [ ] Order of pages matches Section 3; roman then Arabic numbering
   - [ ] Bonafide, Declaration, Title pages match Appendix 1-3 layouts, both students' names present
   - [ ] Figure/table numbers `chapter.n`; captions correct; lists of tables/figures complete
   - [ ] References alphabetical, verified, cited in text
   - [ ] No placeholder `{{...}}` left except those logged in `report_todo.md`
   - [ ] Every result number traceable to `research/results/`
   - [ ] No sentences copied from the journal paper; plagiarism report slot present
7. Outputs: `Project_Report.docx`, `Project_Report.pdf`, `report_todo.md` (missing values, screenshots, items to verify with the supervisor).

---

## 8. Style guidance for the prose

- Third person or "we" consistently (two-author project: use "we").
- Past tense for what was done, present tense for the system's behaviour.
- No marketing words ("revolutionary", "seamless", "guaranteed", "provably"); report effect sizes with confidence intervals.
- Each figure/table must be introduced and discussed in text.
- Short paragraphs (4-7 sentences); use numbered lists only for objectives and procedures.
- Explain every abbreviation at first use (and keep it in the List of Abbreviations).
