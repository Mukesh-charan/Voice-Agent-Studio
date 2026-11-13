with open('../journal.tex', 'r', encoding='utf-8') as f:
    content = f.read()

old_fig1_chunk = r"""  % QTP Multi-Wave Dispatch Sub-boxes (Row 3, below QTP)
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

new_fig1_chunk = r"""  % QTP Multi-Wave Dispatch Sub-boxes (Row 3, below QTP)
  \node[boxWave, draw=eaOlive!80, fill=eaOlive!10] (wave0) at (8.4, -0.2) {\textbf{Wave 0 (Sync Priority)}\\ \normalfont\tiny SQLite ACID $\parallel$ Eager TTS (245\,ms)};
  \node[boxWave, draw=eaNavy2!80, fill=eaNavy2!10] (wave1) at (12.0, -0.2) {\textbf{Wave 1 (Concurrent Async)}\\ \normalfont\tiny Google Cal $\parallel$ Sheets $\parallel$ Webhook (420\,ms)};

  \draw[arrowAmber] (qtp.south) -- (wave0.north);
  \draw[arrowAmber] (qtp.south) -- (wave1.north);
  \draw[arrow] (wave0.east) -- (wave1.west);

  % Unobstructed Barge-In Interrupt Bus running at Y = -1.15 (completely clear below Wave 0 and Wave 1)
  \draw[arrowCoral] (bargeCtrl.south) -- ++(0,-1.75) 
    -- node[midway, below=2pt, font=\tiny\bfseries\color{eaCoral}] {Flush Worklet Queue, Twilio \texttt{clear} Frame \& Abort LLM ($<120$\,ms)} 
    ++(9.7,0) -| (audioOut.south);
  \draw[arrowCoral] ($(bargeCtrl.south) + (9.7,-1.75)$) -- ++(2.5,0) -| (tts.south);"""

assert old_fig1_chunk in content, "Error: old_fig1_chunk not found"
content = content.replace(old_fig1_chunk, new_fig1_chunk, 1)

with open('../journal.tex', 'w', encoding='utf-8') as f:
    f.write(content)

print("Figure 1 bus coordinates perfected.")
