# MotionPet: montagem atual da bancada (sem LCD)

Registro de 2026-11-10. O usuário retirou o LCD e também os dois cabos de alimentação dele (VCC e GND): não sobra fio do LCD na bancada. O acompanhamento é feito pela interface no notebook. Os dois sensores leem juntos (relato do usuário; tensões e exatidão do HC-SR04 não foram medidas, ele não tem multímetro).

## Qual arquivo vale

| Arquivo | Papel |
|---|---|
| `diagram.json` | **Vigente**: montagem atual sem LCD. |
| `diagram_sem_lcd.json` | Rascunho anterior da mesma configuração, feito quando a retirada física dos cabos ainda não estava confirmada. Redundante com `diagram.json` (só difere nos textos); mantido por histórico. |
| `diagram_historico_com_lcd.json` | Antigo `diagram.json`: último estado físico com o LCD (VCC em 5 V, sem SDA/SCL). Histórico. |
| `diagram_base.json`, `diagram_referencia_com_fios.json`, `diagram_atual_7_fios_3_resistores.json`, `diagram_sensores_ok_lcd_5v_sem_sinais.json` | Estados e propostas anteriores; não são a bancada atual. |

## Ligações do `diagram.json`

- ESP32 DevKit de 38 pinos na protoboard P1, USB na COM3 (o DevKitC V4 virtual é só aproximado e fica separado da P1).
- **HC-SR04** em 5 V: VCC no trilho + da P1, alimentado por P1:1J. TRIG em GPIO5 (P1:10A). ECHO passa pelo divisor na P2 (R1 1 kΩ em 8C-12C, R2 1 kΩ em 12D-16D, R3 300 Ω em 16E-20E, 20A no GND) e chega ao GPIO34 por 12A -> P1:15J.
- **TCRT5000** em 3,3 V: VCC no trilho + da P2, vindo de P1:19J; GND pelos trilhos a partir de P1:6J (ponte entre os negativos da P1 e da P2); DO em GPIO35 (P1:14J). AO livre.
- A peça do TCRT no desenho é um fotoresistor LDR usado só como marcador. As cores dos fios no desenho são representativas.
- Os resistores têm conexões invisíveis aos furos (representam as pernas encaixadas). A renderização no Wokwi não foi verificada.

## Abrir e compartilhar

Abra https://wokwi.com/projects/new/esp32, selecione `diagram.json` e substitua todo o texto pelo conteúdo do arquivo desta pasta. O navegador Wokwi não é atualizado automaticamente: o arquivo local registra o estado. O histórico em `hardware/wokwi/diagram.json` permanece intacto. A netlist vigente é `hardware/netlist/motionpet_atual_sem_lcd.json`.

## Histórico

### Registro anterior (com LCD), preservado

`diagram_historico_com_lcd.json` registra as ligações confirmadas pelo usuário. Após instalar agora o jumper de 6J ao primeiro negativo da P1, o usuário relatou que o LED do sensor **acendeu**. No teste anterior, em que o LED estava apagado com o azul no negativo da P1, esse jumper ainda estava ausente; uma resposta anterior presumiu incorretamente que já havia sido recolocado. Isso não demonstra defeito em cabo ou trilho. No teste real em COM3 foram recebidos 115 frames do sensor: 44 `true`, 71 `false`, 34 transições e 0 erros de interpretação. Isso confirma a leitura digital no ensaio, mas não mede VCC nem conclui a validação integrada. Não houve medição com voltímetro. Mantenha o USB desligado enquanto altera ou rastreia fios.

