#ifndef MOTIONPET_LCD2004_DRIVER_H
#define MOTIONPET_LCD2004_DRIVER_H

#include <stdint.h>
#include <stdbool.h>

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

// Índices de glifos customizados na CGRAM do HD44780 (máximo de 8 glifos: 0 a 7)
#define LCD_GLYPH_HEART       0   ///< Ícone de coração (saúde/amor)
#define LCD_GLYPH_FOOD        1   ///< Ícone de grão/comida
#define LCD_GLYPH_BAR_0       2   ///< Barra de progresso vazia
#define LCD_GLYPH_BAR_1       3   ///< Barra de progresso 1/4
#define LCD_GLYPH_BAR_2       4   ///< Barra de progresso 2/4
#define LCD_GLYPH_BAR_3       5   ///< Barra de progresso 3/4
#define LCD_GLYPH_BAR_4       6   ///< Barra de progresso 4/4 (cheia)
#define LCD_GLYPH_ZZZ         7   ///< Ícone de sono

/**
 * @brief Inicializa a comunicação paralela de 4 bits com o controlador HD44780.
 * @param cfg Ponteiro para struct com os GPIOs alocados
 * @return true se a sequência de inicialização de 4 bits foi executada
 */
bool lcd_init(const LCDPinConfig *cfg);

/**
 * @brief Limpa o visor e retorna o cursor para a posição (0, 0).
 */
void lcd_clear(void);

/**
 * @brief Posiciona o cursor nas coordenadas informadas.
 * @param row Linha (0 a 3)
 * @param col Coluna (0 a 19)
 */
void lcd_set_cursor(uint8_t row, uint8_t col);

/**
 * @brief Escreve uma string na posição atual do cursor.
 */
void lcd_print(const char *str);

/**
 * @brief Escreve uma linha completa, preenchendo o restante com espaços em branco.
 * @param row Linha de destino (0 a 3)
 * @param line Texto de até 20 caracteres
 */
void lcd_print_line(uint8_t row, const char *line);

/**
 * @brief Renderiza um buffer completo de 4 linhas no display físico.
 * @param frame Quadro contendo exatamente as 4 linhas
 */
void lcd_render_frame(const LCDFrameBuffer *frame);

/**
 * @brief Grava um caractere customizado na CGRAM do display.
 * @param location Posição de memória (0 a 7)
 * @param charmap Vetor de 8 bytes com o padrão de pixels 5x8
 */
void lcd_create_custom_char(uint8_t location, const uint8_t charmap[8]);

/**
 * @brief Carrega os glifos padrão (coração, comida, barras de status) na CGRAM.
 */
void lcd_load_default_glyphs(void);

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_LCD2004_DRIVER_H
