# ibindex-portfolio

Ett verktyg för att bygga en teoretisk portfölj av svenska investmentbolag, baserat på data från [ibindex.se](https://ibindex.se).

Appen hämtar dagligen data om substansvärde (NAV), aktiepris och premie/rabatt för 21 svenska investmentbolag och föreslår en allokering baserat på vald viktningsmetod.

> **Notering:** Detta projekt är medvetet överkonstruerat som ett DevOps-lärprojekt. Målet är att simulera en produktionsmiljö med microservices, CI/CD, Kubernetes och observability — inte att bygga den enklaste möjliga lösningen.

---

## Funktioner

- Hämtar realtidsdata från ibindex.se (pris, NAV, premie/rabatt)
- Beräknar marknadsvikter via Yahoo Finance (antal utestående aktier × pris)
- Fyra viktningsmetoder:
  - **Marknadsviktat** — ren market cap-viktning
  - **Logaritmiskt viktat** — jämnar ut dominansen från stora bolag
  - **Marknadsviktat med tak** — market cap med konfigurerbar maxvikt per bolag
  - **Likaviktat** — 1/N per bolag
- Filterval per Nasdaq-lista (Large Cap, Mid Cap, Small Cap, First North)
- Historik sparas i databasen vid varje daglig scrape

---

## Arkitektur

```
ibindex-app/
├── scraper/        # Hämtar data från ibindex.se + Yahoo Finance → sparar till DB
├── app/            # Streamlit-UI + portföljlogik
├── shared/         # Gemensamma modeller, DB-lager och konstanter
├── db/             # PostgreSQL-schema
└── tests/          # Enhetstester för portföljlogik
```

### Stack

| Del | Teknik |
|-----|--------|
| Scraping | Python + requests + yfinance |
| Databas | PostgreSQL |
| Frontend | Streamlit |
| Hosting | Kubernetes (k3s) via ArgoCD |
| Schemaläggning | Kubernetes CronJob (daglig scrape efter börsstängning) |

### Varför denna stack?

**Python** är det naturliga valet för datahämtning och analys. Biblioteken `requests` och `yfinance` täcker båda datakällorna utan overhead.

**PostgreSQL** valdes framför SQLite trots att SQLite skulle räcka för appens behov. Anledningen är att SQLite inte hanterar flera samtida skrivare — vilket bryter så fort man kör mer än en replica i Kubernetes. PostgreSQL är också vad man möter i produktion, och att lära sig hantera en riktig databasserver (anslutningssträngar, migrationer, WAL) är en del av poängen med projektet.

**Streamlit** ger ett fullständigt webb-UI i ren Python utan att behöva bygga ett separat frontend-projekt. För en MVP där fokus ligger på infrastrukturen snarare än UI:t är det rätt avvägning.

**Kubernetes (k3s)** och **ArgoCD** driver GitOps-flödet: ett push till `main` resulterar automatiskt i en ny deployment på homelabbets kluster. Det simulerar hur moderna produktionsmiljöer fungerar och är kärnan i vad projektet är till för att lära ut.

---

## Kom igång

### Krav

- Python 3.14+
- [uv](https://github.com/astral-sh/uv)
- PostgreSQL (eller Docker)

### Starta PostgreSQL

```bash
docker run -d --name ibindex-db \
  -e POSTGRES_DB=ibindex \
  -e POSTGRES_PASSWORD=dev \
  -p 5432:5432 postgres:17
```

### Installation

```bash
# Kopiera och fyll i miljövariabler
cp .env.example .env

# Installera beroenden
uv sync
```

### Kör lokalt

```bash
# Hämta data från ibindex.se och Yahoo Finance
python -m scraper.main

# Starta appen
streamlit run app/main.py
```

### Tester

```bash
uv run pytest
```

---

## Datakällor

- **[ibindex.se](https://ibindex.se)** — pris, NAV och premie/rabatt för 21 svenska investmentbolag
- **Yahoo Finance** (via yfinance) — antal utestående aktier för marknadsvärdesberäkning

---

## Status

Se [ROADMAP.md](ROADMAP.md) för planerade faser och framtida features.
