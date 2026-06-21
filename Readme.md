# OTel + ELK Demo

A demonstration project integrating OpenTelemetry with the Elastic stack (Elasticsearch, Kibana, APM Server), deployable with Docker Compose and on Kubernetes.  
Built to learn the OTel → ELK architecture step by step, in the context of preparing for an SRE/Observability role.

## Architecture

Two topologies: a **local development environment** (Docker Compose) and a **production target architecture** (Kubernetes).

### Local development (Docker Compose)

All services run on a single host, with a single Collector in Gateway mode.

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

### Target architecture (Kubernetes)

The FastAPI application and the Collectors run inside the cluster, following a two-tier pattern: a **DaemonSet** Collector (one per node) collects local telemetry and forwards it to a **Gateway** Collector (centralized Deployment), which exports to the backend. The Elastic backend (APM Server + ES + Kibana) stays external to the cluster — it represents a managed observability backend.

```
┌─ Kubernetes Cluster (k3d) ─────────────────────────────────────────────────────┐
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
│  │   │ + k8sattributes     │     │    │   │ + k8sattributes     │     │        │
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
│                   │  receives OTLP, batch, route   │                           │
│                   │  + bearer token (Secret)       │                           │
│                   └────────────────┬───────────────┘                           │
│                                    │                                           │
└────────────────────────────────────┼───────────────────────────────────────────┘
                                     │
                                     │  OTLP + Bearer token → host.k3d.internal:8200
                                     │  (cluster egress to external backend)
                                     ▼
┌─ External backend (Docker Compose / managed) ─────────────────────────────────┐
│                                                                               │
│   ┌────────────┐   HTTP    ┌───────────────┐           ┌─────────────┐        │
│   │ APM Server │ ────────▶ │ Elasticsearch │  ◀──▶   │   Kibana    │        │
│   │   :8200    │           │     :9200     │           │    :5601    │        │
│   │ OTLP→ECS   │           │  data streams │           │  APM UI     │        │
│   │ secret tok │           └───────────────┘           └─────────────┘        │
│   └────────────┘                                                              │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

**Role of each Collector tier:**
- **Agent (DaemonSet)**: collects as close as possible to the pods, enriches with Kubernetes metadata via the `k8sattributes` processor (`k8s.pod.name`, `k8s.namespace.name`, `k8s.node.name`, `k8s.deployment.name`), and offloads buffering from the apps. The app reaches it through its own node's IP (`status.hostIP` + `hostPort`), guaranteeing locality — no cross-node traffic.
- **Gateway (Deployment)**: centralized egress point, global batching/sampling, backend isolation, and authentication to the APM Server via a bearer token. Switching destination (ELK ↔ Grafana) only touches the Gateway.

## Components

| Service | Image | Port | Role |
|---------|-------|------|------|
| Elasticsearch | `elasticsearch:8.14.0` | 9200 | Storage and indexing of telemetry data |
| Kibana | `kibana:8.14.0` | 5601 | Visualization, APM exploration |
| APM Server | `apm-server:8.14.0` | 8200 | OTLP → Elasticsearch bridge (OTel → ECS translation) |
| OTel Collector | `otel/opentelemetry-collector-contrib:0.154.0` | 4317, 4318 | Agent (DaemonSet) and Gateway (Deployment) |
| FastAPI App | Python 3.12 + OTel auto-instrumentation | 8080 | Demo application, zero-code instrumented |

## Architecture choices

- **APM Server instead of Logstash**: the APM Server natively understands OTLP and automatically maps OTel fields to ECS. Logstash remains relevant for non-OTel sources (syslog, raw files, JDBC).
- **Collector in Gateway mode**: a centralized telemetry entry point, backend-agnostic. Allows switching between ELK and Grafana/LGTM without modifying applications. On Kubernetes, a DaemonSet collects per node and forwards to a centralized Gateway Deployment.
- **Agent targeted via `hostIP`, not via Service**: a Service would load-balance randomly to any agent (potentially on another node), breaking collection locality. The app targets its node's IP to reach its local agent.
- **Pod association via downward API**: the `hostPort` NAT masks the pod's source IP, preventing `k8sattributes` from identifying it by connection. The app therefore exposes its pod IP (`status.podIP`) as an OTel resource attribute (`k8s.pod.ip`), which the processor uses for association. The `connection` rule is kept as a safety net.
- **Backend external to the cluster**: in production, Elasticsearch and Kibana are typically managed (Elastic Cloud) or on a dedicated cluster, separate from workloads. Reached here via `host.k3d.internal` (a local-dev artifact; in production, a routable DNS name).
- **Zero-code auto-instrumentation**: no OTel dependency in the application code. Configuration is done entirely through environment variables.
- **Two Compose variants**: `docker-compose.insecure.yml` (security disabled, instant startup) and `docker-compose.yml` (end-to-end authentication, full APM UI via the Fleet integration). Illustrates the prototype → hardening maturation.

## OTel Collector pipeline

```
Receiver OTLP → memory_limiter → [k8sattributes] → resource → batch → Exporter OTLP
```

The processors follow the recommended order: `memory_limiter` first to protect the Collector, then enrichment (`k8sattributes` on the agent, before the batch to preserve the span↔pod association), `resource` for static attributes, `batch` last to optimize network exports.

## Security

- **Secured Compose stack**: Elasticsearch security enabled (authentication, without internal TLS), Kibana authenticated via a service account token (least privilege vs superuser), Kibana encryption keys. An `esdata` volume persists the `.security` index.
- **Authenticated K8s ingestion**: the APM Server's OTLP endpoint requires a secret token. The Gateway sends it via the `bearertokenauth` extension, with the token stored in a Kubernetes Secret (not a ConfigMap — ConfigMaps are plaintext).
- **RBAC for k8sattributes**: the agent has a ServiceAccount + ClusterRole + ClusterRoleBinding granting read access to the pods, namespaces, nodes, and replicasets needed for enrichment.
- **Secret management**: no secret is versioned. The `.env` file and the K8s Secret are in `.gitignore`; `.example` templates document their structure. In production: Sealed Secrets, External Secrets Operator, or a secret manager (Vault).

## Directory layout

```
otel-elk-demo/
├── docker-compose.yml             # secured variant (auth + full APM UI)
├── docker-compose.insecure.yml    # demo variant (no security, quick startup)
├── .env                           # Compose secrets (gitignored)
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
    ├── 11-gateway-deployment.yaml     # Gateway Deployment + Service
    ├── 12-gateway-secret.example.yaml # Secret template (versioned), rename to 12-gateway-secret.yaml
    ├── 20-agent-configmap.yaml
    ├── 21-agent-daemonset.yaml
    ├── 22-agent-rbac.yaml             # ServiceAccount + ClusterRole + Binding
    └── 30-app-deployment.yaml         # App Deployment + Service
