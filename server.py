import json
import os
import shutil
import socket
import ssl
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field

HOST = os.getenv("MASTER_HOST", "192.168.1.187")
PORT = int(os.getenv("MASTER_PORT", "8000"))
MASTER_UUID = os.getenv("MASTER_UUID", "Master_A")
SOCKET_TIMEOUT = int(os.getenv("MASTER_SOCKET_TIMEOUT", "10"))
NEGOTIATION_TIMEOUT = int(os.getenv("NEGOTIATION_TIMEOUT", "5"))
CAPACITY = int(os.getenv("CAPACITY", "100"))
RELEASE_THRESHOLD = int(os.getenv("RELEASE_THRESHOLD", str(int(CAPACITY * 0.6))))
PEER_MASTERS = os.getenv("PEER_MASTERS", "GUTO@10.0.0.4:8000")
HELP_CHECK_INTERVAL = int(os.getenv("HELP_CHECK_INTERVAL", "2"))
INITIAL_TASK_COUNT = int(os.getenv("INITIAL_TASK_COUNT", "0"))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "10"))
HEARTBEAT_TIMEOUT = int(os.getenv("HEARTBEAT_TIMEOUT", "8"))
HEARTBEAT_CHECK_INTERVAL = int(os.getenv("HEARTBEAT_CHECK_INTERVAL", "2"))
MAX_MISSED_HEARTBEATS = int(os.getenv("MAX_MISSED_HEARTBEATS", "3"))
SUPERVISOR_ENABLED = os.getenv("SUPERVISOR_ENABLED", "1")
SUPERVISOR_HOST = os.getenv("SUPERVISOR_HOST", "nuted-ia.dev")
SUPERVISOR_PORT = int(os.getenv("SUPERVISOR_PORT", "443"))
SUPERVISOR_INTERVAL = int(os.getenv("SUPERVISOR_INTERVAL", "10"))
SUPERVISOR_TLS = os.getenv("SUPERVISOR_TLS", "1")
SUPERVISOR_SNI = os.getenv("SUPERVISOR_SNI", SUPERVISOR_HOST)
SUPERVISOR_PAYLOAD_VERSION = "sprint4-monitor"
PROCESS_START_TIME = time.time()


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


def log_event(level, message):
    print(f"[{timestamp()}] [{level}] {message}")


@dataclass
class Task:
    name: str
    worker_uuid: str = None
    server_uuid: str = None
    origin_server_uuid: str = None
    started_at: str = None
    status: str = "TODO"


