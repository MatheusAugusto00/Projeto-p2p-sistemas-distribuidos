import json
import os
import random
import socket
import threading
import time
import uuid
from dataclasses import dataclass

HOST = os.getenv("MASTER_HOST", "192.168.1.187")
PORT = int(os.getenv("MASTER_PORT", "8000"))

WORKER_ID = os.getenv("WORKER_ID", f"W-{os.getpid()}")
SERVER_UUID = os.getenv("SERVER_UUID")
RECONNECT_DELAY = int(os.getenv("RECONNECT_DELAY", "5"))
MASTER_TIMEOUT = int(os.getenv("MASTER_TIMEOUT", "5"))
HEARTBEAT_INTERVAL = int(os.getenv("HEARTBEAT_INTERVAL", "2"))


@dataclass
class WorkerState:
    worker_id: str
    original_master_host: str
    original_master_port: int
    current_master_host: str = None
    current_master_port: int = None
    origin_server_uuid: str = None

    def __post_init__(self):
        if self.current_master_host is None:
            self.current_master_host = self.original_master_host
        if self.current_master_port is None:
            self.current_master_port = self.original_master_port

    @property
    def original_master_address(self):
        return format_address(self.original_master_host, self.original_master_port)


worker_state = WorkerState(
    worker_id=WORKER_ID,
    original_master_host=HOST,
    original_master_port=PORT,
    origin_server_uuid=SERVER_UUID,
)


def send_json(sock, payload):
    sock.sendall((json.dumps(payload) + "\n").encode())


def log_event(level, message):
    print(f"[{time.strftime('%Y-%m-%dT%H:%M:%S')}] [{level}] {message}")


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


def build_typed_message(message_type, payload):
    return {"type": message_type, "request_id": str(uuid.uuid4()), "payload": payload}


def receber_mensagem(sock):
    buffer = ""

    while "\n" not in buffer:
        data = sock.recv(1024)
        if not data:
            raise ConnectionError("Conexao encerrada antes do fim da mensagem")
        buffer += data.decode()

    raw_message, _ = buffer.split("\n", 1)
    return raw_message.strip()


def parse_server_message(raw_message):
    try:
        return json.loads(raw_message)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Mensagem JSON invalida: {exc}") from exc


def build_heartbeat_payload(state):
    payload = {
        "WORKER_UUID": state.worker_id,
    }
    if state.origin_server_uuid:
        payload["SERVER_UUID"] = state.origin_server_uuid
    return build_typed_message("heartbeat", payload)


def heartbeat_loop():
    while True:
        try:
            with socket.create_connection(
                (worker_state.current_master_host, worker_state.current_master_port),
                timeout=MASTER_TIMEOUT,
            ) as sock:
                sock.settimeout(MASTER_TIMEOUT)
                send_json(sock, build_heartbeat_payload(worker_state))
                raw = receber_mensagem(sock)
                resposta = parse_server_message(raw)
                log_event("HEARTBEAT", f"Heartbeat enviado a {worker_state.current_master_host}:{worker_state.current_master_port} - resposta {resposta}")
        except (ConnectionError, TimeoutError, socket.timeout, OSError, ValueError) as exc:
            log_event("HEARTBEAT", f"Falha ao enviar heartbeat: {exc}")
        time.sleep(HEARTBEAT_INTERVAL)


def montar_payload_apresentacao():
    return build_worker_presentation_payload(worker_state)


def build_worker_presentation_payload(state):
    payload = {"WORKER": "ALIVE", "WORKER_UUID": state.worker_id}
    if state.origin_server_uuid:
        payload["SERVER_UUID"] = state.origin_server_uuid
    return payload


def build_register_temporary_worker_payload(state):
    return build_typed_message(
        "register_temporary_worker",
        {
            "worker_id": state.worker_id,
            "original_master_address": state.original_master_address,
        },
    )


def apply_command_redirect(state, payload):
    new_master_address = payload.get("new_master_address")
    if not isinstance(new_master_address, str) or not new_master_address.strip():
        raise ValueError("command_redirect sem new_master_address valido")

    original_master_address = payload.get("original_master_address", state.original_master_address)
    if not isinstance(original_master_address, str) or not original_master_address.strip():
        raise ValueError("command_redirect sem original_master_address valido")

    original_master_id = payload.get("original_master_id")
    if original_master_id is not None and (
        not isinstance(original_master_id, str) or not original_master_id.strip()
    ):
        raise ValueError("command_redirect com original_master_id invalido")

    state.current_master_host, state.current_master_port = parse_address(new_master_address)
    state.original_master_host, state.original_master_port = parse_address(original_master_address)
    if original_master_id:
        state.origin_server_uuid = original_master_id.strip()
    elif not state.origin_server_uuid:
        state.origin_server_uuid = original_master_address
    return build_register_temporary_worker_payload(state)


