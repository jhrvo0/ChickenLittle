#include "display/lcd2004_driver.h"
#include "common/fw_utils.h"

#ifdef ARDUINO
#include <Arduino.h>

static void esp32_lcd_configure_pins(const LCDPinConfig *cfg) {
    pinMode(cfg->pin_rs, OUTPUT);
    pinMode(cfg->pin_en, OUTPUT);
    pinMode(cfg->pin_d4, OUTPUT);
    pinMode(cfg->pin_d5, OUTPUT);
    pinMode(cfg->pin_d6, OUTPUT);
    pinMode(cfg->pin_d7, OUTPUT);

    digitalWrite(cfg->pin_rs, LOW);
    digitalWrite(cfg->pin_en, LOW);
    digitalWrite(cfg->pin_d4, LOW);
    digitalWrite(cfg->pin_d5, LOW);
    digitalWrite(cfg->pin_d6, LOW);
    digitalWrite(cfg->pin_d7, LOW);
}

static void esp32_lcd_write_pin(uint8_t pin, uint8_t level) {
    digitalWrite(pin, level ? HIGH : LOW);
}

static void esp32_lcd_delay_us(uint32_t us) {
    if (us >= 1000UL) {
        delay(us / 1000UL);
        uint32_t rem = us % 1000UL;
        if (rem > 0UL) delayMicroseconds(rem);
    } else if (us > 0UL) {
        delayMicroseconds(us);
    }
}
#endif // ARDUINO

static LCDDriverContext g_default_lcd_ctx;

// Offsets DDRAM canônicos do controlador HD44780 para displays 20x4 (2004A V1.1)
static const uint8_t kHd44780RowOffsets[LCD_ROWS] = { 0x00U, 0x40U, 0x14U, 0x54U };

// Mapas de pixels 5x8 dos 8 glifos CGRAM padrão
static const uint8_t kDefaultGlyphs[8][8] = {
    // 0: HEART
    { 0x00, 0x0A, 0x1F, 0x1F, 0x1F, 0x0E, 0x04, 0x00 },
    // 1: FOOD
    { 0x04, 0x0E, 0x1F, 0x15, 0x1F, 0x0E, 0x00, 0x00 },
    // 2: BAR_0
    { 0x1F, 0x00, 0x00, 0x00, 0x00, 0x00, 0x1F, 0x00 },
    // 3: BAR_1
    { 0x1F, 0x10, 0x10, 0x10, 0x10, 0x10, 0x1F, 0x00 },
    // 4: BAR_2
    { 0x1F, 0x18, 0x18, 0x18, 0x18, 0x18, 0x1F, 0x00 },
    // 5: BAR_3
    { 0x1F, 0x1C, 0x1C, 0x1C, 0x1C, 0x1C, 0x1F, 0x00 },
    // 6: BAR_4
    { 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x1F, 0x00 },
    // 7: ZZZ
    { 0x1E, 0x02, 0x04, 0x08, 0x1E, 0x00, 0x07, 0x00 }
};

static void lcd_pulse_enable(LCDDriverContext *ctx) {
    ctx->hal.write_pin(ctx->pins.pin_en, 0U);
    ctx->hal.delay_us(1UL);
    ctx->hal.write_pin(ctx->pins.pin_en, 1U);
    ctx->hal.delay_us(2UL);  // Largura de pulso E > 450 ns exigida pelo HD44780
    ctx->hal.write_pin(ctx->pins.pin_en, 0U);
    ctx->hal.delay_us(45UL); // Tempo típico de execução de instrução (> 37 µs)
}

static void lcd_write_nibble(LCDDriverContext *ctx, uint8_t nibble) {
    ctx->hal.write_pin(ctx->pins.pin_d4, (nibble >> 0U) & 0x01U);
    ctx->hal.write_pin(ctx->pins.pin_d5, (nibble >> 1U) & 0x01U);
    ctx->hal.write_pin(ctx->pins.pin_d6, (nibble >> 2U) & 0x01U);
    ctx->hal.write_pin(ctx->pins.pin_d7, (nibble >> 3U) & 0x01U);
    lcd_pulse_enable(ctx);
}

