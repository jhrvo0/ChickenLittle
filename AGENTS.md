# ChickenLittle / MotionPet
Sistema embarcado: ESP32 + HC-SR04 (ultrassom) + TCRT5000 (IR) falando JSON Lines v1 por USB serial com uma interface web local no notebook (pet "Piu-piu", jogo Pet Launch, modo Música, modo Slides, tudo controlado pelos sensores). Doc da interface: `docs/interface_notebook.md`.

## Mapa
- `firmware/` C++/FreeRTOS (PlatformIO, env `esp32dev`, Arduino); `terminal/` app Python (`web/` interface na porta 8767, `bench/` guia de bancada na 8766, `pet/`, `games/`, `modes/`, `communication/`, `renderer/`, `diag/`); `simulator/` e `ml/` (simulação e pipeline de gestos); `tests/` (pytest + 2 testes `.cjs`); `docs/` (protocolo, ADRs, ligações); `hardware/` (netlist, CAD, `wokwi/montagem_atual/`); `teste-*` (projetos PlatformIO de bancada); `data/` saves.

## Comandos (confirmados em 2026-11-10, PowerShell na raiz)
| Ação | Comando | Resultado |
|---|---|---|
| Testes Python | `.\.venv\Scripts\python.exe -m pytest -q` | 464 passed, 3 skipped (sem `FRITZING_PARTS_DIR`), ~27 s; o resumo final pode não aparecer: use o exit code |
| Teste UI web | `node --test tests/test_web_ui.cjs` | 1 pass |
| Teste UI guia | `node --test tests/test_guide_ui.cjs` | 9 pass |
| Build firmware | `.\.venv\Scripts\python.exe -m platformio run -d firmware` | SUCCESS em ~15 s (cache quente); RAM 7,5%, flash 24,5% |
| Interface web | `.\.venv\Scripts\python.exe -m terminal.web` | http://127.0.0.1:8767/ (código confere: `terminal/web/server.py`; não subi o servidor). `--demo` roda sem placa |
| Guia de bancada | `.\.venv\Scripts\python.exe -m terminal.bench.guide` | http://127.0.0.1:8766/ (abre a COM3; não rodado) |
Não confirmados (tocam a placa): `gravar_firmware.bat`, `teste_bancada.bat`, upload, monitor serial.
- `.venv` é Python 3.13 ARM64. Nunca instale com `pip`/`python` soltos: use o `.venv` ou `uv`.

## Ligações atuais da bancada
- ESP32 DevKit de 38 pinos na protoboard P1, USB na COM3, firmware integrado gravado.
- HC-SR04 em 5 V (trilho + da P1, alimentado por P1:1J). TRIG em GPIO5 (P1:10A). ECHO passa por divisor na P2 (1 kΩ em 8C-12C, 1 kΩ em 12D-16D, 300 Ω em 16E-20E, 20A no GND) e chega ao GPIO34 por 12A -> P1:15J.
- TCRT5000 em 3,3 V (trilho + da P2, vindo de P1:19J), GND pelos trilhos a partir de P1:6J, DO em GPIO35 (P1:14J).
- Os dois sensores leem juntos, sem erro (relato do usuário; tensões e precisão da distância não foram medidas).
- Fontes de verdade da montagem vigente: `docs/bench_verified_wiring.md`, `hardware/netlist/motionpet_atual_sem_lcd.json`, `hardware/wokwi/montagem_atual/diagram.json`. Quando o usuário mudar um fio, atualize os três (o `diagram.json` é a memória da montagem).
- Históricos com LCD (não descrevem a bancada): `hardware/netlist/motionpet_final_i2c.json` (ainda lido por `hardware/final_assembly.py`, que gera `hardware/guia_montagem_final.html`; não editar o HTML à mão, um teste compara com o gerador), `hardware/wokwi/montagem_atual/diagram_historico_com_lcd.json`, `teste-lcd/`, `teste-i2c-scan/`.

## Restrições elétricas
- LCD 2004 I2C está FORA da montagem: em 3,3 V o texto fica ilegível; em 5 V precisaria de conversor de nível, que o usuário não tem. Nunca sugerir SDA/SCL direto na ESP32 com o LCD em 5 V. A interface no notebook substitui o LCD.
- ESP32 é 3,3 V: nada de 5 V em GPIO; por isso o ECHO do HC-SR04 passa pelo divisor.
- O usuário não tem multímetro (não peça medições de tensão).
- COM3 é exclusiva: um programa por vez. Antes de usar, pare o que a ocupa (servidor web, guia, monitor serial).

## Regras para agentes
- Tudo que envolve a placa (COM3, gravar firmware, monitor serial) é feito só pela thread principal com o usuário, um passo por vez. Subagentes e threads delegadas não tocam na COM3 (a parte física é do usuário e subagente não fala com ele).
- Sem commit, push, merge ou instalação global sem pedido explícito.
- No máximo 2-3 agentes simultâneos (16 GB de RAM).
- Worktree só a partir de um commit; partes em paralelo nunca mexem nos mesmos arquivos; merge só com aprovação.
- Relato de subagente não é prova: o orquestrador confere o diff e roda a verificação.
- Decisões duráveis vão para este arquivo.

## Antes de entregar
- Python/web: `pytest` completo (+ `node --test` se mexeu em `terminal/web/static` ou no guia). Firmware: build PlatformIO. Mudança de ligação: atualizar `diagram.json` e docs.

## Decisões
- 2026-11-10: LCD fora da montagem; a interface no notebook (`terminal.web`) substitui o LCD. O usuário retirou também os cabos de alimentação do LCD: não sobra fio dele na bancada.
- 2026-11-10: a netlist vigente é `motionpet_atual_sem_lcd.json`; `motionpet_final_i2c.json` ficou como perfil histórico com LCD porque o gerador do guia depende dele.
