"""Generate the JCRAI 2026 poster in two print sizes.

A1 landscape follows the board size stated on the submission page; A0 portrait
follows the canvas of the distributed template.  The two layouts are kept as
separate bodies because the shorter A1 board needs a different balance.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parent
FIG = (ROOT.parent / "figures").resolve()

TITLE = (
    "Typed Judgment, Deterministic Enforcement: A Consent-Gated Gateway "
    "Architecture for Inter-Agent Collaboration over Messaging Channels"
)
AUTHORS = "Yizhang Cai, Jun Liu, Di Ma, Ke Yu, Ke Li"
INSTITUTE = (
    "School of Artificial Intelligence, Beijing University of Posts and "
    "Telecommunications \\\\ Beijing Guoshu Zhilian Technology Co., Ltd. \\\\ "
    "2025111259@bupt.cn"
)

MODULES = r"""
\small
\begin{tabular}{@{}l@{\hspace{0.7em}}l@{}}
\textbf{M1} & ingress authentication \\
\textbf{M2} & caller / conversation isolation \\
\textbf{M3} & discovery and routing \\
\textbf{M4} & consent and policy \\
\textbf{M5} & identity-bound execution \\
\textbf{M6} & state, idempotency, recovery \\
\textbf{M7} & delivery and telemetry \\
\end{tabular}

\vspace{0.6em}
\begin{tikzpicture}
\node[fill=teal!15, draw=teal, rounded corners=3pt, inner sep=0.55em,
      text width=0.88\linewidth, align=center]
{\small \textbf{In code:} authorization \textbullet{} identity \textbullet{}
 isolation \textbullet{} idempotency};
\end{tikzpicture}
"""

ROUTING = r"""
\small
\begin{tabular}{@{}l@{\hspace{0.8em}}r@{}}
\textbf{Direct} & 48/48/50 of 50 \\
\textbf{Ambiguous} & 39/38/38 of 40 \\
\textbf{Out of scope} & 0 of 40 \\
\end{tabular}

\vspace{0.3em}
\scriptsize Generated target recommended; more than one agent when two
capabilities fit; no partner when none advertises the request.
"""

ABLATIONS = r"""
\centering
\small
\begin{tabular}{@{}lcc@{}}
\toprule
\textbf{Arm} & \textbf{Control} & \textbf{Removed} \\
\midrule
Identity binding & 0/30 & 30/30 \\
Caller isolation & 0/30 & 30/30 \\
Idempotency & 30 exec. & 60 exec. \\
\bottomrule
\end{tabular}

\vspace{0.3em}
\scriptsize Same-code controls; each arm changes exactly one check.
"""

CONSENT = r"""
\small
Before consent: \textbf{0 / 40} partner actions.\\
Consents producing exactly one action: \textbf{36 / 36}.\\
Replayed consents: no extra action, identical stored reply.
"""

JUDGMENT = r"""
\centering
\small
\begin{tabular}{@{}lcc@{}}
\toprule
 & \textbf{Typed} & \textbf{Free text} \\
\midrule
Accuracy & 94.1\% & 83.9\% \\
Brier & 0.095 & 0.266 \\
ECE & 0.026 & 0.144 \\
\bottomrule
\end{tabular}

\vspace{0.3em}
\scriptsize 280 items, 3 runs, human-verified labels.
"""

TAKEAWAY = r"""
\textbf{Model advises; code controls identity, state, and every side effect.}

\vspace{0.4em}
\small Artifact: \texttt{github.com/ankelas/consent-gated-gateway-artifact}

\vspace{0.2em}
\scriptsize Supported by S\&T Program of Xiongan New Area (No. XA2026111001K).
"""

BODY_A1 = r"""
\begin{columns}
\column{0.31}
\block{The boundary we study}{
Messaging events are unstructured and may be duplicated, delayed, or replayed;
agent protocols expect authenticated endpoints, structured requests, and task
state.

\vspace{0.4em}
\begin{itemize}
  \item Free-text delegation lets model output become an invocation.
  \item Static rules cannot resolve natural-language ambiguity.
\end{itemize}

\textbf{Design rule.} The model answers seven closed questions (J1--J7); policy
code owns thresholds and effects.
}
\block{Seven modules, four invariants}{@@MODULES@@}

