import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta

import streamlit as st

from app.charts import bars, donut
from app.portfolio import (
    InfeasibleCapError,
    WeightingMethod,
    allocate,
    apply_share_class,
    cheapest_share_classes,
    compare_share_classes,
    expand_allocations,
)
from shared.constants import LISTS, NASDAQ_LIST, UNKNOWN_LIST
from shared.db import get_holdings, get_latest_run, get_share_classes, get_snapshots
from shared.models import HoldingRow, ShareClassRow, SnapshotRow

VIEW_COMPANIES = "Investmentbolag"
VIEW_PREMIUM = "Ersätt bolag med premie"
VIEW_LOOK_THROUGH = "Endast underliggande bolag"

CLASS_IBINDEX = "Som ibindex"
CLASS_CHEAPEST = "Billigaste"
CLASS_MANUAL = "Välj själv"


# Streamlit reruns the whole script on every widget interaction; without the
# cache each slider tick opens fresh DB connections. One loader keeps the
# snapshot/holdings pair consistent (same scrape run).
@st.cache_data(ttl=300)
def load_data() -> tuple[datetime, list[SnapshotRow], list[HoldingRow], list[ShareClassRow]] | None:
    run = get_latest_run()
    if run is None:
        return None
    run_id, scraped_at = run
    return scraped_at, get_snapshots(run_id), get_holdings(run_id), get_share_classes(run_id)


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

    # Off by default (fail closed): anyone reaching the app could otherwise
    # spawn scrape subprocesses. Set ENABLE_SCRAPE_BUTTON=true for local dev;
    # in the cluster the CronJob scrapes instead.
    scrape_button_enabled = os.environ.get("ENABLE_SCRAPE_BUTTON", "false").lower() == "true"

    if scrape_button_enabled and st.button("Uppdatera data"):
        with st.spinner("Hämtar data från ibindex.se..."):
            result = subprocess.run(
                [sys.executable, "-m", "scraper.main"],
                capture_output=True,
                text=True,
            )
        if result.returncode == 0:
            st.success("Data uppdaterad!")
            load_data.clear()
            st.rerun()
        else:
            st.error(f"Fel vid hämtning:\n{result.stderr}")

# --- Load data ---
try:
    data = load_data()
except Exception as e:
    st.error(f"Kunde inte läsa databas: {e}")
    st.stop()

if data is None:
    st.warning("Ingen data hittad. Kör scrapern: python -m scraper.main")
    st.stop()

scraped_dt, snapshots, holdings, share_classes = data

age = datetime.now(UTC) - scraped_dt
st.caption(f"Senast uppdaterad: {scraped_dt.strftime('%Y-%m-%d %H:%M')} UTC")

# 72h so weekends (the scraper runs Mon-Fri) don't trigger false alarms.
if age > timedelta(hours=72):
    hours_old = int(age.total_seconds() / 3600)
    st.warning(f"Data är {hours_old} timmar gammal. Uppdatera för aktuella priser.")

# --- Portfolio ---
filtered = [s for s in snapshots if NASDAQ_LIST.get(s.ticker, UNKNOWN_LIST) in selected_lists]

# --- Share class choice ---
# Rendered here rather than in the sidebar block above because it needs the
# scraped data, which loads after it. A second `with st.sidebar` appends.
classes_by_base: dict[str, list[ShareClassRow]] = {}
for sc in sorted(share_classes, key=lambda c: c.price):
    if any(s.ticker == sc.base_ticker for s in filtered):
        classes_by_base.setdefault(sc.base_ticker, []).append(sc)
multi_class = {base: cs for base, cs in classes_by_base.items() if len(cs) > 1}

chosen_classes: dict[str, str] = {}
if multi_class:
    with st.sidebar:
        class_mode = st.radio(
            "Aktieslag",
            options=[CLASS_IBINDEX, CLASS_CHEAPEST, CLASS_MANUAL],
            help=(
                "Vissa bolag är noterade i två aktieslag med identisk rätt till "
                "utdelning och substans — bara rösterna skiljer. Det billigaste "
                "ger därför mest substans per krona. Illikvida aktieslag väljs "
                "aldrig automatiskt."
            ),
        )
        if class_mode == CLASS_CHEAPEST:
            chosen_classes = cheapest_share_classes(share_classes)
        elif class_mode == CLASS_MANUAL:
            names = {s.ticker: s.product_name for s in filtered}
            for base, classes in sorted(multi_class.items()):
                options = [c.ticker for c in classes]
                chosen_classes[base] = st.selectbox(
                    names[base],
                    options=options,
                    index=options.index(base) if base in options else 0,
                    key=f"class_{base}",
                )

portfolio = apply_share_class(filtered, share_classes, chosen_classes)

try:
    results = allocate(portfolio, float(capital), method=method, cap=float(cap))
except InfeasibleCapError as exc:
    st.warning(
        f"Ett tak på {exc.cap_pct:g} % är inte möjligt med "
        f"{exc.company_count} valbara bolag. Höj taket till minst "
        f"{exc.minimum_cap_pct:.1f} %, välj fler listor eller byt viktningsmetod."
    )
    st.stop()

