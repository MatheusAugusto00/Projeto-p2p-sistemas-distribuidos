import socket
import json
import time

HOST = '10.62.217.213'
PORT = 8000

def enviar_heartbeat():
    while True:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.connect((HOST, PORT))

            mensagem = {
                "SERVER_UUID": "MASTER_4",
                "TASK": "HEARTBEAT"
            }

            s.sendall((json.dumps(mensagem) + "\n").encode())

            resposta = s.recv(1024)

            if resposta:
                try:
                    resposta_str = resposta.decode().strip()
                    resposta_json = json.loads(resposta_str)

                    print("[RESPOSTA]:")
                    print(json.dumps(resposta_json, indent=4, ensure_ascii=False) + "\n")

                except json.JSONDecodeError:
                    print("[RESPOSTA NÃO É JSON]:", resposta.decode().strip())

            s.close()

        except Exception as e:
            print("[ERRO]:", e)

        time.sleep(10)


if __name__ == "__main__":
    enviar_heartbeat()