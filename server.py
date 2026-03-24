import socket
import time
import threading
import json

HOST = '127.0.0.1'
PORT = 8000

def tratar_cliente(conn, addr):
    try:
        print(f"[THREAD] Iniciando atendimento para {addr}")
        
        time.sleep(5)

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

                print(f"[REQ {addr}]:", dados)

                if dados.get("TASK") == "HEARTBEAT":
                    resposta = {
                        "SERVER_UUID": "Master_A",
                        "TASK": "HEARTBEAT",
                        "RESPONSE": "ALIVE"
                    }

                    conn.sendall((json.dumps(resposta) + "\n").encode())
        
    except Exception as e:
        print(f"[ERRO] Falha na conexão com {addr}: {e}")
    finally:
        print(f"[THREAD] Fechando conexão com {addr}")
        conn.close()

def iniciar_servidor():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

    s.settimeout(1)
    
    try:
        s.bind((HOST, PORT))
        s.listen(100)
        print(f"Servidor ativo em {HOST}:{PORT}. Aguardando conexões...")

        while True:
            try:
                conn, addr = s.accept()
                print(f"\n[NOVA SESSÃO] Conectado por: {addr}")


                cliente_thread = threading.Thread(target=tratar_cliente, args=(conn, addr))
                
                cliente_thread.start()
                
                print(f"[INFO] Thread disparada. Servidor livre para nova conexão.")
            except socket.timeout:
                continue
    
    except Exception as e:
        print(f"[ERRO] Servidor: {e}")
    
    finally:
        s.close()

if __name__ == "__main__":
    try:
        iniciar_servidor()
    except KeyboardInterrupt:
        print("\n[SERVIDOR] Encerrando servidor...")



