"""Textos estaticos do guia em slides (ajuda). Em portugues; mantidos fora do gerador para facilitar a revisao."""

COMMON_ERRORS = [
    "ESP32 deslocada uma coluna: TODOS os pinos ficam errados. Confira: 3V3 na coluna 4 e 5V na coluna 22 (fileira de baixo).",
    "Letras da protoboard invertidas (A no topo em vez de J): guie-se pelo NÚMERO da coluna; se as letras estiverem ao contrário, gire a protoboard.",
    "HC-SR04 com VCC e GND trocados: pode queimar o módulo. Leia a serigrafia (VCC | TRIG | ECHO | GND) antes de encaixar.",
    "ECHO ligado direto ao GPIO34 (sem divisor): proibido; entrega ~5 V a um pino de 3,3 V.",
    "Ramos do divisor trocados (os 1,3 kΩ em cima, o 1 kΩ embaixo): o nó cai para 2,2 V (abaixo de 2,475 V) e a leitura falha (sem dano, mas sem distância).",
    "TCRT5000 ou potenciômetro ligados em 5 V: só podem usar 3V3.",
    "Fio em IO12, IO6…IO11 (SD0…CLK) ou TX0/RX0: proibido (boot loop, falha de flash ou serial).",
    "LCD com RW (pino 5) no ar: obrigatório ligar ao GND antes de energizar.",
    "Cabo USB só de carga (sem dados): a porta COM nunca aparece.",
    "Jumper 'quase' encaixado: empurre até o fim e puxe de leve para testar.",
]

NO_PORT = [
    "Troque o cabo por um cabo USB DE DADOS e teste outra porta USB do notebook.",
    "Deixe SOMENTE a ESP32 na protoboard (Estágio A): sem sensores nem fios.",
    "Windows: Gerenciador de Dispositivos > Portas (COM e LPT). Sem porta? Instale o driver da ponte USB-serial da placa (CP210x ou CH340).",
    "Rode `python -m terminal.bench ports` para listar as portas.",
    "Não use a ESP32 se 5V/3V3 medirem fora de 4,75–5,25 V / 3,25–3,35 V.",
    "Para gravar o firmware pode ser preciso segurar BOOT ao iniciar o upload.",
]