class TaskManager:
    def __init__(self, initial_tasks):
        self.tasks_todo = deque(Task(name=name) for name in initial_tasks)
        self.tasks_doing = {}
        self.lock = threading.Lock()

    def add_task(self, task_name):
        with self.lock:
            self.tasks_todo.append(Task(name=task_name))

    def assign_task(self, worker_uuid, server_uuid):
        with self.lock:
            if not self.tasks_todo:
                return None
            task = self.tasks_todo.popleft()
            task.worker_uuid = worker_uuid
            task.server_uuid = server_uuid
            task.started_at = timestamp()
            task.status = "DOING"
            self.tasks_doing[worker_uuid] = task
            return task

    def complete_task(self, worker_uuid):
        with self.lock:
            task = self.tasks_doing.pop(worker_uuid, None)
            if task is None:
                return None
            task.status = "DONE"
            task.completed_at = timestamp()
            return task

    def requeue_task(self, worker_uuid):
        with self.lock:
            task = self.tasks_doing.pop(worker_uuid, None)
            if task is None:
                return None
            task.worker_uuid = None
            task.server_uuid = None
            task.origin_server_uuid = None
            task.started_at = None
            task.status = "TODO"
            self.tasks_todo.appendleft(task)
            return task

    def get_load(self):
        with self.lock:
            return len(self.tasks_todo) + len(self.tasks_doing)


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
    worker_heartbeats: dict = field(default_factory=dict)
    worker_failures: int = 0
    peer_status: dict = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self):
        self.task_manager = TaskManager(self.task_queue)
        self.tasks_done = []

    @property
    def tasks_pending(self):
        return [task.name for task in self.task_manager.tasks_todo]

    @property
    def tasks_in_progress(self):
        return {worker: task.name for worker, task in self.task_manager.tasks_doing.items()}

    def register_local_worker(self, worker_uuid):
        with self.lock:
            if worker_uuid not in self.borrowed_workers:
                self.local_workers.add(worker_uuid)

    def register_worker_heartbeat(self, worker_uuid, origin_server_uuid=None):
        with self.lock:
            self.worker_heartbeats[worker_uuid] = {
                "last_heartbeat": time.time(),
                "missed_intervals": 0,
                "origin_server_uuid": origin_server_uuid,
            }
            if origin_server_uuid:
                self.borrowed_workers.setdefault(
                    worker_uuid,
                    {"original_master_address": origin_server_uuid, "registered_at": timestamp()},
                )
            else:
                self.local_workers.add(worker_uuid)

    def update_worker_heartbeat(self, worker_uuid, origin_server_uuid=None):
        with self.lock:
            heartbeat = self.worker_heartbeats.setdefault(
                worker_uuid,
                {
                    "last_heartbeat": time.time(),
                    "missed_intervals": 0,
                    "origin_server_uuid": origin_server_uuid,
                },
            )
            heartbeat["last_heartbeat"] = time.time()
            heartbeat["missed_intervals"] = 0
            if origin_server_uuid:
                heartbeat["origin_server_uuid"] = origin_server_uuid
            return heartbeat

    def assign_next_task(self, worker_uuid):
        task = self.task_manager.assign_task(worker_uuid, self.master_uuid)
        if task is None:
            return None
        with self.lock:
            self.busy_workers.add(worker_uuid)
        return task.name

    def complete_worker_task(self, worker_uuid, status):
        task = self.task_manager.complete_task(worker_uuid)
        with self.lock:
            self.busy_workers.discard(worker_uuid)
            if task is None:
                return None
            self.tasks_done.append(
                {"worker_uuid": worker_uuid, "task": task.name, "status": status}
            )
        return task.name

    def requeue_worker_task(self, worker_uuid):
        task = self.task_manager.requeue_task(worker_uuid)
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

    def cleanup_dead_worker(self, worker_uuid):
        with self.lock:
            self.worker_heartbeats.pop(worker_uuid, None)
            self.local_workers.discard(worker_uuid)
            self.busy_workers.discard(worker_uuid)
            self.pending_redirects.pop(worker_uuid, None)
            self.pending_releases.pop(worker_uuid, None)
            borrowed = self.borrowed_workers.pop(worker_uuid, None)
            self.lent_workers.pop(worker_uuid, None)
            self.worker_failures += 1

        task = self.task_manager.requeue_task(worker_uuid)
        if task:
            log_event(
                "WORKER DEAD",
                f"Worker {worker_uuid} morreu; task {task.name} retornou para tasks_todo",
            )
        else:
            log_event("WORKER DEAD", f"Worker {worker_uuid} morreu sem tarefa ativa")

        if borrowed and borrowed.get("original_master_address"):
            notify_worker_dead(borrowed["original_master_address"], worker_uuid)

        return task


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


def get_payload_alias(payload, canonical_name, alias_name=None, default=None):
    if canonical_name in payload:
        return payload.get(canonical_name)
    if alias_name and alias_name in payload:
        return payload.get(alias_name)
    return default


def ensure_string_alias(payload, canonical_name, alias_name=None, required=True):
    value = get_payload_alias(payload, canonical_name, alias_name)
    if value is None:
        if required:
            raise ValueError(f"Campo obrigatorio ausente: {canonical_name}")
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Campo invalido: {canonical_name}")
    return value


def ensure_int_alias(payload, canonical_name, alias_name=None, required=True, default=None):
    value = get_payload_alias(payload, canonical_name, alias_name, default)
    if value is None:
        if required:
            raise ValueError(f"Campo obrigatorio ausente: {canonical_name}")
        return default
    if not isinstance(value, int):
        raise ValueError(f"Campo invalido: {canonical_name}")
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


def validate_worker_heartbeat(payload):
    worker_uuid = ensure_string_field(payload, "WORKER_UUID")
    origin_server_uuid = payload.get("SERVER_UUID")
    if origin_server_uuid is not None and (
        not isinstance(origin_server_uuid, str) or not origin_server_uuid.strip()
    ):
        raise ValueError("Campo SERVER_UUID invalido")
    return worker_uuid, origin_server_uuid


