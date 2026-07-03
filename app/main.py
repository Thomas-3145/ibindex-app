import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import streamlit as st

from app.charts import bars, donut
from app.portfolio import WeightingMethod, allocate, expand_allocations, premium_pct
from shared.constants import LISTS, NASDAQ_LIST
from shared.db import get_latest_holdings, get_latest_scrape_time, get_latest_snapshots
from shared.models import HoldingRow

VIEW_COMPANIES = "Investmentbolag"
VIEW_PREMIUM = "Ersätt bolag med premie"
VIEW_LOOK_THROUGH = "Endast underliggande bolag"

st.set_page_config(page_title="ibindex portfolio", layout="wide")
st.title("ibindex portfolio")

# --- Sidebar ---
with st.sidebar:
    capital = st.number_input(
        "Kapital (SEK)",
        min_value=1_000,
        max_value=100_000_000,
        value=100_000,
        step=10_000,
    )

    method = WeightingMethod(
        st.selectbox(
            "Viktningsmetod",
            options=[m.value for m in WeightingMethod],
        )
    )

    cap = 20.0
    if method == WeightingMethod.CAPPED:
        cap = st.slider("Maxvikt per bolag (%)", min_value=5, max_value=50, value=20)

    selected_lists = st.multiselect(
        "Listor",
        options=LISTS,
        default=LISTS,
    )

    view = st.radio(
        "Vy",
        options=[VIEW_COMPANIES, VIEW_PREMIUM, VIEW_LOOK_THROUGH],
        help=(
            "**Ersätt bolag med premie**: bolag som handlas över sitt substansvärde "
            "byts ut mot sina noterade innehav. "
            "**Endast underliggande bolag**: alla investmentbolag byts ut mot sina "
            "noterade innehav (genomlysning)."
        ),
    )

    premium_threshold = 0.0
    if view == VIEW_PREMIUM:
        premium_threshold = st.slider(
            "Premietröskel (%)",
            min_value=0.0,
            max_value=20.0,
            value=0.0,
            step=0.5,
            help="Bolag ersätts först när premien överstiger tröskeln.",
        )

    # Disabled in the cluster (the CronJob scrapes there): the subprocess
    # spawns yfinance/pandas inside the app pod's tight memory limit.
    scrape_button_enabled = os.environ.get("ENABLE_SCRAPE_BUTTON", "true").lower() == "true"

    if scrape_button_enabled and st.button("Uppdatera data"):
        with st.spinner("Hämtar data från ibindex.se..."):
            result = subprocess.run(
                [sys.executable, "-m", "scraper.main"],
                capture_output=True,
                text=True,
            )
        if result.returncode == 0:
            st.success("Data uppdaterad!")
            st.rerun()
        else:
            st.error(f"Fel vid hämtning:\n{result.stderr}")

# --- Data freshness ---
try:
    last_scraped = get_latest_scrape_time()
except Exception:
    last_scraped = None

if last_scraped is None:
    st.warning("Ingen data hittad. Klicka på 'Uppdatera data' i sidopanelen.")
    st.stop()

scraped_dt = datetime.fromisoformat(last_scraped)
if scraped_dt.tzinfo is None:
    scraped_dt = scraped_dt.replace(tzinfo=timezone.utc)

age = datetime.now(timezone.utc) - scraped_dt
st.caption(f"Senast uppdaterad: {scraped_dt.strftime('%Y-%m-%d %H:%M')} UTC")

# 72h so weekends (the scraper runs Mon-Fri) don't trigger false alarms.
if age > timedelta(hours=72):
    hours_old = int(age.total_seconds() / 3600)
    st.warning(f"Data är {hours_old} timmar gammal. Uppdatera för aktuella priser.")

# --- Portfolio ---
try:
    snapshots = get_latest_snapshots()
except Exception as e:
    st.error(f"Kunde inte läsa databas: {e}")
    st.stop()

filtered = [s for s in snapshots if NASDAQ_LIST.get(s.ticker) in selected_lists]
results = allocate(filtered, float(capital), method=method, cap=float(cap))

if not results:
    st.info("Inga bolag med vikter hittades i datan.")
    st.stop()

# --- Holdings-based views ---
holdings: list[HoldingRow] = []
if view != VIEW_COMPANIES:
    try:
        holdings = get_latest_holdings()
    except Exception:
        holdings = []
    if not holdings:
        st.info("Innehavsdata saknas ännu — den fylls på vid nästa scrape. Visar investmentbolag.")
        view = VIEW_COMPANIES

if view == VIEW_COMPANIES:
    table_data = [
        {
            "Ticker": r.ticker,
            "Bolag": r.product_name,
            "Pris (SEK)": f"{r.price:,.2f}",
            "Vikt (%)": f"{r.weight:.2f}",
            "Allokering (SEK)": f"{r.allocated_sek:,.0f}",
            "Ungefär antal aktier": f"{r.approx_shares:.2f}",
        }
        for r in results
    ]
    chart_rows = [(r.product_name, r.allocated_sek, r.weight) for r in results]
else:
    expanded = expand_allocations(
        results,
        filtered,
        holdings,
        expand_all=view == VIEW_LOOK_THROUGH,
        premium_threshold=premium_threshold,
    )
    table_data = [
        {
            "Ticker": e.ticker or "—",
            "Bolag": e.name,
            "Vikt (%)": f"{e.weight:.2f}",
            "Allokering (SEK)": f"{e.allocated_sek:,.0f}",
            "Via": ", ".join(e.via),
        }
        for e in expanded
    ]
    chart_rows = [(e.name, e.allocated_sek, e.weight) for e in expanded]

    if view == VIEW_PREMIUM:
        snap_by_ticker = {s.ticker: s for s in filtered}
        owners_with_listed = {h.owner_ticker for h in holdings if h.category == "LST"}
        replaced = []
        for r in results:
            snapshot = snap_by_ticker.get(r.ticker)
            premium = premium_pct(snapshot) if snapshot else None
            if (
                premium is not None
                and premium > premium_threshold
                and r.ticker in owners_with_listed
            ):
                replaced.append(f"{r.product_name} (+{premium:.1f} %)")
        if replaced:
            st.caption("Ersatta premiebolag: " + ", ".join(replaced))

# --- Presentation ---
st.subheader(f"Allokering — {capital:,.0f} SEK")

presentation = st.radio(
    "Presentation",
    options=["Tabell", "Cirkeldiagram", "Stapeldiagram"],
    horizontal=True,
    label_visibility="collapsed",
)

if presentation == "Tabell":
    st.dataframe(table_data, width="stretch", hide_index=True)
elif presentation == "Cirkeldiagram":
    st.altair_chart(donut(chart_rows), width="stretch")
else:
    st.altair_chart(bars(chart_rows), width="stretch")

# --- Companies without weights ---
no_weight = [s for s in filtered if not s.market_cap_weight]
if no_weight:
    with st.expander(f"{len(no_weight)} bolag saknar vikter (ingår ej i allokeringen)"):
        rows = [
            {"Ticker": s.ticker, "Bolag": s.product_name, "Pris (SEK)": f"{s.price:,.2f}"}
            for s in no_weight
        ]
        st.dataframe(
            rows,
            width="stretch",
            hide_index=True,
        )