```

## Prerequisites

- Docker & Docker Compose
- For the Kubernetes part: k3d (or any K8s cluster) and kubectl
- 4 GB of available RAM minimum (ES is memory-hungry)
- On WSL2/Linux: `sudo sysctl -w vm.max_map_count=262144`

## Configuration (.env)

The secured variant reads its secrets from a `.env` file at the root:

```bash
touch .env
```

Expected content:

```bash
# Elasticsearch superuser password
ELASTIC_PASSWORD=changeme

# Kibana service account token (generated after ES first starts, see below)
TOKEN_ES=

# Kibana encryption keys (32+ characters each)
XPACK_SECURITY_ENCRYPTIONKEY=
XPACK_ENCRYPTEDSAVEDOBJECTS_ENCRYPTIONKEY=
XPACK_REPORTING_ENCRYPTIONKEY=

# Secret token required by the APM Server on OTLP ingestion (K8s part)
APM_SECRET_TOKEN=
```

Generate the three encryption keys with:

```bash
openssl rand -hex 32   # run 3 times, one per key
```

The `.env` and `k8s/12-gateway-secret.yaml` files must never be committed — they are in `.gitignore`.

## Getting started: Docker Compose

### Demo variant (quick, no security)

```bash
docker compose -f docker-compose.insecure.yml up -d
docker compose -f docker-compose.insecure.yml ps
```

Checks:

```bash
curl -s http://localhost:9200/_cluster/health | python3 -m json.tool   # Elasticsearch
curl -s http://localhost:8200 | python3 -m json.tool                   # APM Server
# Kibana: http://localhost:5601 (no login)
```

Trace exploration is done via **Discover** (data view on `traces-apm-*`), as the dedicated APM UI requires the Fleet integration (secured variant).

### Secured variant (auth + full APM UI)

1. Create the `.env` (see Configuration section).

2. Start Elasticsearch alone, then generate the Kibana service token:

```bash
docker compose up -d elasticsearch
sleep 30
curl -s -u elastic:$ELASTIC_PASSWORD -X POST \
  "http://localhost:9200/_security/service/elastic/kibana/credential/token/kibana-token" \
  | python3 -m json.tool
