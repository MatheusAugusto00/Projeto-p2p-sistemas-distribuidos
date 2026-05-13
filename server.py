import json
import os
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field

HOST = os.getenv("MASTER_HOST", "127.0.0.1")
PORT = int(os.getenv("MASTER_PORT", "8000"))
MASTER_UUID = os.getenv("MASTER_UUID", "Master_A")
SOCKET_TIMEOUT = int(os.getenv("MASTER_SOCKET_TIMEOUT", "10"))
NEGOTIATION_TIMEOUT = int(os.getenv("NEGOTIATION_TIMEOUT", "5"))
CAPACITY = int(os.getenv("CAPACITY", "100"))
RELEASE_THRESHOLD = int(os.getenv("RELEASE_THRESHOLD", str(int(CAPACITY * 0.6))))
PEER_MASTERS = os.getenv("PEER_MASTERS", "")
HELP_CHECK_INTERVAL = int(os.getenv("HELP_CHECK_INTERVAL", "2"))
INITIAL_TASK_COUNT = int(os.getenv("INITIAL_TASK_COUNT", "50"))


def build_initial_tasks(task_count):
    if task_count < 0:
        raise ValueError("INITIAL_TASK_COUNT nao pode ser negativo")
    return [f"TAREFA{i}" for i in range(1, task_count + 1)]


task_queue = build_initial_tasks(INITIAL_TASK_COUNT)
task_queue_lock = threading.Lock()


def parse_peer_masters(raw_peers):
    peers = {}
    if not raw_peers:
        return peers

    for raw_peer in raw_peers.split(","):
        peer = raw_peer.strip()
        if not peer:
            continue
        try:
            master_id, address = peer.split("@", 1)
            host, port = address.rsplit(":", 1)
        except ValueError as exc:
            raise ValueError(f"Peer invalido: {peer}") from exc
        if not master_id.strip() or not host.strip():
            raise ValueError(f"Peer invalido: {peer}")
        peers[master_id.strip()] = (host.strip(), int(port))
    return peers


def format_address(host, port):
    return f"{host}:{port}"


def parse_address(address):
    try:
        host, port = address.rsplit(":", 1)
    except ValueError as exc:
        raise ValueError(f"Endereco invalido: {address}") from exc
    if not host.strip():
        raise ValueError(f"Endereco invalido: {address}")
    return host.strip(), int(port)


def timestamp():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def log_protocol(direction, message_type, request_id, detail=""):
    suffix = f" {detail}" if detail else ""
    print(f"[{timestamp()}] [{direction}] type={message_type} request_id={request_id}{suffix}")


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
        self.tasks_pending = self.task_queue
        self.tasks_in_progress = {}
        self.tasks_done = []

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
        with self.lock:
            if not self.tasks_pending:
                return None
            task_name = self.tasks_pending.pop(0)
            self.tasks_in_progress[worker_uuid] = task_name
            self.busy_workers.add(worker_uuid)
            return task_name

    def complete_worker_task(self, worker_uuid, status):
        with self.lock:
            task_name = self.tasks_in_progress.pop(worker_uuid, None)
            self.busy_workers.discard(worker_uuid)
            if task_name is None:
                return None
            self.tasks_done.append(
                {"worker_uuid": worker_uuid, "task": task_name, "status": status}
            )
            return task_name

    def requeue_worker_task(self, worker_uuid):
        with self.lock:
            task_name = self.tasks_in_progress.pop(worker_uuid, None)
            self.busy_workers.discard(worker_uuid)
            if task_name is None:
                return None
            self.tasks_pending.insert(0, task_name)
            return task_name

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
        with self.lock:
            return len(self.tasks_pending)


master_state = MasterState(
    master_uuid=MASTER_UUID,
    peers=parse_peer_masters(PEER_MASTERS),
    capacity=CAPACITY,
    release_threshold=RELEASE_THRESHOLD,
    task_queue=task_queue,
)


def send_json(conn, payload):
    conn.sendall((json.dumps(payload) + "\n").encode())


def read_json_line(sock):
    buffer = ""
    while "\n" not in buffer:
        data = sock.recv(1024)
        if not data:
            raise ConnectionError("Conexao encerrada antes do fim da mensagem")
        buffer += data.decode()
    raw_message, _ = buffer.split("\n", 1)
    return parse_json_message(raw_message.strip())


def parse_json_message(raw_message):
    try:
        return json.loads(raw_message)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON invalido: {exc}") from exc