static void lcd_send_byte(LCDDriverContext *ctx, uint8_t value, uint8_t rs_mode) {
    if (!ctx || !ctx->initialized) return;
    ctx->hal.write_pin(ctx->pins.pin_rs, rs_mode ? 1U : 0U);
    lcd_write_nibble(ctx, (value >> 4U) & 0x0FU);
    lcd_write_nibble(ctx, value & 0x0FU);
    ctx->total_bus_bytes_sent++;
}

static void lcd_invalidate_shadow(LCDDriverContext *ctx) {
    for (int r = 0; r < LCD_ROWS; ++r) {
        for (int c = 0; c < LCD_COLS; ++c) {
            ctx->shadow[r][c] = ' ';
        }
    }
    ctx->shadow_valid = false;
    ctx->cursor_row = 0xFFU;
    ctx->cursor_col = 0xFFU;
}

bool lcd_ctx_init(LCDDriverContext *ctx, const LCDPinConfig *cfg, const LCDHalOps *custom_hal) {
    if (!ctx || !cfg) return false;
    ctx->pins = *cfg;
    ctx->initialized = false;
    ctx->total_frames_rendered = 0UL;
    ctx->chars_written_last_frame = 0UL;
    ctx->total_bus_bytes_sent = 0UL;
    lcd_invalidate_shadow(ctx);

    if (custom_hal != NULL) {
        ctx->hal = *custom_hal;
    } else {
#ifdef ARDUINO
        ctx->hal.configure_pins = esp32_lcd_configure_pins;
        ctx->hal.write_pin = esp32_lcd_write_pin;
        ctx->hal.delay_us = esp32_lcd_delay_us;
#else
        return false;
#endif
    }

    if (!ctx->hal.configure_pins || !ctx->hal.write_pin || !ctx->hal.delay_us) {
        return false;
    }

    ctx->hal.configure_pins(&ctx->pins);
    ctx->initialized = true;

    // Sequência oficial Hitachi HD44780 de inicialização por software em 4 bits (com RW=GND)
    ctx->hal.delay_us(50000UL); // Aguarda estabilização de VDD > 4.5 V (~50 ms)
    ctx->hal.write_pin(ctx->pins.pin_rs, 0U);
    ctx->hal.write_pin(ctx->pins.pin_en, 0U);

    lcd_write_nibble(ctx, 0x03U);
    ctx->hal.delay_us(4500UL);
    lcd_write_nibble(ctx, 0x03U);
    ctx->hal.delay_us(4500UL);
    lcd_write_nibble(ctx, 0x03U);
    ctx->hal.delay_us(150UL);
    lcd_write_nibble(ctx, 0x02U); // Entra definitivamente em barramento de 4 bits
    ctx->hal.delay_us(150UL);

    lcd_send_byte(ctx, 0x28U, 0U); // Function Set: 4 bits, 2+ linhas (20x4), fonte 5x8
    lcd_send_byte(ctx, 0x0CU, 0U); // Display Control: Display ON, Cursor OFF, Blink OFF
    lcd_send_byte(ctx, 0x06U, 0U); // Entry Mode Set: incremento automático à direita, sem shift
    lcd_ctx_clear(ctx);
    lcd_ctx_load_default_glyphs(ctx);
    lcd_ctx_set_cursor(ctx, 0U, 0U);
    return true;
}

void lcd_ctx_clear(LCDDriverContext *ctx) {
    if (!ctx || !ctx->initialized) return;
    lcd_send_byte(ctx, 0x01U, 0U);
    ctx->hal.delay_us(2000UL); // Clear Display exige > 1.52 ms no HD44780
    for (int r = 0; r < LCD_ROWS; ++r) {
        for (int c = 0; c < LCD_COLS; ++c) {
            ctx->shadow[r][c] = ' ';
        }
    }
    ctx->shadow_valid = true;
    ctx->cursor_row = 0U;
    ctx->cursor_col = 0U;
}

void lcd_ctx_set_cursor(LCDDriverContext *ctx, uint8_t row, uint8_t col) {
    if (!ctx || !ctx->initialized) return;
    if (row >= LCD_ROWS) row = (uint8_t)(LCD_ROWS - 1);
    if (col >= LCD_COLS) col = (uint8_t)(LCD_COLS - 1);
    uint8_t addr = (uint8_t)(kHd44780RowOffsets[row] + col);
    lcd_send_byte(ctx, (uint8_t)(0x80U | addr), 0U);
    ctx->cursor_row = row;
    ctx->cursor_col = col;
}

