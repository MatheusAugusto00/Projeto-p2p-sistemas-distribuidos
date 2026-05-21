# Plano de Implementação: Gerenciador de Filas Distribuídas com Tolerância a Falhas

> **Para agentes executores:** SUB-SKILL REQUERIDA: Use superpowers:subagent-driven-development (recomendado) ou superpowers:executing-plans para implementar este plano passo a passo. Os passos utilizam a sintaxe de caixas de seleção (`- [ ]`) para acompanhamento.

**Objetivo:** Transformar o sistema distribuído master-worker em um gerenciador de filas distribuídas com controle preciso de estados das tarefas, detecção de falha de workers via heartbeat, balanceamento de carga proporcional e logging padronizado.

**Arquitetura:** Usar uma classe thread-safe `TaskManager` para rastrear os estados (`tasks_todo`, `tasks_doing`, `tasks_done`), uma thread de monitoramento no servidor para inativar workers antigos e devolver tarefas, e uma thread de heartbeat no cliente com sincronização por lock ao escrever no socket compartilhado.

**Stack Tecnológica:** Biblioteca padrão do Python 3 (`socket`, `threading`, `json`, `time`, `dataclasses`, `uuid`).

---

### Task 1: Integração da classe TaskManager
**Arquivos:**
- Modificar: `c:/Users/mathe/Documents/Facul/CC/Sistemas Distribuidos/Projeto principal/server.py`
- Testar: `c:/Users/mathe/Documents/Facul/CC/Sistemas Distribuidos/Projeto principal/tests/test_sprint4_taskmanager.py` (Novo arquivo de teste)

- [ ] **Passo 1: Escrever os testes que falham**
Crie um novo arquivo de teste `tests/test_sprint4_taskmanager.py` para validar o comportamento da `TaskManager`:
```python
import unittest
import server

class TestTaskManager(unittest.TestCase):
    def test_task_manager_basic_lifecycle(self):
        tm = server.TaskManager(["T1", "T2"], "Master_A")
        self.assertEqual(tm.get_load(), 2)
        
        # Atribuir task
        t = tm.assign_task("W1")
        self.assertIsNotNone(t)
        self.assertEqual(t.name, "T1")
        self.assertEqual(t.status, "doing")
        self.assertEqual(t.worker_uuid, "W1")
        self.assertEqual(tm.get_load(), 2)
        
        # Concluir task
        tm.complete_task("W1", "OK")
        self.assertEqual(len(tm.tasks_done), 1)
        self.assertEqual(tm.tasks_done[0].name, "T1")
        self.assertEqual(tm.tasks_done[0].status, "done")
        self.assertEqual(tm.get_load(), 1) # Apenas T2 resta
```

- [ ] **Passo 2: Executar teste para verificar falha**
Execute: `py -m unittest tests/test_sprint4_taskmanager.py`
Resultado esperado: FALHA (ModuleAttributeError: module 'server' has no attribute 'TaskManager')

