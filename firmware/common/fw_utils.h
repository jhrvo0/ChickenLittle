#ifndef MOTIONPET_FW_UTILS_H
#define MOTIONPET_FW_UTILS_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>

/**
 * @file fw_utils.h
 * @brief Utilitarios C/C++ deterministicos e zero-heap (sem dependencia de libc/String dinamica).
 *        Compativel simultaneamente com Xtensa ESP32 (ESP-IDF/Arduino) e compilacao freestanding em host.
 */

static inline size_t fw_strlen(const char *s) {
    if (!s) return 0U;
    size_t n = 0U;
    while (s[n] != '\0') {
        ++n;
    }
    return n;
}

static inline int fw_strcmp(const char *a, const char *b) {
    if (a == b) return 0;
    if (!a) return -1;
    if (!b) return 1;
    while (*a != '\0' && (*a == *b)) {
        ++a;
        ++b;
    }
    return (int)((unsigned char)*a) - (int)((unsigned char)*b);
}

static inline int fw_strncmp(const char *a, const char *b, size_t max_n) {
    if (max_n == 0U || a == b) return 0;
    if (!a) return -1;
    if (!b) return 1;
    for (size_t i = 0U; i < max_n; ++i) {
        if (a[i] != b[i] || a[i] == '\0') {
            return (int)((unsigned char)a[i]) - (int)((unsigned char)b[i]);
        }
    }
    return 0;
}

static inline char fw_toupper(char c) {
    if (c >= 'a' && c <= 'z') {
        return (char)(c - ('a' - 'A'));
    }
    return c;
}

static inline int fw_stricmp(const char *a, const char *b) {
    if (a == b) return 0;
    if (!a) return -1;
    if (!b) return 1;
    while (*a != '\0' && (fw_toupper(*a) == fw_toupper(*b))) {
        ++a;
        ++b;
    }
    return (int)((unsigned char)fw_toupper(*a)) - (int)((unsigned char)fw_toupper(*b));
}

static inline void fw_copy_trunc(char *dst, size_t dst_cap, const char *src, size_t max_chars) {
    if (!dst || dst_cap == 0U) return;
    size_t limit = (max_chars < (dst_cap - 1U)) ? max_chars : (dst_cap - 1U);
    size_t i = 0U;
    if (src) {
        while (i < limit && src[i] != '\0') {
            dst[i] = src[i];
            ++i;
        }
    }
    dst[i] = '\0';
}

static inline void fw_strncpy(char *dst, const char *src, size_t dst_cap) {
    if (!dst || dst_cap == 0U) return;
    fw_copy_trunc(dst, dst_cap, src, dst_cap - 1U);
}

static inline float fw_clamp_2dp(float val, float low, float high) {
    double d = (double)val;
    if (d < (double)low) d = (double)low;
    if (d > (double)high) d = (double)high;
    int64_t scaled = (d >= 0.0) ? (int64_t)(d * 100.0 + 0.5) : (int64_t)(d * 100.0 - 0.5);
    return (float)((double)scaled / 100.0);
}

static inline int fw_round_nonneg(float val) {
    if (val <= 0.0f) return 0;
    // Python round() usa half-to-even; para inteiros + .5 usamos half-to-even compativel
    double d = (double)val;
    int64_t fl = (int64_t)d;
    double frac = d - (double)fl;
    if (frac > 0.5 + 1e-9) return (int)(fl + 1);
    if (frac < 0.5 - 1e-9) return (int)fl;
    return (int)((fl % 2 == 0) ? fl : (fl + 1));
}

typedef struct {
    char *buf;
    size_t cap;
    size_t pos;
    bool overflow;
} FwJsonWriter;

static inline void jw_init(FwJsonWriter *w, char *buffer, size_t capacity) {
    w->buf = buffer;
    w->cap = capacity;
    w->pos = 0U;
    w->overflow = (buffer == NULL || capacity < 2U);
    if (!w->overflow) {
        w->buf[0] = '\0';
    }
}

static inline void jw_putc(FwJsonWriter *w, char c) {
    if (w->overflow) return;
    if (w->pos + 1U >= w->cap) {
        w->overflow = true;
        return;
    }
    w->buf[w->pos++] = c;
    w->buf[w->pos] = '\0';
}

static inline void jw_puts(FwJsonWriter *w, const char *s) {
    if (!s || w->overflow) return;
    while (*s != '\0') {
        jw_putc(w, *s++);
    }
}

static inline void jw_put_escaped_str(FwJsonWriter *w, const char *s) {
    jw_putc(w, '"');
    if (s) {
        while (*s != '\0') {
            unsigned char c = (unsigned char)*s++;
            if (c == '"' || c == '\\') {
                jw_putc(w, '\\');
                jw_putc(w, (char)c);
            } else if (c == '\n') {
                jw_puts(w, "\\n");
            } else if (c == '\r') {
                jw_puts(w, "\\r");
            } else if (c == '\t') {
                jw_puts(w, "\\t");
            } else if (c >= 0x20U && c <= 0x7EU) {
                jw_putc(w, (char)c);
            } else {
                jw_putc(w, '?');
            }
        }
    }
    jw_putc(w, '"');
}

static inline void jw_put_u32(FwJsonWriter *w, uint32_t val) {
    char tmp[12];
    int idx = 0;
    if (val == 0UL) {
        jw_putc(w, '0');
        return;
    }
    while (val > 0UL && idx < 11) {
        tmp[idx++] = (char)('0' + (val % 10UL));
        val /= 10UL;
    }
    while (idx > 0) {
        jw_putc(w, tmp[--idx]);
    }
}

static inline void jw_put_i32(FwJsonWriter *w, int32_t val) {
    if (val < 0) {
        jw_putc(w, '-');
        uint32_t mag = (uint32_t)(-(int64_t)val);
        jw_put_u32(w, mag);
    } else {
        jw_put_u32(w, (uint32_t)val);
    }
}

static inline void jw_put_bool(FwJsonWriter *w, bool b) {
    jw_puts(w, b ? "true" : "false");
}

static inline void jw_put_fixed(FwJsonWriter *w, float val, uint8_t decimals) {
    double scale = 1.0;
    for (uint8_t i = 0U; i < decimals; ++i) {
        scale *= 10.0;
    }
    double d = (double)val;
    if (d < 0.0) {
        jw_putc(w, '-');
        d = -d;
    }
    uint64_t rounded = (uint64_t)(d * scale + 0.5);
    uint64_t iscale = (uint64_t)scale;
    uint32_t int_part = (uint32_t)(rounded / iscale);
    uint32_t frac_part = (uint32_t)(rounded % iscale);

    jw_put_u32(w, int_part);
    if (decimals > 0U) {
        jw_putc(w, '.');
        char fbuf[8];
        for (int i = (int)decimals - 1; i >= 0; --i) {
            fbuf[i] = (char)('0' + (frac_part % 10UL));
            frac_part /= 10UL;
        }
        for (uint8_t i = 0U; i < decimals; ++i) {
            jw_putc(w, fbuf[i]);
        }
    }
}

#endif // MOTIONPET_FW_UTILS_H
