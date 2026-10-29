"""Shared chart style for CityLens: small charts, one question each, values labeled.

Colors follow the project palette: blue for the thing being studied, orange for a
second highlighted series, neutral gray for references and baselines.
"""
from __future__ import annotations

from pathlib import Path

SURFACE, INK, INK_2, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#e7e6e2"
SERIES_1, SERIES_2, NEUTRAL, FAINT = "#2a78d6", "#eb6834", "#8c8a83", "#d6d4ce"


def plt():
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as pyplot
    pyplot.rcParams.update({
        "font.size": 8.5, "axes.titlesize": 10, "axes.labelsize": 8.5,
        "xtick.labelsize": 8, "ytick.labelsize": 8, "font.family": "DejaVu Sans",
    })
    return pyplot


def new(width: float = 6.4, height: float = 3.0, ncols: int = 1, **kw):
    pyplot = plt()
    fig, axes = pyplot.subplots(1, ncols, figsize=(width, height), dpi=200, facecolor=SURFACE, **kw)
    for ax in (axes if ncols > 1 else [axes]):
        style(ax)
    return fig, axes


def style(ax, grid: str = "y") -> None:
    ax.set_facecolor(SURFACE)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    if grid:
        ax.grid(axis=grid, color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(colors=INK_2, length=0)


def title(fig, text: str, subtitle: str | None = None) -> None:
    fig.text(0.01, 0.98, text, ha="left", va="top", fontsize=10, fontweight="bold", color=INK)
    if subtitle:
        fig.text(0.01, 0.91, subtitle, ha="left", va="top", fontsize=8, color=INK_2)


def save(fig, path: Path, top: float = 0.82) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0, 0, 1, top))
    fig.savefig(path, facecolor=SURFACE)
    plt().close(fig)
    return path.name


def end_label(ax, x, y, text: str, color: str = INK, bold: bool = False, dy: float = 0) -> None:
    ax.annotate(text, (x, y), xytext=(5, dy), textcoords="offset points", va="center", fontsize=8,
                color=color, fontweight="bold" if bold else "normal")


def label_points(ax, xs, ys, texts, dx: float = 6, dy: float = 0, step: float = 9, color: str = INK,
                 bold: bool = False, fontsize: float = 7.5, ha: str = "left") -> None:
    """Label points without overlaps. Each label tries its default spot, then nudges up and
    down, then tries the other side; it is never dropped. A thin halo keeps text readable
    on top of markers, and a hairline leader connects any label that had to move."""
    import matplotlib.patheffects as pe
    fig = ax.figure
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    halo = [pe.withStroke(linewidth=2.4, foreground=SURFACE)]
    other = "right" if ha == "left" else "left"
    tries = [(dx, k, ha) for k in (0, 1, -1, 2, -2, 3, -3)] + [(-dx, k, other) for k in (0, 1, -1, 2, -2)]
    placed = []
    for x, y, text in zip(xs, ys, texts):
        for i, (ddx, k, side) in enumerate(tries):
            last = i == len(tries) - 1
            ann = ax.annotate(text, (x, y), xytext=(ddx, dy + k * step), textcoords="offset points", ha=side,
                              va="center", fontsize=fontsize, color=color, zorder=5, path_effects=halo,
                              fontweight="bold" if bold else "normal",
                              arrowprops=dict(arrowstyle="-", color=NEUTRAL, lw=0.5, shrinkA=0, shrinkB=2)
                              if (k or side != ha) else None)
            bb = ann.get_window_extent(renderer).expanded(1.04, 1.15)
            if last or not any(bb.overlaps(p) for p in placed):
                placed.append(bb)
                break
            ann.remove()