void lcd_ctx_print(LCDDriverContext *ctx, const char *str) {
    if (!ctx || !ctx->initialized || !str) return;
    while (*str != '\0' && ctx->cursor_row < LCD_ROWS && ctx->cursor_col < LCD_COLS) {
        unsigned char uc = (unsigned char)*str++;
        char clean = (uc <= 0x07U || (uc >= 0x20U && uc <= 0x7EU)) ? (char)uc : '?';
        lcd_send_byte(ctx, (uint8_t)clean, 1U);
        ctx->shadow[ctx->cursor_row][ctx->cursor_col] = clean;
        ctx->cursor_col++;
    }
}

void lcd_ctx_print_line(LCDDriverContext *ctx, uint8_t row, const char *line) {
    if (!ctx || !ctx->initialized || row >= LCD_ROWS) return;
    lcd_ctx_set_cursor(ctx, row, 0U);
    bool ended = (line == NULL);
    for (uint8_t c = 0U; c < LCD_COLS; ++c) {
        char ch = ' ';
        if (!ended) {
            if (line[c] == '\0') {
                ended = true;
            } else {
                unsigned char uc = (unsigned char)line[c];
                ch = (uc <= 0x07U || (uc >= 0x20U && uc <= 0x7EU)) ? (char)uc : '?';
            }
        }
        lcd_send_byte(ctx, (uint8_t)ch, 1U);
        ctx->shadow[row][c] = ch;
    }
    ctx->cursor_row = row;
    ctx->cursor_col = LCD_COLS;
}

void lcd_ctx_render_frame(LCDDriverContext *ctx, const LCDFrameBuffer *frame) {
    if (!ctx || !ctx->initialized || !frame) return;
    uint32_t written = 0UL;

    for (uint8_t r = 0U; r < LCD_ROWS; ++r) {
        bool ended = false;
        for (uint8_t c = 0U; c < LCD_COLS; ++c) {
            char raw = frame->lines[r][c];
            if (raw == '\0') ended = true;
            char clean = ' ';
            if (!ended) {
                unsigned char uc = (unsigned char)raw;
                clean = (uc <= 0x07U || (uc >= 0x20U && uc <= 0x7EU)) ? raw : '?';
            }

            if (!ctx->shadow_valid || ctx->shadow[r][c] != clean) {
                if (ctx->cursor_row != r || ctx->cursor_col != c) {
                    lcd_ctx_set_cursor(ctx, r, c);
                }
                lcd_send_byte(ctx, (uint8_t)clean, 1U);
                ctx->shadow[r][c] = clean;
                ctx->cursor_col = (uint8_t)(c + 1U);
                written++;
            }
        }
    }

    ctx->shadow_valid = true;
    ctx->chars_written_last_frame = written;
    ctx->total_frames_rendered++;
}

void lcd_ctx_create_custom_char(LCDDriverContext *ctx, uint8_t location, const uint8_t charmap[8]) {
    if (!ctx || !ctx->initialized || !charmap) return;
    uint8_t slot = (uint8_t)(location & 0x07U);
    lcd_send_byte(ctx, (uint8_t)(0x40U | (slot << 3U)), 0U);
    for (int i = 0; i < 8; ++i) {
        lcd_send_byte(ctx, (uint8_t)(charmap[i] & 0x1FU), 1U);
    }
    // Invalida cursor DDRAM após escrita na CGRAM
    ctx->cursor_row = 0xFFU;
    ctx->cursor_col = 0xFFU;
}

void lcd_ctx_load_default_glyphs(LCDDriverContext *ctx) {
    if (!ctx || !ctx->initialized) return;
    for (uint8_t slot = 0U; slot < 8U; ++slot) {
        lcd_ctx_create_custom_char(ctx, slot, kDefaultGlyphs[slot]);
    }
}

// ---------------- Equivalência 1:1 com `Lcd20x4Renderer` (`terminal/renderer/lcd20x4.py`) ----------------

static const char *stage_short_3(PetStage s) {
    switch (s) {
        case STAGE_EGG:           return "EGG";
        case STAGE_CHICK:         return "CHK";
        case STAGE_CYBER_ROOSTER: return "CYB";
        default:                  return "PET";
    }
}

