"""Tabela canônica única de pinagem e validador elétrico de segurança para bancada ESP32."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

# Limites elétricos inegociáveis do ESP-WROOM-32 (VDD_3V3 = 3,3 V, NÃO tolerante a 5 V).
# REGRA DO CICLO 5: 3,5 V NÃO é aceito como tensão segura para um GPIO de 3,3 V!
ESP32_GPIO_MAX_SAFE_V = 3.30
ESP32_GPIO_RECOMMENDED_CEILING_V = 3.20
ESP32_GPIO_MIN_RELIABLE_VIH_V = 2.50

# Montagem atual: R1=1k; R2 equivale a 1k + 300 ohms em série.
PREFERRED_ECHO_R1_OHM = 1000.0
PREFERRED_ECHO_R2_OHM = 1300.0

FORBIDDEN_SPI_FLASH_GPIOS: tuple[int, ...] = (6, 7, 8, 9, 10, 11)
SENSITIVE_STRAPPING_GPIOS: tuple[int, ...] = (0, 2, 12, 15)
RESERVED_UART0_GPIOS: tuple[int, ...] = (1, 3)


@dataclass(frozen=True)
class CanonicalPinAssignment:
    """Registro imutável de um pino na tabela canônica única do MotionPet."""

    peripheral: str
    signal: str
    esp32_pin: str
    gpio_number: int | None
    direction: str
    supply_domain: str
    electrical_conditioning: str


CANONICAL_PINOUT_TABLE: tuple[CanonicalPinAssignment, ...] = (
    CanonicalPinAssignment(
        peripheral="HC-SR04",
        signal="TRIG",
        esp32_pin="GPIO5",
        gpio_number=5,
        direction="OUTPUT (3.3 V)",
        supply_domain="Sensor VCC = 5 V",
        electrical_conditioning="Direto (3.3 V >= limiar TTL V_IH 2.0 V do HC-SR04)",
    ),
    CanonicalPinAssignment(
        peripheral="HC-SR04",
        signal="ECHO",
        esp32_pin="GPIO34",
        gpio_number=34,
        direction="INPUT-ONLY (GPI)",
        supply_domain="Sensor VCC = 5 V -> Divisor <= 3.30 V",
        electrical_conditioning=(
            "Divisor da montagem: R1=1 kOhm (ECHO->No), R2=1 kOhm + 300 Ohm "
            "em serie (No->GND). Medir o no antes de conectar GPIO34; nao exceder 3.30 V."
        ),
    ),
    CanonicalPinAssignment(
        peripheral="TCRT5000",
        signal="DO",
        esp32_pin="GPIO35",
        gpio_number=35,
        direction="INPUT-ONLY (GPI)",
        supply_domain="Modulo VCC = 3.3 V ESTRITO",
        electrical_conditioning="Saida digital 3.3 V direta (NUNCA alimentar TCRT5000 em 5 V)",
    ),
    CanonicalPinAssignment(
        peripheral="TCRT5000",
        signal="AO (opcional)",
        esp32_pin="GPIO39 (VN / ADC1_CH3)",
        gpio_number=39,
        direction="INPUT-ONLY (ADC1)",
        supply_domain="Modulo VCC = 3.3 V ESTRITO",
        electrical_conditioning="Analogico 0..3.3 V em ADC1 (desativado; deixar AO desconectado)",
    ),
    CanonicalPinAssignment(
        peripheral="Potenciometro",
        signal="WIPER (cursor)",
        esp32_pin="GPIO36 (VP / ADC1_CH0)",
        gpio_number=36,
        direction="INPUT-ONLY (ADC1)",
        supply_domain="Extremos em 3.3 V e GND",
        electrical_conditioning="Desativado no firmware; fora da montagem atual",
    ),
    CanonicalPinAssignment(
        peripheral="LCD 2004 I2C",
        signal="SDA",
        esp32_pin="GPIO21",
        gpio_number=21,
        direction="I2C (bidirecional)",
        supply_domain="Backpack VCC = 3.3 V (sem conversor)",
        electrical_conditioning="Pull-ups em 3V3; 5 V apenas com conversor I2C bidirecional",
    ),
    CanonicalPinAssignment(
        peripheral="LCD 2004 I2C",
        signal="SCL",
        esp32_pin="GPIO22",
        gpio_number=22,
        direction="I2C clock",
        supply_domain="Backpack VCC = 3.3 V (sem conversor)",
        electrical_conditioning="RW controlado pelo PCF8574; usar apenas os 4 pinos do backpack",
    ),
)

ALL_ASSIGNED_GPIOS: tuple[int, ...] = (5, 34, 35, 39, 36, 21, 22)

PINOUT_RECONCILIATION_NOTE = (
    "Reconciliacao Ciclo 5: `PIN_HCSR04_ECHO` e CANONICAMENTE `GPIO34` "
    "(GPI somente-entrada, conforme `firmware/main/pinout_config.h`, `docs/hardware_safety.md` e "
    "`docs/bench_assembly_guide.md`), corrigindo a mencao textual isolada a `GPIO32` no resumo "
    "do Ciclo 4. Zero conflito com SPI Flash (GPIO6..11), strapping (GPIO0/2/12/15), UART0 (GPIO1/3), "
    "ADC1 ou LCD I2C (SDA=21, SCL=22). O LCD paralelo de 16 pinos e historico; "
    "siga docs/bench_assembly_guide.md e hardware/guia_montagem_final.html."
)


@dataclass(frozen=True)
class EchoDividerAssessment:
    """Resultado da validação elétrica do divisor resistivo do pino ECHO (5 V -> <= 3,30 V)."""

    r1_ohm: float
    r2_ohm: float
    ratio: float
    vin_nominal_v: float
    vin_max_v: float
    vout_nominal_v: float
    vout_max_v: float
    measured_peak_v: float | None
    safe: bool
    has_recommended_margin: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_echo_divider(
    r1_ohm: float = PREFERRED_ECHO_R1_OHM,
    r2_ohm: float = PREFERRED_ECHO_R2_OHM,
    vin_nominal_v: float = 5.00,
    vin_max_v: float = 5.25,
    measured_peak_v: float | None = None,
) -> EchoDividerAssessment:
    """Calcula e valida rigorosamente o divisor resistivo do sinal `ECHO` do HC-SR04.

    Rejeita qualquer combinação ou medição que possa ultrapassar `3,30 V` (incluindo `1 kΩ / 2 kΩ`,
    que produz `3,33 V` @ `5,00 V` e `3,50 V` @ `5,25 V`, ou medições de `3,5 V`).
    """
    reasons: list[str] = []
    if r1_ohm <= 0 or r2_ohm <= 0:
        return EchoDividerAssessment(
            r1_ohm=float(r1_ohm),
            r2_ohm=float(r2_ohm),
            ratio=0.0,
            vin_nominal_v=float(vin_nominal_v),
            vin_max_v=float(vin_max_v),
            vout_nominal_v=0.0,
            vout_max_v=0.0,
            measured_peak_v=measured_peak_v,
            safe=False,
            has_recommended_margin=False,
            reasons=("Resistores R1 e R2 devem ser estritamente positivos.",),
        )

    ratio = float(r2_ohm) / float(r1_ohm + r2_ohm)
    vout_nom = float(vin_nominal_v) * ratio
    vout_max = float(vin_max_v) * ratio

    if (r1_ohm + r2_ohm) < 1000.0:
        reasons.append(
            f"Impedancia total muito baixa ({r1_ohm + r2_ohm:.0f} Ohm < 1 kOhm): "
            "sobrecarrega o driver de saida do HC-SR04."
        )
    if (r1_ohm + r2_ohm) > 100_000.0:
        reasons.append(
            f"Impedancia total muito alta ({r1_ohm + r2_ohm:.0f} Ohm > 100 kOhm): "
            "degrada bordas do pulso ECHO pela capacitancia parasita."
        )

    if vout_nom > ESP32_GPIO_MAX_SAFE_V or vout_max > ESP32_GPIO_MAX_SAFE_V:
        reasons.append(
            f"TENSAO PERIGOSA CALCULADA: Vout_nom={vout_nom:.2f} V, Vout_max={vout_max:.2f} V "
            f"(limite estrito <= {ESP32_GPIO_MAX_SAFE_V:.2f} V; 3.5 V NAO e aceito!). "
            "Confira o divisor da montagem: R1=1 kOhm e R2=1 kOhm + 300 Ohm em serie."
        )

    if vout_nom < ESP32_GPIO_MIN_RELIABLE_VIH_V:
        reasons.append(
            f"Tensao nominal muito baixa (Vout_nom={vout_nom:.2f} V < {ESP32_GPIO_MIN_RELIABLE_VIH_V:.2f} V): "
            "risco de falha na deteccao de nivel logico ALTO (V_IH) no GPIO34."
        )

    if measured_peak_v is not None:
        if measured_peak_v > ESP32_GPIO_MAX_SAFE_V:
            reasons.append(
                f"TENSAO MEDIDA REPROVADA ({measured_peak_v:.2f} V > {ESP32_GPIO_MAX_SAFE_V:.2f} V): "
                "NUNCA conecte este sinal ao GPIO34! 3.5 V NAO e seguro para GPIO de 3.3 V."
            )
        elif measured_peak_v < ESP32_GPIO_MIN_RELIABLE_VIH_V:
            reasons.append(
                f"Tensao medida insuficiente ({measured_peak_v:.2f} V < {ESP32_GPIO_MIN_RELIABLE_VIH_V:.2f} V): "
                "verifique conexoes do divisor e alimentacao de 5 V do HC-SR04."
            )

    safe = len(reasons) == 0
    has_margin = safe and (vout_max <= ESP32_GPIO_RECOMMENDED_CEILING_V) and (
        measured_peak_v is None or measured_peak_v <= ESP32_GPIO_RECOMMENDED_CEILING_V
    )
    return EchoDividerAssessment(
        r1_ohm=round(float(r1_ohm), 2),
        r2_ohm=round(float(r2_ohm), 2),
        ratio=round(ratio, 4),
        vin_nominal_v=round(float(vin_nominal_v), 3),
        vin_max_v=round(float(vin_max_v), 3),
        vout_nominal_v=round(vout_nom, 3),
        vout_max_v=round(vout_max, 3),
        measured_peak_v=round(float(measured_peak_v), 3) if measured_peak_v is not None else None,
        safe=safe,
        has_recommended_margin=has_margin,
        reasons=tuple(reasons),
    )


def verify_canonical_pinout_conflicts() -> tuple[bool, list[str]]:
    """Audita programaticamente a tabela canônica contra duplicidades e pinos proibidos."""
    issues: list[str] = []
    seen: set[int] = set()
    for pin in ALL_ASSIGNED_GPIOS:
        if pin in seen:
            issues.append(f"Conflito de GPIO duplicado: GPIO{pin}")
        seen.add(pin)
        if pin in FORBIDDEN_SPI_FLASH_GPIOS:
            issues.append(f"GPIO{pin} pertence ao barramento proibido da Flash SPI (GPIO6..11)")
        if pin in SENSITIVE_STRAPPING_GPIOS:
            issues.append(f"GPIO{pin} e pino sensivel de strapping do ESP32")
        if pin in RESERVED_UART0_GPIOS:
            issues.append(f"GPIO{pin} conflita com UART0 USB Serial (GPIO1/GPIO3)")
    return (len(issues) == 0), issues
