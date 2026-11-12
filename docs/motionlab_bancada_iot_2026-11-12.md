# Ensaio Wi-Fi/MQTT na bancada — 12/11/2026

Este registro atualiza a situação física descrita na [Fase E](motionlab_fase_e.md), que era uma auditoria de software. A bancada usou a ESP32 e os dois sensores, rede Wi-Fi residencial de 2,4 GHz, broker Mosquitto no WSL e encaminhador no Windows. O broker exigiu autenticação e TLS; o envio usou QoS 1.

## Resultados observados

- A ESP32 conectou ao Wi-Fi e ao broker e publicou amostras que o consumidor persistiu em SQLite isolado. A origem dos registros é `real_hardware`; uma das amostras observadas indicava ultrassom e IR válidos. O diagnóstico da placa indicou `online` e confirmações de publicação.
- O certificado inicialmente não foi aceito pela biblioteca TLS embarcada. O certificado do servidor passou a conter o endereço tanto em SAN de IP quanto em SAN de nome, mantendo a mesma CA e a verificação do servidor; após o ajuste a placa conectou por TLS. O provisionador gera certificados compatíveis com ambos os tipos de cliente.
- No intervalo padrão de aquisição de **70 ms**, foram recebidas 183 amostras em 20 segundos e houve 80 novos descartes na placa. Em outra tentativa, um ajuste experimental no broker não resolveu o problema e foi revertido. Esses descartes são distintos dos acumulados durante as primeiras tentativas de conexão.
- Com `PERIOD 150`, temporário e aplicado por comando serial, foram recebidas 183 amostras em uma janela de 25 segundos, sem novos descartes na janela observada. Esse ajuste também afeta o USB e a frequência de atualização da interface; não é garantia de desempenho dos gestos nem de entrega durante desconexões.
- Uma versão ajustada, gravada e testada na placa, reduziu a espera entre a confirmação e o próximo envio, preservando QoS 1 e uma publicação pendente. Em 30 segundos a **70 ms**, recebeu 394 amostras e registrou 40 novos descartes: melhor que o primeiro ensaio, mas ainda insuficiente para garantir a taxa original.
- Na mesma versão, com `PERIOD 90`, foram recebidas **334 amostras em 30 segundos, sem novos descartes** nessa janela. O diagnóstico indicou `online`, fila de 1/32 e nenhum erro de publicação no momento da consulta. O intervalo é temporário: após reiniciar, o firmware volta ao padrão de 70 ms.
- Uma versão posterior manteve o polling mais rápido e desativou o modem-sleep Wi-Fi, com maior consumo de energia. No padrão de **70 ms**, foram persistidas **432 amostras em 30 segundos, sem novos descartes** nessa janela. Após reiniciar brevemente o broker, a ESP32 voltou ao estado `online`; em uma janela subsequente de 20 segundos, chegaram 291 amostras sem aumento do contador. O diagnóstico mostrava fila 1/32, uma reconexão, zero erros de publicação e 89 descartes acumulados na sessão. Não se mediu quantos ocorreram exatamente durante o reinício.

O backup integral da flash anterior à gravação foi lido e validado pelo esptool; ele e a configuração privada estão em `ops/iot/local/`, ignorado pelo Git. O arquivo compilado incorpora credenciais e também deve permanecer privado. A evidência bruta deste ensaio está na pasta local de bancada dentro de `ops/iot/local/`; os dados não são incluídos automaticamente no repositório nem no corpus de treinamento.

## Limites e próximos passos

- Repetir os testes em janelas mais longas e após desconexões prolongadas e reinício da placa; uma fila volátil pode descartar amostras durante quedas. Os testes sem novos descartes cobrem apenas as janelas informadas, não garantem perda zero.
- A comunicação física demonstrada não mede precisão dos sensores, desempenho dos modelos ou qualidade dos gestos. O campo `physical_validation=pending` continua apropriado para a validação abrangente.
- O certificado usa o IP do notebook no momento da preparação. Se o IP mudar, é necessário atualizar o certificado e a configuração com cuidado; não desabilitar a verificação TLS.
- Verificar reconexão, reinício e funcionamento em condições de uso. A rede local e o firewall podem exigir configuração específica. Não abrir portas no roteador.