def ensure_string_field(payload, field_name, required=True):
    value = payload.get(field_name)
    if value is None:
        if required:
            raise ValueError(f"Campo obrigatorio ausente: {field_name}")
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Campo invalido: {field_name}")
    return value


def ensure_int_field(payload, field_name, required=True, default=None):
    value = payload.get(field_name)
    if value is None:
        if required:
            raise ValueError(f"Campo obrigatorio ausente: {field_name}")
        return default
    if not isinstance(value, int):
        raise ValueError(f"Campo invalido: {field_name}")
    return value


def validate_master_message(payload):
    message_type = ensure_string_field(payload, "type")
    request_id = ensure_string_field(payload, "request_id")
    message_payload = payload.get("payload")
    if not isinstance(message_payload, dict):
        raise ValueError("Campo obrigatorio ausente ou invalido: payload")
    return message_type, request_id, message_payload


def build_master_message(message_type, request_id, payload):
    return {"type": message_type, "request_id": request_id, "payload": payload}


def validate_worker_handshake(payload):
    worker_state = ensure_string_field(payload, "WORKER")
    if worker_state != "ALIVE":
        raise ValueError("Campo WORKER deve ter valor ALIVE")

    worker_uuid = ensure_string_field(payload, "WORKER_UUID")
    origin_server_uuid = ensure_string_field(payload, "SERVER_UUID", required=False)
    return worker_uuid, origin_server_uuid


def validate_worker_status(payload):
    status = ensure_string_field(payload, "STATUS")
    if status not in {"OK", "NOK"}:
        raise ValueError("Campo STATUS deve ser OK ou NOK")

    task_name = ensure_string_field(payload, "TASK")
    if task_name != "QUERY":
        raise ValueError("Campo TASK deve ter valor QUERY")

    worker_uuid = ensure_string_field(payload, "WORKER_UUID")
    return status, worker_uuid


def pop_next_task():
    return master_state.assign_next_task("UNKNOWN_WORKER")


def push_task_front(task_name):
    with master_state.lock:
        master_state.tasks_pending.insert(0, task_name)


def worker_origin_label(origin_server_uuid):
    if origin_server_uuid and origin_server_uuid != MASTER_UUID:
        return f"EMPRESTADO de {origin_server_uuid}"
    return "LOCAL"


def maybe_negotiate_help():
    negotiate_help_if_saturated(master_state, request_help_from_peer)


def negotiate_help_if_saturated(state, requester):
    with state.lock:
        if state.help_request_pending:
            return False

    load = state.current_load()
    if load <= state.capacity or not state.peers:
        return False

    workers_needed = max(1, load - state.capacity)
    for peer_id, peer_address in state.peers.items():
        response = requester(peer_id, peer_address, load, workers_needed)
        if response and response.get("type") == "response_accepted":
            with state.lock:
                state.help_request_pending = True
            return True
    return False


def saturation_monitor_loop():
    while True:
        negotiate_help_if_saturated(master_state, request_help_from_peer)
        time.sleep(HELP_CHECK_INTERVAL)


def start_saturation_monitor():
    thread = threading.Thread(target=saturation_monitor_loop, daemon=True)
    thread.start()
    return thread


def request_help_from_peer(peer_id, peer_address, current_load, workers_needed):
    request_id = str(uuid.uuid4())
    payload = {
        "master_id": MASTER_UUID,
        "current_load": current_load,
        "capacity": master_state.capacity,
        "workers_needed": workers_needed,
        "return_address": format_address(HOST, PORT),
    }
    message = build_master_message("request_help", request_id, payload)

    try:
        with socket.create_connection(peer_address, timeout=NEGOTIATION_TIMEOUT) as sock:
            sock.settimeout(NEGOTIATION_TIMEOUT)
            log_protocol("M2M OUT", "request_help", request_id, f"peer={peer_id}")
            send_json(sock, message)
            response = read_json_line(sock)
            message_type, response_request_id, _ = validate_master_message(response)
            if response_request_id != request_id:
                raise ValueError("response request_id diferente da requisicao")
            log_protocol("M2M IN", message_type, response_request_id, f"peer={peer_id}")
            return response
    except (OSError, TimeoutError, socket.timeout, ValueError) as exc:
        print(f"[M2M] Falha ao negociar com {peer_id}: {exc}")
        return None