\column{0.35}
\block{Architecture}{
\centering
\includegraphics[width=0.96\linewidth]{@@FIG1@@}

\vspace{0.3em}
\small M1 ingress, M2 partition by caller and conversation, M3 discovery,
M4 consent, M5 identity-bound execution, M6 state, M7 delivery.
}
\block{Consent gate}{@@CONSENT@@}

\column{0.34}
\block{Results: routing (130 requests, 3 deliveries)}{@@ROUTING@@}
\block{Results: invariants (paired ablations)}{@@ABLATIONS@@}
\block{Results: judgment layer}{@@JUDGMENT@@}
\end{columns}

\vspace{0.7em}
\begin{columns}
\column{0.56}
\block{Takeaway}{@@TAKEAWAY@@}
\column{0.44}
\block{Gateway cost}{
\centering
\includegraphics[width=0.98\linewidth]{@@FIG3@@}
}
\end{columns}
"""

BODY_A0 = r"""

\begin{columns}
\column{0.31}
\block{The boundary we study}{
Messaging events are unstructured and may be duplicated, delayed, or replayed;
agent protocols expect authenticated endpoints, structured requests, and task
state.

\vspace{0.4em}
\begin{itemize}
  \item Free-text delegation lets model output become an invocation.
  \item Static rules cannot resolve natural-language ambiguity.
\end{itemize}

\textbf{Design rule.} The model answers closed questions; policy code owns
thresholds and effects.
}
\block{Seven modules, four invariants}{
\small
\begin{tabular}{@{}l@{\hspace{0.7em}}l@{}}
\textbf{M1} & ingress authentication \\
\textbf{M2} & caller / conversation isolation \\
\textbf{M3} & discovery and routing \\
\textbf{M4} & consent and policy \\
\textbf{M5} & identity-bound execution \\
\textbf{M6} & state, idempotency, recovery \\
\textbf{M7} & delivery and telemetry \\
\end{tabular}

\vspace{0.5em}
\begin{tikzpicture}
\node[fill=teal!15, draw=teal, rounded corners=3pt, inner sep=0.5em,
      text width=0.88\linewidth, align=center]
{\small \textbf{In code:} authorization \textbullet{} identity \textbullet{}
 isolation \textbullet{} idempotency};
\end{tikzpicture}
}
\block{The judgment plane: seven closed questions}{
\small The layer returns closed labels or probabilities only; it never emits free
text, never calls a tool, and only parameterizes policy thresholds.

\vspace{0.4em}
\begin{tabular}{@{}ll@{}}
\textbf{J1} intent & \textbf{J2} routing \\
\textbf{J3} ambiguity & \textbf{J4} consent \\
\textbf{J5} replay & \textbf{J6} retryability \\
\textbf{J7} injection & \\
\end{tabular}
}

\column{0.36}
\block{Architecture}{
\centering
\includegraphics[width=0.94\linewidth]{@@FIG1@@}

\vspace{0.3em}
\small M1 ingress, M2 partition by caller and conversation, M3 discovery,
M4 consent, M5 identity-bound execution, M6 state, M7 delivery.
}