if not results:
    st.info("Inga bolag med vikter hittades i datan.")
    st.stop()

invested_total = round(sum(r.allocated_sek for r in results), 2)
cash = round(float(capital) - invested_total, 2)
cash_weight = cash / float(capital) * 100

invested_col, cash_col = st.columns(2)
invested_col.metric("Investerat", f"{invested_total:,.0f} SEK")
cash_col.metric("Kvar i kassa", f"{cash:,.0f} SEK")

# --- Share class comparison ---
comparisons = compare_share_classes(filtered, share_classes)
if comparisons:
    # comparisons[0] is the widest spread among the classes that actually
    # trade, which is the only one worth putting in the headline.
    headline = comparisons[0]
    others = f" (+ {len(comparisons) - 1} till)" if len(comparisons) > 1 else ""
    with st.expander(
        f"Aktieslag: {headline.cheapest_ticker} är {headline.spread_pct:.1f} % "
        f"billigare än {headline.priciest_ticker}{others}"
    ):
        st.dataframe(
            [
                {
                    "Bolag": c.product_name,
                    "Billigast": c.cheapest_ticker,
                    "Pris (SEK)": f"{c.cheapest_price:,.2f}",
                    "Dyrast": c.priciest_ticker,
                    "Pris (SEK) ": f"{c.priciest_price:,.2f}",
                    "Skillnad (%)": f"{c.spread_pct:.2f}",
                    "Anmärkning": "Tunt handlat — priset kan vara inaktuellt" if c.illiquid else "",
                }
                for c in comparisons
            ],
            width="stretch",
            hide_index=True,
        )
        st.caption(
            "Aktieslagen har identisk rätt till utdelning och substansvärde — "
            "skillnaden är rösträtt. För en passiv ägare ger det billigaste "
            "aktieslaget mest substans per krona."
        )

# --- Holdings-based views ---
if view != VIEW_COMPANIES and not holdings:
    st.info("Innehavsdata saknas ännu — den fylls på vid nästa scrape. Visar investmentbolag.")
    view = VIEW_COMPANIES

if view == VIEW_COMPANIES:
    table_data = [
        {
            "Ticker": chosen_classes.get(r.ticker, r.ticker),
            "Bolag": r.product_name,
            "Pris (SEK)": f"{r.price:,.2f}",
            "Målvikt (%)": f"{r.weight:.2f}",
            "Målbelopp (SEK)": f"{r.target_sek:,.0f}",
            "Antal aktier": f"{r.shares:,}",
            "Investerat (SEK)": f"{r.allocated_sek:,.2f}",
            "Faktisk vikt (%)": f"{r.allocated_sek / float(capital) * 100:.2f}",
        }
        for r in results
    ]
    table_data.append(
        {
            "Ticker": "—",
            "Bolag": "Kassa",
            "Pris (SEK)": "—",
            "Målvikt (%)": "—",
            "Målbelopp (SEK)": "—",
            "Antal aktier": "—",
            "Investerat (SEK)": f"{cash:,.2f}",
            "Faktisk vikt (%)": f"{cash_weight:.2f}",
        }
    )
    chart_rows = [
        (r.product_name, r.allocated_sek, r.allocated_sek / float(capital) * 100) for r in results
    ]
else:
    expanded, replaced, unavailable = expand_allocations(
        results,
        portfolio,
        holdings,
        expand_all=view == VIEW_LOOK_THROUGH,
        premium_threshold=premium_threshold,
    )
    table_data = [
        {
            "Ticker": e.ticker or "—",
            "Bolag": e.name,
            "Faktisk vikt (%)": f"{e.weight:.2f}",
            "Investerat (SEK)": f"{e.allocated_sek:,.2f}",
            "Via": ", ".join(e.via),
        }
        for e in expanded
    ]
    table_data.append(
        {
            "Ticker": "—",
            "Bolag": "Kassa",
            "Faktisk vikt (%)": f"{cash_weight:.2f}",
            "Investerat (SEK)": f"{cash:,.2f}",
            "Via": "Ej investerat",
        }
    )
    chart_rows = [(e.name, e.allocated_sek, e.weight) for e in expanded]

    if view == VIEW_PREMIUM and replaced:
        st.caption(
            "Ersatta premiebolag: "
            + ", ".join(f"{name} (+{premium:.1f} %)" for name, premium in replaced)
        )
    if unavailable:
        st.warning(
            "Kan inte genomlysa följande bolag eftersom noterade innehav saknas: "
            + ", ".join(unavailable)
            + ". De visas därför som direktägda."
        )

chart_rows.append(("Kassa", cash, cash_weight))

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
no_weight = [s for s in portfolio if not s.market_cap_weight]
if no_weight:
    suffix = "men ingår i likaviktningen" if method == WeightingMethod.EQUAL else "och ingår inte"
    with st.expander(f"{len(no_weight)} bolag saknar marknadsvikt ({suffix})"):
        rows = [
            {"Ticker": s.ticker, "Bolag": s.product_name, "Pris (SEK)": f"{s.price:,.2f}"}
            for s in no_weight
        ]
        st.dataframe(
            rows,
            width="stretch",
            hide_index=True,
        )
