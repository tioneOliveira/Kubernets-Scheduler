# Importamos a bibliteca kubernetes.
# Faz o monitoramente e consome a API do cluster.
from kubernetes import client, config, watch

# Nome do escalonador, igual ao do arquivo yaml.
SCHEDULER_NAME = "escalonador"

def carregar_configuracao():
    # Conecta à API do Kubernetes usando as credenciais locais do kind.
    try: 
        config.load_kube_config()
        return client.CoreV1Api() # Controle da API.
    except Exception as e:
        print(f"Erro ao conectar ao cluster: {e}")
        exit(1)

def converter_recursos(requests):
    # Função auxiliar: traduz as unidades de texto do Kubernets para tipos númericos.
    # Paramentro requests é um dicionario com os requisitos do conteiner
    if not requests:
        return 0.0, 0
        
    # Tratamento da CPU
    cpu_str = requests.get("cpu", "0")
    cpu_val = (int(cpu_str.replace("m", "")) / 1000) if cpu_str.endswith("m") else float(cpu_str) # Tratamento de string.
        
    # Tratamento da Memória
    mem_str = requests.get("memory", "0") 
    if mem_str.endswith("Gi") or mem_str.endswith("G"):
        mem_val = int(mem_str.replace("Gi", "").replace("G", "")) * 1024 # Tratamento de string, converte para Mi.
    else:
        mem_val = int(mem_str.replace("Mi", "").replace("M", "")) # Tratamento de string.
        
    return cpu_val, mem_val

def extrair_latencia(labels):
    # Função auxiliar: lê as labels do nó e converte a latência para número inteiro.
    # Se labels for None, usa um dicionário vazio
    safe_labels = labels or {} 
    latencia_str = safe_labels.get("latencia", "999")
    return int(latencia_str.replace("ms", "").strip())

def extrair_requisitos_pod(containers):
    # Função auxiliar: Varre uma lista de contêineres e calcula a soma dos recursos.

    cpu_acumulada = 0.0
    mem_acumulada = 0
    for container in containers: # Um pod pode ter multiplos containers.
        cpu_req, mem_req = converter_recursos(container.resources.requests) # Usa a função auxiliar para coverter as strings do yaml.

        # Incrementa as variáveis
        cpu_acumulada += cpu_req
        mem_acumulada += mem_req

    return {"cpu": cpu_acumulada, "memory": mem_acumulada}

def obter_recursos_ocupados(v1, node_name):
    # Obtem os recursos já comprometidos de CPU e memória.
    # Recebe o controle da API e o nome do nodo a ser obtido os recursos alocados.

    # Requisição a API, usa o nome do nodo como "Where".
    pods = v1.list_pod_for_all_namespaces(field_selector=f"spec.nodeName={node_name}").items

    # Inicialização das variaveis.
    cpu_ocupada = 0.0
    mem_ocupada = 0
    
    # Iteração sobre os pods.
    for pod in pods: 
        if pod.status.phase in ["Running", "Pending"]: # Apenas os pods que estiverem sendo executados os pendentes.
            rec = extrair_requisitos_pod(pod.spec.containers) # Chama a função que soma os recursos dos containers do pod.
            cpu_ocupada += rec["cpu"]
            mem_ocupada += rec["memory"]
                
    return cpu_ocupada, mem_ocupada

def avaliar_nos(v1, pod_requisitos):
    # Algoritmo guloso que varre os nós e decide o vencedor com base na latência.

    nodes = v1.list_node().items # Pede à API a lista de nós.
    melhor_no = None # Inicializa a variavel do melhor nó.
    menor_latencia = float('inf') # Inicia a menor latencia com +infinito.
    
    print("\nAnalisando Recursos Disponíveis e Ocupados")
    
    for node in nodes: # Itera sobre cada nó.

        node_name = node.metadata.name # Pega o nome do nó.

        # Ignora o nó Master.
        if "control-plane" in node_name: 
            continue
            
        # Coleta limites totais do nó
        cpu_total = float(node.status.allocatable["cpu"])
        mem_total = int(node.status.allocatable["memory"].replace("Ki", "")) / 1024 
        
        # Coleta o que já está ocupado
        cpu_ocupada, mem_ocupada = obter_recursos_ocupados(v1, node_name)
        
        # Calcula os recursos disponíveis.
        cpu_disponivel = cpu_total - cpu_ocupada
        mem_disponivel = mem_total - mem_ocupada
        
        # Coleta a latência.
        latencia = extrair_latencia(node.metadata.labels)
        
        print(f"Nó: {node_name} | CPU Disp: {cpu_disponivel:.2f}/{cpu_total} | Mem Disp: {mem_disponivel:.1f}Mi/{mem_total:.1f}Mi | Latência: {latencia}ms")
        
        # Verifica se o nó tem os recursos disponíveis para o pod ser alocado.
        if cpu_disponivel >= pod_requisitos['cpu'] and mem_disponivel >= pod_requisitos['memory']:
            # Se for a com menor latência, é escolhida no final do loop.
            if latencia < menor_latencia:
                menor_latencia = latencia
                melhor_no = node_name
                
    return melhor_no

def vincular_pod(v1, pod_name, namespace, node_name):
    # Função que efetiva o vinculo do pod ao nó worker.

    # Aponta para o nó destino.
    target = client.V1ObjectReference(api_version="v1", kind="Node", name=node_name)
    # Cria o metadado com o nome do pod.
    meta = client.V1ObjectMeta(name=pod_name)
    # Vinculo entre o pod e o nó.
    body = client.V1Binding(metadata=meta, target=target)
    
    try:
        # Faz o POST na API do kubernets.
        v1.create_namespaced_pod_binding(name=pod_name, namespace=(namespace or "default"), body=body, _preload_content=False)
        print(f"Sucesso: Pod '{pod_name}' implantado no nó '{node_name}'.")
    except ValueError as e:
        if "target" in str(e).lower():
            # Trata falso positivo.
            print(f"[*] Sucesso: Pod '{pod_name}' implantado no nó '{node_name}'.")
        else:
            raise e
    except Exception as e:
        print(f"[-] Erro real ao vincular o Pod {pod_name}: {e}")

def iniciar_escalonador():
    # Executa o sistema.
    v1 = carregar_configuracao() # Carrega a configuração.
    print(f"Escalonador '{SCHEDULER_NAME}' ativo e aguardando Pods...")
    
    w = watch.Watch() # Escuta ativa.
    for event in w.stream(v1.list_pod_for_all_namespaces): # Escuta alterações nos pods do cluster.
        pod = event['object']
        
        if pod.status.phase == "Pending" and pod.spec.scheduler_name == SCHEDULER_NAME and pod.spec.node_name is None: # Verificação se o pod busca o escalonador e não está alocado.
            print(f"\n[+] Novo Pod detectado: {pod.metadata.name}")
            
            # Extrai os requisitos do pod e procura o melhor nó para vincula-lo.
            pod_requisitos = extrair_requisitos_pod(pod.spec.containers)
            no_escolhido = avaliar_nos(v1, pod_requisitos)
            
            # Faz o vinculo.
            if no_escolhido:
                vincular_pod(v1, pod.metadata.name, pod.metadata.namespace, no_escolhido)
            else:
                print(f"[!] Alerta: Nenhum Worker possui recursos suficientes para o Pod {pod.metadata.name}.")

if __name__ == "__main__":
    iniciar_escalonador()