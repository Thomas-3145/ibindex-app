"""Altair charts for the allocation views.

Colors follow the dataviz reference palette: categorical hues in fixed
slot order (never cycled), everything beyond eight series folded into a
neutral "Övriga" bucket, and a 2px surface-colored gap between segments.
"""

import altair as alt
import pandas as pd
import streamlit as st

_CATEGORICAL_LIGHT = [
    "#2a78d6",
    "#1baf7a",
    "#eda100",
    "#008300",
    "#4a3aa7",
    "#e34948",
    "#e87ba4",
    "#eb6834",
]
_CATEGORICAL_DARK = [
    "#3987e5",
    "#199e70",
    "#c98500",
    "#008300",
    "#9085e9",
    "#e66767",
    "#d55181",
    "#d95926",
]
_OTHER_COLOR = "#898781"  # muted — the fold-in bucket
_OTHER_LABEL = "Övriga"

# Streamlit's default app backgrounds, used as the gap color between arcs.
_SURFACE_LIGHT = "#ffffff"
_SURFACE_DARK = "#0e1117"

MAX_SLICES = 8


def _is_dark() -> bool:
    try:
        return st.context.theme.type == "dark"
    except Exception:
        return False


def _fold(rows: list[tuple[str, float, float]]) -> pd.DataFrame:
    """Keep the MAX_SLICES largest rows, fold the rest into one bucket."""
    ordered = sorted(rows, key=lambda r: r[1], reverse=True)
    kept = ordered[:MAX_SLICES]
    rest = ordered[MAX_SLICES:]
    if rest:
        kept.append((_OTHER_LABEL, sum(r[1] for r in rest), sum(r[2] for r in rest)))
    return pd.DataFrame(kept, columns=["Bolag", "SEK", "Vikt"])


def donut(rows: list[tuple[str, float, float]]) -> alt.Chart:
    """rows: (label, allocated_sek, weight_pct)"""
    df = _fold(rows)
    palette = _CATEGORICAL_DARK if _is_dark() else _CATEGORICAL_LIGHT
    surface = _SURFACE_DARK if _is_dark() else _SURFACE_LIGHT
    domain = df["Bolag"].tolist()
    colors = palette[: len(domain)]
    if domain and domain[-1] == _OTHER_LABEL:
        colors = palette[: len(domain) - 1] + [_OTHER_COLOR]

    # Annotated assignment: altair's fluent API is typed as Any under strict mypy.
    chart: alt.Chart = (
        alt.Chart(df)
        .mark_arc(innerRadius=70, stroke=surface, strokeWidth=2)
        .encode(
            theta=alt.Theta("SEK:Q"),
            color=alt.Color(
                "Bolag:N",
                scale=alt.Scale(domain=domain, range=colors),
                sort=None,
                legend=alt.Legend(title=None),
            ),
            order=alt.Order("SEK:Q", sort="descending"),
            tooltip=[
                alt.Tooltip("Bolag:N"),
                alt.Tooltip("SEK:Q", format=",.0f", title="Allokering (SEK)"),
                alt.Tooltip("Vikt:Q", format=".2f", title="Vikt (%)"),
            ],
        )
        .properties(height=420)
    )
    return chart


def bars(rows: list[tuple[str, float, float]]) -> alt.Chart:
    """rows: (label, allocated_sek, weight_pct). Magnitude job: one hue."""
    df = pd.DataFrame(rows, columns=["Bolag", "SEK", "Vikt"])
    palette = _CATEGORICAL_DARK if _is_dark() else _CATEGORICAL_LIGHT

    chart: alt.Chart = (
        alt.Chart(df)
        .mark_bar(cornerRadiusEnd=4, color=palette[0])
        .encode(
            x=alt.X("SEK:Q", axis=alt.Axis(title=None, format="~s")),
            y=alt.Y("Bolag:N", sort="-x", axis=alt.Axis(title=None, labelLimit=220)),
            tooltip=[
                alt.Tooltip("Bolag:N"),
                alt.Tooltip("SEK:Q", format=",.0f", title="Allokering (SEK)"),
                alt.Tooltip("Vikt:Q", format=".2f", title="Vikt (%)"),
            ],
        )
        .properties(height=max(240, 26 * len(rows)))
    )
    return chart
