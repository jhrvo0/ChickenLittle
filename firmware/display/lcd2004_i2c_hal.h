#ifndef MOTIONPET_LCD2004_I2C_HAL_H
#define MOTIONPET_LCD2004_I2C_HAL_H

#include <stdint.h>
#include <stdbool.h>
#include "display/lcd2004_driver.h"
#include "main/pinout_config.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief HAL do LCD 2004A ligado ao adaptador I2C PCF8574 (backpack).
 *
 * O driver HD44780 (lcd2004_driver.cpp) continua o mesmo, em 4 bits. Esta HAL traduz cada
 * "pino" do driver para um bit do PCF8574: P0=RS, P1=RW, P2=E, P3=BL, P4..P7=D4..D7.
 * RW fica sempre em 0 (escrita) e BL sempre em 1 (luz de fundo, com o jumper LED fechado).
 *
 * Barramento: SDA=GPIO21, SCL=GPIO22, Wire padrao (100 kHz).
 */
#define LCD_I2C_SDA_GPIO      PIN_LCD_SDA
#define LCD_I2C_SCL_GPIO      PIN_LCD_SCL
#define LCD_I2C_ADDR_PRIMARY  0x27U
#define LCD_I2C_ADDR_ALT      0x3FU

// Bits do PCF8574 usados como "pinos" do driver HD44780
#define LCD_I2C_BIT_RS  0U
#define LCD_I2C_BIT_EN  2U
#define LCD_I2C_BIT_D4  4U
#define LCD_I2C_BIT_D5  5U
#define LCD_I2C_BIT_D6  6U
#define LCD_I2C_BIT_D7  7U

/** @brief Preenche a configuração de pinos do driver com os bits do PCF8574. */
void lcd_i2c_fill_pin_config(LCDPinConfig *cfg);

/** @brief Operações de HAL para `lcd_ctx_init`. Use no lugar do HAL paralelo. */
extern const LCDHalOps g_lcd_i2c_hal_ops;

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_LCD2004_I2C_HAL_H