def pop_next_task():
    return master_state.assign_next_task("UNKNOWN_WORKER")


def push_task_front(task_name):
    with master_state.lock:
        master_state.task_manager.tasks_todo.appendleft(Task(name=task_name))


def worker_origin_label(origin_server_uuid):
    if origin_server_uuid and origin_server_uuid != MASTER_UUID:
        return f"EMPRESTADO de {origin_server_uuid}"
    return "LOCAL"


def parse_bool(value):
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def utc_timestamp(now=None):
    current = time.time() if now is None else now
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(current))


def supervisor_hostname(master_uuid):
    return os.getenv("HOSTNAME") or f"{master_uuid}.farm.local"


def collect_system_metrics(now=None):
    current = time.time() if now is None else now
    uptime_seconds = max(0, int(current - PROCESS_START_TIME))
    load_average_1m = 0.0
    load_average_5m = 0.0
    if hasattr(os, "getloadavg"):
        try:
            load_average_1m, load_average_5m, _ = os.getloadavg()
        except OSError:
            load_average_1m = 0.0
            load_average_5m = 0.0

    count_logical = os.cpu_count() or 1
    count_physical = count_logical
    cpu_usage_percent = min(100.0, round((load_average_1m / count_logical) * 100, 2))

    total_mb = 0
    available_mb = 0
    if hasattr(os, "sysconf"):
        try:
            page_size = os.sysconf("SC_PAGE_SIZE")
            physical_pages = os.sysconf("SC_PHYS_PAGES")
            available_pages = os.sysconf("SC_AVPHYS_PAGES")
            total_mb = int((page_size * physical_pages) / (1024 * 1024))
            available_mb = int((page_size * available_pages) / (1024 * 1024))
        except (OSError, ValueError):
            total_mb = 0
            available_mb = 0
    memory_used = max(0, total_mb - available_mb)
    memory_percent_used = round((memory_used / total_mb) * 100, 2) if total_mb else 0.0

    disk_usage = shutil.disk_usage("/")
    disk_total_gb = round(disk_usage.total / (1024 ** 3), 2)
    disk_free_gb = round(disk_usage.free / (1024 ** 3), 2)
    disk_percent_used = (
        round(((disk_usage.total - disk_usage.free) / disk_usage.total) * 100, 2)
        if disk_usage.total
        else 0.0
    )

    return {
        "uptime_seconds": uptime_seconds,
        "load_average_1m": round(load_average_1m, 2),
        "load_average_5m": round(load_average_5m, 2),
        "cpu": {
            "usage_percent": cpu_usage_percent,
            "count_logical": count_logical,
            "count_physical": count_physical,
        },
        "memory": {
            "total_mb": total_mb,
            "available_mb": available_mb,
            "percent_used": memory_percent_used,
            "memory_used": memory_used,
        },
        "disk": {
            "total_gb": disk_total_gb,
            "free_gb": disk_free_gb,
            "percent_used": disk_percent_used,
        },
    }


def borrowed_worker_peer_uuid(worker_id, worker_data, worker_heartbeats):
    heartbeat = worker_heartbeats.get(worker_id, {})
    return (
        heartbeat.get("origin_server_uuid")
        or worker_data.get("peer_uuid")
        or worker_data.get("original_master_id")
        or worker_data.get("original_master_address")
        or "unknown"
    )


def lent_worker_peer_uuid(worker_data):
    return (
        worker_data.get("borrower")
        or worker_data.get("peer_uuid")
        or worker_data.get("new_master_address")
        or "unknown"
    )