- **Sensor:** verde VCC ao primeiro positivo da P2; azul GND ao terceiro negativo da P1. Laranja liga DO a 14J da P1 (GPIO35), conforme montagem informada anteriormente e leitura real; AO está livre.
- **P1:** 1J ligado ao primeiro positivo, conforme confirmado anteriormente; fio marrom de 19J ao segundo positivo da P2; jumper de 6J ao primeiro negativo da P1 instalado agora.
- **Ponte:** segundo negativo da P1 ao primeiro negativo da P2 permanece. Os dois fios de GND do desenho aparecem em preto apenas como representação, pois as cores físicas não foram informadas.
- **P2:** os trilhos em uso ficam no extremo próximo à coluna 30, conforme indicado pelo usuário. Nesta conversa, +1 (verde), +2 (marrom) e -1 (ponte) contam a partir dessa extremidade; são apelidos de furos do trilho, não os números impressos na área central. Na P1 a contagem dos trilhos é feita a partir do lado do USB/coluna 1. O arquivo usa os contatos de trilho Wokwi 25, 24 e 25, respectivamente; o posicionamento visual ainda não foi renderizado.
- **Captura conjunta COM3:** em 8 s, 116 frames, 105 leituras HC válidas, 11 timeouts (9,48%), distâncias de 2,78 a 16,38 cm (média 9,43 cm), IR verdadeiro em 116 frames, 0 erros de interpretação e 0 lacunas de sequência. O ultrassom apresentou leituras; não houve medição de exatidão com referência. O IR permaneceu ativo nessa captura e havia alternado 34 vezes no ensaio anterior. VCC e ECHO não foram medidos.
- **Observação posterior no painel COM3:** o usuário confirmou que a distância mudou ao mover o livro e que o IR alternou entre DETECTADO e LIVRE ao mover o cartão. Os dois sensores responderam juntos nessa observação; a exatidão do HC e as tensões não foram medidas. Na captura automática anterior de 12 s foram registrados 172 frames, 151 leituras HC válidas, 21 timeouts e IR verdadeiro nos 172 frames, sem transições; essa captura permanece como histórico separado da observação posterior.
- **LCD isolado após regressão:** o usuário confirmou que havia ligado os quatro fios do LCD (VCC, GND, SDA e SCL); depois relatou que o sensor parou de funcionar e a tela não ligou. Com o USB desligado, retirou os quatro cabos do LCD e informou que o sensor voltou a funcionar. Depois o usuário ligou somente VCC e GND do LCD aos terceiros furos positivo e negativo da P2, contando a partir do lado 30, e relatou que a iluminação do LCD acendeu com o sensor funcionando. Depois o usuário confirmou SDA ligado a 14A e SCL a 17A da P1. Relatou que a iluminação acendeu, mas os caracteres não apareceram; a reinicialização por EN também não os mostrou. Em seguida, com o USB desligado, retirou SDA e SCL e moveu apenas VCC do LCD ao terceiro positivo da P1 (5 V), mantendo GND no terceiro negativo da P2. Nesse teste sem comunicação, relatou iluminação e blocos visíveis. Isso não valida texto nem comunicação I2C em 5 V; a causa da ausência de caracteres em 3,3 V não foi determinada. A causa da regressão anterior não foi identificada e nenhuma tensão foi medida.
- **Medição do divisor:** o usuário informou não possuir multímetro. O ensaio estático não foi executado e a tensão real não foi medida. Aproximadamente 2,83 V é somente o valor nominal calculado para entrada de 5 V e resistores de 1 kΩ, 1 kΩ e 300 Ω, não uma leitura nem validação. O usuário confirmou posteriormente ECHO e GPIO34 ligados ao divisor; sua tensão real continua sem medição.
- **Furos centrais da P2:** 8C e 12C ficam na área central, não no trilho lateral perto da coluna 30. O usuário confirmou R1 de 1 kΩ entre 8C e 12C, R2 de 1 kΩ entre 12D e 16D e R3 de 300 Ω entre 16E e 20E. No arquivo seus terminais têm conexões invisíveis aos furos: representam as pernas encaixadas, não jumpers. Os componentes continuam separados visualmente da placa, pois a disposição ainda não foi renderizada nem serve como gabarito. O usuário confirmou o fio de 20A ao quarto negativo da P2, contando a partir da extremidade 30; ele aparece em preto apenas como representação, pois a cor física não foi informada. O usuário confirmou depois ECHO para 8A e 12A ao 15J da P1 (GPIO34). Laranja e verde desses fios no desenho são cores representativas, pois as cores físicas não foram informadas.
- **HC-SR04:** VCC ligado ao segundo positivo da P1 e GND ao quarto negativo da P1, conforme confirmação do usuário. TRIG está ligado a 10A da P1 (GPIO5); ECHO está ligado a 8A da P2, e 12A da P2 a 15J da P1 (GPIO34). O amarelo do TRIG é apenas representativo, pois a cor física não foi informada. As cores vermelho e preto usadas nos novos fios do HC e no fio 1J → positivo da P1 são representativas; as cores físicas não foram informadas. No estado atual de teste, o VCC do LCD está no terceiro positivo de 5 V da P1 e o GND no terceiro negativo da P2; SDA e SCL estão removidos. Vermelho e preto no desenho são representativos, pois as cores físicas desses fios não foram informadas. Não conectar SDA/SCL diretamente aos GPIOs enquanto o LCD estiver em 5 V; para comunicação nessa alimentação falta um conversor bidirecional de níveis.

O DevKitC V4 virtual é de 38 pinos mas difere da NodeMCU ESP-32S v1.1 física, inclusive no pino vizinho de 5V (CMD no virtual e GND na placa física descrita). Ele fica separado da P1 e não é gabarito mecânico. A peça identificada como TCRT é um **fotoresistor LDR usado apenas como marcador**: não tem a mesma aparência nem o comportamento do sensor real.
