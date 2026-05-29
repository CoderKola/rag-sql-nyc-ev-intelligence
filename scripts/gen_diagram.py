"""Generate docs/reasoning.png — run once to regenerate the diagram."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np

FIG_W, FIG_H = 9, 12
fig = plt.figure(figsize=(FIG_W, FIG_H))
ax = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, FIG_W)
ax.set_ylim(0, FIG_H)
ax.axis("off")
BG = "#0F172A"
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)

# ── palette ───────────────────────────────────────────────────────────────────
SLATE   = "#1E293B"
PURPLE  = "#7C3AED"
BLUE    = "#2563EB"
TEAL    = "#0D9488"
CYAN    = "#0891B2"
VIOLET  = "#7C3AED"
GREEN   = "#16A34A"
ORANGE  = "#EA580C"
RED     = "#DC2626"
WHITE   = "#F8FAFC"
MUTED   = "#94A3B8"
LABEL   = "#64748B"

# ── helpers ───────────────────────────────────────────────────────────────────
def box(cx, cy, w, h, label, fc, tc=WHITE, fs=8.5, sub=None, radius=0.22):
    p = FancyBboxPatch(
        (cx - w / 2, cy - h / 2), w, h,
        boxstyle=f"round,pad=0,rounding_size={radius}",
        fc=fc, ec="none", zorder=3,
    )
    ax.add_patch(p)
    if sub:
        ax.text(cx, cy + 0.14, label, ha="center", va="center",
                fontsize=fs, color=tc, fontweight="bold", zorder=4)
        ax.text(cx, cy - 0.16, sub, ha="center", va="center",
                fontsize=fs - 1.5, color=tc, alpha=0.75, zorder=4)
    else:
        ax.text(cx, cy, label, ha="center", va="center",
                fontsize=fs, color=tc, fontweight="bold", zorder=4)


def diamond(cx, cy, w, h, label, fc):
    pts = np.array([[cx, cy + h / 2], [cx + w / 2, cy],
                    [cx, cy - h / 2], [cx - w / 2, cy]])
    ax.add_patch(plt.Polygon(pts, fc=fc, ec="none", zorder=3))
    ax.text(cx, cy, label, ha="center", va="center",
            fontsize=8.5, color=WHITE, fontweight="bold", zorder=4)


def arr(x1, y1, x2, y2, lbl="", rad=0, color=MUTED, lbl_dx=0.12, lbl_dy=0):
    ax.annotate(
        "", xy=(x2, y2), xytext=(x1, y1),
        arrowprops=dict(arrowstyle="->", color=color, lw=1.4,
                        connectionstyle=f"arc3,rad={rad}"),
        zorder=2,
    )
    if lbl:
        mx = (x1 + x2) / 2 + lbl_dx
        my = (y1 + y2) / 2 + lbl_dy
        ax.text(mx, my, lbl, fontsize=7, color=LABEL, style="italic", zorder=5)


# ── title ─────────────────────────────────────────────────────────────────────
ax.text(4.5, 11.5, "Reasoning Workflow", ha="center",
        fontsize=15, color=WHITE, fontweight="bold")
ax.text(4.5, 11.05, "question  →  guard  →  rag retrieval  →  route  →  execute  →  stream",
        ha="center", fontsize=7.5, color=MUTED, style="italic")

# ── nodes (top → bottom) ──────────────────────────────────────────────────────
# 1. Question
box(4.5, 10.2, 3.0, 0.6, "User Question", SLATE, fs=10)

# 2. Guard
diamond(4.5, 9.05, 2.6, 0.78, "EV Guard", RED)
box(7.4, 9.05, 1.5, 0.45, "Rejected", "#450A0A", "#FCA5A5", fs=8)

# 3. ChromaDB KB  — wide, prominent
box(4.5, 7.8, 8.2, 0.82,
    "ChromaDB Knowledge Base",
    PURPLE, fs=9,
    sub="Schema · 21 columns     Analyst Skills     Data Gotchas     Program Docs")

# 4. Router
diamond(4.5, 6.65, 2.8, 0.75, "Route Classifier", BLUE)

# 5. Four branches
BX = [1.0, 3.0, 6.0, 8.0]
BC = [TEAL, CYAN, VIOLET, GREEN]
BL = ["DeepSeek\nSQL gen", "Nominatim\n+ Haversine", "Re-run\nprior SQL", "DeepSeek\nRAG answer"]
for bx, bc, bl in zip(BX, BC, BL):
    box(bx, 5.4, 1.55, 0.68, bl, bc, fs=7.8)

# 6. DuckDB (covers SQL / Nearest / Explain paths)
box(3.5, 4.05, 4.6, 0.6, "DuckDB  ·  Parquet  ·  vectorized column scan", ORANGE, fs=8.5)

# auto-fix loop label
ax.text(5.95, 4.55, "auto-fix ↺", fontsize=7, color="#FB923C",
        style="italic", ha="center")

# 7. DeepSeek interpret
box(3.5, 2.95, 4.6, 0.6, "DeepSeek  ·  Interpret  +  Visualize", BLUE, fs=8.5)

# 8. Output
box(4.5, 1.75, 6.5, 0.65, "Text  ·  Plotly Chart  ·  MapLibre Map", SLATE, fs=9.5,
    sub=None)
# subtle glow border on output
glow = FancyBboxPatch(
    (4.5 - 6.5/2 - 0.03, 1.75 - 0.65/2 - 0.03), 6.5 + 0.06, 0.65 + 0.06,
    boxstyle="round,pad=0,rounding_size=0.25",
    fc="none", ec=TEAL, linewidth=1.2, alpha=0.5, zorder=2,
)
ax.add_patch(glow)

# ── arrows ────────────────────────────────────────────────────────────────────
arr(4.5, 9.9,  4.5, 9.44)                        # Q → Guard
arr(5.8, 9.05, 6.65, 9.05, "fail")               # Guard → Rejected
arr(4.5, 8.66, 4.5, 8.21, "pass")                # Guard → KB
arr(4.5, 7.39, 4.5, 7.03)                         # KB → Router

# Router → 4 branches (angled)
arr(3.5, 6.28, 1.0, 5.74,  "analytics")
arr(4.0, 6.28, 3.0, 5.74,  "nearest")
arr(5.0, 6.28, 6.0, 5.74,  "explain")
arr(5.5, 6.28, 8.0, 5.74,  "info")

# SQL, Nearest, Explain → DuckDB
arr(1.0, 5.06, 2.0, 4.35)
arr(3.0, 5.06, 3.1, 4.35)
arr(6.0, 5.06, 5.5, 4.35)

# DuckDB → DeepSeek
arr(3.5, 3.75, 3.5, 3.25)

# DeepSeek → Output
arr(3.5, 2.65, 3.8, 2.08)

# Info → Output (direct bypass, curved)
ax.annotate(
    "", xy=(6.5, 2.08), xytext=(8.0, 5.06),
    arrowprops=dict(arrowstyle="->", color=GREEN, lw=1.3,
                    connectionstyle="arc3,rad=0.25"),
    zorder=2,
)

plt.savefig(
    "/Users/ko/Documents/nyc-intelligence/docs/reasoning.png",
    dpi=160, bbox_inches="tight",
    facecolor=BG, edgecolor="none",
)
print("Saved docs/reasoning.png")
