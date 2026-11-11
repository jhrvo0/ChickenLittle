"""Textos estaticos do guia em slides (ajuda). Em portugues; mantidos fora do gerador para facilitar a revisao."""

COMMON_ERRORS = [
    "ESP32 virada 180° (USB-C para o lado da coluna 19): os fios caem nos pinos da memória flash e ela reinicia sem parar ('invalid header' na serial). A USB-C fica na ponta da COLUNA 1, com o 5V e o CLK nessa ponta.",
    "ESP32 deslocada uma coluna: TODOS os pinos ficam errados. Confira: 5V na coluna 1 e 3V3 na coluna 19, ambos na fileira de cima (J).",
    "O lado A–E não é conectado ao lado F–J através do canal central. Use o número e a letra dos furos; confirme também o sentido da numeração da sua protoboard.",
    "HC-SR04 com VCC e GND trocados: pode queimar o módulo. Leia a serigrafia (VCC | TRIG | ECHO | GND) antes de encaixar.",
    "ECHO ligado direto a qualquer GPIO, inclusive IO5 ou IO34: não ligue. O ECHO deve entrar no divisor; só o nó do divisor vai ao IO34.",
    "Ramos do divisor trocados (os 1,3 kΩ em cima, o 1 kΩ embaixo): o nó cai para 2,2 V (abaixo de 2,475 V) e a leitura falha (sem dano, mas sem distância).",
    "TCRT5000 ligado no trilho + (5 V): ele só pode usar o 3V3 da ESP32, indicado como 19J no desenho assumido; confira a serigrafia da sua placa.",
    "Trilhos trocados (vermelho/azul): confira a cor antes de encaixar; + é 5 V e − é GND.",
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