static const char *mood_short_4(PetMood m) {
    switch (m) {
        case MOOD_ECSTATIC: return "ECST";
        case MOOD_HAPPY:    return "HAPY";
        case MOOD_CONTENT:  return "OKAY";
        case MOOD_HUNGRY:   return "HNGR";
        case MOOD_TIRED:    return "TIRD";
        case MOOD_SAD:      return "SAD!";
        case MOOD_SICK:     return "SICK";
        case MOOD_SLEEPING: return "ZZZ.";
        default:            return "OKAY";
    }
}

static const char *anim_badge_6(PetAnimation a, uint32_t parity) {
    bool p0 = ((parity & 1UL) == 0UL);
    switch (a) {
        case ANIM_IDLE:     return p0 ? "*IDLE*" : ".IDLE.";
        case ANIM_EATING:   return p0 ? "~EAT!~" : "*CHMP*";
        case ANIM_PLAYING:  return p0 ? ">PLAY<" : "^JUMP^";
        case ANIM_SLEEPING: return p0 ? "zZZZZz" : ".zZZz.";
        case ANIM_PETTING:  return p0 ? "<3PET!" : "*LUV!*";
        case ANIM_HEALING:  return p0 ? "+HEAL+" : "*CURE*";
        case ANIM_EVOLVING: return p0 ? "!EVOL!" : "*LVL+*";
        case ANIM_SICK:     return p0 ? "!SICK!" : "!HELP!";
        default:            return p0 ? "*IDLE*" : ".IDLE.";
    }
}

static const char *select_face_6(const PetStateSnapshot *state, uint32_t parity) {
    bool p0 = ((parity & 1UL) == 0UL);
    if (state->stage == STAGE_EGG) {
        if (state->is_sleeping) {
            return p0 ? "(-_-)z" : "(-_-)Z";
        }
        return p0 ? "[o_o] " : "[O_o]~";
    }
    if (state->is_sleeping) {
        return p0 ? "(-v-)z" : "(-v-)Z";
    }
    if (state->mood == MOOD_SICK) {
        return p0 ? "(x_x)!" : "(+_+)!";
    }
    if (state->animation == ANIM_EATING) {
        return p0 ? "(>O<)*" : "(>v<).";
    }
    if (state->animation == ANIM_PLAYING) {
        return p0 ? "\\^v^/*" : "/^v^\\+";
    }
    if (state->animation == ANIM_PETTING) {
        return p0 ? "(^v^)<" : "(>v<)3";
    }
    if (state->animation == ANIM_EVOLVING) {
        return p0 ? "*\\O/*+" : "+/O\\*+";
    }
    if (state->mood == MOOD_HUNGRY) {
        return p0 ? "(oAo)?" : "(o_o)!";
    }
    if (state->mood == MOOD_SAD || state->mood == MOOD_TIRED) {
        return p0 ? "(;v;) " : "(._.) ";
    }
    if (state->mood == MOOD_ECSTATIC) {
        return p0 ? "(^v^)*" : "(^o^)*";
    }
    return p0 ? "(^v^) " : "(^v^)~";
}

static void put_padded_ascii(char *dst, size_t col_start, size_t width, const char *src) {
    bool ended = (src == NULL);
    for (size_t i = 0U; i < width; ++i) {
        char ch = ' ';
        if (!ended) {
            if (src[i] == '\0') {
                ended = true;
            } else {
                unsigned char uc = (unsigned char)src[i];
                ch = (uc >= 0x20U && uc <= 0x7EU) ? src[i] : '?';
            }
        }
        dst[col_start + i] = ch;
    }
}

static void put_right_int3(char *dst, size_t col_start, int val, bool zero_pad) {
    if (val < 0) val = 0;
    if (val > 999) val = 999;
    int d2 = (val / 100) % 10;
    int d1 = (val / 10) % 10;
    int d0 = val % 10;
    char pad = zero_pad ? '0' : ' ';

    dst[col_start + 0U] = (val >= 100) ? (char)('0' + d2) : pad;
    dst[col_start + 1U] = (val >= 10)  ? (char)('0' + d1) : ((val >= 100) ? '0' : pad);
    dst[col_start + 2U] = (char)('0' + d0);
}

