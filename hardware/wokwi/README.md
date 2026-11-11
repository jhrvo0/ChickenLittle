# Simulacao Wokwi do MotionPet (gerada)

**Referencia do CAD paralelo historico.** A montagem fisica atual usa [o guia final I2C](../guia_montagem_final.html).
O diagrama padrao abaixo so representa o estagio C (sem LCD); os antigos D/E exportados usam LCD paralelo.
O cenario do HC-SR04 simula distancias, nao valida o circuito real.

Arquivos gerados por `python -m hardware.build` a partir de `hardware/netlist/motionpet.netlist.json`:

- `diagram.json` — estagio C: ESP32-DevKitC V4, HC-SR04 e resistores R1-R3 do divisor. O LCD (estagio D) nao esta no diagrama padrao; o potenciometro foi removido da montagem.
- `wokwi.toml` — aponta para o firmware compilado pelo PlatformIO (`pio run -d firmware`).
- `scenarios/hcsr04.test.yaml` — cenario proposto com distancias 25 cm e 300 cm. Espera quadros validos, mas nao confirma os valores lidos ou a mudanca de distancia. Suporte ao controle `distance` tambem precisa ser verificado na versao usada.

## O que o Wokwi NAO prova
- Nao e medicao com multimetro e **nao valida o divisor resistivo** (a simulacao e digital). Nao comprova compatibilidade eletrica.
- Nao ha modelo do TCRT5000: a rede `IR_DO` nao e simulada.
- Os nomes de pino seguem exemplos publicos do Wokwi (`esp:5`, `esp:34`, `esp:5V`, `esp:GND.1`...). Qual `GND.n` e qual pino fisico e **assumido**.

## Estado de verificacao (honesto)
Em 2026-10-29, `wokwi-cli` 0.29.1 verificou o diagrama sem erros; informou que o tipo `board-esp32-devkit-c-v4` nao esta documentado e pode mudar. O cenario **nao foi executado**: requer token e compilacao do firmware. Para verificar na sua maquina:

```powershell
iwr https://wokwi.com/ci/install.ps1 -useb | iex          # instalador oficial (inspecione antes de rodar)
$env:WOKWI_CLI_TOKEN = "<token do painel Wokwi CI>"        # NAO grave no Git
wokwi-cli lint hardware/wokwi
pio run -d firmware
wokwi-cli hardware/wokwi --scenario scenarios/hcsr04.test.yaml --serial-log-file wokwi-serial.log
if ($LASTEXITCODE -eq 0) { python hardware/wokwi/verify_distances.py wokwi-serial.log }
```
O analisador exige uma leitura valida entre 22 e 28 cm seguida de outra entre 290 e 310 cm. Ele deve ser usado somente depois da execucao bem-sucedida do cenario; nao prova tensoes ou comportamento fisico. O controle de distancia e o proprio cenario ainda precisam ser confirmados no Wokwi. A CLI interpreta o caminho do cenario relativamente a `hardware/wokwi`.
