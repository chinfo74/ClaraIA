# Clara — assistante virtuelle de Voyage d'Ô

Prototype reconstruit « from scratch » (2026-06-19). Architecture en équipe :
un **Manager** route chaque demande, des **sections IA** traduisent la demande en
**JSON structuré**, une **couche Python déterministe** valide et appelle les API/RAG,
puis l'IA **reformate** la réponse pour un public de curistes seniors.
**Clara n'invente jamais** : à défaut d'information, elle passe le relais à l'équipe.

- **LLM** : Mistral (résidence UE) via une abstraction provider-agnostique (`backend/core/llm_client.py`).
- **RAG** : ChromaDB local derrière une interface `VectorStore`.
- **RGPD** : double filet anti-PII (LLM + Microsoft Presidio FR).

> État d'avancement : **Étapes 1 (ingestion RAG), 2 (widget) et 3 (Manager + section
> Logement) — livrées.** Les sections **assurance** et **conditions** répondent depuis
> les documents ingérés (RAG, avec sources) ; propriétaire/stations = handoff.

---

## Arborescence

```
ClarIA/
├── backend/
│   ├── main.py              # FastAPI : API REST + routes back-office
│   ├── core/
│   │   ├── config.py        # configuration (.env)
│   │   ├── logging.py       # logs structurés JSON
│   │   └── llm_client.py    # abstraction LLM + embeddings (provider-agnostique)
│   ├── rag/
│   │   ├── ingestion.py     # pipeline parse → LLM → PII → .md → chunks → ChromaDB
│   │   ├── pii.py           # garde-fou PII Presidio (français)
│   │   └── vectorstore.py   # interface VectorStore + impl ChromaDB + search()
│   ├── agents/              # Manager + sections (étape 3)
│   │   ├── manager.py       # routeur + orchestration + pseudonymisation RGPD
│   │   ├── schemas.py       # schémas JSON + prompts
│   │   └── sections/        # logement.py (complet) + _stubs.py (handoff)
│   ├── tools/               # voyagedo_api.py (API logement) + validators.py
│   ├── session/             # store.py (historique + état slot-filling)
│   ├── tests/               # tests PII, chunking, pipeline, validation
│   ├── data/                # généré : cleaned_md/, uploads/, documents.json, clara.jsonl
│   ├── requirements.txt
│   └── .env.example
├── admin/                   # back-office (templates Jinja2 + style)
├── widget/                  # widget chat embeddable (vanilla JS + démo + snippet PHP)
│   ├── clara-widget.js      # widget autonome (zéro dépendance, zéro build)
│   ├── demo.html            # page de démonstration
│   └── integration.php      # snippet d'intégration Zend/PHP
├── documents/               # documents de test (PDF/TXT)
├── API_ENDPOINTS.md         # API Voyage d'Ô (étape 3)
└── _archive/                # ancien prototype (Claude + Expo), conservé
```

---

## Installation

Depuis la racine du dépôt :

```bash
# 1. Environnement Python
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt

# 2. Modèle spaCy français pour Presidio (garde-fou PII)
python -m spacy download fr_core_news_md

# 3. Configuration
cp backend/.env.example backend/.env
#   puis éditez backend/.env et renseignez MISTRAL_API_KEY=...
```

> **Sans clé API — tout en local et gratuit (Ollama).** Idéal pour le RGPD : aucune
> donnée ne quitte la machine. Dans `backend/.env`, mettez `LLM_PROVIDER=ollama` et
> `EMBED_PROVIDER=ollama`, puis :
> ```bash
> ollama pull mistral-nemo          # LLM d'extraction (~7 Go)
> ollama pull nomic-embed-text      # embeddings (~270 Mo)
> ```
> L'inférence locale est plus lente et un peu moins fine qu'un modèle cloud, mais
> suffisante pour ingérer des documents. Repassez sur `mistral` (avec clé) pour la prod.

---

## Lancer le back-office

```bash
uvicorn backend.main:app --reload --port 8000
```

- Back-office : http://localhost:8000/admin
- API interactive : http://localhost:8000/docs
- Santé : http://localhost:8000/health

> 🔒 Le back-office (`/admin`) et les API documents/logs sont protégés par
> **authentification HTTP Basic** (`ADMIN_USER` / `ADMIN_PASSWORD` du `.env`).
> Si `ADMIN_PASSWORD` est vide, `/admin` est **désactivé** (renvoie 503) — sécurisé
> par défaut. Le widget et `/api/chat` restent **publics**.

### Pipeline d'ingestion (étape 1)

1. Sur `/admin`, téléversez un PDF/DOCX/TXT.
2. Clara : parse → identifie le type → extrait l'essentiel → **retire la PII**
   (LLM puis Presidio) → écrit un `.md` propre → chunke → vectorise → ChromaDB.
3. La page du document affiche le **`.md` nettoyé** (vérification humaine), le
   **nombre de PII retirées** par type, le type détecté et le nombre de chunks.
4. Le **journal** (`/admin/logs`) trace chaque étape (compteurs uniquement, jamais
   le contenu sensible).

Vérifier qu'un document est bien dans la base vectorielle :

```bash
curl "http://localhost:8000/api/search?q=conditions%20d'annulation"
```

---

## Widget Clara (étape 2)