- [ ] **Passo 3: Escrever implementação mínima**
Defina `Task` e `TaskManager` no arquivo `server.py` e substitua `self.tasks_pending`, `self.tasks_in_progress`, e `self.tasks_done` na classe `MasterState` por um objeto `TaskManager`:
```python
from dataclasses import dataclass, field
from typing import Optional, List, Dict
import time

@dataclass
class Task:
    name: str
    status: str = "todo"                      # "todo", "doing", "done"
    worker_uuid: Optional[str] = None
    start_time: Optional[str] = None
    server_uuid: Optional[str] = None

class TaskManager:
    def __init__(self, initial_tasks: List[str], server_uuid: str):
        self.lock = threading.Lock()
        self.server_uuid = server_uuid
        self.tasks_todo = [
            Task(name=name, status="todo", server_uuid=server_uuid)
            for name in initial_tasks
        ]
        self.tasks_doing: Dict[str, Task] = {}  # worker_uuid -> Task
        self.tasks_done: List[Task] = []

    def get_load(self) -> int:
        with self.lock:
            return len(self.tasks_todo) + len(self.tasks_doing)

    def add_task(self, task_name: str):
        with self.lock:
            task = Task(name=task_name, status="todo", server_uuid=self.server_uuid)
            self.tasks_todo.append(task)

    def assign_task(self, worker_uuid: str) -> Optional[Task]:
        with self.lock:
            if not self.tasks_todo:
                return None
            task = self.tasks_todo.pop(0)
            task.status = "doing"
            task.worker_uuid = worker_uuid
            task.start_time = timestamp()
            self.tasks_doing[worker_uuid] = task
            return task

    def complete_task(self, worker_uuid: str, status_msg: str) -> Optional[Task]:
        with self.lock:
            task = self.tasks_doing.pop(worker_uuid, None)
            if task:
                task.status = "done"
                self.tasks_done.append(task)
            return task

    def fail_task(self, worker_uuid: str) -> Optional[Task]:
        with self.lock:
            task = self.tasks_doing.pop(worker_uuid, None)
            if task:
                task.status = "todo"
                task.worker_uuid = None
                task.start_time = None
                self.tasks_todo.insert(0, task)
            return task

    def requeue_task(self, task: Task):
        with self.lock:
            task.status = "todo"
            task.worker_uuid = None
            task.start_time = None
            self.tasks_todo.insert(0, task)
```
Atualize `MasterState` para integrar `TaskManager`:
```python
@dataclass
class MasterState:
    master_uuid: str
    peers: dict
    capacity: int
    release_threshold: int
    task_queue: list
    local_workers: set = field(default_factory=set)
    busy_workers: set = field(default_factory=set)
    borrowed_workers: dict = field(default_factory=dict)
    lent_workers: dict = field(default_factory=dict)
    pending_redirects: dict = field(default_factory=dict)
    pending_releases: dict = field(default_factory=dict)
    help_request_pending: bool = False
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self):
        self.task_manager = TaskManager(self.task_queue, self.master_uuid)

    def register_local_worker(self, worker_uuid):
        with self.lock:
            if worker_uuid not in self.borrowed_workers:
                self.local_workers.add(worker_uuid)

    def mark_worker_busy(self, worker_uuid):
        with self.lock:
            self.busy_workers.add(worker_uuid)

    def mark_worker_idle(self, worker_uuid):
        with self.lock:
            self.busy_workers.discard(worker_uuid)

    def assign_next_task(self, worker_uuid):
        task = self.task_manager.assign_task(worker_uuid)
        if task:
            with self.lock:
                self.busy_workers.add(worker_uuid)
            return task.name
        return None

    def complete_worker_task(self, worker_uuid, status):
        task = self.task_manager.complete_task(worker_uuid, status)
        with self.lock:
            self.busy_workers.discard(worker_uuid)
        return task.name if task else None

    def requeue_worker_task(self, worker_uuid):
        task = self.task_manager.fail_task(worker_uuid)
        with self.lock:
            self.busy_workers.discard(worker_uuid)
        return task.name if task else None

    def available_local_workers(self, limit):
        with self.lock:
            available = [
                worker
                for worker in sorted(self.local_workers)
                if worker not in self.busy_workers
                and worker not in self.pending_redirects
                and worker not in self.lent_workers
            ]
            return available[:limit]

    def current_load(self):
        return self.task_manager.get_load()
```
Modifique também `push_task_front` para utilizar a `self.task_manager`.

- [ ] **Passo 4: Executar teste para verificar aprovação**
Execute: `py -m unittest tests/test_sprint4_taskmanager.py` e também a suite inteira `py -m unittest discover -v`
Resultado esperado: PASS (Sucesso)

- [ ] **Passo 5: Commit**
```bash
git add server.py tests/test_sprint4_taskmanager.py
git commit -m "feat: integrar TaskManager e dataclass Task"
```

---

### Task 2: Registro de Heartbeats no Servidor e Monitor Loop
**Arquivos:**
- Modificar: `c:/Users/mathe/Documents/Facul/CC/Sistemas Distribuidos/Projeto principal/server.py`
- Testar: `c:/Users/mathe/Documents/Facul/CC/Sistemas Distribuidos/Projeto principal/tests/test_sprint4_heartbeat_server.py` (Novo arquivo de teste)

- [ ] **Passo 1: Escrever os testes que falham**
Crie o arquivo `tests/test_sprint4_heartbeat_server.py`:
```python
import unittest
import time
import server

class TestServerHeartbeat(unittest.TestCase):
    def test_worker_heartbeat_timeout_requeues_task(self):
        state = server.MasterState("Master_A", {}, 10, 5, ["T1"])
        state.register_local_worker("W1")
        
        # Conecta e atribui tarefa
        state.assign_next_task("W1")
        self.assertIn("W1", state.task_manager.tasks_doing)
        
        # Simula heartbeat antigo expirado (Timeout = 10s)
        state.last_heartbeats = {"W1": time.time() - 20}
        
        # Executa rotina de monitoramento
        dead_workers = server.check_and_cleanup_dead_workers(state, timeout=10)
        self.assertIn("W1", dead_workers)
        
        # A tarefa deve voltar para tasks_todo e o worker ser removido
        self.assertEqual(len(state.task_manager.tasks_todo), 1)
        self.assertNotIn("W1", state.task_manager.tasks_doing)
        self.assertNotIn("W1", state.local_workers)
```

