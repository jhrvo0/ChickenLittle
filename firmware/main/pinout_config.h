#ifndef MOTIONPET_PINOUT_CONFIG_H
#define MOTIONPET_PINOUT_CONFIG_H

#include <stdint.h>
#include <stdbool.h>

/**
 * @file pinout_config.h
 * @brief Tabela canonica unica de pinagem e parametros temporais do MotionPet (ESP-WROOM-32).
 *
 * RECONCILIACAO CANONICA DE PINAGEM E SEGURANCA ELETRICA (CICLO 5):
 * 1. HC-SR04 ECHO reside CANONICAMENTE no `GPIO34` (GPI somente-entrada, alta impedancia, zero
 *    conflito com strapping/ADC/LCD; corrige mencao textual divergente a GPIO32 no resumo do Ciclo 4).
 * 2. O pino ECHO do HC-SR04 (5 V TTL) NUNCA deve ser ligado direto ao GPIO34 nem exceder 3.30 V.
 *    3.50 V NAO e aceito como tensao segura para GPIO de 3.3 V!
 *    A montagem atual usa R1=1 kOhm (ECHO->No) e R2=1 kOhm + R3=300 Ohm em serie
 *    (No->GND): Vout nominal 2.83 V @ 5.00 V; calculo com tolerancia de 5%: maximo 3.10 V.
 *    O divisor 2.2 kOhm / 3.3 kOhm e uma alternativa; medir antes de conectar ao GPIO34.
 * 3. LCD com backpack I2C PCF8574: SDA=GPIO21, SCL=GPIO22, VCC=3V3 sem conversor.
 *    RW e controlado pelo bit P1 do backpack, mantido em zero pelo HAL. Nao adicionar fio ao pino 5.
 * 4. O TCRT5000 usa 3.3 V (pino 3V3). O potenciometro de entrada esta desativado e fora da montagem.
 * 5. Pinos reservados de SPI Flash (GPIO6..GPIO11) e strapping critico (GPIO12/MTDI, GPIO0) NAO sao usados.
 * 6. Todas as leituras analogicas residem exclusivamente no bloco ADC1 (GPIO36=POT, GPIO39=IR_AO opcional).
 */

// Status explicito de validacao fisica
#define MOTIONPET_PINOUT_STATUS "CANONICAL_GPIO34_PENDING_PHYSICAL_VALIDATION"
#define MOTIONPET_FW_VERSION    "0.5.0-cycle5"

// Comunicacao Serial USB (UART0)
#ifndef MOTIONPET_SERIAL_BAUD
#define MOTIONPET_SERIAL_BAUD 115200UL
#endif

// HC-SR04 (Ultrassom 1D)
#define PIN_HCSR04_TRIG       5    // Saida 3.3 V -> TRIG (compativel com limiar TTL >= 2.0 V)
#define PIN_HCSR04_ECHO       34   // Entrada GPI somente-entrada <- Divisor resistivo 5V->3.3V!

// TCRT5000 (Infravermelho Reflexivo alimentado em 3.3 V)
#define PIN_TCRT5000_DO       35   // Entrada GPI somente-entrada <- Saida digital DO (3.3 V)
#define PIN_TCRT5000_AO       39   // Entrada GPI / ADC1_CH3 (VN) <- Saida analogica AO opcional (-1 desativa)
#define DEFAULT_IR_ENABLED    true
#define DEFAULT_IR_ANALOG_EN  false
#define DEFAULT_IR_ACTIVE_LOW true // Modulos LM393 tipicos colocam DO=LOW ao detectar reflexao

// Potenciometro Rotativo (alimentado em 3.3 V)
#define PIN_POT_ADC1          36   // Entrada GPI / ADC1_CH0 (VP)
#define DEFAULT_POT_ENABLED   false  // potenciometro removido da montagem (bancada 2026-10-29); GPIO36 nao e lido

// LCD 2004A com backpack PCF8574. Pull-ups do I2C em 3V3, nunca em 5 V direto ao ESP32.
// O layout paralelo antigo foi preservado em hardware/netlist/archive/pinout_parallel.h.
#define PIN_LCD_SDA           21
#define PIN_LCD_SCL           22

// Temporizacoes operacionais (em milissegundos)
#define DEFAULT_SENSOR_PERIOD_MS   70UL   // Faixa inicial recomendada: 60..80 ms (~14.3 Hz)
#define MIN_SENSOR_PERIOD_MS       50UL   // Minimo fisico para evitar eco residual acustico
#define MAX_SENSOR_PERIOD_MS       500UL  // Maximo configuravel em modo lento
#define PET_TICK_PERIOD_MS         1000UL // 1 Hz para ciclo biologico do pet
#define LCD_REFRESH_PERIOD_MS      200UL  // 5 Hz para atualizacao diferencial do LCD 20x4

// Prioridades e pilhas FreeRTOS (em bytes no ESP-IDF FreeRTOS, onde StackType_t = uint8_t)
#define TASK_PRIO_SENSOR_ACQUIRE   4
#define TASK_PRIO_GESTURE_INFER    3
#define TASK_PRIO_PET_DOMAIN       2
#define TASK_PRIO_SERIAL_COMM      2
#define TASK_PRIO_LCD_DISPLAY      1

#define TASK_STACK_SENSOR_BYTES    3072U
#define TASK_STACK_GESTURE_BYTES   4096U
#define TASK_STACK_PET_BYTES       4096U
#define TASK_STACK_SERIAL_BYTES    4096U
#define TASK_STACK_LCD_BYTES       3072U

// Capacidade das filas estaticas FreeRTOS
#define QUEUE_LEN_SENSOR_INFER     8U
#define QUEUE_LEN_SENSOR_TX        8U
#define QUEUE_LEN_GESTURE_PET      6U
#define QUEUE_LEN_GESTURE_TX       6U
#define QUEUE_LEN_CMD_PET          8U

#endif // MOTIONPET_PINOUT_CONFIG_H
