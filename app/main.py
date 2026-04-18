import subprocess
import sys
from datetime import datetime, timedelta, timezone

import streamlit as st

from app.portfolio import WeightingMethod, allocate
from shared.constants import LISTS, NASDAQ_LIST
from shared.db import get_latest_scrape_time, get_latest_snapshots

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

    if st.button("Uppdatera data"):
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

if age > timedelta(hours=24):
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

# --- Allocation table ---
st.subheader(f"Allokering — {capital:,.0f} SEK")

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

st.dataframe(table_data, width="stretch", hide_index=True)

# --- Companies without weights ---
no_weight = [s for s in snapshots if not s.market_cap_weight or s.market_cap_weight == 0]
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