- [ ] **Passo 2: Executar teste para verificar falha**
Execute: `py -m unittest tests/test_sprint4_heartbeat_server.py`
Resultado esperado: FALHA (Atributo last_heartbeats inexistente em MasterState)

- [ ] **Passo 3: Escrever implementação mínima**
1. Adicione `last_heartbeats: Dict[str, float] = field(default_factory=dict)` a `MasterState`.
2. Adicione o dicionário de conexões `worker_connections: Dict[str, socket.socket] = field(default_factory=dict)` em `MasterState` para possibilitar fechar o socket do worker inativo.
3. Desenvolva os métodos `update_worker_heartbeat`, `check_and_cleanup_dead_workers` e `monitor_workers_loop`.
4. Adicione tratamento de notificação M2M `worker_dead` e envie aos peers caso o worker inativo seja emprestado.
No arquivo `server.py`:
```python
def update_worker_heartbeat(state, worker_uuid):
    with state.lock:
        state.last_heartbeats[worker_uuid] = time.time()

def check_and_cleanup_dead_workers(state, timeout=10):
    now = time.time()
    dead_workers = []
    with state.lock:
        for worker_uuid, last_ts in list(state.last_heartbeats.items()):
            if now - last_ts > timeout:
                dead_workers.append(worker_uuid)

    for worker_uuid in dead_workers:
        print(f"[{timestamp()}] [WORKER_DEAD] Worker {worker_uuid} inativo detectado.")
        
        conn = None
        with state.lock:
            conn = state.worker_connections.pop(worker_uuid, None)
        if conn:
            try:
                conn.close()
            except OSError:
                pass

        requeued_task = state.requeue_worker_task(worker_uuid)
        if requeued_task:
            print(f"[{timestamp()}] [REQUEUE] Task {requeued_task} recolocada na fila.")

        with state.lock:
            state.local_workers.discard(worker_uuid)
            state.busy_workers.discard(worker_uuid)
            borrowed_info = state.borrowed_workers.pop(worker_uuid, None)
            state.pending_redirects.pop(worker_uuid, None)
            state.pending_releases.pop(worker_uuid, None)
            state.last_heartbeats.pop(worker_uuid, None)

        if borrowed_info:
            orig_addr = borrowed_info.get("original_master_address")
            if orig_addr:
                notify_worker_dead_to_peer(orig_addr, worker_uuid)

    return dead_workers

def notify_worker_dead_to_peer(peer_address, worker_uuid):
    request_id = str(uuid.uuid4())
    message = build_master_message(
        "worker_dead",
        request_id,
        {"worker_id": worker_uuid}
    )
    try:
        host, port = parse_address(peer_address)
        with socket.create_connection((host, port), timeout=NEGOTIATION_TIMEOUT) as sock:
            send_json(sock, message)
    except Exception as exc:
        print(f"[M2M] Falha ao notificar morte de {worker_uuid} para {peer_address}: {exc}")

def monitor_workers_loop():
    while True:
        check_and_cleanup_dead_workers(master_state, timeout=SOCKET_TIMEOUT)
        time.sleep(2)
```
Atualize `tratar_cliente` para lidar com `HEARTBEAT` sob o loop de dados:
```python
                    if "type" in dados:
                        handle_master_message(conn, dados)
                    elif "HEARTBEAT" in dados:
                        w_uuid = dados["WORKER_UUID"]
                        update_worker_heartbeat(master_state, w_uuid)
                    elif "WORKER" in dados:
                        if current_task is not None:
                            raise ValueError("Worker solicitou nova task antes de concluir a anterior")
                        current_worker_uuid, current_task = handle_worker_presentation(conn, dados)
                        with master_state.lock:
                            master_state.worker_connections[current_worker_uuid] = conn
                        update_worker_heartbeat(master_state, current_worker_uuid)
```
Trate também a mensagem `worker_dead` em `handle_master_message`:
```python
    elif message_type == "worker_dead":
        worker_id = ensure_string_field(message_payload, "worker_id")
        with master_state.lock:
            master_state.lent_workers.pop(worker_id, None)
            master_state.pending_redirects.pop(worker_id, None)
        print(f"[{timestamp()}] [WORKER_DEAD] Notificacao de morte recebida: {worker_id} morreu no peer.")
```
Inicie a thread de monitoramento em `iniciar_servidor`:
```python
    monitor_thread = threading.Thread(target=monitor_workers_loop, daemon=True)
    monitor_thread.start()
```

