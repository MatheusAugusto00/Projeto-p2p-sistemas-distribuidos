import socket
import json
import time

HOST = '127.0.0.1'
PORT = 8000

def enviar_heartbeat():
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((HOST, PORT))

            mensagem = {
                "SERVER_UUID": "Worker_A1",
                "TASK": "HEARTBEAT"
            }

            s.sendall((json.dumps(mensagem) + "\n").encode())

            resposta = s.recv(1024)

            if resposta:
                print("[RESPOSTA]:", resposta.decode().strip())

            s.close()

        except Exception as e:
            print("[ERRO]:", e)

        time.sleep(10)


if __name__ == "__main__":
    enviar_heartbeat()