def build_farm_state_metrics(state, now=None):
    with state.lock:
        local_workers = set(state.local_workers)
        busy_workers = set(state.busy_workers)
        borrowed_workers = dict(state.borrowed_workers)
        lent_workers = dict(state.lent_workers)
        worker_heartbeats = dict(state.worker_heartbeats)
        worker_failures = state.worker_failures

    with state.task_manager.lock:
        tasks_pending = len(state.task_manager.tasks_todo)
        tasks_running = len(state.task_manager.tasks_doing)
        oldest_task_age_s = 0

    registered_workers = local_workers | set(borrowed_workers) | set(lent_workers)
    alive_workers = set(worker_heartbeats)
    idle_workers = alive_workers - busy_workers - set(lent_workers)
    workers_home = local_workers - set(lent_workers)

    tasks_completed = sum(1 for task in state.tasks_done if task.get("status") == "OK")
    tasks_failed = sum(1 for task in state.tasks_done if task.get("status") == "NOK")

    borrowed_worker_entries = []
    for worker_id, worker_data in sorted(lent_workers.items()):
        borrowed_worker_entries.append(
            {"direction": "out", "peer_uuid": lent_worker_peer_uuid(worker_data)}
        )
    for worker_id, worker_data in sorted(borrowed_workers.items()):
        borrowed_worker_entries.append(
            {
                "direction": "in",
                "peer_uuid": borrowed_worker_peer_uuid(worker_id, worker_data, worker_heartbeats),
            }
        )

    return {
        "workers": {
            "total_registered": len(registered_workers),
            "workers_utilization": len(busy_workers),
            "workers_alive": len(alive_workers),
            "workers_idle": len(idle_workers),
            "workers_borrowed": len(lent_workers),
            "workers_received": len(borrowed_workers),
            "workers_failed": worker_failures,
            "workers_home": len(workers_home),
            "workers_available_capacity": len(idle_workers),
            "borrowed_workers": borrowed_worker_entries,
        },
        "tasks": {
            "tasks_pending": tasks_pending,
            "tasks_running": tasks_running,
            "tasks_completed": tasks_completed,
            "tasks_failed": tasks_failed,
            "oldest_task_age_s": oldest_task_age_s,
        },
    }


def build_neighbor_metrics(state):
    with state.lock:
        peer_status = dict(state.peer_status)

    neighbors = []
    for peer_id in sorted(state.peers):
        status = peer_status.get(peer_id, {})
        neighbors.append(
            {
                "server_uuid": peer_id,
                "status": status.get("status", "unavailable"),
                "last_heartbeat": status.get("last_heartbeat"),
            }
        )
    return neighbors


def build_supervisor_payload(state, hostname=None, now=None, message_id=None):
    return {
        "server_uuid": state.master_uuid,
        "hostname": hostname or supervisor_hostname(state.master_uuid),
        "role": "master",
        "task": "performance_report",
        "timestamp": utc_timestamp(now),
        "message_id": message_id or str(uuid.uuid4()),
        "payload_version": SUPERVISOR_PAYLOAD_VERSION,
        "performance": {
            "system": collect_system_metrics(now),
            "farm_state": build_farm_state_metrics(state, now),
            "config_thresholds": {
                "max_task": state.capacity,
                "warn_cpu_percent": 85,
                "warn_memory_percent": 85,
                "release_task": state.release_threshold,
            },
            "neighbors": build_neighbor_metrics(state),
        },
    }


def send_supervisor_payload(
    payload,
    host=SUPERVISOR_HOST,
    port=SUPERVISOR_PORT,
    use_tls=True,
    sni=None,
    connector=socket.create_connection,
    timeout=NEGOTIATION_TIMEOUT,
):
    encoded_payload = (json.dumps(payload) + "\n").encode()
    with connector((host, port), timeout=timeout) as raw_sock:
        if use_tls:
            context = ssl.create_default_context()
            with context.wrap_socket(raw_sock, server_hostname=sni or host) as tls_sock:
                tls_sock.sendall(encoded_payload)
        else:
            raw_sock.sendall(encoded_payload)


def supervisor_metrics_loop():
    while True:
        try:
            payload = build_supervisor_payload(master_state)
            send_supervisor_payload(
                payload,
                host=SUPERVISOR_HOST,
                port=SUPERVISOR_PORT,
                use_tls=parse_bool(SUPERVISOR_TLS),
                sni=SUPERVISOR_SNI,
            )
            log_event("SUPERVISOR", f"Metricas enviadas para {SUPERVISOR_HOST}:{SUPERVISOR_PORT}")
        except (OSError, TimeoutError, ssl.SSLError, ValueError) as exc:
            log_event("SUPERVISOR", f"Falha ao enviar metricas: {exc}")
        time.sleep(SUPERVISOR_INTERVAL)


