# Montagem simples do MotionPet — duas protoboards e testes no guia

**Escopo atualizado: sem LCD.** O usuário optou por ESP32, HC-SR04, TCRT5000 e terminal. Consulte [o registro atual](../hardware/wokwi/montagem_atual/README.md) e [o desenho sem LCD](../hardware/wokwi/montagem_atual/diagram_sem_lcd.json). As etapas abaixo conservam o roteiro anterior com LCD e não devem ser confundidas com essa nova configuração.

**Revisão 4, 10/11/2026 — GND em 6J e diagnóstico com os fios existentes.** Abra o [guia visual](../hardware/guia_montagem_final.html). A montagem normal abaixo continua em 3,3 V para o LCD; o teste temporário em 5 V está separado e exige retirar SDA/SCL. Para habilitar os botões de teste pela USB, rode na raiz do projeto:

```powershell
.\.venv\Scripts\python.exe -m terminal.bench.guide
```

Depois abra [o guia com testes locais](http://127.0.0.1:8766/). Ele oferece **Testar ESP32 → Testar LCD → Testar TCRT5000 → Testar HC-SR04 → Testar conjunto**, após cada instalação. O arquivo HTML também mostra os passos sem o serviço; os testes pela USB precisam do serviço aberto. Ctrl+C no terminal encerra o serviço. Ele só escuta em 127.0.0.1 e não grava firmware automaticamente.

**Se F1–F4 e o LCD já estão instalados, mantenha os fios e retome em Teste o LCD antes de continuar.** Para a luz instável/apagada, use o diagnóstico desse passo. As instruções de retirar fios e testar a ESP32 sozinha são para começar do zero.

Os três componentes funcionaram individualmente segundo o usuário. O histórico do LCD foi recuperado: 6J=GND, 19J=3V3, 14A=SDA e 17A=SCL, com scanner em 0x27 e texto confirmado em 05/11. Veja [o registro dos testes anteriores](bench_verified_wiring.md). A montagem conjunta permanece **`PENDING_INTEGRATED_PHYSICAL_VALIDATION`**. O firmware e as pinagens de sinais continuam os mesmos. A revisão muda a organização física e acrescenta testes guiados; ela não demonstra, por software, a tensão ou o contato da montagem real.

## 1. O que fica em cada placa

Chame a placa da ESP32 de **P1** e a outra de **P2**. Cada uma tem um par +/− nas duas laterais. Vamos usar **um par por placa**, junto à fileira J, para reduzir pontes e facilitar a conferência. O par da lateral oposta fica sem fios.

| Local | Uso |
|---|---|
| P1, trilho + escolhido | **5 V**, para o HC-SR04 |
| P1, trilho − escolhido | **GND** |
| P2, trilho + escolhido | **3,3 V**, para LCD e TCRT5000 |
| P2, trilho − escolhido | **GND**, unido ao − da P1 por um jumper |
| Região central da P2 | Divisor do ECHO, afastado dos pinos da ESP32 |

**Não faça ponte entre os dois +:** um tem 5 V, o outro 3,3 V. A linha vermelha e o sinal + indicam polaridade, não uma tensão fixa. Encaixar as protoboards uma na outra não conecta seus trilhos.

Em cada trilho, use apenas o **primeiro grupo de cinco furos**, contado a partir do lado da linha 1. Confira continuidade dentro desse grupo com a USB desligada. Assim não dependemos de continuidade até o meio, outro lado ou outra protoboard.

No guia, `P1:+1` significa primeiro furo desse grupo no + da P1; `P1:−2` significa segundo furo no − da P1; `P2:+3` significa terceiro no + da P2. Esses nomes são do guia, não números impressos da placa. `P2:12A` é um furo da região central da segunda placa e **não** pertence ao trilho lateral.

## 2. Separe as peças

Para começar do zero, com a USB fora, retire os fios externos da versão anterior. Mantenha a ESP32 na P1 e os módulos fora das placas, ligados por cabos, com a face dos sensores livre e o LCD apoiado sem encostar em metal. Separe 11 jumpers fêmea–macho, 6 macho–macho e multímetro. Reserve dois resistores de **1 kΩ** e um de **300 Ω** para o ultrassom; os primeiros testes de LCD e IR não os usam.

O guia de furos da ESP32 considera a NODEMCU ESP-32S de 38 pinos registrada no projeto, USB para a linha 1, pinos em B/I e A/J livres. Só use os furos se a **serigrafia coincidir**:

| Pino | Furo livre na P1 |
|---|---|
| 5V | P1:1J |
| GND usado no teste do LCD | **P1:6J** |
| 3V3 | P1:19J |
| IO5 / GPIO5 | P1:10A |
| IO34 / GPIO34 | P1:15J |
| IO35 / GPIO35 | P1:14J |
| IO21 / GPIO21 | P1:14A |
| IO22 / GPIO22 | P1:17A |

A–E e F–J de mesmo número são duas tiras separadas. A P2 tem numeração própria. Não coloque fios sob a ESP32 ou duas pontas no mesmo furo.

## 3. Teste a ESP32 isolada

Conecte somente a ESP32, escolha a porta no guia e clique em **Testar ESP32**. A ferramenta espera o firmware integrado com JSON Lines e comando DIAG. Se a placa ainda estiver com um dos programas `teste-lcd`/`teste-hcsr04`, feche monitores seriais e grave uma vez o programa completo, substituindo COMx pela porta listada:

```powershell
.\.venv\Scripts\python.exe -m platformio run -d firmware -t upload --upload-port COMx
```

Se ficar em Connecting, segure BOOT durante a conexão e solte ao iniciar a gravação. Depois repita o teste no guia. Falta de ultrassom nessa fase é esperada e não reprova a comunicação da placa. Tire a USB antes de instalar os fios seguintes.

Abrir a porta pode reiniciar a ESP32: a consulta DIAG é repetida dentro do prazo para não depender de um comando enviado durante o boot. A recepção guarda fragmentos USB até o fim de cada linha JSON. Se atualizar o código Python do serviço ou transporte com o serviço aberto, encerre-o com Ctrl+C e execute novamente `python.exe -m terminal.bench.guide` pelo ambiente do projeto. O serviço da revisão 4 lê o HTML gerado a cada acesso: futuras alterações somente no guia precisam apenas de nova geração e F5, sem reiniciar o Python.

## 4. Distribua a alimentação e confira

| Fio | Origem | Destino |
|---|---|---|
| F1 | ESP32 5V — P1:1J | P1:+1 |
| F2 | ESP32 GND — **P1:6J** | P1:−1 |
| F3 | ESP32 3V3 — P1:19J | P2:+1 |
| F4 | P1:−2 | P2:−1 |

Ligue USB apenas para medir: na P1, preta em −4 e vermelha em +3 deve dar aproximadamente 5 V; na P2, preta em −5 e vermelha em +4 deve dar aproximadamente 3,3 V. Veja os limites em [segurança elétrica](hardware_safety.md). Se faltar tensão, corrija os quatro fios antes dos módulos. Desligue USB para continuar.

## 5. LCD — somente jumpers, depois teste

| Fio | Pino do backpack | Destino |
|---|---|---|
| F14 | VCC | P2:+3 — 3,3 V |
| F15 | GND | P2:−3 |
| F16 | SDA | GPIO21 — P1:14A |
| F17 | SCL | GPIO22 — P1:17A |

Use somente os quatro pinos do backpack, identificados na peça. Os 16 contatos já estão ligados ao adaptador; não acrescente fios de RW/RS/E/D4–D7, R4/R5 ou potenciômetro externo. O trimpot azul do backpack ajusta contraste e seu jumper habilita o backlight. Sem conversor de nível, VCC fica em **3V3**, não em 5 V.

Conecte USB e observe primeiro a iluminação. **Se a luz de trás pisca ou a frente fica apagada, desligue USB e faça o diagnóstico abaixo antes de continuar.** Com a iluminação estável, use **Testar LCD** na montagem normal de 3V3. Meça VCC/GND no próprio adaptador e informe a leitura. O guia mostra as quatro linhas enviadas pelo firmware. Ajuste contraste e confirme a imagem física somente depois de compará-la. A serial, sozinha, não prova que a tela acendeu. Depois do teste, tire USB.

### Luz do LCD instável ou apagada — diagnóstico temporário

Abra [diretamente o diagnóstico de iluminação](http://127.0.0.1:8766/#lcd-power) ou, no passo **Teste o LCD**, use **Luz do LCD instável ou apagada: ver diagnóstico**. O desenho muda para mostrar o teste de iluminação, e o teste I²C fica bloqueado. A página conserva esse aviso após recarregar até você declarar a volta à ligação de 3,3 V. Este procedimento ainda precisa ser feito fisicamente; abrir a página não muda a alimentação.

**Não desmonte os fios de alimentação já posicionados.** Eles continuam:

| Fio | Origem | Destino | Ação |
|---|---|---|---|
| F1 | P1:1J — 5 V | P1:+1 | Manter |
| F2 | P1:6J — GND | P1:−1 | Manter |
| F3 | P1:19J — 3V3 | P2:+1 | Manter |
| F4 | P1:−2 | P2:−1 | Manter |

Com **USB desligado**, retire os cabos **F16/SDA e F17/SCL por inteiro**. Depois mude somente as pontas macho dos dois cabos de alimentação do LCD:

| Cabo | Sai de | Vai temporariamente para |
|---|---|---|
| F14 — VCC do LCD | P2:+3 | **P1:+3 — trilho de 5 V** |
| F15 — GND do LCD | P2:−3 | **P1:−4 — trilho GND** |

As pontas do lado do adaptador continuam em VCC/GND. Não tente inserir uma segunda ponta em 1J, 6J ou 19J: esses furos já são usados por F1/F2/F3. P1:+3 e P1:−4 ficam livres no circuito normal; não pode haver jumper temporário de ensaio nesses contatos. Os demais fios e resistores já posicionados ficam onde estão. Não adicione novos componentes durante o diagnóstico.

Conecte USB apenas para observar se a luz POWER estabiliza e se a iluminação frontal acende. Sem SDA/SCL não esperamos texto nem executamos o botão de teste LCD. Se a alimentação continuar instável, desligue e confira contatos/cabos e a tensão medida em VCC/GND do adaptador. Se só funcionar em 5 V, a comunicação nesse perfil exige conversor I²C.

**Para voltar:** desligue USB, devolva F14 de P1:+3 para **P2:+3 (3V3)** e F15 de P1:−4 para **P2:−3**. Só depois recoloque F16/SDA em P1:14A e F17/SCL em P1:17A. Marque no guia que restaurou os fios e use **Voltar ao teste LCD em 3,3 V**. Não reconecte os sinais diretos mantendo o LCD em 5 V.

## 6. TCRT5000 — somente jumpers, depois teste

| Fio | Pino do módulo | Destino |
|---|---|---|
| F11 | VCC | P2:+2 — 3,3 V |
| F12 | GND | P2:−2 |
| F13 | DO | GPIO35 — P1:14J |
| — | AO | Sem fio |

Leia os nomes: a ordem física varia. Conecte USB, informe a tensão real no módulo e clique em **Testar TCRT5000**. Durante os oito segundos de captura, aproxime e afaste um cartão claro, inicialmente a poucos milímetros. Ajuste o trimpot do sensor se não houver alternância. Os timeouts do ultrassom ainda ausente não reprovam o IR. Desligue USB para continuar.

## 7. HC-SR04 — única parte com resistores externos

Com as peças registradas, esta proteção é necessária. O HC-SR04 padrão usa 5 V, e seu ECHO não deve chegar direto ao GPIO34. Para eliminar os resistores externos seria preciso acrescentar um **conversor adequado de sinal digital 5 V → 3,3 V** ou substituir o sensor por uma variante documentada compatível com 3,3 V. Não vamos presumir essa compatibilidade para o sensor atual.

Na P2, com espaço livre:

| Item | Ligação |
|---|---|
| R1 — 1 kΩ | P2:8C ↔ P2:12C |
| R2 — 1 kΩ | P2:12D ↔ P2:16D |
| R3 — 300 Ω | P2:16E ↔ P2:20E |
| F10 | P2:20A ↔ P2:−4 |

1 kΩ com quatro faixas: **marrom, preto, vermelho, dourado**. 300 Ω: **laranja, preto, marrom, dourado**. Confira os valores soltos. R2/R3 ficam em série; não deixe pernas de tiras diferentes se tocarem.

Antes de ligar HC-SR04 e GPIO34, faça o ensaio: com USB fora, jumper temporário de P1:+3 a P2:8B. Ligue USB só para medir: preta em P2:−5 e vermelha em P2:12B. O cálculo prevê cerca de 2,83 V; espere aproximadamente 2,5–3,2 V e nunca aceite mais de 3,30 V. **Anote sua medição, desligue USB e retire o jumper temporário.** Este teste estático não mede o pico real do ECHO. Pode usar o jumper reservado ao F9.

Agora ligue:

| Fio | Origem | Destino |
|---|---|---|
| F5 | HC-SR04 VCC | P1:+2 — 5 V |
| F6 | HC-SR04 GND | P1:−3 |
| F7 | HC-SR04 TRIG | GPIO5 — P1:10A |
| F8 | HC-SR04 ECHO | P2:8A — entrada de R1 |
| F9 | P2:12A — ponto entre R1/R2 | GPIO34 — P1:15J |

```text
ECHO ── R1 1 kΩ ── ponto 12 da P2 ── R2 1 kΩ ── R3 300 Ω ── GND
                          └── GPIO34
```

Ponha um livro de frente para o sensor a uma distância medida, por exemplo 25 cm. Conecte USB, informe a tensão anotada no ensaio do divisor e a distância do alvo e clique em **Testar HC-SR04**.

## 8. Teste conjunto e resultados

Clique em **Testar conjunto**. Estimule o IR durante os oito segundos, mantenha o alvo na referência e compare o LCD físico. O resultado separa:

- **Aprovado:** evidências seriais esperadas e conferências solicitadas fornecidas pelo operador.
- **Pendente:** faltam medições ou confirmação da imagem/fiação; nunca se presume que o software mediu a tensão ou viu a tela.
- **Falha:** dados ausentes/inválidos, sensor sem resposta ou referência divergente; o guia informa o motivo.

Nenhum teste do guia usa dados simulados. O botão não grava firmware e não mede tensões. As capturas usam a porta física escolhida e ficam registradas em `data/reports/bench_validation_log.json`. Se mudar fios ou porta, repita os testes. Desligue USB antes de qualquer correção. Reconhecimento TinyML e minijogo têm validações próprias.

Se LCD e IR ficarem apagados juntos, confira primeiro F3 (3V3 até o + da P2) e F4 (GND entre as placas) e meça no VCC/GND dos módulos. A ESP32 acesa só confirma a alimentação da própria placa; não confirma os trilhos externos. O HC-SR04 não tem um LED de alimentação para essa conferência.

## Se o LCD ficar ilegível em 3,3 V

O PCF8574 aceita 3,3 V, mas isso não garante que o painel LCD e seu circuito de contraste funcionem bem nessa tensão. Se backlight e comunicação existem, mas o contraste não resolve, use um **conversor I²C bidirecional de dois canais, próprio para open-drain**, mantendo os GPIOs iguais:

- LCD VCC e HV do conversor → 5 V; LV do conversor → 3V3; GND de todos em comum.
- GPIO21 → LV1; HV1 → SDA do LCD.
- GPIO22 → LV2; HV2 → SCL do LCD.

Siga a identificação LV/HV e os pull-ups do conversor real. Não use o divisor resistivo do ECHO no barramento I²C. Este é outro perfil elétrico: a etapa D padrão em 3V3 não valida automaticamente essa alternativa. O firmware é o mesmo.

## Arquivos atuais

Fios e furos: `hardware/netlist/motionpet_final_i2c.json`. Gerador visual: `.\.venv\Scripts\python.exe -m hardware.final_assembly`. Serviço dos botões: `.\.venv\Scripts\python.exe -m terminal.bench.guide`. O [checklist](cycle5_bench_checklist.md) registra a montagem atual.

A revisão 1 concentrava a montagem em uma placa e não usava os trilhos; a revisão 2 introduziu duas placas e testes incrementais. A revisão 3 recuperou o GND em 6J do teste real anterior e retirou a indicação alternativa de 2J. A revisão 4 acrescenta o diagnóstico opcional de iluminação sem refazer os trilhos, com as mudanças de F14/F15 e a volta para 3V3 explícitas. A causa física da falha atual ainda precisa ser confirmada. O CAD paralelo em `hardware/out/estagio*.md`, `.fzz`, `protoboard_estagio*.svg` e o Wokwi antigo continuam históricos e não representam este backpack I²C.
