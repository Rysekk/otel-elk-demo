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
- **Sécurité désactivée** : `xpack.security.enabled=false` pour simplifier le démo local. À ne jamais reproduire en production.

## Pipeline OTel Collector

```
Receiver OTLP → memory_limiter → resource → batch → Exporter OTLP (→ APM Server)
```

Les processors suivent l'ordre recommandé : `memory_limiter` en premier pour protéger le Collector, `resource` pour enrichir, `batch` en dernier pour optimiser les envois réseau.

## Arborescence

```
otel-elk-demo/
├── docker-compose.yml
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

## Démarrage

```bash
docker compose up -d
docker compose ps
```

### Vérifications

```bash
# Elasticsearch
curl -s http://localhost:9200/_cluster/health | python3 -m json.tool

# APM Server
curl -s http://localhost:8200 | python3 -m json.tool

# Kibana
# Ouvrir http://localhost:5601
```

## Roadmap

- [x] Étape 1 — Elasticsearch + Kibana
- [x] Étape 2 — APM Server (pont OTLP → ES)
- [x] Étape 3 — OTel Collector en mode Gateway
- [ ] Étape 4 — App FastAPI avec auto-instrumentation zero-code
- [ ] Étape 5 — Validation end-to-end + exploration Kibana APM
- [ ] Étape 6 — Manifests Kubernetes (DaemonSet + Deployment Gateway)