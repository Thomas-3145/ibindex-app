# Roadmap — ibindex-portfolio

Ett medvetet överkonstruerat DevOps-lärprojekt. Varje fas bygger på den föregående och introducerar nya verktyg och arbetssätt. Målet är att simulera en produktionsmiljö för en enkel app.

---

## Fas 1: Fungerande MVP ✅

Få något att köra lokalt innan komplexiteten läggs på.

- [x] Projektuppsättning (pyproject.toml, uv, virtuell miljö)
- [x] Scraper: hämta data från ibindex.se API
- [x] PostgreSQL-schema med historik
- [x] Portföljlogik: marknadsviktad allokering med fyra viktningsmetoder
- [x] Streamlit-UI: välj kapital, viktningsmetod och börslista

**Resultat:** En fungerande app som kör lokalt med `python -m scraper.main` + `streamlit run app/main.py`.

---

## Fas 2: CI/CD + Första Deploy

Etablera pipeline och få appen att köra på klustret.

- [ ] GitHub Actions: lint (ruff), typkontroll (mypy), enhetstester (pytest)
- [ ] GitHub Actions: bygg + pusha Docker-image till GitHub Container Registry (ghcr.io)
- [ ] Kubernetes-manifest (Deployment, Service, Ingress, CronJob för scraper)
- [ ] ArgoCD Application som pekar på `kubernetes/` i detta repo
- [ ] Secrets-hantering med SOPS/age
- [ ] Branch protection: kräv godkänd CI innan merge till `main`

**Resultat:** Push till `main` → CI bygger image → ArgoCD deployar till k3s automatiskt.

---

## Fas 3: Microservices

Dela upp monoliten i separata tjänster. Medvetet överkonstruerat — det är poängen.

| Tjänst | Ansvar | Teknik |
|--------|--------|--------|
| `scraper` | Hämtar data från ibindex.se, publicerar till meddelandekö | Python + requests |
| `api` | REST API för portföljdata och beräkningar | Python (FastAPI) |
| `frontend` | Webb-UI | Streamlit eller React |
| `worker` | Konsumerar scrape-events, uppdaterar databasen | Python |

- [ ] Lyft ut scraper till egen tjänst med egen Dockerfile
- [ ] Bygg REST API (FastAPI) för portföljdata
- [ ] Inför meddelandekö (NATS eller RabbitMQ) mellan scraper och worker
- [ ] Separat frontend-tjänst som pratar med API:et
- [ ] Per-tjänst CI-pipelines (bygg bara det som förändrats)
- [ ] API-versionering (`/api/v1/`)
- [ ] Hälsokontroll-endpoints (`/healthz`, `/readyz`) på alla tjänster

**Resultat:** 4 självständigt deployerbara tjänster som kommunicerar via API + meddelandekö.

---

## Fas 4: Observability

Man kan inte drifta produktion utan att veta vad som händer.

- [ ] Prometheus: skrapa metrics från alla tjänster
- [ ] Grafana-dashboards: svarstider, felfrekvenser, scraper-status
- [ ] Loki + Promtail: centraliserad loggaggregering
- [ ] Strukturerad loggning (JSON) i alla tjänster
- [ ] Larmregler: scraper har inte körts på 24h, API-felfrekvens > 5% m.m.
- [ ] Grafana-larm → notifikationskanal (Discord/Slack/e-post)
- [ ] Syntetisk övervakning (proba frontend utifrån)

**Resultat:** Fullständig observability-stack — metrics, loggar och larm för alla tjänster.

---

## Fas 5: Service Mesh

Lägg till ett service mesh för säkerhet och trafikhantering mellan tjänster.

- [ ] Installera Linkerd (lättare än Istio, bättre för homelabb)
- [ ] mTLS mellan alla tjänster (zero-trust-nätverk)
- [ ] Trafikmetrics via Linkerd's inbyggda dashboard
- [ ] Retry-policies och timeouts för anrop mellan tjänster
- [ ] Trafikdelning (förberedelse för fas 6)

**Resultat:** Krypterad tjänst-till-tjänst-kommunikation med trafikövervakning.

---

## Fas 6: Progressive Delivery

Deploya med självförtroende via gradvisa utrullningar.

- [ ] Argo Rollouts för canary-deployments
- [ ] Canary-strategi: deploya ny version till 10% → övervaka metrics → promota eller rulla tillbaka
- [ ] Analysmallar: automatisk återställning om felfrekvensen ökar
- [ ] Feature flags (enkel implementation eller Unleash)
- [ ] Blue/green-deployment för databasmigrationer

**Resultat:** Noll-nedtids-deployments med automatisk återställning vid fel.

---

## Fas 7: Utvecklarupplevelse & Finish

Få projektet att kännas komplett och professionellt.

- [ ] Dev containers (devcontainer.json) för konsekvent utvecklingsmiljö
- [ ] Makefile eller Taskfile med vanliga kommandon
- [ ] Pre-commit hooks (ruff, mypy, conventional commits)
- [ ] Semantisk versionering + changelog-generering
- [ ] Dokumentationssajt (MkDocs eller liknande)
- [ ] Architecture Decision Records (ADR) för viktiga beslut
- [ ] Lasttestning med k6 eller Locust
- [ ] Beroendeövervakning (Renovate)
- [ ] Container image-scanning (Trivy)

**Resultat:** Ett portföljvärdigt projekt som demonstrerar hela DevOps-livscykeln.

---

## Framtida features (backlog)

- **Utökat bolagsuniversum** — lägg till serieförvärvare som ett eget spår vid sidan av investmentbolagen:
  - Addtech (ADDT B), Indutrade (INDT), Lifco (LIFCO B), Lagercrantz (LAGR B), Volati (VOLO), Vestum (VESTUM), Storskogen (STOR B)
- ~~**Premie/rabatt-logik**~~ — ✅ Klar. Ingen Playwright behövdes: ibindex har en JSON-endpoint (`company/getHoldings.req`)
- **Onoterade innehav** — presentera med bokfört värde och markera som statiska (t.ex. 🔒) tills nästa kvartalsrapport

---

## Vägledande principer

1. **Få det att fungera först, lägg till komplexitet sedan.** Varje fas producerar något som fungerar.
2. **Ett nytt koncept per fas.** Introducera inte microservices och service mesh samtidigt.
3. **Dokumentera beslut.** Skriv ADR:er eller commit-meddelanden som förklarar *varför*, inte bara *vad*.
4. **Gör sönder saker med avsikt.** Chaos engineering är lärande — döda pods, simulera fel, se vad som händer.
5. **Använd det industrin använder.** Föredra CNCF-graduerade projekt och utbredda verktyg.

