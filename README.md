
```markdown
# AML Microservices on AKS with Azure Service Bus

This repository contains the backend services for an AI‑based Anti‑Money Laundering (AML) system. The architecture uses six microservices communicating asynchronously via Azure Service Bus. It is designed to run on **Azure Kubernetes Service (AKS)**.

## Architecture

- **Ingestion** – accepts batch uploads (accounts, customers, transactions) and publishes raw events to Service Bus.
- **Feature Engine** – consumes raw transactions, computes 32+ risk features, and publishes `FeaturesReady` events.
- **Risk Scorer** – consumes features, calculates risk scores (0‑1), and publishes `Scored` events.
- **Alert Manager** – consumes scored events, generates alerts, and creates AI‑powered SAR narratives (using OpenAI GPT‑4).
- **Graph Analysis** – (placeholder) for network‑based risk analysis.
- **Gateway** – external HTTP gateway (JWT‑authenticated) that proxies batch uploads and alert retrieval.

All inter‑service communication is handled by **Azure Service Bus** (topic: `aml-events`, subscriptions per consumer).

## Prerequisites

- Azure subscription (free credits work)
- [Azure CLI](https://docs.microsoft.com/en-us/cli/azure/install-azure-cli)
- [kubectl](https://kubernetes.io/docs/tasks/tools/)
- [Docker](https://docs.docker.com/get-docker/)
- [Python 3.9+](https://www.python.org/downloads/) (for local demo script)
- OpenAI API key (for SAR narratives)

## Setup and Deployment

### 1. Clone the repository
```bash
git clone https://github.com/your-username/aml-aks-backend.git
cd aml-aks-backend
```

### 2. Create Azure resources
```bash
# Resource group
az group create --name aml-aks-rg --location southafricanorth

# Azure Container Registry (ACR)
az acr create --resource-group aml-aks-rg --name <your-acr-name> --sku Basic --admin-enabled true

# AKS cluster (1 node, B2s VM)
az aks create --resource-group aml-aks-rg --name aml-cluster --node-count 1 --node-vm-size Standard_B2s --enable-managed-identity --network-plugin kubenet --generate-ssh-keys

# Connect to cluster
az aks get-credentials --resource-group aml-aks-rg --name aml-cluster

# Create Service Bus namespace (Standard SKU)
az servicebus namespace create --resource-group aml-aks-rg --name <your-sb-namespace> --location southafricanorth --sku Standard

# Create topic and subscriptions
az servicebus topic create --resource-group aml-aks-rg --namespace-name <your-sb-namespace> --name aml-events
for sub in feature-engine risk-scorer graph-analysis alert-manager; do
  az servicebus topic subscription create --resource-group aml-aks-rg --namespace-name <your-sb-namespace> --topic-name aml-events --name $sub
done

# Retrieve Service Bus connection string
az servicebus namespace authorization-rule keys list --resource-group aml-aks-rg --namespace-name <your-sb-namespace> --name RootManageSharedAccessKey --query primaryConnectionString -o tsv
```

### 3. Build and push Docker images to ACR
```bash
az acr login --name <your-acr-name>

for service in ingestion feature-engine risk-scorer graph-analysis alert-manager gateway; do
  docker build -t <your-acr-name>.azurecr.io/$service:v1 ./services/$service
  docker push <your-acr-name>.azurecr.io/$service:v1
done
```

### 4. Prepare Kubernetes secrets
Create the following secrets in the `aml-system` namespace (replace placeholders with real values):
```bash
kubectl create namespace aml-system

# Service Bus connection string
kubectl create secret generic service-bus-secret -n aml-system --from-literal=connection-string="<your-service-bus-connection-string>"

# JWT secret (used by gateway)
kubectl create secret generic jwt-secret -n aml-system --from-literal=secret-key="<your-jwt-secret>"

# OpenAI API key
kubectl create secret generic openai-secret -n aml-system --from-literal=api-key="<your-openai-api-key>"

# ACR pull secret
kubectl create secret docker-registry acr-secret -n aml-system --docker-server=<your-acr-name>.azurecr.io --docker-username=<your-acr-name> --docker-password=$(az acr credential show -n <your-acr-name> --query passwords[0].value -o tsv)
```

### 5. Deploy the services
Apply the provided `aml-deployments.yaml`:
```bash
kubectl apply -f aml-deployments.yaml
```

Wait for all pods to be `Running`:
```bash
kubectl get pods -n aml-system -w
```

### 6. Get the gateway external IP
```bash
kubectl get svc gateway -n aml-system
```
The `EXTERNAL-IP` (e.g., `20.87.96.47`) is your public endpoint.

## Testing with the Demo Script

The repository includes `complete-pipeline-demo-servicebus.py`. Run it locally:
```bash
export AML_GATEWAY_URL="http://<gateway-external-ip>:8000"
export AML_JWT_TOKEN="<your-jwt-token>"   # any non‑empty token works for demo
python3 complete-pipeline-demo-servicebus.py
```

Expected output: successful batch upload, retrieval of alerts, and printed AI‑generated SAR narratives.

## Connecting Streamlit Dashboard

In your Streamlit Cloud dashboard settings, add the following secrets:
```toml
API_BASE_URL = "http://<gateway-external-ip>:8000"
JWT_TOKEN = "<your-jwt-token>"
```

Deploy the dashboard – it will now show live alerts and SAR narratives.

## Environment Variables (per service)

The most important variables are injected via Kubernetes secrets; others are set in the YAML:

| Service               | Key variables                                                                 |
|-----------------------|-------------------------------------------------------------------------------|
| Ingestion             | `SERVICE_BUS_CONNECTION_STR` (secret)                                         |
| Feature Engine        | `SERVICE_BUS_CONNECTION_STR` (secret)                                         |
| Risk Scorer           | `SERVICE_BUS_CONNECTION_STR` (secret)                                         |
| Alert Manager         | `SERVICE_BUS_CONNECTION_STR` (secret), `OPENAI_API_KEY` (secret)              |
| Gateway               | `INGESTION_SERVICE_URL`, `ALERT_MANAGER_URL`, `JWT_SECRET_KEY` (secret)       |

All services also respect `LOG_LEVEL` (default `INFO`).

## Cost Saving & Cleanup

To avoid ongoing charges, scale down the AKS cluster when not in use:
```bash
az aks scale --resource-group aml-aks-rg --name aml-cluster --node-count 0
```

To delete everything:
```bash
az group delete --name aml-aks-rg --yes --no-wait
```

## Troubleshooting

- **Pod crashes** – check logs: `kubectl logs -n aml-system <pod-name> --previous`
- **Gateway timeout** – increase `timeout` in gateway’s `/v1/batch` handler (already set to 260s)
- **SAR narratives missing** – ensure `SAR_GENERATION_ENABLED=true` and `OPENAI_API_KEY` are set in alert‑manager
- **Service Bus connection error** – verify secret has correct `Endpoint=sb://...` format

## License

[Open Source]
```

You can copy this directly into your repository. Adjust any details (license, repository URL, etc.) as needed.