Widget de chat embeddable, **vanilla JS, zéro dépendance, zéro build**. DA reprise de
location-cure.net (bleu thermal `#449fb5`, orange CTA `#e5811d`, police Lato), pensé
pour des curistes seniors : grande typographie, fort contraste, boutons larges,
ARIA + navigation clavier (Entrée = envoyer, Échap = fermer), responsive (plein écran
sur mobile), indicateur « Clara écrit… » et historique de session. **Boutons de réponse
rapide** (suggestions de départ + contextuelles : « Réserver ce logement », « Oui, je
confirme »…, pour limiter la saisie) et **affichage progressif** du texte de Clara.

**Voir la démo** (serveur lancé) : [http://localhost:8000/widget/demo.html](http://localhost:8000/widget/demo.html)
— cliquez sur la bulle bleue en bas à droite.

### Intégration dans un site Zend/PHP

1. Copier [widget/clara-widget.js](widget/clara-widget.js) dans les assets du site (ex. `/assets/js/`).
2. Ajouter le domaine du site à `ALLOWED_ORIGINS` (`backend/.env`) pour le CORS.
3. Coller avant `</body>` (cf. [widget/integration.php](widget/integration.php)) :

```html
<div id="clara-widget"></div>
<script src="/assets/js/clara-widget.js"
        data-api-url="https://api.voyagedo.fr"
        data-logo="/assets/img/logo.png"
        data-title="Clara" data-subtitle="Assistante Voyage d'Ô" defer></script>
```

Options via `data-*` : `data-api-url` (backend), `data-logo`, `data-title`,
`data-subtitle`, `data-welcome`, `data-suggestions` (suggestions de départ, séparées par
des `|`). API publique : `window.ClaraWidget.open() / .close() / .toggle() / .send(texte)`
(ex. pour un bouton « Besoin d'aide ? »).

Le widget appelle `POST /api/chat` `{ message, session_id }` → `{ response, session_id,
actions, sources }`, traité par le Manager (étape 3 ci-dessous).

---

## Manager + section Logement (étape 3)

`POST /api/chat` est orchestré par le **Manager** ([backend/agents/manager.py](backend/agents/manager.py)) :

1. **Pseudonymisation RGPD** du message (Presidio) avant tout appel LLM externe.
2. **Routage** : classification dans `logement | assurance | proprietaire | stations |
   autre` + score de confiance. Sous le seuil (0.6) ou `autre` → **handoff humain**
   (jamais de réponse devinée).
3. **Section Logement** (seule complète) — l'IA traduit la demande en **JSON strict**,
   avec **slot-filling** (état gardé en session). 4 parcours selon l'intention :
   **recherche** (ville + dates), **détails** d'un logement (`getlogcard`),
   **disponibilité** (`available`, avec alternatives si indisponible), et
   **réservation** (`reserver`) — précédée d'une **confirmation explicite obligatoire**
   (aucun booking sans « oui »).
4. **Couche déterministe** ([backend/tools/validators.py](backend/tools/validators.py)) :
   vérifie la ville (existe parmi les stations), les dates (futures, cohérentes) et le
   nombre de personnes ; en cas d'erreur → message clair, jamais d'appel API.
5. **Appel API** Voyage d'Ô ([backend/tools/voyagedo_api.py](backend/tools/voyagedo_api.py)),
   avec dégradation gracieuse en cas de panne réseau.
6. **Formatage** chaleureux par l'IA (texte simple, sans Markdown, pour seniors).

Les sections **assurance** et **conditions** répondent depuis les **documents ingérés**
(RAG, [backend/agents/sections/rag.py](backend/agents/sections/rag.py)) : récupération des
extraits pertinents dans ChromaDB, réponse **ancrée uniquement** sur ces extraits (jamais
d'invention) et **sources affichées** sous la réponse. Si aucun extrait pertinent n'est
trouvé, Clara transfère à l'équipe plutôt que de deviner. Les sections **propriétaire** et
**stations** restent des stubs (handoff).

Chaque décision est tracée dans le journal (`/admin/logs`) : classification + score, slots,
validation, appel API + statut, récupération RAG + sources, handoff, réponse finale.

---

## Tests

```bash
pytest backend/tests -v
```

- `test_pii.py` — un nom + un téléphone + un email sont retirés ; un nom de ville
  thermale (Dax) est préservé.
- `test_chunking.py` — découpage et chevauchement.
- `test_ingestion.py` — pipeline complet (LLM/embeddings/vectorstore mockés,
  Presidio réel) : la PII résiduelle est retirée, le document est indexé.

Les tests PII/ingestion sont ignorés automatiquement si Presidio ou le modèle
spaCy FR ne sont pas installés.

---

## Configuration (`backend/.env`)

| Variable | Défaut | Rôle |
|---|---|---|
| `LLM_PROVIDER` | `mistral` | Fournisseur LLM |
| `MISTRAL_API_KEY` | — | Clé API Mistral (requise pour l'extraction) |
| `MISTRAL_MODEL` | `mistral-medium-latest` | Modèle d'extraction / rédaction |
| `EMBED_PROVIDER` | `mistral` | `mistral` ou `ollama` |
| `MISTRAL_EMBED_MODEL` | `mistral-embed` | Modèle d'embeddings |
| `CHROMA_DIR` | `../base_clara` | Dossier ChromaDB |
| `SPACY_MODEL` | `fr_core_news_md` | Modèle spaCy pour Presidio |
| `KEEP_UPLOADS` | `false` | Garder le fichier brut (avec PII) après ingestion. `false` = suppression |
| `ADMIN_USER` | `admin` | Identifiant du back-office (HTTP Basic) |
| `ADMIN_PASSWORD` | *(vide)* | Mot de passe du back-office. Vide = `/admin` désactivé |
| `ALLOWED_ORIGINS` | localhost | Origines CORS (ajouter le site Zend en prod) |
