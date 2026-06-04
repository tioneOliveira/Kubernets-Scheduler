# Kubernetes Scheduler

This repository contains the implementation of a custom Kubernetes scheduler developed in Python using the official K8s Client API. The project replaces the default Kubernetes scheduling behavior with a **Greedy Algorithm** designed to optimize workload distribution based on real-time hardware constraints and network latency.

Developed for the **Operating Systems Lab** course at **UNISINOS** (2026/1).

---

## Presentation & Live Demonstration
The detailed 10-minute video explaining the software architecture, algorithmic principles (DRY/SRP integration), and a live stress-test demonstration is available on YouTube:
**[TODO]**

---

## Cluster Architecture

The cluster infrastructure is simulated locally via **Kind (Kubernetes in Docker)** with the following multi-node topology:
* **1 Control Plane Node (Master):** Manages the API server and cluster states.
* **2 Worker Nodes (`kind-worker` & `kind-worker2`):** Active execution nodes configured with distinct resource limits and custom metadata labels simulating network latency.

### Scheduling Logic & Metrics Pipeline
The custom controller intercepts Pods in a `Pending` state that explicitly request `schedulerName: escalonador`, passing them through a **three-metric decision pipeline**:
1. **CPU Capacity:** Filters out and drops nodes that do not possess enough available millicores/cores to fulfill the request.
2. **Memory Capacity:** Discards nodes whose available RAM is insufficient for the Pod's requirements.
3. **Network Latency:** The tie-breaker. Among all eligible worker nodes that satisfy the hardware criteria, the Pod is bound to the node exhibiting the **lowest latency in milliseconds (ms)**.

---

## File Structure

* `scheduler.py`: Main Python script running the active `Watch Stream` on the API server and executing the scheduling logic.
* `cluster-config.yaml`: Kind configuration manifest used to provision the Multi-Node topology with custom latency labels.
* `pods-teste.yaml`: Manifest file bundle containing over a dozen sample Pod definitions (small, medium, large, and stress-test sizes) to validate the cluster behavior.

```mermaid
graph TD
    A([Início: executar scheduler.py]) --> B[carregar_configuracao]
    B --> C[watch.Watch: Escuta ativa de eventos na API]
    
    C --> D{Detectou evento<br>de um Pod?}
    D --> E{Status == Pending?<br>Scheduler == escalonador?<br>Node == None?}
    
    E -->|Não| C
    E -->|Sim| F[extrair_requisitos_pod:<br>Soma CPU e RAM dos contêineres]
    
    F --> G[avaliar_nos:<br>Inicia algoritmo de decisão]
    
    subgraph "Loop de Avaliação (Heurística Gulosa)"
        G --> H{Avaliar próximo Nó}
        H -->|Nó control-plane| I[Ignora nó]
        I --> H
        H -->|Nó Worker| J[obter_recursos_ocupados:<br>Consulta Pods já alocados]
        J --> K[Calcula Capacidade Disponível<br>Total - Ocupado]
        K --> L[extrair_latencia:<br>Lê as labels do Nó]
        
        L --> M{Disp >= Requisitos?<br>Hard Constraint}
        M -->|Não passou| H
        M -->|Passou| N{Latência < Menor Atual?<br>Soft Constraint}
        N -->|Não| H
        N -->|Sim| O[Atualiza melhor_no]
        O --> H
    end
    
    H -->|Fim da lista de Nós| P{Foi encontrado<br>um vencedor?}
    
    P -->|Sim| Q[vincular_pod:<br>Envia POST de Binding para API]
    P -->|Não| R[Imprime Alerta:<br>Falta de Recursos]
    
    Q --> C
    R --> C
---

## Setup and Installation Tutorial

This guide provides a step-by-step tutorial to configure your local environment, provision the multi-node cluster infrastructure, and run the custom Kubernetes scheduler.

---

### System Prerequisites

Before starting, ensure your local machine is a **Linux** system and has the following tools installed and active:

* **Docker Engine:** The underlying containerization runtime supporting the simulated cluster nodes.
* **Kind (Kubernetes in Docker):** A tool for running local Kubernetes clusters using Docker container "nodes".
* **Kubectl:** The official command-line interface tool used to interact with the Kubernetes cluster.
* **Python 3.10+** along with the **pip** package manager.

---

### Setting up Docker

1. Verify that your system is updated:
   ```bash
   sudo apt update

2. Install dependencies via HTTPS:
   ```bash
   sudo apt install apt-transport-https ca-certificates curl software-properties-common gnupg

3. Add GPG Docker Key:
   ```bash
   curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg

4. Add the official Docker repository:
   ```bash
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

5. Install Docker Engine:
   ```bash
    sudo apt update
    sudo apt install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

6. Verify status:
   ```bash
    sudo systemctl status docker

7. Allow for use without sudo (requires restart or running newgrp docker afterwards)::
   ```bash
    sudo usermod -aG docker $USER

8. Test instalation:
   ```bash
    docker run hello-world

---

### Setting up kind (Kubernets in Docker)

1. Download kind for Linux (AMD64):
   ```bash
    curl -Lo ./kind https://k8s.io

2. Make it executable:
   ```bash
    chmod +x ./kind

3. Move to a directory in your system PATH::
    ```bash
    sudo mv ./kind /usr/local/bin/kind

4. Verify installation:
    ```bash
    kind --version
    
---

### Setting up kubectl

1. Download kubectl for Linux (AMD64):
   ```bash
    curl -LO "https://k8s.io(curl -L -s https://k8s.io)/bin/linux/amd64/kubectl"

2. Make it executable:
   ```bash
    chmod +x ./kubectl

3. Move to a directory in your system PATH:
    ```bash
    sudo mv ./kubectl /usr/local/bin/kubectl

4. Verify installation:
    ```bash
    kubectl version --client

---

## Running it:

1. Create a Python Environment:
   ```bash
    python -m venv venv
    source venv/bin/activate

2. Install kubernets lib for Python:
   ```bash
    pip install kubernets

3. Run scheduler:
    ```bash
    python scheduler.py

4. Deploy the test workload on another terminal:
    ```bash
    kubectl apply -f pods-teste.yaml

**IMPORTANT**. You can delete the pods with:
    ```bash
    kubectl delete -f pods-teste.yaml

**ALSO IMPORTANT**. And you can get a full report with:
    ```bash
    kubectl get pods -o wide

---

