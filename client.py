import json
import os
import random
import socket
import time

HOST = os.getenv("MASTER_HOST", "10.62.217.40")
PORT = int(os.getenv("MASTER_PORT", "8000"))

WORKER_ID = os.getenv("WORKER_ID", f"W-{os.getpid()}")
SERVER_UUID = os.getenv("SERVER_UUID")
RECONNECT_DELAY = int(os.getenv("RECONNECT_DELAY", "5"))
MASTER_TIMEOUT = int(os.getenv("MASTER_TIMEOUT", "5"))


def send_json(sock, payload):
    sock.sendall((json.dumps(payload) + "\n").encode())


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


def montar_payload_apresentacao():
    payload = {"WORKER": "ALIVE", "WORKER_UUID": WORKER_ID}
    if SERVER_UUID:
        payload["SERVER_UUID"] = SERVER_UUID
    return payload


def validar_resposta_inicial(payload):
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
    if payload.get("WORKER_UUID") != WORKER_ID:
        raise ValueError(f"ACK destinado a outro worker: {payload}")


def worker_loop():
    while True:
        try:
            with socket.create_connection((HOST, PORT), timeout=MASTER_TIMEOUT) as sock:
                sock.settimeout(MASTER_TIMEOUT)
                print(f"[WORKER {WORKER_ID}] Conectado ao Master")

                apresentacao = montar_payload_apresentacao()
                send_json(sock, apresentacao)

                resposta = parse_server_message(receber_mensagem(sock))
                print("[MASTER]:", resposta)

                task = validar_resposta_inicial(resposta)
                if task == "NO_TASK":
                    print(f"[WORKER {WORKER_ID}] Nenhuma tarefa disponivel.")
                    time.sleep(3)
                    continue

                current_task = resposta["USER"]
                print(f"[WORKER {WORKER_ID}] Processando tarefa para usuario {current_task}...")
                time.sleep(random.randint(1, 3))

                status = {
                    "STATUS": random.choice(["OK", "NOK"]),
                    "TASK": "QUERY",
                    "WORKER_UUID": WORKER_ID,
                    "USER": current_task,
                }

                send_json(sock, status)

                ack = parse_server_message(receber_mensagem(sock))
                validar_ack(ack)
                print(f"[ACK] Task {current_task} confirmada:", ack)
        except (ConnectionError, TimeoutError, socket.timeout) as exc:
            print(f"[TIMEOUT/CONEXAO]: {exc}")
        except ValueError as exc:
            print(f"[PROTOCOLO]: {exc}")
        except OSError as exc:
            print(f"[ERRO DE SOCKET]: {exc}")
        except Exception as exc:
            print(f"[ERRO]: {exc}")

        print(f"[WORKER {WORKER_ID}] Nova tentativa em {RECONNECT_DELAY} segundos.")
        time.sleep(RECONNECT_DELAY)


if __name__ == "__main__":
    worker_loop()
