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