def start_supervisor_metrics(enabled=None, thread_factory=threading.Thread):
    should_start = parse_bool(SUPERVISOR_ENABLED if enabled is None else enabled)
    if not should_start:
        log_event("SUPERVISOR", "Envio de metricas desabilitado")
        return None

    thread = thread_factory(target=supervisor_metrics_loop, daemon=True)
    thread.start()
    return thread


def maybe_negotiate_help():
    negotiate_help_if_saturated(master_state, request_help_from_peer)


def calculate_workers_needed(state):
    overload = max(0, state.current_load() - state.capacity)
    return overload


def negotiate_help_if_saturated(state, requester):
    with state.lock:
        if state.help_request_pending:
            return False

    load = state.current_load()
    if load <= state.capacity or not state.peers:
        return False

    workers_needed = calculate_workers_needed(state)
    if workers_needed == 0:
        return False

    for peer_id, peer_address in state.peers.items():
        response = requester(peer_id, peer_address, load, workers_needed)
        if response and response.get("type") == "response_accepted":
            with state.lock:
                state.help_request_pending = True
            log_event("SATURATION", f"Saturated load={load}; help requested from {peer_id} for {workers_needed} workers")
            return True
    return False


def saturation_monitor_loop():
    while True:
        negotiate_help_if_saturated(master_state, request_help_from_peer)
        time.sleep(HELP_CHECK_INTERVAL)


def monitor_workers_loop():
    while True:
        now = time.time()
        expired = []
        with master_state.lock:
            for worker_uuid, heartbeat in list(master_state.worker_heartbeats.items()):
                if now - heartbeat["last_heartbeat"] > HEARTBEAT_TIMEOUT:
                    heartbeat["missed_intervals"] += 1
                    log_event(
                        "HEARTBEAT",
                        f"Worker {worker_uuid} missed heartbeat {heartbeat['missed_intervals']}/{MAX_MISSED_HEARTBEATS}",
                    )
                    if heartbeat["missed_intervals"] >= MAX_MISSED_HEARTBEATS:
                        expired.append(worker_uuid)
        for worker_uuid in expired:
            master_state.cleanup_dead_worker(worker_uuid)
        time.sleep(HEARTBEAT_CHECK_INTERVAL)


def start_monitoring_workers():
    thread = threading.Thread(target=monitor_workers_loop, daemon=True)
    thread.start()
    return thread


def start_saturation_monitor():
    thread = threading.Thread(target=saturation_monitor_loop, daemon=True)
    thread.start()
    return thread


