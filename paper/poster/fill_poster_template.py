"""Fill the conference's PPTX poster template.

The template is one slide (A0 portrait) with dashed section frames and text
placeholders.  This script keeps the frame layout and fills each placeholder,
then optionally scales every shape and font to A1 portrait (594 x 841 mm),
which preserves the template's proportions.
"""

from __future__ import annotations

import re
import shutil
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
TEMPLATE = ROOT / "jcrai_poster_template.pptx"

CONTENT = {
    "Poster title": [
        "Typed Judgment, Deterministic Enforcement: A Consent-Gated Gateway "
        "Architecture for Inter-Agent Collaboration over Messaging Channels",
    ],
    "Author lists": ["Yizhang Cai, Jun Liu, Di Ma, Ke Yu, Ke Li"],
    "Affiliated programs, organizations,institutions,schools etc": [
        "Beijing University of Posts and Telecommunications  |  Beijing Guoshu "
        "Zhilian Technology Co., Ltd.  |  2025111259@bupt.cn",
    ],
    "Paper ID": ["Session XII"],
    "Introduction or abstract": ["Introduction"],
    "Type your text here": None,  # filled positionally below
    "Objectives": ["Objectives"],
    "Materials & Methods": ["Materials and Methods"],
    "Results": ["Results"],
    "Conclusion": ["Conclusion"],
    "References": ["References"],
    "Acknowlegements or Contact": ["Acknowledgements and Contact"],
    "Conference Full Name Here": [
        "JCRAI 2026  |  6th International Joint Conference on Robotics and "
        "Artificial Intelligence",
    ],
}

BODY = {
    "intro": [
        "Messaging channels and agent protocols make different assumptions. "
        "Human events are unstructured, duplicated, delayed or replayed; "
        "protocol calls expect authenticated endpoints, structured requests and "
        "explicit task state. A gateway must decide whether a message requests "
        "work, which agent is eligible, whether consent is needed, and whether "
        "an event is a replay or an injection.",
        "We separate bounded model judgment from deterministic enforcement: the "
        "model answers closed questions, while policy code owns thresholds and "
        "every effect.",
    ],
    "objectives": [
        "Seven-module gateway from an iMessage/Photon ingress to an ACPs/AIP "
        "v2.2 Leader-Partner path.",
        "Four invariants kept in code: authorization, identity, isolation, "
        "idempotency.",
        "A judgment plane of seven closed questions (J1-J7) that can only "
        "parameterize thresholds.",
        "Live measurement of routing, consent, and the deployed advisory "
        "judgment path.",
    ],
    "methods": [
        "M1 ingress authentication; M2 caller/conversation isolation; M3 "
        "discovery and routing; M4 consent and policy; M5 identity-bound "
        "execution; M6 state, idempotency and recovery; M7 delivery and "
        "telemetry.",
        "130 generated requests through the real ingress, three deliveries "
        "each; paired same-code ablations on staging copies; consent trials on "
        "the deployed adapter; a 280-item judgment suite sampled three times.",
    ],
    "results": [
        "Routing: the target was recommended for 48/48/50 of 50 direct "
        "requests; 39/38/38 of 40 ambiguous requests received more than one "
        "agent; 0/40 out-of-scope requests recommended a study partner.",
        "Ablations: identity 0/30 to 30/30; isolation 0/30 to 30/30; "
        "idempotency 30 to 60 executions.",
        "Consent: 0/40 partner actions before consent; 36/36 consents produced "
        "exactly one action.",
        "Judgment layer: 94.1% vs 83.9% accuracy; Brier 0.095 vs 0.266; ECE "
        "0.026 vs 0.144.",
    ],
    "conclusion": [
        "Model advises; code controls identity, state and every side effect. "
        "Typed answers are more accurate and better calibrated than free text, "
        "and the injection score is only a threshold parameter because it "
        "over-triggers on quoted text.",
    ],
    "references": [
        "J. Liu et al., ACPs: Agent Collaboration Protocols for the Internet of "
        "Agents, arXiv:2505.13523, 2025.",
        "Q. Zhan et al., InjecAgent, arXiv:2403.02691, 2024.",
        "S. Chen et al., StruQ, arXiv:2402.06363, 2024.",
        "E. Debenedetti et al., AgentDojo, NeurIPS 2024.",
    ],
    "ack": [
        "2025111259@bupt.cn",
        "github.com/ankelas/consent-gated-gateway-artifact",
        "Supported by S&T Program of Xiongan New Area (No. XA2026111001K).",
    ],
}

