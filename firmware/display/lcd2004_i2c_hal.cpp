#include "display/lcd2004_i2c_hal.h"

#ifdef ARDUINO
#include <Arduino.h>
#include <Wire.h>
#endif

// Estado do PCF8574: BL (bit 3) sempre ligado, RW (bit 1) sempre em 0.
static uint8_t g_expander_shadow = 0x08U;
static uint8_t g_last_sent = 0x00U;
static bool g_last_valid = false;
static uint8_t g_i2c_addr = LCD_I2C_ADDR_PRIMARY;

// Envia o byte atual ao PCF8574 somente se mudou desde a última transmissão bem-sucedida.
static void lcd_i2c_flush(void) {
#ifdef ARDUINO
    if (g_last_valid && g_expander_shadow == g_last_sent) return;
    Wire.beginTransmission(g_i2c_addr);
    Wire.write(g_expander_shadow);
    g_last_valid = (Wire.endTransmission() == 0U);
    g_last_sent = g_expander_shadow;
#endif
}

static void lcd_i2c_configure_pins(const LCDPinConfig *cfg) {
    (void)cfg;
#ifdef ARDUINO
    Wire.begin(LCD_I2C_SDA_GPIO, LCD_I2C_SCL_GPIO, 100000UL);
    // Mesmas faixas PCF8574/PCF8574A do teste isolado; 0x27 e 0x3F tem prioridade.
    g_i2c_addr = LCD_I2C_ADDR_PRIMARY;
    Wire.beginTransmission((uint8_t)LCD_I2C_ADDR_PRIMARY);
    if (Wire.endTransmission() != 0U) {
        Wire.beginTransmission((uint8_t)LCD_I2C_ADDR_ALT);
        if (Wire.endTransmission() == 0U) {
            g_i2c_addr = LCD_I2C_ADDR_ALT;
        } else {
            for (uint8_t addr = 0x20U; addr <= 0x3FU; ++addr) {
                if (addr > 0x27U && addr < 0x38U) continue;
                Wire.beginTransmission(addr);
                if (Wire.endTransmission() == 0U) {
                    g_i2c_addr = addr;
                    break;
                }
            }
        }
    }
#endif
    g_expander_shadow = 0x08U;  // BL ligado, RS/RW/E/dados em 0
    g_last_valid = false;
    lcd_i2c_flush();
}

static void lcd_i2c_write_pin(uint8_t pin, uint8_t level) {
    uint8_t mask = (uint8_t)(1U << (pin & 0x07U));
    if (level) {
        g_expander_shadow |= mask;
    } else {
        g_expander_shadow &= (uint8_t)~mask;
    }
    lcd_i2c_flush();
}

static void lcd_i2c_delay_us(uint32_t us) {
#ifdef ARDUINO
    if (us >= 1000UL) {
        delay(us / 1000UL);
        uint32_t rem = us % 1000UL;
        if (rem > 0UL) delayMicroseconds(rem);
    } else if (us > 0UL) {
        delayMicroseconds(us);
    }
#else
    (void)us;
#endif
}

void lcd_i2c_fill_pin_config(LCDPinConfig *cfg) {
    if (!cfg) return;
    cfg->pin_rs = LCD_I2C_BIT_RS;
    cfg->pin_en = LCD_I2C_BIT_EN;
    cfg->pin_d4 = LCD_I2C_BIT_D4;
    cfg->pin_d5 = LCD_I2C_BIT_D5;
    cfg->pin_d6 = LCD_I2C_BIT_D6;
    cfg->pin_d7 = LCD_I2C_BIT_D7;
}

const LCDHalOps g_lcd_i2c_hal_ops = {
    lcd_i2c_configure_pins,
    lcd_i2c_write_pin,
    lcd_i2c_delay_us,
};