def request_help_from_peer(peer_id, peer_address, current_load, workers_needed):
    request_id = str(uuid.uuid4())
    payload = {
        "master_id": MASTER_UUID,
        "MASTER_ID": MASTER_UUID,
        "current_load": current_load,
        "CURRENT_LOAD": current_load,
        "capacity": master_state.capacity,
        "CAPACITY": master_state.capacity,
        "workers_needed": workers_needed,
        "WORKERS_NEEDED": workers_needed,
        "return_address": format_address(HOST, PORT),
        "RETURN_ADDRESS": format_address(HOST, PORT),
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
            with master_state.lock:
                master_state.peer_status[peer_id] = {
                    "status": "available",
                    "last_heartbeat": utc_timestamp(),
                }
            return response
    except (OSError, TimeoutError, socket.timeout, ValueError) as exc:
        with master_state.lock:
            master_state.peer_status[peer_id] = {
                "status": "unavailable",
                "last_heartbeat": None,
            }
        log_event("M2M", f"Falha ao negociar com {peer_id}: {exc}")
        return None


def handle_request_help_message(state, request_id, payload):
    requester = ensure_string_alias(payload, "master_id", "MASTER_ID")
    workers_needed = ensure_int_alias(payload, "workers_needed", "WORKERS_NEEDED")
    return_address = get_payload_alias(payload, "return_address", "RETURN_ADDRESS")
    if not return_address and requester in state.peers:
        return_address = format_address(*state.peers[requester])

    offered_workers = state.available_local_workers(workers_needed)
    if not offered_workers:
        return build_master_message(
            "response_rejected",
            request_id,
            {"reason": "no_workers_available", "REASON": "no_workers_available"},
        )

    worker_details = []
    worker_details_upper = []
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
            worker_details_upper.append({"ID": worker_uuid, "ADDRESS": "dynamic"})

    return build_master_message(
        "response_accepted",
        request_id,
        {
            "workers_offered": len(worker_details),
            "worker_details": worker_details,
            "WORKERS_OFFERED": len(worker_details_upper),
            "WORKER_DETAILS": worker_details_upper,
        },
    )


def handle_heartbeat_message(state, request_id, payload):
    worker_uuid, origin_server_uuid = validate_worker_heartbeat(payload)
    state.update_worker_heartbeat(worker_uuid, origin_server_uuid)
    log_event("HEARTBEAT", f"Recebido heartbeat de {worker_uuid}")
    return build_master_message(
        "heartbeat_ack",
        request_id,
        {"worker_id": worker_uuid},
    )


def handle_notify_worker_dead_message(state, request_id, payload):
    worker_id = ensure_string_alias(payload, "worker_id", "WORKER_ID")
    source_server = ensure_string_alias(payload, "source_server", "SOURCE_SERVER")
    with state.lock:
        state.lent_workers.pop(worker_id, None)
        state.pending_redirects.pop(worker_id, None)
    log_event("NOTIFY", f"Worker morto notificado: {worker_id} de {source_server}")
    return build_master_message(
        "notify_worker_dead_ack",
        request_id,
        {"worker_id": worker_id},
    )


def handle_register_temporary_worker_message(state, request_id, payload):
    worker_id = ensure_string_alias(payload, "worker_id", "WORKER_ID")
    original_master_address = ensure_string_alias(
        payload,
        "original_master_address",
        "ORIGINAL_MASTER_ADDRESS",
    )

    with state.lock:
        state.borrowed_workers[worker_id] = {
            "original_master_address": original_master_address,
            "registered_at": timestamp(),
        }
        state.local_workers.discard(worker_id)
        state.help_request_pending = False

    log_event("BORROWED", f"Worker {worker_id} registrado de {original_master_address}")
    return build_master_message(
        "register_temporary_worker_ack",
        request_id,
        {"worker_id": worker_id, "WORKER_ID": worker_id},
    )


def handle_notify_worker_returned_message(state, request_id, payload):
    worker_id = ensure_string_alias(payload, "worker_id", "WORKER_ID")
    with state.lock:
        state.lent_workers.pop(worker_id, None)
        state.pending_redirects.pop(worker_id, None)
    log_event("RETURNED", f"Worker {worker_id} voltou ao {state.master_uuid}")
    return build_master_message(
        "notify_worker_returned_ack",
        request_id,
        {"worker_id": worker_id, "WORKER_ID": worker_id},
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
        {"worker_id": worker_id, "WORKER_ID": worker_id},
    )
    try:
        with socket.create_connection(parse_address(original_master_address), timeout=NEGOTIATION_TIMEOUT) as sock:
            sock.settimeout(NEGOTIATION_TIMEOUT)
            log_protocol("M2M OUT", "notify_worker_returned", request_id, f"worker={worker_id}")
            send_json(sock, message)
    except (OSError, TimeoutError, socket.timeout, ValueError) as exc:
        log_event("M2M", f"Falha ao notificar devolucao de {worker_id}: {exc}")


def notify_worker_dead(original_master_address, worker_id):
    request_id = str(uuid.uuid4())
    message = build_master_message(
        "notify_worker_dead",
        request_id,
        {
            "worker_id": worker_id,
            "WORKER_ID": worker_id,
            "source_server": MASTER_UUID,
            "SOURCE_SERVER": MASTER_UUID,
        },
    )
    try:
        with socket.create_connection(parse_address(original_master_address), timeout=NEGOTIATION_TIMEOUT) as sock:
            sock.settimeout(NEGOTIATION_TIMEOUT)
            log_protocol("M2M OUT", "notify_worker_dead", request_id, f"worker={worker_id}")
            send_json(sock, message)
    except (OSError, TimeoutError, socket.timeout, ValueError) as exc:
        log_event("M2M", f"Falha ao notificar worker morto {worker_id}: {exc}")


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
    elif message_type == "heartbeat":
        response = handle_heartbeat_message(master_state, request_id, message_payload)
        send_json(conn, response)
        log_protocol("M2M OUT", response["type"], response["request_id"])
    elif message_type == "notify_worker_dead":
        response = handle_notify_worker_dead_message(master_state, request_id, message_payload)
        send_json(conn, response)
        log_protocol("M2M OUT", response["type"], response["request_id"])
    else:
        log_event("M2M", f"Tipo desconhecido ignorado: {message_type}")


def handle_worker_presentation(conn, payload):
    worker_uuid, origin_server_uuid = validate_worker_handshake(payload)
    master_state.update_worker_heartbeat(worker_uuid, origin_server_uuid)

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
                "NEW_MASTER_ADDRESS": redirect["new_master_address"],
                "original_master_address": format_address(HOST, PORT),
                "ORIGINAL_MASTER_ADDRESS": format_address(HOST, PORT),
                "original_master_id": master_state.master_uuid,
                "ORIGINAL_MASTER_ID": master_state.master_uuid,
            },
        )
        send_json(conn, response)
        log_event("REDIRECT", f"Worker {worker_uuid} enviado para {redirect['new_master_address']}")
        return worker_uuid, None

    if release:
        response = build_master_message(
            "command_release",
            str(uuid.uuid4()),
            {
                "original_master_address": release["original_master_address"],
                "ORIGINAL_MASTER_ADDRESS": release["original_master_address"],
            },
        )
        send_json(conn, response)
        notify_worker_returned(release["original_master_address"], worker_uuid)
        with master_state.lock:
            master_state.borrowed_workers.pop(worker_uuid, None)
        log_event("RELEASE", f"Worker {worker_uuid} devolvido para {release['original_master_address']}")
        return worker_uuid, None

    queue_releases_if_needed(master_state)
    maybe_negotiate_help()
    next_task = master_state.assign_next_task(worker_uuid)

    if next_task:
        response = {"TASK": "QUERY", "USER": next_task}
    else:
        response = {"TASK": "NO_TASK"}

    log_event(
        "WORKER",
        f"{worker_uuid} apresentou-se ao {MASTER_UUID} como {worker_origin_label(origin_server_uuid)}",
    )
    if next_task:
        log_event("DISPATCH", f"{next_task} atribuido a Worker {worker_uuid}")
    else:
        log_event("QUEUE", f"Nenhuma tarefa disponivel para Worker {worker_uuid}")
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

    log_event(
        "TASK",
        f"Worker {worker_uuid} concluiu {current_task} com status {status}",
    )
    master_state.complete_worker_task(worker_uuid, status)
    send_json(conn, ack)