\block{Processing flow}{
\centering
\includegraphics[width=0.82\linewidth]{@@FIG2@@}

\vspace{0.3em}
\small Deduplication precedes every model call; a pending consent re-enters at
authentication; a failed identity or endpoint check never reaches execution.
}
\column{0.31}
\block{Results: routing (130 requests, 3 deliveries)}{
\small
\begin{tabular}{@{}l@{\hspace{0.8em}}r@{}}
\textbf{Direct} & 48/48/50 of 50 \\
\textbf{Ambiguous} & 39/38/38 of 40 \\
\textbf{Out of scope} & 0 of 40 \\
\end{tabular}

\vspace{0.3em}
}
\block{Results: invariants (paired ablations)}{
\centering
\begin{tabular}{@{}lcc@{}}
\toprule
\textbf{Arm} & \textbf{Control} & \textbf{Removed} \\
\midrule
Identity binding & 0/30 & 30/30 \\
Caller isolation & 0/30 & 30/30 \\
Idempotency & 30 exec. & 60 exec. \\
\bottomrule
\end{tabular}

\vspace{0.3em}
\small Same-code controls; each arm changes exactly one check.
}
\block{Consent and judgment}{
\small Consent gate: \textbf{0/40} before consent, \textbf{36/36} exactly one
action; replayed consents add nothing.

\vspace{0.4em}
\centering
\begin{tabular}{@{}lcc@{}}
\toprule
 & \textbf{Typed} & \textbf{Free text} \\
\midrule
Accuracy & 94.1\% & 83.9\% \\
Brier & 0.095 & 0.266 \\
ECE & 0.026 & 0.144 \\
\bottomrule
\end{tabular}
}
\block{Takeaway}{
\textbf{Model advises; code controls identity, state, and every side effect.}

\small Consent \textbf{0/40} before, \textbf{36/36} after.\quad Judgment
\textbf{94.1\%} vs \textbf{83.9\%}; Brier \textbf{0.095} vs \textbf{0.266}.

\scriptsize Artifact: \texttt{github.com/ankelas/consent-gated-gateway-artifact}
\quad S\&T Program of Xiongan New Area (No. XA2026111001K).
}
\end{columns}

\vspace{0.6em}
\begin{columns}
\column{0.5}
\block{Injection stress set (200 injected, 256 benign near-misses)}{
Both answer shapes catch every injected item (0\% miss), yet flag about half of
the quoted benign mentions: 52.5\% typed and 59.6\% free text, which is why the
injection score only parameterizes policy.
}
\column{0.5}
\block{Gateway cost}{
\centering
\includegraphics[width=0.9\linewidth]{@@FIG3@@}
}
\end{columns}

"""

PREAMBLE = r"""
\documentclass[25pt, @@OPTIONS@@]{tikzposter}
\usepackage[T1]{fontenc}
\usepackage{helvet}
\renewcommand{\familydefault}{\sfdefault}
\usepackage{booktabs}
\usepackage{graphicx}
\definecolor{navy}{HTML}{0F2A44}
\definecolor{teal}{HTML}{1F7A8C}
\colorlet{colorOne}{navy}
\colorlet{colorTwo}{teal}
\usetheme{Default}
\title{\parbox{0.92\linewidth}{\centering\LARGE @@TITLE@@}}
\author{@@AUTHORS@@}
\institute{@@INSTITUTE@@}
\begin{document}
\maketitle[width=0.96\linewidth]
"""


def fill(text: str, options: str) -> str:
    return (text
            .replace("@@OPTIONS@@", options)
            .replace("@@TITLE@@", TITLE)
            .replace("@@AUTHORS@@", AUTHORS)
            .replace("@@INSTITUTE@@", INSTITUTE)
            .replace("@@MODULES@@", MODULES)
            .replace("@@ROUTING@@", ROUTING)
            .replace("@@ABLATIONS@@", ABLATIONS)
            .replace("@@CONSENT@@", CONSENT)
            .replace("@@JUDGMENT@@", JUDGMENT)
            .replace("@@TAKEAWAY@@", TAKEAWAY)
            .replace("@@FIG1@@", str(FIG / "fig1_architecture.png"))
            .replace("@@FIG2@@", str(FIG / "fig2_state_machine.png"))
            .replace("@@FIG3@@", str(FIG / "fig3_overhead.png")))


def build(name: str, options: str, body: str) -> Path:
    tex = fill(PREAMBLE, options) + fill(body, options) + "\n\\end{document}\n"
    out = ROOT / f"{name}.tex"
    out.write_text(tex, encoding="utf-8")
    print(out)
    return out


if __name__ == "__main__":
    build("poster_a1_landscape", "a1paper, landscape", BODY_A1)
    build("poster_a0_portrait", "a0paper, portrait", BODY_A0)