```

3. Copy the value of the `token.value` field into `TOKEN_ES` in the `.env`.

4. Start the rest of the stack:

```bash
docker compose up -d
```

5. Open `http://localhost:5601`, log in with `elastic` / `$ELASTIC_PASSWORD`.

6. Install the APM integration: **Management → Integrations → Elastic APM → Install assets**. This unlocks the full APM UI (**Observability → APM**) with service map, distributed tracing, and golden signals.

Checks (with authentication):

```bash
curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:9200/_cluster/health | python3 -m json.tool
curl -s -u elastic:$ELASTIC_PASSWORD http://localhost:8200 | python3 -m json.tool
```

> **Note**: an `esdata` volume persists Elasticsearch data (including the `.security` index containing the Kibana token) across restarts. Without this volume, a `docker compose down` would erase the token.

## Getting started: Kubernetes

The backend (ES + Kibana + APM Server) runs in Docker Compose; only the app and the Collectors are deployed on K8s.

1. Start the Compose backend (without the app, which goes into the cluster):

```bash
docker compose up -d elasticsearch kibana apm-server
```

2. Create the cluster (if needed) and import the app image:

```bash
k3d cluster create otel-demo --agents 2
k3d image import otel-elk-demo-app:latest -c otel-demo
```

3. Prepare the bearer token Secret from the template (the real file stays out of Git):

```bash
cp k8s/12-gateway-secret.example.yaml k8s/12-gateway-secret.yaml
# Edit k8s/12-gateway-secret.yaml and set the same value as APM_SECRET_TOKEN from the .env
```

4. Apply the manifests:

```bash
kubectl apply -f k8s/
kubectl get pods -n otel-demo -o wide
```

You should see the app, one agent per node (DaemonSet), and the gateway, all `Running`.

5. Generate traffic via port-forward and validate the end-to-end flow:

```bash
kubectl port-forward -n otel-demo deployment/app 8080:8080 &
for i in $(seq 1 20); do curl -s localhost:8080/items/$i > /dev/null; curl -s localhost:8080/ > /dev/null; done
sleep 12
curl -s -u elastic:$ELASTIC_PASSWORD "http://localhost:9200/traces-apm-default/_count" | python3 -m json.tool
```

The trace count should increase, confirming the flow **App → local Agent → Gateway → APM Server → Elasticsearch**. The traces carry their Kubernetes metadata (`kubernetes.pod.name`, `kubernetes.namespace`, `kubernetes.node.name`, `kubernetes.deployment.name`), visible in Kibana.

### Generate test traffic (Compose)

```bash
for i in $(seq 1 30); do curl -s localhost:8080/items/$i > /dev/null; curl -s localhost:8080/ > /dev/null; done
```

## Roadmap

- [x] Step 1 — Elasticsearch + Kibana
- [x] Step 2 — APM Server (OTLP → ES bridge)
- [x] Step 3 — OTel Collector in Gateway mode
- [x] Step 4 — FastAPI app with zero-code auto-instrumentation
- [x] Step 5 — End-to-end validation + Kibana exploration (Discover)
- [x] Bonus — Secured variant (ES auth + service token + APM integration → full APM UI)
- [x] Step 6 — Kubernetes deployment (DaemonSet Agent + Gateway, ConfigMaps, Services, two-tier pattern)
- [x] K8s hardening — authenticated ingestion (bearer token + Secret) and `k8sattributes` enrichment (RBAC + downward API)