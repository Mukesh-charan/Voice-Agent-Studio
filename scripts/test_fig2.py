import subprocess

test_fig2 = r"""\documentclass[5p,twocolumn,times]{elsarticle}
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
\begin{subfigure}[t]{0.48\textwidth}
\centering
\begin{tikzpicture}
\begin{axis}[
  width=\linewidth,
  height=5.4cm,
  xlabel={\small Number of Transactional Tasks ($N$)},
  ylabel={\small Execution Makespan (ms)},
  xmin=2.5, xmax=10.5,
  ymin=0, ymax=1950,
  xtick={3,4,5,6,8,10},
  grid=major,
  grid style={dashed, gray!30},
  legend pos=north west,
  legend style={font=\tiny, fill=white, fill opacity=0.9},
  font=\sffamily\scriptsize
]
\addplot[mark=square*, eaCoral, line width=1.1pt] coordinates {
  (3, 105.0) (4, 315.0) (5, 655.0) (6, 935.0) (8, 1250.0) (10, 1800.0)
};
\addlegendentry{Naive Serial Execution}

\addplot[mark=triangle*, eaAmber, line width=1.1pt] coordinates {
  (3, 80.0) (4, 255.0) (5, 550.0) (6, 550.0) (8, 550.0) (10, 550.0)
};
\addlegendentry{Greedy Heuristic}

\addplot[mark=*, eaNavy2, line width=1.3pt] coordinates {
  (3, 80.0) (4, 245.0) (5, 375.0) (6, 595.0) (8, 420.0) (10, 420.0)
};
\addlegendentry{QTP-SA (Proposed)}

\draw[eaOlive, line width=1.0pt, dashed] ({rel axis cs:0,0.41}) -- ({rel axis cs:1,0.41}) 
  node[pos=0.85, above=1pt, font=\tiny\bfseries\color{eaOlive}] {Human Psychoacoustic Limit (800\,ms)};
\end{axis}
\end{tikzpicture}
\caption{Transactional makespan scaling across task loads.}
\label{fig:qtp_makespan}
\end{subfigure}
\hfill
\begin{subfigure}[t]{0.48\textwidth}
\centering
\begin{tikzpicture}
\begin{axis}[
  width=\linewidth,
  height=5.4cm,
  xlabel={\small Number of Transactional Tasks ($N$)},
  ylabel={\small Concurrency Speedup Factor ($\times$)},
  ymin=1.0, ymax=4.8,
  xmin=2.5, xmax=10.5,
  xtick={3,4,5,6,8,10},
  ytick={1.0,1.5,2.0,2.5,3.0,3.5,4.0,4.5},
  grid=major,
  grid style={dashed, gray!30},
  legend pos=north west,
  legend style={font=\tiny, fill=white, fill opacity=0.9},
  font=\sffamily\scriptsize
]
\addplot[mark=*, eaNavy, line width=1.3pt] coordinates {
  (3, 1.31) (4, 1.29) (5, 1.75) (6, 1.57) (8, 2.98) (10, 4.29)
};
\addlegendentry{QTP Concurrency Speedup ($\times$)}

\addplot[mark=diamond*, eaOlive, line width=1.0pt, dashed] coordinates {
  (3, 1.31) (4, 1.24) (5, 1.19) (6, 1.70) (8, 2.27) (10, 3.27)
};
\addlegendentry{Greedy Speedup ($\times$)}

\node[fill=eaNavy!10, draw=eaNavy!60, rounded corners=3pt, font=\tiny, inner sep=2.5pt] at (axis cs:9.2, 4.2) {Peak: $4.29\times$ ($N=10$)};
\node[fill=eaOlive!10, draw=eaOlive!60, rounded corners=3pt, font=\tiny, inner sep=2.5pt] at (axis cs:5.5, 3.8) {Solver Overhead: $<15.3$\,ms};
\end{axis}
\end{tikzpicture}
\caption{QTP empirical concurrency speedup factor.}
\label{fig:qtp_speedup_panel}
\end{subfigure}
\caption{Empirical evaluation of the Quantum Task Parallelizer (QTP) across increasing transactional task loads $N \in [3, 10]$ ($K \in [2, 3]$ stages). (a) Total transaction makespan: Naive serial execution scales linearly to \SI{1800}{\milli\second}, whereas QTP collapses makespan to \SI{420}{\milli\second}, remaining well within the psychoacoustic ceiling. (b) Speedup factor reaches $4.29\times$ under simulated annealing, requiring under \SI{15.3}{\milli\second} of optimization time.}
\label{fig:qtp_eval}
\end{figure*}

\end{document}
"""

with open('test_fig2.tex', 'w', encoding='utf-8') as f:
    f.write(test_fig2)

res = subprocess.run(["pdflatex", "-interaction=nonstopmode", "-halt-on-error", "test_fig2.tex"], capture_output=True, text=True)
print("Exit code:", res.returncode)
if res.returncode != 0:
    print(res.stdout[-1500:])
else:
    print("Success! test_fig2.pdf created without error.")
