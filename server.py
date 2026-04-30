import json
import os
import socket
import threading

HOST = os.getenv("MASTER_HOST", "127.0.0.1")
PORT = int(os.getenv("MASTER_PORT", "8000"))
MASTER_UUID = os.getenv("MASTER_UUID", "Master_A")
SOCKET_TIMEOUT = int(os.getenv("MASTER_SOCKET_TIMEOUT", "10"))

task_queue = [f"Task{i}" for i in range(1, 51)]
task_queue_lock = threading.Lock()


def send_json(conn, payload):
    conn.sendall((json.dumps(payload) + "\n").encode())


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
    with task_queue_lock:
        if not task_queue:
            return None
        return task_queue.pop(0)


def push_task_front(task_name):
    with task_queue_lock:
        task_queue.insert(0, task_name)


def worker_origin_label(origin_server_uuid):
    if origin_server_uuid and origin_server_uuid != MASTER_UUID:
        return f"EMPRESTADO de {origin_server_uuid}"
    return "LOCAL"


def handle_worker_presentation(conn, payload):
    worker_uuid, origin_server_uuid = validate_worker_handshake(payload)
    next_task = pop_next_task()

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

                    if "WORKER" in dados:
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
        if current_task is not None:
            push_task_front(current_task)
            print(
                f"[REQUEUE] {current_task} retornou para a fila apos falha na conexao "
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

    while True:
        conn, addr = server_socket.accept()
        thread = threading.Thread(target=tratar_cliente, args=(conn, addr), daemon=True)
        thread.start()


if __name__ == "__main__":
    iniciar_servidor()
