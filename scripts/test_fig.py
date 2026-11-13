import subprocess
import os

test_tex = r"""\documentclass[5p,twocolumn,times]{elsarticle}
\usepackage{amsmath,amssymb,amsfonts,bm}
\usepackage{tikz}
\usepackage{pgfplots}
\usepackage{subcaption}
\usepackage{booktabs}
\usepackage{tabularx}
\usepackage{colortbl}
\usepackage{siunitx}

\usetikzlibrary{arrows.meta,positioning,shapes.geometric,fit,calc,backgrounds}
\pgfplotsset{compat=1.18}

\definecolor{eaNavy}{RGB}{12,44,86}
\definecolor{eaNavy2}{RGB}{20,70,140}
\definecolor{eaOlive}{RGB}{46,117,89}
\definecolor{eaCoral}{RGB}{196,56,42}
\definecolor{eaAmber}{RGB}{204,119,34}
\definecolor{eaSlate}{RGB}{74,85,104}

\begin{document}

\begin{figure*}[t]
\centering
\begin{tikzpicture}[
  font=\sffamily\footnotesize,
  boxOffline/.style={rectangle, rounded corners=5pt, draw=eaNavy!80, fill=eaNavy!5, line width=0.8pt, align=center, inner sep=4pt},
  boxOnline/.style={rectangle, rounded corners=5pt, draw=eaOlive!80, fill=eaOlive!5, line width=0.8pt, align=center, inner sep=4pt},
  boxBarge/.style={rectangle, rounded corners=5pt, draw=eaCoral!90, fill=eaCoral!10, line width=0.9pt, align=center, inner sep=4pt},
  boxQTP/.style={rectangle, rounded corners=5pt, draw=eaAmber!90, fill=eaAmber!10, line width=0.8pt, align=center, inner sep=4pt},
  boxWave/.style={rectangle, rounded corners=4pt, draw=eaAmber!80, fill=white, line width=0.7pt, align=center, inner sep=3pt},
  arrow/.style={-{Latex[length=2.5mm]}, line width=0.8pt, draw=eaSlate},
  arrowNavy/.style={-{Latex[length=3mm]}, line width=1.3pt, draw=eaNavy},
  arrowCoral/.style={-{Latex[length=2.5mm]}, line width=1.1pt, draw=eaCoral, dashed},
  arrowAmber/.style={-{Latex[length=2.5mm]}, line width=1.0pt, draw=eaAmber}
]
  % Container 1: Offline Compilation Layer
  \node[draw=eaNavy, fill=eaNavy!4, rounded corners=6pt, line width=0.9pt, inner sep=8pt, fit={(-0.2,5.2) (17.5,7.0)}] (offlineBox) {};
  \node[anchor=north west, font=\bfseries\color{eaNavy}] at (0.0, 6.9) {OFFLINE PROMPT COMPILATION LAYER (QPO) \normalfont\scriptsize(Executed once at build-time; introduces 0 ms runtime latency)};

  \node[boxOffline, minimum width=2.4cm] (pLib) at (1.4, 6.0) {Prompt Library $\mathcal{P}$\\ \normalfont\tiny $n=15$ Atomic Modules};
  \node[boxOffline, minimum width=2.6cm] (penMat) at (4.9, 6.0) {Conflict $\mathbf{C}$ \& Synergy $\mathbf{S}$\\ \normalfont\tiny Penalties \& Bonuses};
  \node[boxOffline, minimum width=2.6cm] (quboMat) at (8.6, 6.0) {QUBO Matrix $\mathbf{Q}$\\ \normalfont\tiny Parabolic Token Penalty};
  \node[boxOffline, minimum width=2.6cm] (isingHam) at (12.3, 6.0) {Ising Spin Glass\\ \normalfont\tiny $\mathcal{H}_C = \sum h_i \sigma_i^z + \sum J_{ij}\sigma_i^z\sigma_j^z$};
  \node[boxOffline, fill=eaNavy!15, minimum width=2.2cm] (optBit) at (15.9, 6.0) {Optimal Prompt $\bm{x}^*$\\ \normalfont\tiny QAOA / Eigensolver (145t)};

  \draw[arrow] (pLib) -- (penMat);
  \draw[arrow] (penMat) -- (quboMat);
  \draw[arrow] (quboMat) -- (isingHam);
  \draw[arrow] (isingHam) -- (optBit);

  % Container 2: Online Runtime Appliance
  \node[draw=eaOlive, fill=eaOlive!4, rounded corners=6pt, line width=0.9pt, inner sep=8pt, fit={(-0.2,-1.3) (17.5,3.75)}] (onlineBox) {};
  \node[anchor=north west, font=\bfseries\color{eaOlive}] at (0.0, 3.65) {ONLINE REAL-TIME INFERENCE \& SCHEDULING RUNTIME \normalfont\scriptsize(Multi-Stage Docker Appliance; Hybrid Cloud or Sovereign Edge)};
  \node[anchor=south east, font=\tiny\bfseries\color{eaSlate}] at (17.4, -1.25) {\fbox{Docker Appliance: Multi-Process Microservice ($\approx 2.1$\,GB, CUDA/Alpine)}};

  % Row 1 of Runtime: Audio In -> ASR -> Query -> Context -> LLM -> Chunker
  \node[boxOnline, minimum width=2.0cm] (audioIn) at (1.3, 2.6) {Dual Ingress\\ \normalfont\tiny WebRTC / Twilio PSTN};
  \node[boxOnline, minimum width=2.3cm] (asr) at (4.0, 2.6) {Dual-Mode ASR\\ \normalfont\tiny Whisper CUDA / Web Speech};
  \node[boxOnline, minimum width=2.1cm] (query) at (6.9, 2.6) {User Query\\ \normalfont\tiny Text Intent $q_t$};
  \node[boxOnline, fill=eaOlive!15, minimum width=2.6cm] (ctx) at (10.2, 2.6) {Context Assembly\\ \normalfont\tiny $[\bm{x}^* \,\|\, R_t^{\mathrm{BM25}} \,\|\, H_{t-1}]$};
  \node[boxOnline, minimum width=2.3cm] (llm) at (13.5, 2.6) {Dual-Engine LLM\\ \normalfont\tiny Groq LPU / Local INT4};
  \node[boxOnline, minimum width=2.3cm] (chunk) at (16.2, 2.6) {Sentence Chunker\\ \normalfont\tiny Punctuation Dispatch};

  \draw[arrow] (audioIn) -- (asr);
  \draw[arrow] (asr) -- (query);
  \draw[arrow] (query) -- (ctx);
  \draw[arrow] (ctx) -- (llm);
  \draw[arrow] (llm) -- (chunk);

  % Downward Prompt Injection in clear channel between containers
  \draw[arrowNavy] (optBit.south) -- ++(0,-1.15) -| 
    node[pos=0.25, above=2pt, font=\scriptsize\bfseries\color{eaNavy}] {Static Prompt Injection $\bm{x}^*$ (0 ms Overhead)} 
    (ctx.north);

  % Row 2 of Runtime: VAD, Barge-In, BM25, QTP Scheduler, Audio Out, TTS
  \node[boxBarge, minimum width=2.0cm] (vad) at (1.3, 0.9) {Continuous VAD\\ \normalfont\tiny Energy $E_t > \theta$};
  \node[boxBarge, minimum width=2.3cm] (bargeCtrl) at (4.0, 0.9) {Barge-In FSM\\ \normalfont\tiny Cancel / Twilio \texttt{clear}};
  \node[boxOnline, minimum width=2.1cm] (bm25) at (6.9, 0.9) {In-Memory BM25\\ \normalfont\tiny $P@1 = 98.4\%$, 0.05 ms};
  
  % Quantum Task Scheduler Engine
  \node[boxQTP, minimum width=3.0cm] (qtp) at (10.4, 0.9) {\textbf{Quantum Task Scheduler (QTP)}\\ \normalfont\tiny Runtime QUBO / SA Solver ($<15.3$\,ms)};
  
  \node[boxOnline, fill=eaOlive!20, minimum width=2.1cm] (audioOut) at (13.7, 0.9) {Dual Audio Out\\ \normalfont\tiny Worklet / Twilio Stream};
  \node[boxOnline, minimum width=2.1cm] (tts) at (16.2, 0.9) {Piper ONNX TTS\\ \normalfont\tiny 22.05 kHz (68 ms)};

  % Direct connections in Row 2 & Cross-row flows
  \draw[arrowCoral] (audioIn.south) -- (vad.north);
  \draw[arrowCoral] (vad.east) -- (bargeCtrl.west);
  \draw[arrow] (query.south) -- (bm25.north);
  \draw[arrow] (bm25.north east) -- (ctx.south west);
  \draw[arrow] (chunk.south) -- (tts.north);
  \draw[arrow] (tts.west) -- (audioOut.east);

  % LLM Tool Intent dispatch to QTP
  \draw[arrowAmber] (llm.south) -- ++(0,-0.7) -| node[pos=0.25, above, font=\tiny\bfseries\color{eaAmber}] {Tool Intent} (qtp.north);

  % QTP Multi-Wave Dispatch Sub-boxes (Row 3, below QTP)
  \node[boxWave, draw=eaOlive!80, fill=eaOlive!10] (wave0) at (8.5, -0.4) {\textbf{Wave 0 (Sync Priority)}\\ \normalfont\tiny SQLite ACID $\parallel$ Eager TTS (245\,ms)};
  \node[boxWave, draw=eaNavy2!80, fill=eaNavy2!10] (wave1) at (12.3, -0.4) {\textbf{Wave 1 (Concurrent Async)}\\ \normalfont\tiny Google Cal $\parallel$ Sheets $\parallel$ Webhook (420\,ms)};

  \draw[arrowAmber] (qtp.south) -| (wave0.north);
  \draw[arrowAmber] (qtp.south) -| (wave1.north);
  \draw[arrow] (wave0.north) |- node[pos=0.75, left, font=\tiny\color{eaOlive}] {2PC Commit} (ctx.south);
  \draw[arrow] (wave0.east) -- (wave1.west);

  % Unobstructed Barge-In Interrupt Bus underneath
  \draw[arrowCoral] (bargeCtrl.south) -- ++(0,-1.5) 
    -- node[midway, below, font=\tiny\bfseries\color{eaCoral}] {Flush Worklet Queue, Twilio \texttt{clear} Frame \& Abort LLM ($<120$\,ms)} 
    ++(9.7,0) -| (audioOut.south);
  \draw[arrowCoral] ($(bargeCtrl.south) + (9.7,-1.5)$) -- ++(2.5,0) -| (tts.south);
\end{tikzpicture}
\caption{Decoupled voice agent architecture rendered as native vector code. Top: Offline QUBO/Ising prompt compilation layer (blue) produces optimal prompt configuration $\bm{x}^*$ with zero runtime overhead. Bottom: Real-time streaming conversational pipeline (green) featuring the Quantum Task Parallelizer (QTP) scheduler (amber). QTP optimizes multi-task runtime execution into dependency-preserving waves: Wave 0 (synchronous SQLite ACID and eager voice synthesis) and Wave 1 (concurrent asynchronous Google Calendar, Sheets, and Webhook dispatch), collapsing transactional latency by $4.29\times$.}
\label{fig:architecture}
\end{figure*}

\end{document}
"""

with open('test_fig.tex', 'w', encoding='utf-8') as f:
    f.write(test_tex)

res = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "test_fig.tex"], capture_output=True, text=True)
print("Exit code:", res.returncode)
if res.returncode != 0:
    print(res.stdout[-1500:])
else:
    print("Success! test_fig.pdf created without error.")