def handle_request_help_message(state, request_id, payload):
    requester = ensure_string_field(payload, "master_id")
    workers_needed = ensure_int_field(payload, "workers_needed")
    return_address = payload.get("return_address")

    offered_workers = state.available_local_workers(workers_needed)
    if not offered_workers:
        return build_master_message(
            "response_rejected",
            request_id,
            {"reason": "no_workers_available"},
        )

    worker_details = []
    with state.lock:
        for worker_uuid in offered_workers:
            state.pending_redirects[worker_uuid] = {
                "new_master_address": return_address,
                "requester": requester,
            }
            state.lent_workers[worker_uuid] = {
                "borrower": requester,
                "new_master_address": return_address,
            }
            worker_details.append({"id": worker_uuid, "address": "dynamic"})

    return build_master_message(
        "response_accepted",
        request_id,
        {
            "workers_offered": len(worker_details),
            "worker_details": worker_details,
        },
    )


def handle_register_temporary_worker_message(state, request_id, payload):
    worker_id = ensure_string_field(payload, "worker_id")
    original_master_address = ensure_string_field(payload, "original_master_address")

    with state.lock:
        state.borrowed_workers[worker_id] = {
            "original_master_address": original_master_address,
            "registered_at": timestamp(),
        }
        state.local_workers.discard(worker_id)
        state.help_request_pending = False

    print(f"[BORROWED] Worker {worker_id} registrado de {original_master_address}")
    return build_master_message(
        "register_temporary_worker_ack",
        request_id,
        {"worker_id": worker_id},
    )


def handle_notify_worker_returned_message(state, request_id, payload):
    worker_id = ensure_string_field(payload, "worker_id")
    with state.lock:
        state.lent_workers.pop(worker_id, None)
        state.pending_redirects.pop(worker_id, None)
    print(f"[RETURNED] Worker {worker_id} voltou ao {state.master_uuid}")
    return build_master_message(
        "notify_worker_returned_ack",
        request_id,
        {"worker_id": worker_id},
    )


def queue_releases_if_needed(state):
    if state.current_load() > state.release_threshold:
        return []

    queued = []
    with state.lock:
        for worker_id, worker_data in list(state.borrowed_workers.items()):
            if worker_id in state.busy_workers or worker_id in state.pending_releases:
                continue
            state.pending_releases[worker_id] = {
                "original_master_address": worker_data["original_master_address"]
            }
            queued.append(worker_id)
    return queued


def notify_worker_returned(original_master_address, worker_id):
    request_id = str(uuid.uuid4())
    message = build_master_message(
        "notify_worker_returned",
        request_id,
        {"worker_id": worker_id},
    )
    try:
        with socket.create_connection(parse_address(original_master_address), timeout=NEGOTIATION_TIMEOUT) as sock:
            sock.settimeout(NEGOTIATION_TIMEOUT)
            log_protocol("M2M OUT", "notify_worker_returned", request_id, f"worker={worker_id}")
            send_json(sock, message)
    except (OSError, TimeoutError, socket.timeout, ValueError) as exc:
        print(f"[M2M] Falha ao notificar devolucao de {worker_id}: {exc}")


def handle_master_message(conn, payload):
    message_type, request_id, message_payload = validate_master_message(payload)
    log_protocol("M2M IN", message_type, request_id)

    if message_type == "request_help":
        response = handle_request_help_message(master_state, request_id, message_payload)
        send_json(conn, response)
        log_protocol("M2M OUT", response["type"], response["request_id"])
    elif message_type == "register_temporary_worker":
        response = handle_register_temporary_worker_message(master_state, request_id, message_payload)
        send_json(conn, response)
        log_protocol("M2M OUT", response["type"], response["request_id"])
    elif message_type == "notify_worker_returned":
        response = handle_notify_worker_returned_message(master_state, request_id, message_payload)
        send_json(conn, response)
        log_protocol("M2M OUT", response["type"], response["request_id"])
    else:
        print(f"[M2M] Tipo desconhecido ignorado: {message_type}")


