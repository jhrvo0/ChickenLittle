# Simulacao Wokwi do MotionPet (gerada)

Arquivos gerados por `python -m hardware.build` a partir de `hardware/netlist/motionpet.netlist.json`:

- `diagram.json` — ESP32-DevKitC V4 (`board-esp32-devkit-c-v4`, 38 pinos), HC-SR04, R1/R2/R3 e potenciometro (estagios A-C). O LCD (estagio D) esta adiado.
- `wokwi.toml` — aponta para o firmware compilado pelo PlatformIO (`pio run -d firmware`).
- `scenarios/hcsr04.test.yaml` — cenario de teste (sensor_frame, distancias 25 cm e 300 cm).

## O que o Wokwi NAO prova
- Nao e medicao com multimetro e **nao valida o divisor resistivo** (a simulacao e digital). Nao comprova compatibilidade eletrica.
- Nao ha modelo do TCRT5000: a rede `IR_DO` nao e simulada.
- Os nomes de pino seguem exemplos publicos do Wokwi (`esp:5`, `esp:34`, `esp:5V`, `esp:GND.1`...). Qual `GND.n` e qual pino fisico e **assumido**.

## Estado de verificacao (honesto)
`wokwi-cli` nao pode ser instalado/executado no ambiente de geracao (download do binario negado e `wokwi.com` bloqueado),
portanto **`wokwi-cli lint` e os cenarios NAO foram executados**. Para verificar na sua maquina:

```powershell
iwr https://wokwi.com/ci/install.ps1 -useb | iex          # instalador oficial (inspecione antes de rodar)
$env:WOKWI_CLI_TOKEN = "<token do painel Wokwi CI>"        # NAO grave no Git
wokwi-cli lint hardware/wokwi
pio run -d firmware
wokwi-cli hardware/wokwi --scenario hardware/wokwi/scenarios/hcsr04.test.yaml
```
