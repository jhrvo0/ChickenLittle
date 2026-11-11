# Checklist da montagem conjunta — LCD I²C

> **Aviso (10/11/2026):** o LCD saiu da montagem; os itens de LCD/I²C abaixo são históricos. Montagem vigente: [bench_verified_wiring.md](bench_verified_wiring.md).

Siga o [guia atual](bench_assembly_guide.md) ou o [passo a passo visual](../hardware/guia_montagem_final.html). Os três componentes já funcionaram separadamente conforme relato do usuário; os itens abaixo continuam sem confirmação para o conjunto. Status formal: `PENDING_PHYSICAL_VALIDATION`.

Registro de 10/11/2026: comunicação da ESP32 isolada verificada fisicamente na COM3 após a correção da recepção USB e da consulta durante o boot. Duas capturas aprovadas, com 37 e 36 quadros de sensores, aproximadamente 14,28 Hz, zero erros JSONL e zero lacunas de sequência em ambas. Os valores de sensores desconectados não validam periféricos. O teste conjunto continua pendente.

Diagnóstico posterior do LCD: usuário relatou backlight aceso com apenas alimentação direta, mas sem texto após ligar SDA/SCL. Com os quatro fios, DIAG ficou sem resposta e a tentativa de gravar o scanner informou falha de comunicação com a flash. Após o usuário retirar todos os fios externos, o firmware integrado foi restaurado na COM3 com BOOT pressionado; upload concluído com hash verificado. Depois de soltar BOOT, ESP32 isolada aprovada com 37 quadros, 14,29 Hz, zero erros JSONL e zero lacunas. O scanner não chegou a ser validado. Conferir foto/serigrafia e posição real da placa antes de reutilizar os furos indicados para SDA/SCL; a causa física ainda não foi confirmada.

- [x] Comunicação da ESP32 isolada na COM3 e firmware integrado `0.5.0-cycle5` verificados nas duas capturas registradas.

- [ ] Duas protoboards: + da P1=5V, + da P2=3V3, − de ambas unidos por F4. Somente o primeiro grupo de cinco furos de cada trilho em uso; continuidade conferida com USB fora.
- [ ] USB fora para montar; serigrafia da ESP32 coincide com os furos do guia, ou conexões foram feitas por nome do pino.
- [ ] R1=1 kΩ entre ECHO e nó; R2=1 kΩ + R3=300 Ω em série entre nó e GND. Resistores conferidos soltos.
- [ ] Ensaio estático do divisor feito sem HC-SR04 e sem GPIO34; nó dentro do limite. Tensão medida: ______ V. Jumper temporário retirado.
- [ ] HC-SR04: VCC=5V, GND comum, TRIG=GPIO5, ECHO ao divisor e nó protegido ao GPIO34.
- [ ] TCRT5000: VCC=3V3, GND comum, DO=GPIO35; AO desconectado.
- [ ] LCD: somente os quatro pinos do backpack; VCC=3V3, GND comum, SDA=GPIO21, SCL=GPIO22. Nenhum fio adicional nos 16 contatos.
- [ ] 5V, 3V3 e GND separados; sem curto ou pernas expostas se tocando. Fios da montagem antiga removidos.
- [ ] Alimentação medida: 5V=______ V; 3V3=______ V; VCC do backpack=______ V.
- [ ] Firmware completo da pasta `firmware` gravado na porta real: ______.
- [ ] Botões do guia executados na ordem ESP32 → LCD → TCRT5000 → HC-SR04 → conjunto, com a porta física e medições reais.
- [ ] Distância acompanha alvo em 20 e 40 cm, IR alterna com cartão e LCD permanece legível, tudo ligado ao mesmo tempo.
- [ ] LCD físico comparado com o quadro serial. Se usado o assistente: etapa D padrão I²C com tensão real, `--i2c-wiring-confirmed` e `--visual-confirmed` somente após a conferência.

Observações, falhas e ajustes: ________________________________________________

Um multímetro comum não mede necessariamente o pico de ECHO; registre à parte se houver medição com instrumento adequado. A alternativa LCD em 5 V exige conversor I²C bidirecional e outro registro elétrico; não basta trocar a alimentação. Testes simulados e build não confirmam fiação nem imagem no LCD físico. Coleta TinyML: [guia de dados reais](real_data_collection_guide.md).

Histórico recuperado: o teste LCD de 05/11 usou GND=6J, VCC=19J (3V3), SDA=14A e SCL=17A, scanner 0x27 e texto confirmado pelo usuário antes da troca posterior para 5 V. A revisão 3 retorna ao GND6J e não usa 2J. Fonte e distinção entre os testes em [bench_verified_wiring.md](bench_verified_wiring.md). A montagem atual ainda aguarda repetição; não atribuir a falha a 2J sem evidência adicional.
