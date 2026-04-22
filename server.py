import socket
import threading
import json

HOST = '127.0.0.1'
PORT = 8000

task_queue = [f"Task{i}" for i in range(1, 1001)]

def tratar_cliente(conn, addr):
    try:
        print(f"[THREAD] Atendimento {addr}")

        buffer = ""

        while True:
            data = conn.recv(1024)
            if not data:
                break

            buffer += data.decode()

            while "\n" in buffer:
                mensagem, buffer = buffer.split("\n", 1)

                if mensagem.strip() == "":
                    continue

                dados = json.loads(mensagem)
                print("[REQ]:", dados)

                if dados.get("WORKER") == "ALIVE":
                    
                    if task_queue:
                        user = task_queue.pop(0)
                        resposta = {
                            "TASK": "QUERY",
                            "USER": user
                        }
                    else:
                        resposta = {
                            "TASK": "NO_TASK"
                        }

                    conn.sendall((json.dumps(resposta) + "\n").encode())

                elif dados.get("STATUS") in ["OK", "NOK"]:
                    print("[STATUS RECEBIDO]:", dados)

                    ack = {
                        "STATUS": "ACK",
                        "WORKER_UUID": dados.get("WORKER_UUID")
                    }

                    conn.sendall((json.dumps(ack) + "\n").encode())

    except Exception as e:
        print("[ERRO]:", e)

    finally:
        print(f"[THREAD] Encerrando {addr}")
        conn.close()


def iniciar_servidor():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    s.bind((HOST, PORT))
    s.listen(100)

    print(f"Servidor rodando em {HOST}:{PORT}")

    while True:
        conn, addr = s.accept()
        thread = threading.Thread(target=tratar_cliente, args=(conn, addr))
        thread.start()


if __name__ == "__main__":
    iniciar_servidor()

