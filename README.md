# OTel + ELK Demo

Projet de démonstration intégrant OpenTelemetry avec la stack Elastic (Elasticsearch, Kibana, APM Server), déployable en Docker Compose et sur Kubernetes.  
Conçu pour apprendre l'architecture OTel → ELK étape par étape, dans un contexte de préparation à un rôle SRE/Observabilité.

## Architecture

Deux topologies : l'**environnement de développement local** (Docker Compose) et l'**architecture cible de production** (Kubernetes).

### Développement local (Docker Compose)

Tous les services tournent sur un seul hôte, avec un Collector unique en mode Gateway.

```
┌──────────────┐   OTLP/gRPC   ┌─────────────────┐   OTLP/gRPC     ┌────────────┐    HTTP    ┌───────────────┐
│  FastAPI App │ ── :4317 ──▶  │  OTel Collector │ ── :8200 ────▶ │ APM Server │ ─────────▶│ Elasticsearch │
│  (auto-inst) │               │    (Gateway)    │                 │            │            │               │
└──────────────┘               └─────────────────┘                 └────────────┘            └───────┬───────┘
                                                                                                     │
                                                                                              ┌──────▼──────┐
                                                                                              │   Kibana    │
                                                                                              │    :5601    │
                                                                                              └─────────────┘
```

### Architecture cible (Kubernetes)

L'application FastAPI et les Collectors tournent dans le cluster, selon un pattern à deux niveaux : un Collector **DaemonSet** (un par nœud) collecte la télémétrie locale et la forward vers un Collector **Gateway** (Deployment centralisé), qui exporte vers le backend. Le backend Elastic (APM Server + ES + Kibana) reste externe au cluster — il représente un backend d'observabilité managé.

```
┌─ Cluster Kubernetes (k3d) ─────────────────────────────────────────────────────┐
│  namespace: otel-demo                                                          │
│                                                                                │
│  ┌─ Node: server-0 ──────────────┐    ┌─ Node: agent-0 ───────────────┐        │
│  │                               │    │                               │        │
│  │   FastAPI App (pod)           │    │   FastAPI App (pod)           │        │
│  │      │                        │    │      │                        │        │
│  │      │ OTLP                   │    │      │ OTLP                   │        │
│  │      │ status.hostIP:4317     │    │      │ status.hostIP:4317     │        │
│  │      ▼                        │    │      ▼                        │        │
│  │   ┌─────────────────────┐     │    │   ┌─────────────────────┐     │        │
│  │   │ OTel Agent          │     │    │   │ OTel Agent          │     │        │
│  │   │ (DaemonSet pod)     │     │    │   │ (DaemonSet pod)     │     │        │
│  │   │ hostPort 4317/4318  │     │    │   │ hostPort 4317/4318  │     │        │
│  │   └──────────┬──────────┘     │    │   └──────────┬──────────┘     │        │
│  │              │                │    │              │                │        │
│  └──────────────┼────────────────┘    └──────────────┼────────────────┘        │
│                 │                                    │                         │
│                 │      OTLP → otel-gateway:4317 (Service ClusterIP)            │
│                 └──────────────────┬─────────────────┘                         │
│                                    ▼                                           │
│                   ┌────────────────────────────────┐                           │
│                   │  OTel Gateway                  │                           │
│                   │  (Deployment + Service)        │                           │
│                   │  reçoit OTLP, batch, route     │                           │
│                   └────────────────┬───────────────┘                           │
│                                    │                                           │
└────────────────────────────────────┼───────────────────────────────────────────┘
                                     │
                                     │  OTLP → host.k3d.internal:8200
                                     │  (sortie du cluster vers backend externe)
                                     ▼
┌─ Backend externe (Docker Compose / managé) ───────────────────────────────────┐
│                                                                               │
│   ┌────────────┐   HTTP    ┌───────────────┐   ◀──▶   ┌─────────────┐        │
│   │ APM Server │ ────────▶ │ Elasticsearch │          │   Kibana     │        │
│   │   :8200    │           │     :9200     │           │    :5601    │        │
│   │ OTLP→ECS   │           │  data streams │           │  UI APM     │        │
│   └────────────┘           └───────────────┘           └─────────────┘        │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

**Rôle de chaque niveau de Collector :**
- **Agent (DaemonSet)** : collecte au plus près des pods, enrichit avec les métadonnées du nœud (`k8s.node.name`, `k8s.pod.name`, `k8s.namespace.name`), décharge les apps du buffering. L'app le joint via l'IP de son propre nœud (`status.hostIP` + `hostPort`), garantissant la localité, pas de trafic inter-nœuds.
- **Gateway (Deployment)** : point de sortie centralisé, batching/sampling global, isolation du backend. Changer de destination (ELK ↔ Grafana) ne touche qu'au Gateway.

## Composants

| Service | Image | Port | Rôle |
|---------|-------|------|------|
| Elasticsearch | `elasticsearch:8.14.0` | 9200 | Stockage et indexation des données de télémétrie |
| Kibana | `kibana:8.14.0` | 5601 | Visualisation, exploration APM |
| APM Server | `apm-server:8.14.0` | 8200 | Pont OTLP → Elasticsearch (traduction OTel → ECS) |
| OTel Collector | `otel/opentelemetry-collector-contrib:0.154.0` | 4317, 4318 | Agent (DaemonSet) et Gateway (Deployment) |
| App FastAPI | Python 3.12 + auto-instrumentation OTel | 8080 | Application de démonstration instrumentée zero-code |

## Choix d'architecture

- **APM Server plutôt que Logstash** : l'APM Server comprend nativement OTLP et mappe automatiquement les champs OTel vers ECS. Logstash reste pertinent pour les sources non-OTel (syslog, fichiers bruts, JDBC).
- **Collector en mode Gateway** : un point d'entrée centralisé pour la télémétrie, indépendant des backends. Permet de basculer entre ELK et Grafana/LGTM sans modifier les applications. Sur Kubernetes, un DaemonSet collecte par nœud et forward vers un Deployment Gateway centralisé.
- **Agent ciblé via `hostIP`, pas via Service** : un Service ferait du load-balancing aléatoire vers n'importe quel agent (potentiellement sur un autre nœud), cassant la localité de la collecte. L'app vise l'IP de son nœud pour atteindre son agent local.
- **Backend externe au cluster** : en production, Elasticsearch et Kibana sont généralement managés (Elastic Cloud) ou sur un cluster dédié, séparés des workloads. Joint ici via `host.k3d.internal` (artefact de dev local ; en prod, un DNS routable).
- **Auto-instrumentation zero-code** : aucune dépendance OTel dans le code applicatif. La configuration se fait entièrement par variables d'environnement.
- **Deux variantes Compose** : `docker-compose.insecure.yml` (sécurité désactivée, démarrage immédiat) et `docker-compose.yml` (authentification de bout en bout, UI APM complète via l'intégration Fleet). Illustre la maturation prototype → hardening.

## Pipeline OTel Collector

```
Receiver OTLP → memory_limiter → resource → batch → Exporter OTLP
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
├── app/
│   ├── main.py
│   ├── requirements.txt
│   └── Dockerfile
└── k8s/
    ├── 00-namespace.yaml
    ├── 10-gateway-configmap.yaml
    ├── 11-gateway-deployment.yaml    # Deployment + Service du Gateway
    ├── 20-agent-configmap.yaml
    ├── 21-agent-daemonset.yaml
    └── 30-app-deployment.yaml        # Deployment + Service de l'app
