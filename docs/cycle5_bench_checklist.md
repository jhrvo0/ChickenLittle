# Checklist Rápido de Bancada — MotionPet (Ciclo 5)

- **Status Físico Atual:** **`PENDING_PHYSICAL_VALIDATION`** *(nenhuma medição física inventada; validar item a item na protoboard)*
- **Status de Pinagem:** `MOTIONPET_PINOUT_STATUS = "CANONICAL_GPIO34_PENDING_PHYSICAL_VALIDATION"`
- **Versão do Firmware:** `MOTIONPET_FW_VERSION = "0.5.0-cycle5"` ([pinout_config.h](file:///c:/Users/joaoh/Downloads/ChickenLittle/firmware/main/pinout_config.h))

---

## 1. Reconciliação Canônica de Pinagem (`HC-SR04 ECHO = GPIO34`)

- No Ciclo 3 ([pinout_config.h](file:///c:/Users/joaoh/Downloads/ChickenLittle/firmware/main/pinout_config.h), linha 35), `PIN_HCSR04_ECHO` foi configurado em **`GPIO34`**. No resumo textual do Ciclo 4 houve uma menção divergente a `GPIO32`.
- Após auditoria completa, **`GPIO34` fica estabelecido como o único pino canônico para `HC-SR04 ECHO`**: é GPI *input-only* de alta impedância (impossível acionar acidentalmente saída `3,3 V` contra o divisor), sem conflito de *boot strapping*, e sem sobreposição com `TRIG` (`GPIO5`), `TCRT5000 DO` (`GPIO35`), `TCRT5000 AO` (`GPIO39`, opc.), `Potenciômetro` (`GPIO36`), `LCD 2004A` (`19, 18, 21, 22, 23, 27` + `RW=GND`) ou `UART0` (`1, 3`). Nenhuma migração de código C++ foi necessária no firmware.

---

## 2. Regras de Ouro de Segurança Elétrica e Parada Imediata

> [!CAUTION]
> **CRITÉRIO DE PARADA IMEDIATA:** Se houver curto entre `5V`/`3V3` e `GND`, se o nó do divisor medir **`> 3,30 V`**, se `LCD RW` não tiver **`0,0 Ω` para `GND`**, ou se `terminal.bench` acusar falha, **desconecte o cabo USB imediatamente e NÃO avance de etapa!**

- [ ] **`ECHO <= 3,30 V` (`3,5 V` É PROIBIDO!)**: Usar divisor canônico **`R1 = 2,2 kΩ`** (`ECHO -> Nó`) e **`R2 = 3,3 kΩ`** (`Nó -> GND`) $\rightarrow$ fator `0,600` (**`3,00 V` @ `5,00 V`**; **`3,15 V` @ `5,25 V`**; faixa segura de nível alto: `2,50..3,20 V`). *Alternativas aprovadas: `4,7 kΩ + 6,8 kΩ` ou `2×1 kΩ + 3×1 kΩ`. O par antigo `1 kΩ / 2 kΩ` está **descontinuado/proibido** (`3,33..3,50 V`).* **Medir o nó ANTES de ligar ao `GPIO34`!**
- [ ] **`LCD RW` (Pino 5) = `GND` (`0,0 Ω`)**: Aterramento permanente obrigatório para impedir retorno de `5 V` em `D4..D7`.
- [ ] **`TCRT5000` e `Potenciômetro` = `3,3 V` (`3V3`)**: **NUNCA** alimentar em `5 V`.
- [ ] **Terra Comum e Pinos Reservados Livres**: Todos os `GND` unificados; `GPIO6..11` (SPI Flash), `GPIO12` (MTDI) e `GPIO1/3` (`UART0`) 100% livres na protoboard.

---

## 3. Tabela Canônica Única de Pinos

| Periférico | Pino Módulo | Pino ESP32 | Alimentação / Nível | Regra Obrigatória |
| :--- | :--- | :--- | :--- | :--- |
| **HC-SR04** | `VCC` / `GND` | `5V (VIN)` / `GND` | `5,0 V` | `GND` comum obrigatório. |
| **HC-SR04** | `TRIG` | `GPIO5` | Saída `3,3 V` | Ligação direta (`3,3 V >= 2,0 V` TTL). |
| **HC-SR04** | `ECHO` | **`GPIO34`** | Entrada **`<= 3,30 V`** | **Via divisor `R1 = 2,2 kΩ` / `R2 = 3,3 kΩ` (`3,00 V` nom.)**. |
| **TCRT5000** | `VCC` / `GND` | **`3V3`** / `GND` | **`3,3 V` estrito** | **NUNCA ligar em `5 V`!** |
| **TCRT5000** | `DO` / `AO`*(opc.)* | `GPIO35` / `GPIO39` | `0..3,3 V` (GPI) | `AO` opcional (`ADC1_CH3`, desligado por padrão). |
| **Potenciômetro** | Extremos / Cursor | **`3V3`**, `GND` / `GPIO36` | **`3,3 V` estrito** | Cursor em `ADC1_CH0` (`VP`). **NUNCA ligar em `5 V`!** |
| **LCD 2004A** | `1(VSS)` / `2(VDD)` | `GND` / `5V (VIN)` | `5,0 V` | Clone CMOS c/ falha lógica: diodo `1N4148`/`1N4007` em série no `VDD`. |
| **LCD 2004A** | `3(V0)` / **`5(RW)`** | Resistor `GND` / **`GND`** | `0,4..0,8 V` / **`0,0 V`** | `V0`: `1 kΩ..2,2 kΩ` p/ `GND`. **`RW`: `0,0 Ω` fixo no `GND`!** |
| **LCD 2004A** | `4(RS)` / `6(E)` | `GPIO19` / `GPIO18` | Saída `3,3 V` | Pinos `7..10 (D0..D3)` desconectados (`NC`). |
| **LCD 2004A** | `11..14 (D4..D7)` | `GPIO21, 22, 23, 27` | Saída `3,3 V` | `D4=21`, `D5=22`, `D6=23`, `D7=27`. |
| **LCD 2004A** | `15(A)` / `16(K)` | `5V (VIN)` / `GND` | Backlight `5 V` | Pino `15` c/ resistor `100–220 Ω` se placa não tiver SMD `R8`/`R9`. |

---

## 4. Comissionamento Incremental (`Etapa A -> B -> C -> D`)

*(Substitua `COMx` pela porta real identificada. O upload de firmware é **sempre manual** pelo usuário).*

### Pré-voo no Host
- [ ] Verificar ambiente, porta serial `COMx` e checklist interativo:
  ```powershell
  .\.venv\Scripts\python.exe -m terminal.bench check-deps
  .\.venv\Scripts\python.exe -m terminal.bench ports
  .\.venv\Scripts\python.exe -m terminal.bench checklist
  ```

### Etapa A — ESP32 Isolado (Sem Periféricos)
- [ ] Conferir ausência de curto `5V-GND` e `3V3-GND`. Plugar USB apenas no ESP32 e medir `VIN` (`4,75..5,25 V`) e `3V3` (`3,25..3,35 V`).
- [ ] Gravar manualmente o firmware `0.5.0-cycle5` e validar Etapa A:
  ```powershell
  pio run -d firmware -t upload --upload-port COMx
  .\.venv\Scripts\python.exe -m terminal.bench stage A --serial-port COMx
  .\.venv\Scripts\python.exe -m terminal.bench diag --serial-port COMx
  ```

### Etapa B — `HC-SR04` + Divisor `2,2 kΩ / 3,3 kΩ` (`ECHO -> GPIO34`)
- [ ] **Desligar USB.** Medir `R1 = 2,2 kΩ` e `R2 = 3,3 kΩ`. Montar `HC-SR04` (`VCC=5V`, `GND`, `TRIG=GPIO5`) e divisor, **deixando o `GPIO34` desconectado**.
- [ ] **Ligar USB.** Medir tensão máxima no nó entre `R1` e `R2` (**PARAR SE `> 3,30 V`!**) e validar:
  ```powershell
  .\.venv\Scripts\python.exe -m terminal.bench divider --r1 2200 --r2 3300 --measured-v 3.00
  ```
- [ ] **Desligar USB**, ligar nó ao `GPIO34`, **religar USB** e validar leitura com alvo a `25 cm`:
  ```powershell
  .\.venv\Scripts\python.exe -m terminal.bench stage B --serial-port COMx
  .\.venv\Scripts\python.exe -m terminal.bench inspect --serial-port COMx --duration 5 --reference-cm 25
  ```

### Etapa C — `TCRT5000` (`3,3 V`) + Potenciômetro (`3,3 V`)
- [ ] **Desligar USB.** Ligar `TCRT5000` (`VCC=3V3`, `GND`, `DO=GPIO35`) e Potenciômetro (`3V3`, `GND`, cursor=`GPIO36`). **Confirmar que nenhum fio vai ao `5V`!**
- [ ] **Religar USB** e validar Etapa C + painel em tempo real:
  ```powershell
  .\.venv\Scripts\python.exe -m terminal.bench stage C --serial-port COMx
  .\.venv\Scripts\python.exe -m terminal.diag --serial-port COMx
  ```

### Etapa D — `LCD 2004A V1.1` (`5 V`, `RW = GND` Fixo)
- [ ] **Desligar USB.** Montar LCD 2004A conforme Seção 3. **Confirmar `0,0 Ω` entre pino 5 (`RW`) e `GND`** e resistor de backlight (`100–220 Ω`) no pino 15 (`A`) se necessário.
- [ ] **Religar USB**, verificar legibilidade das 4 linhas e validar Etapa D:
  ```powershell
  .\.venv\Scripts\python.exe -m terminal.bench stage D --serial-port COMx
  ```

---

## 5. Coleta Real $\rightarrow$ TinyML $\rightarrow$ Regravação $\rightarrow$ Teste E2E (`Pet Launch`)

- [ ] **1. Planejar campanha (`>= 5` participantes `p01..p05`, zero dados sintéticos)**:
  ```powershell
  .\.venv\Scripts\python.exe -m ml.collection --plan-campaign
  ```
- [ ] **2. Coletar sessões reais guiadas (`NEUTRAL`, `APPROACH`, `RETREAT`, `HOLD`) em `data/raw/real`**:
  ```powershell
  .\.venv\Scripts\python.exe -m ml.collection --serial-port COMx --participant p01 --schedule "NEUTRAL:20,APPROACH:15,NEUTRAL:15,RETREAT:15,NEUTRAL:15,HOLD:15,NEUTRAL:20" --conditions "bancada_interna_vel_normal" --guided --output-dir data/raw/real
  ```
- [ ] **3. Treinar, gerar relatório honesto, exportar `tinyml_model.h` e verificar build do firmware**:
  ```powershell
  .\.venv\Scripts\python.exe -m ml.real_pipeline --raw-dir data/raw/real --models-dir data/models --reports-dir data/reports --export-header firmware/gestures/tinyml_model.h --verify-firmware-build
  ```
- [ ] **4. Regravar manualmente o firmware com o modelo TinyML treinado em dados reais**:
  ```powershell
  pio run -d firmware -t upload --upload-port COMx
  ```
- [ ] **5. Executar validação ponta a ponta e testar modo `Pet Launch`**:
  ```powershell
  .\.venv\Scripts\python.exe -m terminal.bench e2e --serial-port COMx
  ```
  - Validar jogabilidade real no **`Pet Launch`** (LCD 2004A + terminal): ajuste contínuo de ângulo/mira no potenciômetro (`GPIO36`), carregamento/disparo por gestos reais (`HOLD` / `APPROACH` / `RETREAT` no `HC-SR04`) e resposta imediata de proximidade no `TCRT5000`, sem resets ou falsos disparos em repouso (`NEUTRAL`).