def register_temporary_worker_best_effort(state, connector=socket.create_connection, logger=log_event):
    register_payload = build_register_temporary_worker_payload(state)
    try:
        with connector(
            (state.current_master_host, state.current_master_port),
            timeout=MASTER_TIMEOUT,
        ) as register_sock:
            register_sock.settimeout(MASTER_TIMEOUT)
            send_json(register_sock, register_payload)
            register_ack = parse_server_message(receber_mensagem(register_sock))
    except (ConnectionError, TimeoutError, socket.timeout, OSError, ValueError) as exc:
        logger(
            "REGISTER",
            f"Registro temporario sem ACK padronizado; seguindo para apresentacao Sprint 2: {exc}",
        )
        return False

    if register_ack.get("type") == "register_temporary_worker_ack":
        logger("REGISTER", f"ACK de registro temporario recebido: {register_ack}")
        return True

    logger(
        "REGISTER",
        f"Resposta de registro temporario nao padronizada; seguindo para apresentacao Sprint 2: {register_ack}",
    )
    return False


def apply_command_release(state, payload):
    original_master_address = payload.get("original_master_address", state.original_master_address)
    if not isinstance(original_master_address, str) or not original_master_address.strip():
        raise ValueError("command_release sem original_master_address valido")

    state.current_master_host, state.current_master_port = parse_address(original_master_address)
    state.original_master_host, state.original_master_port = parse_address(original_master_address)
    state.origin_server_uuid = None


def validar_resposta_inicial(payload):
    if payload.get("type") in {"command_redirect", "command_release"}:
        return payload["type"]
    task = payload.get("TASK")
    if task == "QUERY":
        if not isinstance(payload.get("USER"), str) or not payload["USER"].strip():
            raise ValueError("Payload QUERY sem campo USER valido")
        return task
    if task == "NO_TASK":
        return task
    if payload.get("ERROR"):
        raise ValueError(f"Master rejeitou a mensagem: {payload}")
    raise ValueError(f"Resposta inicial inesperada: {payload}")


def validar_ack(payload):
    if payload.get("STATUS") != "ACK":
        raise ValueError(f"ACK invalido: {payload}")
    if payload.get("WORKER_UUID") != worker_state.worker_id:
        raise ValueError(f"ACK destinado a outro worker: {payload}")


def worker_loop():
    while True:
        try:
            with socket.create_connection(
                (worker_state.current_master_host, worker_state.current_master_port),
                timeout=MASTER_TIMEOUT,
            ) as sock:
                sock.settimeout(MASTER_TIMEOUT)
                print(
                    f"[WORKER {worker_state.worker_id}] Conectado ao Master "
                    f"{worker_state.current_master_host}:{worker_state.current_master_port}"
                )

                apresentacao = montar_payload_apresentacao()
                send_json(sock, apresentacao)

                resposta = parse_server_message(receber_mensagem(sock))
                log_event("MASTER", f"Resposta recebida: {resposta}")

                task = validar_resposta_inicial(resposta)
                if task == "command_redirect":
                    apply_command_redirect(worker_state, resposta["payload"])
                    log_event(
                        "REDIRECT",
                        f"Worker {worker_state.worker_id} indo para {worker_state.current_master_host}:{worker_state.current_master_port}",
                    )
                    register_temporary_worker_best_effort(worker_state)
                    continue
                if task == "command_release":
                    apply_command_release(worker_state, resposta["payload"])
                    log_event(
                        "RELEASE",
                        f"Worker {worker_state.worker_id} voltando para {worker_state.current_master_host}:{worker_state.current_master_port}",
                    )
                    continue
                if task == "NO_TASK":
                    log_event("WORKER", f"{worker_state.worker_id} sem tarefa disponivel")
                    time.sleep(3)
                    continue

                current_task = resposta["USER"]
                log_event("WORKER", f"{worker_state.worker_id} processando tarefa {current_task}")
                time.sleep(random.randint(1, 3))

                status = {
                    "STATUS": random.choice(["OK", "NOK"]),
                    "TASK": "QUERY",
                    "WORKER_UUID": worker_state.worker_id,
                    "USER": current_task,
                }

                send_json(sock, status)

                ack = parse_server_message(receber_mensagem(sock))
                validar_ack(ack)
                log_event("ACK", f"Task {current_task} confirmada {ack}")
        except (ConnectionError, TimeoutError, socket.timeout) as exc:
            log_event("CONNECTION", f"{exc}")
        except ValueError as exc:
            log_event("PROTOCOLO", f"{exc}")
        except OSError as exc:
            log_event("SOCKET", f"{exc}")
        except Exception as exc:
            log_event("ERRO", f"{exc}")

        log_event("RECONNECT", f"Nova tentativa em {RECONNECT_DELAY} segundos")
        time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    heartbeat_thread = threading.Thread(target=heartbeat_loop, daemon=True)
    heartbeat_thread.start()
    worker_loop()