SIZE_OVERRIDE = {"Poster title": 5000,
                 "Affiliated programs, organizations,institutions,schools etc": 2400}

BODY_ORDER = ["intro", "objectives", "methods", "results", "conclusion",
              "references", "ack"]


def escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def paragraphs(lines: list[str], size: int) -> str:
    return "".join(
        f'<a:p><a:r><a:rPr lang="en-US" altLang="zh-CN" sz="{size}"/>'
        f"<a:t>{escape(line)}</a:t></a:r></a:p>"
        for line in lines
    )


def fill_slide(xml: str, scale: float) -> str:
    """Replace placeholder text and scale geometry by ``scale``."""

    def shape_replace(match: re.Match[str]) -> str:
        shape = match.group(0)
        label = " ".join(re.findall(r"<a:t>(.*?)</a:t>", shape)).strip()
        label = label.replace("&amp;", "&")
        if not label:
            return shape

        body_key = None
        marker = re.match(r"@@BODY:([a-z]+)@@", label)
        if marker:
            body_key = marker.group(1)
            text = None
        else:
            text = CONTENT.get(label)
            if text is None:
                return shape

        # Sections whose body is a separate "Type your text here" box.
        size_match = re.search(r'<a:rPr[^>]*sz="(\d+)"', shape)
        base_size = int(size_match.group(1)) if size_match else 3600
        base_size = SIZE_OVERRIDE.get(label, base_size)
        new_size = int(round(base_size * scale / 100.0)) * 100
        lines = text if text else (BODY.get(body_key, []) if body_key else [])
        if not lines:
            return shape
        shape = re.sub(
            r"<p:txBody>.*?</p:txBody>",
            lambda m: (m.group(0).split("<a:p>")[0]
                       + paragraphs(lines, new_size)
                       + "</p:txBody>"),
            shape,
            flags=re.S,
        )
        return shape

    xml = re.sub(r"<p:sp>.*?</p:sp>", shape_replace, xml, flags=re.S)

    def scale_pair(match: re.Match[str]) -> str:
        tag = match.group(1)
        x = int(round(int(match.group(2)) * scale))
        y = int(round(int(match.group(3)) * scale))
        return f'<a:{tag} {match.group(4)}="{x}" {match.group(5)}="{y}"/>'

    xml = re.sub(
        r'<a:(off|ext) ([a-z]+)="(\d+)" ([a-z]+)="(\d+)"/>',
        lambda m: (f'<a:{m.group(1)} {m.group(2)}="{int(round(int(m.group(3)) * scale))}" '
                   f'{m.group(4)}="{int(round(int(m.group(5)) * scale))}"/>'),
        xml,
    )
    return xml


def build(name: str, scale: float, width: int, height: int) -> Path:
    out = ROOT / name
    with zipfile.ZipFile(TEMPLATE) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for item in src.infolist():
            data = src.read(item.filename)
            if item.filename == "ppt/slides/slide1.xml":
                xml = data.decode("utf-8")
                # Mark each body placeholder in document order.
                parts = xml.split('>Type your text here<')
                if len(parts) == len(BODY_ORDER) + 1:
                    rebuilt = parts[0]
                    for key, part in zip(BODY_ORDER, parts[1:]):
                        rebuilt += f">@@BODY:{key}@@<" + part
                    xml = rebuilt
                xml = fill_slide(xml, scale)
                xml = re.sub(
                    r'<p:sldSz[^>]*/>',
                    f'<p:sldSz cx="{width}" cy="{height}"/>',
                    xml,
                )
                data = xml.encode("utf-8")
            elif item.filename == "ppt/presentation.xml":
                xml = data.decode("utf-8")
                xml = re.sub(
                    r'<p:sldSz[^>]*/>',
                    f'<p:sldSz cx="{width}" cy="{height}"/>',
                    xml,
                )
                data = xml.encode("utf-8")
            dst.writestr(item, data)
    print(out)
    return out


if __name__ == "__main__":
    # A0 portrait, template size unchanged.
    build("poster_template_a0.pptx", 1.0, 30275213, 42803763)
    # A1 portrait: 594 x 841 mm, uniformly scaled by 1/sqrt(2).
    build("poster_template_a1.pptx", 0.7071, 21384000, 30276000)