def handle_worker_presentation(conn, payload):
    worker_uuid, origin_server_uuid = validate_worker_handshake(payload)
    if origin_server_uuid:
        with master_state.lock:
            master_state.borrowed_workers.setdefault(
                worker_uuid,
                {"original_master_address": origin_server_uuid, "registered_at": timestamp()},
            )
    else:
        master_state.register_local_worker(worker_uuid)

    with master_state.lock:
        redirect = master_state.pending_redirects.pop(worker_uuid, None)
        release = master_state.pending_releases.pop(worker_uuid, None)

    if redirect and redirect.get("new_master_address"):
        response = build_master_message(
            "command_redirect",
            str(uuid.uuid4()),
            {
                "new_master_address": redirect["new_master_address"],
                "original_master_address": format_address(HOST, PORT),
            },
        )
        send_json(conn, response)
        print(f"[REDIRECT] Worker {worker_uuid} enviado para {redirect['new_master_address']}")
        return worker_uuid, None

    if release:
        response = build_master_message(
            "command_release",
            str(uuid.uuid4()),
            {"original_master_address": release["original_master_address"]},
        )
        send_json(conn, response)
        notify_worker_returned(release["original_master_address"], worker_uuid)
        with master_state.lock:
            master_state.borrowed_workers.pop(worker_uuid, None)
        print(f"[RELEASE] Worker {worker_uuid} devolvido para {release['original_master_address']}")
        return worker_uuid, None

    queue_releases_if_needed(master_state)
    maybe_negotiate_help()
    next_task = master_state.assign_next_task(worker_uuid)

    if next_task:
        response = {"TASK": "QUERY", "USER": next_task}
    else:
        response = {"TASK": "NO_TASK"}

    print(
        f"[WORKER] {worker_uuid} apresentou-se ao {MASTER_UUID} "
        f"como {worker_origin_label(origin_server_uuid)}"
    )
    if next_task:
        print(f"[DISPATCH] {next_task} -> Worker {worker_uuid}")
    else:
        print(f"[FILA] Nenhuma tarefa disponivel para Worker {worker_uuid}")
    send_json(conn, response)
    return worker_uuid, next_task


def handle_worker_status(conn, payload, current_worker_uuid, current_task):
    status, worker_uuid = validate_worker_status(payload)
    reported_task = payload.get("USER")

    if current_task is None:
        raise ValueError("Worker reportou status sem task em andamento")
    if worker_uuid != current_worker_uuid:
        raise ValueError("STATUS recebido de worker diferente do handshake")
    if reported_task is not None and reported_task != current_task:
        raise ValueError("STATUS recebido para task diferente da task atribuida")

    ack = {"STATUS": "ACK", "WORKER_UUID": worker_uuid}

    print(
        f"[STATUS RECEBIDO] Worker {worker_uuid} concluiu {current_task} "
        f"com status {status}"
    )
    master_state.complete_worker_task(worker_uuid, status)
    send_json(conn, ack)


def tratar_cliente(conn, addr):
    buffer = ""
    current_worker_uuid = None
    current_task = None
    conn.settimeout(SOCKET_TIMEOUT)

    try:
        print(f"[THREAD] Atendimento {addr}")

        while True:
            try:
                data = conn.recv(1024)
            except socket.timeout:
                print(f"[TIMEOUT] Encerrando conexao inativa de {addr}")
                break

            if not data:
                break

            buffer += data.decode()

            while "\n" in buffer:
                mensagem, buffer = buffer.split("\n", 1)

                if not mensagem.strip():
                    continue

                try:
                    dados = parse_json_message(mensagem)
                    print("[REQ]:", dados)

                    if "type" in dados:
                        handle_master_message(conn, dados)
                    elif "WORKER" in dados:
                        if current_task is not None:
                            raise ValueError("Worker solicitou nova task antes de concluir a anterior")
                        current_worker_uuid, current_task = handle_worker_presentation(conn, dados)
                    elif "STATUS" in dados:
                        handle_worker_status(conn, dados, current_worker_uuid, current_task)
                        current_task = None
                    else:
                        raise ValueError("Mensagem sem tipo conhecido")
                except ValueError as exc:
                    print(f"[PROTOCOLO] {addr}: {exc}")
                    send_json(conn, {"ERROR": "INVALID_PAYLOAD", "DETAIL": str(exc)})
    except Exception as exc:
        print("[ERRO]:", exc)
    finally:
        requeued_task = None
        if current_worker_uuid is not None:
            requeued_task = master_state.requeue_worker_task(current_worker_uuid)
        if requeued_task is None and current_task is not None:
            push_task_front(current_task)
            requeued_task = current_task
        if requeued_task is not None:
            print(
                f"[REQUEUE] {requeued_task} retornou para a fila apos falha na conexao "
                f"com Worker {current_worker_uuid or addr}"
            )
        print(f"[THREAD] Encerrando {addr}")
        conn.close()


def iniciar_servidor():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(100)

    print(f"Servidor {MASTER_UUID} rodando em {HOST}:{PORT}")
    start_saturation_monitor()

    while True:
        conn, addr = server_socket.accept()
        thread = threading.Thread(target=tratar_cliente, args=(conn, addr), daemon=True)
        thread.start()


if __name__ == "__main__":
    iniciar_servidor()