void lcd_format_pet_frame(
    const PetStateSnapshot *state,
    uint32_t frame_idx,
    const SensorRawFrame *sensor,
    LCDFrameBuffer *out_frame
) {
    if (!state || !out_frame) return;
    uint32_t parity = frame_idx % 2UL;

    for (int r = 0; r < LCD_ROWS; ++r) {
        for (int c = 0; c < LCD_COLS; ++c) {
            out_frame->lines[r][c] = ' ';
        }
        out_frame->lines[r][LCD_COLS] = '\0';
    }

    // Linha 0: "{name[:7]:<7} {stage:3} L{lvl:02d} {mood:4}" -> 7+1+3+1+3+1+4 = 20
    char *l0 = out_frame->lines[0];
    put_padded_ascii(l0, 0U, 7U, state->name[0] ? state->name : "Pip");
    l0[7] = ' ';
    put_padded_ascii(l0, 8U, 3U, stage_short_3(state->stage));
    l0[11] = ' ';
    int lvl = (int)state->level;
    if (lvl < 1) lvl = 1;
    if (lvl > 99) lvl = 99;
    l0[12] = 'L';
    l0[13] = (char)('0' + ((lvl / 10) % 10));
    l0[14] = (char)('0' + (lvl % 10));
    l0[15] = ' ';
    put_padded_ascii(l0, 16U, 4U, mood_short_4(state->mood));

    // Linha 1: "{face:6} HG:{hg:3d} HP:{hp:3d}" -> 6+1+6+1+6 = 20
    char *l1 = out_frame->lines[1];
    put_padded_ascii(l1, 0U, 6U, select_face_6(state, parity));
    l1[6] = ' ';
    l1[7] = 'H'; l1[8] = 'G'; l1[9] = ':';
    put_right_int3(l1, 10U, fw_round_nonneg(state->hunger), false);
    l1[13] = ' ';
    l1[14] = 'H'; l1[15] = 'P'; l1[16] = ':';
    put_right_int3(l1, 17U, fw_round_nonneg(state->happiness), false);

    // Linha 2: "{badge:6} EN:{en:3d} HL:{hl:3d}" -> 6+1+6+1+6 = 20
    char *l2 = out_frame->lines[2];
    put_padded_ascii(l2, 0U, 6U, anim_badge_6(state->animation, parity));
    l2[6] = ' ';
    l2[7] = 'E'; l2[8] = 'N'; l2[9] = ':';
    put_right_int3(l2, 10U, fw_round_nonneg(state->energy), false);
    l2[13] = ' ';
    l2[14] = 'H'; l2[15] = 'L'; l2[16] = ':';
    put_right_int3(l2, 17U, fw_round_nonneg(state->health), false);

    // Linha 3: "D:{dist:03d}cm {last_action[:12]:<12}" ou "D:---cm {last_action[:12]:<12}"
    char *l3 = out_frame->lines[3];
    l3[0] = 'D'; l3[1] = ':';
    if (sensor != NULL && sensor->valid_ultrasonic && sensor->distance_cm >= 0.0f) {
        int dist_i = fw_round_nonneg(sensor->distance_cm);
        if (dist_i > 999) dist_i = 999;
        put_right_int3(l3, 2U, dist_i, true);
    } else {
        l3[2] = '-'; l3[3] = '-'; l3[4] = '-';
    }
    l3[5] = 'c'; l3[6] = 'm'; l3[7] = ' ';
    put_padded_ascii(l3, 8U, 12U, state->last_action[0] ? state->last_action : "READY");
}

// Wrappers globais de compatibilidade
bool lcd_init(const LCDPinConfig *cfg) {
    return lcd_ctx_init(&g_default_lcd_ctx, cfg, NULL);
}

void lcd_clear(void) {
    lcd_ctx_clear(&g_default_lcd_ctx);
}

void lcd_set_cursor(uint8_t row, uint8_t col) {
    lcd_ctx_set_cursor(&g_default_lcd_ctx, row, col);
}

void lcd_print(const char *str) {
    lcd_ctx_print(&g_default_lcd_ctx, str);
}

void lcd_print_line(uint8_t row, const char *line) {
    lcd_ctx_print_line(&g_default_lcd_ctx, row, line);
}

void lcd_render_frame(const LCDFrameBuffer *frame) {
    lcd_ctx_render_frame(&g_default_lcd_ctx, frame);
}

void lcd_create_custom_char(uint8_t location, const uint8_t charmap[8]) {
    lcd_ctx_create_custom_char(&g_default_lcd_ctx, location, charmap);
}

void lcd_load_default_glyphs(void) {
    lcd_ctx_load_default_glyphs(&g_default_lcd_ctx);
}