def tratar_cliente(conn, addr):
    buffer = ""
    current_worker_uuid = None
    current_task = None
    conn.settimeout(SOCKET_TIMEOUT)

    try:
        log_event("THREAD", f"Atendimento {addr}")

        while True:
            try:
                data = conn.recv(1024)
            except socket.timeout:
                log_event("TIMEOUT", f"Encerrando conexao inativa de {addr}")
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
                    log_event("REQ", f"{dados}")

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
                    log_event("PROTOCOLO", f"{addr}: {exc}")
                    send_json(conn, {"ERROR": "INVALID_PAYLOAD", "DETAIL": str(exc)})
    except Exception as exc:
        log_event("ERRO", f"{exc}")
    finally:
        requeued_task = None
        if current_worker_uuid is not None:
            requeued_task = master_state.requeue_worker_task(current_worker_uuid)
        if requeued_task is None and current_task is not None:
            push_task_front(current_task)
            requeued_task = current_task
        if requeued_task is not None:
            log_event(
                "REQUEUE",
                f"{requeued_task} retornou para a fila apos falha na conexao com Worker {current_worker_uuid or addr}",
            )
        log_event("THREAD", f"Encerrando {addr}")
        conn.close()


def iniciar_servidor():
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server_socket.bind((HOST, PORT))
    server_socket.listen(100)

    log_event("START", f"Servidor {MASTER_UUID} rodando em {HOST}:{PORT}")
    start_saturation_monitor()
    start_monitoring_workers()
    start_supervisor_metrics()

    while True:
        conn, addr = server_socket.accept()
        thread = threading.Thread(target=tratar_cliente, args=(conn, addr), daemon=True)
        thread.start()


if __name__ == "__main__":
    iniciar_servidor()
