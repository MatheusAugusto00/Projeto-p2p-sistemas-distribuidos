import socket
import json
import time
import random

HOST = '127.0.0.1'
PORT = 8000

WORKER_ID = "W-123"

def receber_mensagem(sock):
    buffer = ""
    while "\n" not in buffer:
        data = sock.recv(1024)
        if not data:
            break
        buffer += data.decode()
    return buffer.strip()


def worker_loop():
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((HOST, PORT))

            print("[WORKER] Conectado ao Master")


            mensagem = {
                "WORKER": "ALIVE",
                "WORKER_UUID": WORKER_ID
            }

            s.sendall((json.dumps(mensagem) + "\n").encode())


            resposta = receber_mensagem(s)

            if resposta:
                dados = json.loads(resposta)
                print("[MASTER]:", dados)

                if dados.get("TASK") == "QUERY":
                    print("[WORKER] Processando tarefa...")

                    time.sleep(random.randint(1, 3))

                    status = {
                        "STATUS": "OK",
                        "TASK": "QUERY",
                        "WORKER_UUID": WORKER_ID
                    }

                    s.sendall((json.dumps(status) + "\n").encode())


                    ack = receber_mensagem(s)
                    print("[ACK]:", ack)

                elif dados.get("TASK") == "NO_TASK":
                    print("[WORKER] Nenhuma tarefa disponível.")

            s.close()

        except Exception as e:
            print("[ERRO]:", e)

        time.sleep(5)


if name == "main":
    worker_loop()