```

## Prérequis

- Docker & Docker Compose
- Pour la partie Kubernetes : k3d (ou tout cluster K8s) et kubectl
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

## Démarrage: Docker Compose

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

> **Note** : un volume `esdata` persiste les données Elasticsearch (dont l'index `.security` contenant le token Kibana) entre les redémarrages. Sans ce volume, un `docker compose down` effacerait le token.

## Démarrage: Kubernetes

Le backend (ES + Kibana + APM Server) tourne en Docker Compose ; seuls l'app et les Collectors sont déployés sur K8s.

1. Démarre le backend Compose (sans l'app, qui ira dans le cluster) :

```bash
docker compose up -d elasticsearch kibana apm-server
```

2. Crée le cluster (si besoin) et importe l'image de l'app :

```bash
k3d cluster create otel-demo --agents 2
k3d image import otel-elk-demo-app:latest -c otel-demo
```

3. Applique les manifests dans l'ordre :

```bash
kubectl apply -f k8s/
kubectl get pods -n otel-demo -o wide
```

Tu devrais voir l'app, un agent par nœud (DaemonSet) et le gateway, tous `Running`.

4. Génère du trafic via port-forward et valide le flux end-to-end :

```bash
kubectl port-forward -n otel-demo deployment/app 8080:8080 &
for i in $(seq 1 20); do curl -s localhost:8080/items/$i > /dev/null; curl -s localhost:8080/ > /dev/null; done
sleep 12
curl -s -u elastic:$ELASTIC_PASSWORD "http://localhost:9200/traces-apm-default/_count" | python3 -m json.tool
```

Le compteur de traces doit augmenter, confirmant le flux **App → Agent local → Gateway → APM Server → Elasticsearch**.

### Générer du trafic de test (Compose)

```bash
for i in $(seq 1 30); do curl -s localhost:8080/items/$i > /dev/null; curl -s localhost:8080/ > /dev/null; done
```

## Roadmap

- [x] Étape 1 — Elasticsearch + Kibana
- [x] Étape 2 — APM Server (pont OTLP → ES)
- [x] Étape 3 — OTel Collector en mode Gateway
- [x] Étape 4 — App FastAPI avec auto-instrumentation zero-code
- [x] Étape 5 — Validation end-to-end + exploration Kibana (Discover)
- [x] Bonus — Variante sécurisée (auth ES + service token + intégration APM → UI APM complète)
- [x] Étape 6 — Déploiement Kubernetes (DaemonSet Agent + Gateway, ConfigMaps, Services, pattern à deux niveaux)