- [ ] **Passo 4: Executar teste para verificar aprovação**
Execute: `py -m unittest tests/test_sprint4_heartbeat_server.py` e descubra os demais testes.
Resultado esperado: PASS

- [ ] **Passo 5: Commit**
```bash
git add server.py tests/test_sprint4_heartbeat_server.py
git commit -m "feat: implementar registro e monitoramento de heartbeat no servidor"
```

---

### Task 3: Envio de Heartbeat e Reconexão no Cliente (Worker)
**Arquivos:**
- Modificar: `c:/Users/mathe/Documents/Facul/CC/Sistemas Distribuidos/Projeto principal/client.py`

- [ ] **Passo 1: Implementar Lock de Escrita e Loop de Heartbeat no Cliente**
Adicione um lock e controle da thread de heartbeat em `client.py`:
```python
import threading

socket_lock = threading.Lock()
heartbeat_active = False

def send_json_safe(sock, payload):
    with socket_lock:
        sock.sendall((json.dumps(payload) + "\n").encode())

def client_heartbeat_loop(sock, worker_id, interval=3):
    global heartbeat_active
    while heartbeat_active:
        try:
            send_json_safe(sock, {"HEARTBEAT": "PING", "WORKER_UUID": worker_id})
        except Exception:
            break
        time.sleep(interval)
```

- [ ] **Passo 2: Modificar loop de execução do Worker para manter conexão persistente**
Refatore `worker_loop` em `client.py` para gerenciar a thread de heartbeat ao conectar e garantir reconexão automática estável:
```python
def worker_loop():
    global heartbeat_active
    while True:
        try:
            with socket.create_connection(
                (worker_state.current_master_host, worker_state.current_master_port),
                timeout=MASTER_TIMEOUT,
            ) as sock:
                sock.settimeout(MASTER_TIMEOUT)
                print(
                    f"[{timestamp()}] [RECONNECT] Conectado ao Master "
                    f"{worker_state.current_master_host}:{worker_state.current_master_port}"
                )

                heartbeat_active = True
                hb_thread = threading.Thread(
                    target=client_heartbeat_loop,
                    args=(sock, worker_state.worker_id),
                    daemon=True
                )
                hb_thread.start()

                while True:
                    apresentacao = montar_payload_apresentacao()
                    send_json_safe(sock, apresentacao)

                    resposta = parse_server_message(receber_mensagem(sock))
                    print("[MASTER]:", resposta)

                    task = validar_resposta_inicial(resposta)
                    if task == "command_redirect":
                        register_payload = apply_command_redirect(worker_state, resposta["payload"])
                        print(
                            f"[{timestamp()}] [REDIRECT] Worker {worker_state.worker_id} indo para "
                            f"{worker_state.current_master_host}:{worker_state.current_master_port}"
                        )
                        heartbeat_active = False
                        with socket.create_connection(
                            (worker_state.current_master_host, worker_state.current_master_port),
                            timeout=MASTER_TIMEOUT,
                        ) as register_sock:
                            register_sock.settimeout(MASTER_TIMEOUT)
                            send_json(register_sock, register_payload)
                            register_ack = parse_server_message(receber_mensagem(register_sock))
                            print("[REGISTER ACK]:", register_ack)
                        break # Sai do loop interno para reconectar ao novo master
                    
                    if task == "command_release":
                        apply_command_release(worker_state, resposta["payload"])
                        print(
                            f"[{timestamp()}] [RELEASE] Worker {worker_state.worker_id} voltando para "
                            f"{worker_state.current_master_host}:{worker_state.current_master_port}"
                        )
                        heartbeat_active = False
                        break # Sai do loop interno para reconectar ao master original

                    if task == "NO_TASK":
                        print(f"[{timestamp()}] [FILA] Nenhuma tarefa disponivel.")
                        time.sleep(3)
                        continue

                    current_task = resposta["USER"]
                    print(f"[{timestamp()}] [DISPATCH] Processando tarefa {current_task}...")
                    time.sleep(random.randint(1, 3))

                    status = {
                        "STATUS": random.choice(["OK", "NOK"]),
                        "TASK": "QUERY",
                        "WORKER_UUID": worker_state.worker_id,
                        "USER": current_task,
                    }

                    send_json_safe(sock, status)

                    ack = parse_server_message(receber_mensagem(sock))
                    validar_ack(ack)
                    print(f"[{timestamp()}] [TASK_COMPLETED] Task {current_task} confirmada.")
                    time.sleep(1)

        except (ConnectionError, TimeoutError, socket.timeout, OSError) as exc:
            print(f"[{timestamp()}] [RECONNECT] Falha na conexao: {exc}")
        finally:
            heartbeat_active = False

        print(f"[{timestamp()}] [RECONNECT] Nova tentativa em {RECONNECT_DELAY} segundos.")
        time.sleep(RECONNECT_DELAY)
```

