#ifndef MOTIONPET_LCD2004_DRIVER_H
#define MOTIONPET_LCD2004_DRIVER_H

#include <stdint.h>
#include <stdbool.h>
#include "sensors/sensor_types.h"
#include "pet/pet_state.h"

#ifdef __cplusplus
extern "C" {
#endif

#define LCD_ROWS 4
#define LCD_COLS 20

/**
 * @brief Configuração de pinos para o LCD 2004A operando em modo paralelo de 4 bits.
 *
 * NOTA DE SEGURANÇA: O pino RW do LCD NÃO deve ser conectado a nenhum GPIO.
 * Ele deve ser soldado/conectado diretamente ao GND da protoboard (somente-escrita).
 */
typedef struct {
    uint8_t pin_rs;     ///< GPIO conectado a Register Select (LCD pino 4)
    uint8_t pin_en;     ///< GPIO conectado a Enable Clock (LCD pino 6)
    uint8_t pin_d4;     ///< GPIO conectado a Data bit 4 (LCD pino 11)
    uint8_t pin_d5;     ///< GPIO conectado a Data bit 5 (LCD pino 12)
    uint8_t pin_d6;     ///< GPIO conectado a Data bit 6 (LCD pino 13)
    uint8_t pin_d7;     ///< GPIO conectado a Data bit 7 (LCD pino 14)
} LCDPinConfig;

/**
 * @brief Buffer de quadro completo espelhado das 4 linhas do display de 20 colunas.
 */
typedef struct {
    char lines[LCD_ROWS][LCD_COLS + 1];  ///< 4 linhas com 20 caracteres cada + terminador nulo
} LCDFrameBuffer;

/**
 * @brief Abstração de hardware (HAL) para o barramento paralelo de 4 bits do HD44780.
 */
typedef struct {
    void (*configure_pins)(const LCDPinConfig *cfg);
    void (*write_pin)(uint8_t pin, uint8_t level);
    void (*delay_us)(uint32_t us);
} LCDHalOps;

/**
 * @brief Contexto do driver HD44780 com shadow buffer 4x20 para atualização diferencial sem flicker.
 */
typedef struct {
    LCDPinConfig pins;
    LCDHalOps hal;
    char shadow[LCD_ROWS][LCD_COLS];
    bool shadow_valid;
    bool initialized;
    uint8_t cursor_row;
    uint8_t cursor_col;
    uint32_t total_frames_rendered;
    uint32_t chars_written_last_frame;
    uint32_t total_bus_bytes_sent;
} LCDDriverContext;

// Índices de glifos customizados na CGRAM do HD44780 (máximo de 8 glifos: 0 a 7)
#define LCD_GLYPH_HEART       0   ///< Ícone de coração (saúde/amor)
#define LCD_GLYPH_FOOD        1   ///< Ícone de grão/comida
#define LCD_GLYPH_BAR_0       2   ///< Barra de progresso vazia
#define LCD_GLYPH_BAR_1       3   ///< Barra de progresso 1/4
#define LCD_GLYPH_BAR_2       4   ///< Barra de progresso 2/4
#define LCD_GLYPH_BAR_3       5   ///< Barra de progresso 3/4
#define LCD_GLYPH_BAR_4       6   ///< Barra de progresso 4/4 (cheia)
#define LCD_GLYPH_ZZZ         7   ///< Ícone de sono

// API com contexto explícito (usada em testes automatizados e tasks)
bool lcd_ctx_init(LCDDriverContext *ctx, const LCDPinConfig *cfg, const LCDHalOps *custom_hal);
void lcd_ctx_clear(LCDDriverContext *ctx);
void lcd_ctx_set_cursor(LCDDriverContext *ctx, uint8_t row, uint8_t col);
void lcd_ctx_print(LCDDriverContext *ctx, const char *str);
void lcd_ctx_print_line(LCDDriverContext *ctx, uint8_t row, const char *line);
void lcd_ctx_render_frame(LCDDriverContext *ctx, const LCDFrameBuffer *frame);
void lcd_ctx_create_custom_char(LCDDriverContext *ctx, uint8_t location, const uint8_t charmap[8]);
void lcd_ctx_load_default_glyphs(LCDDriverContext *ctx);

/**
 * @brief Formata o quadro 20x4 do Pet com equivalência caractere-por-caractere a `Lcd20x4Renderer` (Python).
 */
void lcd_format_pet_frame(
    const PetStateSnapshot *state,
    uint32_t frame_idx,
    const SensorRawFrame *sensor,
    LCDFrameBuffer *out_frame
);

// API global original (opera sobre instância estática padrão)
bool lcd_init(const LCDPinConfig *cfg);
void lcd_clear(void);
void lcd_set_cursor(uint8_t row, uint8_t col);
void lcd_print(const char *str);
void lcd_print_line(uint8_t row, const char *line);
void lcd_render_frame(const LCDFrameBuffer *frame);
void lcd_create_custom_char(uint8_t location, const uint8_t charmap[8]);
void lcd_load_default_glyphs(void);

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_LCD2004_DRIVER_H
