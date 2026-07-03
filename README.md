# ibindex-portfolio

**Live:** [ibindex.3145.blog](https://ibindex.3145.blog)

Ett medvetet överkonstruerat DevOps-lärprojekt — appen är ett fordon, inte målet. Målet är att simulera en produktionsmiljö med microservices, CI/CD, Kubernetes och observability.

Appen i sig hämtar dagligen data om svenska investmentbolag från [ibindex.se](https://ibindex.se) och föreslår en portföljallokering baserat på marknadsvärde.

> **Notering om appkoden:** Själva applikationskoden (Python, scraper, portföljlogik) är genererad av AI. Det är ett medvetet val — fokus och lärande ligger på infrastruktur och DevOps, inte apputveckling.

---

## Varför denna stack?

**Python** är det naturliga valet för datahämtning och analys. Biblioteken `requests` och `yfinance` täcker båda datakällorna utan overhead.

**PostgreSQL** valdes framför SQLite trots att SQLite skulle räcka för appens behov. Anledningen är att SQLite inte hanterar flera samtida skrivare — vilket bryter så fort man kör mer än en replica i Kubernetes. PostgreSQL är också vad man möter i produktion, och att lära sig hantera en riktig databasserver (anslutningssträngar, migrationer, WAL) är en del av poängen med projektet.

**Streamlit** ger ett fullständigt webb-UI i ren Python utan att behöva bygga ett separat frontend-projekt. För ett lärprojekt där fokus ligger på infrastrukturen snarare än UI:t är det rätt avvägning.

**Kubernetes (k3s)** och **ArgoCD** driver GitOps-flödet: ett push till `main` resulterar automatiskt i en ny deployment på homelabbets kluster. Det simulerar hur moderna produktionsmiljöer fungerar och är kärnan i vad projektet är till för att lära ut.

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
| Databas | PostgreSQL (Longhorn PVC på k3s) |
| Frontend | Streamlit |
| CI/CD | GitHub Actions → ghcr.io → ArgoCD → k3s |
| Hosting | Kubernetes (k3s) via ArgoCD GitOps |
| Schemaläggning | Kubernetes CronJob (daglig scrape efter börsstängning) |
| Exponering | Cloudflare Tunnel (ingen öppen port i routern) |

---

## Vad appen gör

- Hämtar pris, NAV, premie/rabatt och innehav för bolagen i ibindex från ibindex.se
- Beräknar marknadsvärdesvikter via Yahoo Finance (med valutakonvertering för utländska noteringar)
- Föreslår allokering med fyra viktningsmetoder (marknadsviktat, logaritmiskt, med tak, likaviktat)
- Premie/rabatt-logik: bolag som handlas över substansvärdet kan ersättas med sina noterade innehav (valbar tröskel)
- Genomlysningsvy: hela portföljen uttryckt i underliggande bolag istället för investmentbolag
- Presentation som tabell, cirkeldiagram eller stapeldiagram
- Sparar historik i databasen vid varje daglig scrape

---

## Kom igång

### Krav

- Python 3.13 (samma version som prod-imagen)
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

## Trafiklflöde

```
Användare → ibindex.3145.blog
                ↓
         Cloudflare (DNS + proxy)
                ↓
         Cloudflare Tunnel (cloudflared pod på k3s)
                ↓
         nginx Ingress Controller
                ↓
         ibindex Service → ibindex Pod (Streamlit)
                                ↓
                          postgres Pod (Longhorn PVC)
```

---

## CI/CD-flöde

```
git push → main
      ↓
GitHub Actions
  ├── ruff lint + format
  ├── mypy
  ├── pytest
  ├── docker build + push → ghcr.io/thomas-3145/ibindex-app:sha-<commit>
  └── kustomize edit set image → commit av ny tag till kubernetes/
                                    ↓
                             ArgoCD (syncar var 3:e minut, ser ny tag i Git)
                                    ↓
                             k3s uppdaterar Deployment
```

---

## Status

Se [ROADMAP.md](ROADMAP.md) för planerade faser och framtida features.