- [ ] **Passo 3: Validar a estabilidade da reconexão e logs**
Inicie os scripts e valide o log formatado em tempo real.
Resultado esperado: Sucesso total sem exceções de concorrência.

- [ ] **Passo 4: Commit**
```bash
git add client.py
git commit -m "feat: implementar loop de heartbeat e conexao persistente no client"
```

---

### Task 4: Melhoria no Balanceamento de Carga
**Arquivos:**
- Modificar: `c:/Users/mathe/Documents/Facul/CC/Sistemas Distribuidos/Projeto principal/server.py`
- Testar: `c:/Users/mathe/Documents/Facul/CC/Sistemas Distribuidos/Projeto principal/tests/test_sprint4_load_balancing.py` (Novo arquivo de teste)

- [ ] **Passo 1: Escrever os testes que falham**
Crie o arquivo `tests/test_sprint4_load_balancing.py`:
```python
import unittest
import server

class TestLoadBalancing(unittest.TestCase):
    def test_calculate_workers_needed(self):
        # capacidade = 100, carga = 140 -> deve pedir 40 workers
        needed = server.calculate_workers_needed(load=140, capacity=100)
        self.assertEqual(needed, 40)
        
        # capacidade = 100, carga = 101 -> deve pedir 1 worker
        needed = server.calculate_workers_needed(load=101, capacity=100)
        self.assertEqual(needed, 1)

        # capacidade = 100, carga = 90 -> deve pedir 0 workers
        needed = server.calculate_workers_needed(load=90, capacity=100)
        self.assertEqual(needed, 0)
```

- [ ] **Passo 2: Executar teste para verificar falha**
Execute: `py -m unittest tests/test_sprint4_load_balancing.py`
Resultado esperado: FALHA (Atributo 'calculate_workers_needed' ausente no módulo server)

- [ ] **Passo 3: Escrever implementação mínima**
1. Implemente `calculate_workers_needed(load, capacity)` em `server.py`:
```python
def calculate_workers_needed(load, capacity):
    if load <= capacity:
        return 0
    return load - capacity
```
2. Modifique a rotina `negotiate_help_if_saturated` para utilizar a nova função e gerar logs padronizados de `[SATURATION]`.
3. Garanta que na liberação (devolução) de workers emprestados (`queue_releases_if_needed`), apenas workers **ociosos** (que não estão em `state.task_manager.tasks_doing`) sejam listados.

- [ ] **Passo 4: Executar testes da suite completa**
Execute: `py -m unittest discover -v`
Resultado esperado: PASS

- [ ] **Passo 5: Commit**
```bash
git add server.py tests/test_sprint4_load_balancing.py
git commit -m "feat: implementar calculo proporcional de workers necessarios e correcao de releases"
```

---

### Task 5: Padronização Final de Logs
**Arquivos:**
- Modificar: `c:/Users/mathe/Documents/Facul/CC/Sistemas Distribuidos/Projeto principal/server.py`
- Modificar: `c:/Users/mathe/Documents/Facul/CC/Sistemas Distribuidos/Projeto principal/client.py`

- [ ] **Passo 1: Ajustar os prints de logs nos dois arquivos**
Garanta que todos os eventos do ciclo de vida sigam estritamente o formato:
`[TIMESTAMP] [TIPO] mensagem`

- [ ] **Passo 2: Executar suite de testes integrados**
Execute:
```bash
py -m unittest discover -v
```
Verifique o sucesso de todos os testes unitários da aplicação.

- [ ] **Passo 3: Commit**
```bash
git add server.py client.py
git commit -m "style: logs padronizados em conformidade com as regras de log"
```
