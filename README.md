# Arquitetura-de-Sistemas-Distribuidos
Projeto para a aula Arquitetura de Sistemas Distribuídos de 2026 do sétimo semestre de Ciência da Computação CEUB.

Task 1:
Implementei a infraestrutura de comunicação TCP entre um nó Master e um Worker utilizando sockets em Python. O Master atua como servidor concorrente, utilizando threads para atender múltiplos clientes simultaneamente, enquanto o Worker atua como cliente enviando requisições. Foi desenvolvido um mecanismo de escuta contínua e tratamento de mensagens, além do uso de timeout para evitar bloqueios e permitir o encerramento seguro do servidor.

Sobre essa infraestrutura, implementei um protocolo de comunicação baseado em JSON sobre TCP, utilizando o delimitador de nova linha (\n) para segmentação correta das mensagens no stream. O servidor realiza o processamento das mensagens por meio de um buffer, identificando requisições do tipo HEARTBEAT e respondendo adequadamente, garantindo a verificação de disponibilidade entre os nós do sistema distribuído.
