"""Turns a visual block's structured spec into something drawable.

The model never draws or links images: it describes a visual (labels,
connections, rows) and the app draws it. Graphs become Graphviz DOT (rendered
in the browser by Streamlit), tables become Markdown, charts become data.
"""

import re

from app.schemas.enums import VisualType
from app.schemas.lesson import ContentBlock

GRAPH_TYPES = {VisualType.FLOWCHART, VisualType.TIMELINE, VisualType.CONCEPT_MAP,
               VisualType.LABELED_DIAGRAM}

_EDGE = re.compile(r"^\s*(.+?)\s*-+>\s*(.+?)\s*(?::\s*(.+))?$")


def _q(text: str) -> str:
    """Escape a label for DOT and wrap long labels onto two lines."""
    text = text.replace("\\", "\\\\").replace('"', '\\"')
    if len(text) > 22 and " " in text:
        middle = len(text) // 2
        cut = min((i for i, ch in enumerate(text) if ch == " "), key=lambda i: abs(i - middle))
        text = text[:cut] + "\\n" + text[cut + 1:]
    return text


def to_dot(block: ContentBlock) -> str:
    vt = block.visual_type
    left_to_right = vt in (VisualType.FLOWCHART, VisualType.TIMELINE)
    lines = [
        "digraph {",
        f'  rankdir={"LR" if left_to_right else "TB"}; bgcolor="transparent"; pad="0.2"; nodesep="0.35";',
        '  node [shape=box, style="rounded,filled", fillcolor="#F0FDF4", color="#047857", penwidth=1.4,'
        ' fontname="Helvetica", fontsize=12, fontcolor="#1C1917", margin="0.18,0.1"];',
        '  edge [color="#57534E", fontname="Helvetica", fontsize=10, fontcolor="#57534E", arrowsize=0.8];',
    ]
    ids: dict[str, str] = {}

    def node(label: str) -> str:
        key = label.strip().casefold()
        if key not in ids:
            ids[key] = f"n{len(ids)}"
            lines.append(f'  {ids[key]} [label="{_q(label.strip())}"];')
        return ids[key]

    elements = list(block.elements)
    for label in elements:
        node(label)
    if vt is VisualType.LABELED_DIAGRAM and elements:  # the whole thing stands out
        lines.append(f'  {ids[elements[0].strip().casefold()]} [fillcolor="#DCFCE7", penwidth=2.2];')
    if vt is VisualType.TIMELINE:
        lines.append('  node [shape=ellipse];')

    edges = []
    for connection in block.connections:
        match = _EDGE.match(connection)
        if match:
            edges.append((node(match.group(1)), node(match.group(2)), match.group(3)))
    if not edges and len(elements) > 1:  # sensible defaults when no connections were given
        if vt in (VisualType.FLOWCHART, VisualType.TIMELINE):
            edges = [(node(a), node(b), None) for a, b in zip(elements, elements[1:])]
        else:
            edges = [(node(elements[0]), node(part), None) for part in elements[1:]]
    for source, target, label in edges:
        attrs = f' [label="{_q(label)}"]' if label else ""
        lines.append(f"  {source} -> {target}{attrs};")
    lines.append("}")
    return "\n".join(lines)


def table_markdown(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    cells = [[(c or "").replace("|", "\\|").replace("\n", " ") for c in r] + [""] * (width - len(r)) for r in rows]
    header, *body = cells
    out = ["| " + " | ".join(header) + " |", "|" + "---|" * width]
    out += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(out)


def chart_data(rows: list[list[str]]) -> tuple[str, list[str], list[float]] | None:
    """(value label, categories, numbers) if the rows really are label/number pairs."""
    if len(rows) < 2 or any(len(r) < 2 for r in rows):
        return None
    labels, values = [], []
    for row in rows[1:]:
        try:
            values.append(float(re.sub(r"[^\d.\-]", "", row[1])))
        except ValueError:
            return None
        labels.append(row[0])
    return rows[0][1] or "Value", labels, values


def visual_markdown(block: ContentBlock) -> str:
    """A text version of a visual, for Markdown export."""
    vt = block.visual_type
    head = f"*Visual ({vt.value.replace('_', ' ')}): {block.caption}*"
    if vt in (VisualType.TABLE, VisualType.CHART) and block.rows:
        return head + "\n\n" + table_markdown(block.rows)
    if vt is VisualType.CODE_SNIPPET:
        notes = "\n".join(f"- {e}" for e in block.elements)
        return head + f"\n\n```\n{block.content}\n```" + (f"\n\n{notes}" if notes else "")
    parts = [f"- {e}" for e in block.elements]
    parts += [f"- {c}" for c in block.connections]
    return head + ("\n\n" + "\n".join(parts) if parts else "")
