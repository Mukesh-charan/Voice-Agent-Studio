with open('../journal.tex', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Polish Figure 1 TikZ
old_fig1_code = r"""  % Container 2: Online Runtime Appliance
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
  \draw[arrowCoral] ($(bargeCtrl.south) + (9.7,-1.5)$) -- ++(2.5,0) -| (tts.south);"""

new_fig1_code = r"""  % Container 2: Online Runtime Appliance
  \node[draw=eaOlive, fill=eaOlive!4, rounded corners=6pt, line width=0.9pt, inner sep=8pt, fit={(-0.2,-1.65) (17.5,3.75)}] (onlineBox) {};
  \node[anchor=north west, font=\bfseries\color{eaOlive}] at (0.0, 3.65) {ONLINE REAL-TIME INFERENCE \& SCHEDULING RUNTIME \normalfont\scriptsize(Multi-Stage Docker Appliance; Hybrid Cloud or Sovereign Edge)};
  \node[anchor=south east, font=\tiny\bfseries\color{eaSlate}] at (17.4, -1.6) {\fbox{Docker Appliance: Multi-Process Microservice ($\approx 2.1$\,GB, CUDA/Alpine)}};

  % Row 1 of Runtime: Audio In -> ASR -> Query -> Context -> LLM -> Chunker
  \node[boxOnline, minimum width=2.0cm] (audioIn) at (1.3, 2.6) {Dual Ingress\\ \normalfont\tiny WebRTC / Twilio PSTN};
  \node[boxOnline, minimum width=2.3cm] (asr) at (4.0, 2.6) {Dual-Mode ASR\\ \normalfont\tiny Whisper CUDA / Web Speech};
  \node[boxOnline, minimum width=2.1cm] (query) at (6.8, 2.6) {User Query\\ \normalfont\tiny Text Intent $q_t$};
  \node[boxOnline, fill=eaOlive!15, minimum width=2.6cm] (ctx) at (10.1, 2.6) {Context Assembly\\ \normalfont\tiny $[\bm{x}^* \,\|\, R_t^{\mathrm{BM25}} \,\|\, H_{t-1}]$};
  \node[boxOnline, minimum width=2.3cm] (llm) at (13.5, 2.6) {Dual-Engine LLM\\ \normalfont\tiny Groq LPU / Local INT4};
  \node[boxOnline, minimum width=2.2cm] (chunk) at (16.2, 2.6) {Sentence Chunker\\ \normalfont\tiny Punctuation Dispatch};

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
  \node[boxBarge, minimum width=2.0cm] (vad) at (1.3, 0.95) {Continuous VAD\\ \normalfont\tiny Energy $E_t > \theta$};
  \node[boxBarge, minimum width=2.3cm] (bargeCtrl) at (4.0, 0.95) {Barge-In FSM\\ \normalfont\tiny Cancel / Twilio \texttt{clear}};
  \node[boxOnline, minimum width=2.1cm] (bm25) at (6.8, 0.95) {In-Memory BM25\\ \normalfont\tiny $P@1 = 98.4\%$, 0.05 ms};
  
  % Quantum Task Scheduler Engine
  \node[boxQTP, minimum width=2.8cm] (qtp) at (10.1, 0.95) {\textbf{Quantum Task Scheduler (QTP)}\\ \normalfont\tiny Runtime QUBO / SA Solver ($<15.3$\,ms)};
  
  \node[boxOnline, fill=eaOlive!20, minimum width=2.1cm] (audioOut) at (13.7, 0.95) {Dual Audio Out\\ \normalfont\tiny Worklet / Twilio Stream};
  \node[boxOnline, minimum width=2.1cm] (tts) at (16.2, 0.95) {Piper ONNX TTS\\ \normalfont\tiny 22.05 kHz (68 ms)};

  % Direct connections in Row 2 & Cross-row flows
  \draw[arrowCoral] (audioIn.south) -- (vad.north);
  \draw[arrowCoral] (vad.east) -- (bargeCtrl.west);
  \draw[arrow] (query.south) -- (bm25.north);
  \draw[arrow] (bm25.north) -- (ctx.south -| bm25.north);
  \draw[arrow] (chunk.south) -- (tts.north);
  \draw[arrow] (tts.west) -- (audioOut.east);

  % LLM Tool Intent dispatch to QTP
  \draw[arrowAmber] (llm.south) -- ++(0,-0.6) -| node[pos=0.25, above, font=\tiny\bfseries\color{eaAmber}] {Tool Intent} (qtp.north east);
  \draw[arrowAmber] (qtp.north) -- node[midway, left, font=\tiny\bfseries\color{eaAmber}] {2PC Verified} (ctx.south);

  % QTP Multi-Wave Dispatch Sub-boxes (Row 3, below QTP)
  \node[boxWave, draw=eaOlive!80, fill=eaOlive!10] (wave0) at (8.5, -0.3) {\textbf{Wave 0 (Sync Priority)}\\ \normalfont\tiny SQLite ACID $\parallel$ Eager TTS (245\,ms)};
  \node[boxWave, draw=eaNavy2!80, fill=eaNavy2!10] (wave1) at (12.0, -0.3) {\textbf{Wave 1 (Concurrent Async)}\\ \normalfont\tiny Google Cal $\parallel$ Sheets $\parallel$ Webhook (420\,ms)};

  \draw[arrowAmber] (qtp.south -| wave0.north) -- (wave0.north);
  \draw[arrowAmber] (qtp.south -| wave1.north) -- (wave1.north);
  \draw[arrow] (wave0.east) -- (wave1.west);

  % Unobstructed Barge-In Interrupt Bus running at Y = -1.1 (well clear of waves)
  \draw[arrowCoral] (bargeCtrl.south) -- ++(0,-1.05) 
    -- node[midway, below=2pt, font=\tiny\bfseries\color{eaCoral}] {Flush Worklet Queue, Twilio \texttt{clear} Frame \& Abort LLM ($<120$\,ms)} 
    ++(9.7,0) -| (audioOut.south);
  \draw[arrowCoral] ($(bargeCtrl.south) + (9.7,-1.05)$) -- ++(2.5,0) -| (tts.south);"""

assert old_fig1_code in content, "Error: old_fig1_code not found"
content = content.replace(old_fig1_code, new_fig1_code, 1)

# 2. Polish Figure 9 (qtp_eval) TikZ
old_fig9_sub = r"""\draw[eaOlive, line width=1.0pt, dashed] ({rel axis cs:0,0.41}) -- ({rel axis cs:1,0.41}) 
  node[pos=0.85, above=1pt, font=\tiny\bfseries\color{eaOlive}] {Human Psychoacoustic Limit (800\,ms)};"""

new_fig9_sub = r"""\draw[eaOlive, line width=1.0pt, dashed] ({rel axis cs:0,0.41}) -- ({rel axis cs:1,0.41}) 
  node[pos=0.50, above=1pt, font=\tiny\bfseries\color{eaOlive}] {Human Psychoacoustic Limit (800\,ms)};"""

assert old_fig9_sub in content, "Error: old_fig9_sub not found"
content = content.replace(old_fig9_sub, new_fig9_sub, 1)

old_fig9_sub2 = r"""\node[fill=eaNavy!10, draw=eaNavy!60, rounded corners=3pt, font=\tiny, inner sep=2.5pt] at (axis cs:9.2, 4.2) {Peak: $4.29\times$ ($N=10$)};
\node[fill=eaOlive!10, draw=eaOlive!60, rounded corners=3pt, font=\tiny, inner sep=2.5pt] at (axis cs:5.5, 3.8) {Solver Overhead: $<15.3$\,ms};"""

new_fig9_sub2 = r"""\node[fill=eaNavy!10, draw=eaNavy!60, rounded corners=3pt, font=\tiny, inner sep=2.5pt] at (axis cs:8.2, 4.3) {Peak: $4.29\times$ ($N=10$)};
\node[fill=eaOlive!10, draw=eaOlive!60, rounded corners=3pt, font=\tiny, inner sep=2.5pt] at (axis cs:5.0, 3.8) {Solver Overhead: $<15.3$\,ms};"""

assert old_fig9_sub2 in content, "Error: old_fig9_sub2 not found"
content = content.replace(old_fig9_sub2, new_fig9_sub2, 1)

with open('../journal.tex', 'w', encoding='utf-8') as f:
    f.write(content)

print("Polished Figure 1 and Figure 9 code written.")
