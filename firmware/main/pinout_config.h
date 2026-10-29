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
 *    Utilize divisor com margem abaixo de 3.3 V: preferencialmente R1=2.2 kOhm (ECHO->No) e
 *    R2=3.3 kOhm (No->GND), resultando em Vout=3.00 V @ 5.00 V e Vout_max=3.15 V @ 5.25 V.
 * 3. O pino RW (pino 5) do LCD 2004A DEVE ser aterrado permanentemente no GND (modo somente-escrita).
 * 4. O TCRT5000 e o potenciometro devem ser alimentados exclusivamente em 3.3 V (pino 3V3), NUNCA em 5 V.
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
#define DEFAULT_POT_ENABLED   true

// LCD 2004A V1.1 (HD44780 em modo paralelo de 4 bits; pino 5 RW conectado direto ao GND!)
#define PIN_LCD_RS            19
#define PIN_LCD_EN            18
#define PIN_LCD_D4            21
#define PIN_LCD_D5            22
#define PIN_LCD_D6            23
#define PIN_LCD_D7            27

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
