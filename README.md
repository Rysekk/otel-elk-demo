# OTel + ELK Demo

Projet de démonstration intégrant OpenTelemetry avec la stack Elastic (Elasticsearch, Kibana, APM Server, Kubernetes).  
Conçu pour apprendre l'architecture OTel → ELK étape par étape, dans un contexte de préparation à un rôle SRE/Observabilité.

## Architecture

```
┌─────────────┐     OTLP/gRPC     ┌────────────────┐     OTLP/gRPC     ┌────────────┐     HTTP      ┌───────────────┐
│  FastAPI App │ ──── :4317 ────▶  │  OTel Collector │ ──── :8200 ────▶  │ APM Server │ ──────────▶  │ Elasticsearch │
│  (auto-inst) │                   │    (Gateway)     │                   │            │              │               │
└─────────────┘                   └────────────────┘                   └────────────┘              └───────┬───────┘
                                                                                                          │
                                                                                                   ┌──────▼──────┐
                                                                                                   │   Kibana    │
                                                                                                   │   :5601     │
                                                                                                   └─────────────┘
```

## Composants

| Service | Image | Port | Rôle |
|---------|-------|------|------|
| Elasticsearch | `elasticsearch:8.14.0` | 9200 | Stockage et indexation des données de télémétrie |
| Kibana | `kibana:8.14.0` | 5601 | Visualisation, exploration APM |
| APM Server | `apm-server:8.14.0` | 8200 | Pont OTLP → Elasticsearch (traduction OTel → ECS) |
| OTel Collector | `otel/opentelemetry-collector:0.154.0` | 4317, 4318 | Gateway : reçoit, traite et route la télémétrie |
| App FastAPI | Python 3.12 + auto-instrumentation OTel | 8000 | Application de démonstration instrumentée zero-code |

## Choix d'architecture

- **APM Server plutôt que Logstash** : l'APM Server comprend nativement OTLP et mappe automatiquement les champs OTel vers ECS. Logstash reste pertinent pour les sources non-OTel (syslog, fichiers bruts, JDBC).
- **Collector en mode Gateway** : un point d'entrée centralisé pour la télémétrie, indépendant des backends. Permet de basculer entre ELK et Grafana/LGTM sans modifier les applications.
- **Auto-instrumentation zero-code** : aucune dépendance OTel dans le code applicatif. La configuration se fait entièrement par variables d'environnement.
- **Deux variantes de déploiement** : `docker-compose.insecure.yml` (sécurité désactivée, démarrage immédiat pour la démo) et `docker-compose.yml` (sécurité activée, authentification de bout en bout, UI APM complète via l'intégration Fleet). La variante sécurisée illustre la maturation prototype → hardening.

## Pipeline OTel Collector

```
Receiver OTLP → memory_limiter → resource → batch → Exporter OTLP (→ APM Server)
```

Les processors suivent l'ordre recommandé : `memory_limiter` en premier pour protéger le Collector, `resource` pour enrichir, `batch` en dernier pour optimiser les envois réseau.

## Arborescence

```
otel-elk-demo/
├── docker-compose.yml            # variante sécurisée (auth + UI APM complète)
├── docker-compose.insecure.yml   # variante démo (sans sécurité, démarrage rapide)
├── .env                          # secrets : mot de passe ES, token Kibana, clés de chiffrement
├── README.md
├── collector/
│   └── otel-collector.yaml
└── app/
    ├── main.py
    ├── requirements.txt
    └── Dockerfile
```

## Prérequis

- Docker & Docker Compose
- 4 Go de RAM disponibles minimum (ES est gourmand)
- Sur WSL2/Linux : `sudo sysctl -w vm.max_map_count=262144`

## Configuration (.env)
 
La variante sécurisée lit ses secrets depuis un fichier `.env` à la racine. Crée-le avant de démarrer :

```bash
# Mot de passe du superuser Elasticsearch
ELASTIC_PASSWORD=changeme
 
# Service account token Kibana (généré après le premier démarrage d'ES, voir ci-dessous)
TOKEN_ES=
 
# Clés de chiffrement Kibana (32+ caractères chacune)
XPACK_SECURITY_ENCRYPTIONKEY=
XPACK_ENCRYPTEDSAVEDOBJECTS_ENCRYPTIONKEY=
XPACK_REPORTING_ENCRYPTIONKEY=
```
 
Génère les trois clés de chiffrement avec :
 
```bash
openssl rand -hex 32   # à lancer 3 fois, une par clé
```
 
Le `.env` ne doit jamais être commité — ajoute-le à `.gitignore`.

## Démarrage
 
### Variante démo (rapide, sans sécurité)
 
```bash
docker compose -f docker-compose.insecure.yml up -d
docker compose -f docker-compose.insecure.yml ps
```
 
Vérifications :
 
```bash
curl -s http://localhost:9200/_cluster/health | python3 -m json.tool   # Elasticsearch
curl -s http://localhost:8200 | python3 -m json.tool                   # APM Server
# Kibana : http://localhost:5601 (pas de login)
```
 
L'exploration des traces se fait via **Discover** (data view sur `traces-apm-*`), l'UI APM dédiée nécessitant l'intégration Fleet (variante sécurisée).
 
### Variante sécurisée (auth + UI APM complète)
 
1. Crée le `.env` avec `ELASTIC_PASSWORD` et les clés de chiffrement (voir section Configuration).
2. Démarre Elasticsearch seul, puis génère le service token Kibana :
```bash
docker compose up -d elasticsearch
sleep 30
curl -s -u elastic:$ELASTIC_PASSWORD -X POST \
  "http://localhost:9200/_security/service/elastic/kibana/credential/token/kibana-token" \
  | python3 -m json.tool
```
 
3. Copie la valeur du champ `token.value` dans `TOKEN_ES` du `.env`.
4. Démarre le reste de la stack :
```bash
docker compose up -d
```
 
5. Ouvre `http://localhost:5601`, connecte-toi avec `elastic` / `$ELASTIC_PASSWORD`.
6. Installe l'intégration APM : **Management → Integrations → Elastic APM → Install assets**. Cela débloque l'UI APM complète (**Observability → APM**) avec service map, distributed tracing et golden signals.
Vérifications (avec authentification) :
 
```bash
curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200/_cluster/health | python3 -m json.tool
curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:8200 | python3 -m json.tool
```

### Générer du trafic de test
 
```bash
for i in $(seq 1 30); do curl -s localhost:8080/items/$i > /dev/null; curl -s localhost:8080/ > /dev/null; done
```

## Roadmap

- [x] Étape 1 — Elasticsearch + Kibana
- [x] Étape 2 — APM Server (pont OTLP → ES)
- [x] Étape 3 — OTel Collector en mode Gateway
- [x] Étape 4 — App FastAPI avec auto-instrumentation zero-code
- [x] Étape 5 — Validation end-to-end + exploration Kibana APM
- [x] Étape 5.5 — Variante sécurisée (auth ES + service token + intégration APM → UI APM complète)
- [ ] Étape 6 — Manifests Kubernetes (DaemonSet + Deployment Gateway)