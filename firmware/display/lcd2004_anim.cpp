#include "display/lcd2004_anim.h"

#include <string.h>

// Sprite de 10x16 pixels, dividido em 4 celulas 5x8 do HD44780:
//   TL (codigo 1) TR (codigo 2) na linha 1 do LCD, BL (codigo 3) BR (codigo 4) na linha 2.
// O codigo 0 nao serve aqui: ele termina a string no buffer do quadro. Por isso usamos 1..4.
#define BOOT_CODE_TL  1U
#define BOOT_CODE_TR  2U
#define BOOT_CODE_BL  3U
#define BOOT_CODE_BR  4U

typedef enum {
    BOOT_SPR_NONE = 0,
    BOOT_SPR_EGG,
    BOOT_SPR_CRACK,
    BOOT_SPR_CHICK
} BootSprite;

typedef struct {
    const char *row0;   ///< Linha 0 em ASCII (NULL = vazia)
    BootSprite sprite;  ///< Sprite exibido nas linhas 1 e 2
    uint8_t x0;         ///< Coluna da celula esquerda do sprite (0..18)
    const char *row3;   ///< Linha 3 em ASCII (NULL = vazia)
    uint16_t hold_ms;   ///< Tempo que o quadro fica na tela
} BootFrame;

// Glifos gerados por gerar_sprites.py (bit 4 = pixel mais a esquerda de cada linha)
static const uint8_t kEggGlyphs[4][8] = {
    {0x03, 0x04, 0x08, 0x08, 0x10, 0x10, 0x10, 0x10},
    {0x18, 0x04, 0x02, 0x02, 0x01, 0x01, 0x01, 0x01},
    {0x10, 0x10, 0x10, 0x10, 0x08, 0x08, 0x04, 0x03},
    {0x01, 0x01, 0x01, 0x01, 0x02, 0x02, 0x04, 0x18}
};

static const uint8_t kCrackGlyphs[4][8] = {
    {0x03, 0x04, 0x08, 0x08, 0x10, 0x10, 0x11, 0x10},
    {0x18, 0x04, 0x02, 0x02, 0x01, 0x01, 0x01, 0x11},
    {0x11, 0x12, 0x10, 0x10, 0x08, 0x08, 0x04, 0x03},
    {0x01, 0x01, 0x01, 0x01, 0x02, 0x02, 0x04, 0x18}
};

static const uint8_t kChickGlyphs[4][8] = {
    {0x03, 0x07, 0x0F, 0x0F, 0x0F, 0x07, 0x07, 0x03},
    {0x18, 0x1C, 0x0E, 0x1F, 0x1E, 0x1C, 0x1C, 0x18},
    {0x0F, 0x0F, 0x0F, 0x07, 0x07, 0x03, 0x06, 0x06},
    {0x1E, 0x1E, 0x1E, 0x1C, 0x1C, 0x18, 0x0C, 0x0C}
};

// Total de hold: 2950 ms. Cada quadro dura pelo menos 250 ms (no maximo 4 quadros por segundo).
static const BootFrame kBootFrames[] = {
    // 0: ovo aparece no centro
    { "Um ovo misterioso...", BOOT_SPR_EGG,   9U, NULL,                  600U },
    // 1..3: ovo balanca para a esquerda, para a direita e volta ao centro
    { "Um ovo misterioso...", BOOT_SPR_EGG,   8U, NULL,                  250U },
    { "Um ovo misterioso...", BOOT_SPR_EGG,  10U, NULL,                  250U },
    { "Um ovo misterioso...", BOOT_SPR_EGG,   9U, NULL,                  250U },
    // 4: o ovo racha
    { "Um ovo misterioso...", BOOT_SPR_CRACK, 9U, "    tec! tec!",       300U },
    // 5: o pintinho nasce
    { NULL,                   BOOT_SPR_CHICK, 9U, NULL,                  500U },
    // 6: saudacao
    { NULL,                   BOOT_SPR_CHICK, 9U, " Ola, sou o Bitinho!", 800U },
};

static const uint8_t kBootFrameCount = (uint8_t)(sizeof(kBootFrames) / sizeof(kBootFrames[0]));

static void copy_row(char dst[LCD_COLS + 1], const char *src) {
    size_t n = src ? strlen(src) : 0U;
    if (n > LCD_COLS) n = LCD_COLS;
    if (n > 0U) memcpy(dst, src, n);
    for (size_t c = n; c < LCD_COLS; ++c) dst[c] = ' ';
    dst[LCD_COLS] = '\0';
}

// Carrega os 4 glifos do sprite nos codigos 1..4 da CGRAM
static void boot_load_sprite(LCDDriverContext *ctx, BootSprite s) {
    const uint8_t (*set)[8] = NULL;
    if (s == BOOT_SPR_EGG) {
        set = kEggGlyphs;
    } else if (s == BOOT_SPR_CRACK) {
        set = kCrackGlyphs;
    } else if (s == BOOT_SPR_CHICK) {
        set = kChickGlyphs;
    }
    if (!set) return;
    for (uint8_t k = 0U; k < 4U; ++k) {
        lcd_ctx_create_custom_char(ctx, (uint8_t)(BOOT_CODE_TL + k), set[k]);
    }
}

static void boot_build_frame(const BootFrame *f, LCDFrameBuffer *out) {
    copy_row(out->lines[0], f->row0);
    copy_row(out->lines[1], NULL);
    copy_row(out->lines[2], NULL);
    copy_row(out->lines[3], f->row3);
    if (f->sprite != BOOT_SPR_NONE) {
        uint8_t x = f->x0;
        out->lines[1][x]        = (char)BOOT_CODE_TL;
        out->lines[1][x + 1U]   = (char)BOOT_CODE_TR;
        out->lines[2][x]        = (char)BOOT_CODE_BL;
        out->lines[2][x + 1U]   = (char)BOOT_CODE_BR;
    }
}

void lcd_play_boot_animation(LCDDriverContext *ctx) {
    if (!ctx || !ctx->initialized) return;
    BootSprite carregado = BOOT_SPR_NONE;
    LCDFrameBuffer frame;
    for (uint8_t i = 0U; i < kBootFrameCount; ++i) {
        const BootFrame *f = &kBootFrames[i];
        if (f->sprite != BOOT_SPR_NONE && f->sprite != carregado) {
            boot_load_sprite(ctx, f->sprite);
            carregado = f->sprite;
        }
        boot_build_frame(f, &frame);
        lcd_ctx_render_frame(ctx, &frame);
        if (ctx->hal.delay_us && f->hold_ms > 0U) {
            ctx->hal.delay_us((uint32_t)f->hold_ms * 1000UL);
        }
    }
    // Devolve os glifos padrao e limpa a tela antes do quadro do pet
    lcd_ctx_load_default_glyphs(ctx);
    lcd_ctx_clear(ctx);
}
