#ifndef MOTIONPET_LCD2004_ANIM_H
#define MOTIONPET_LCD2004_ANIM_H

#include <stdint.h>
#include "display/lcd2004_driver.h"

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Toca a animacao de boot (~2,95 s): ovo balanca, racha e o pintinho nasce.
 *
 * Usa sprites 10x16 px montados com 4 glifos 5x8 nos codigos 1..4 da CGRAM (o codigo 0
 * nao pode ser usado, pois termina a string do quadro). Ao terminar, restaura os glifos
 * padrao e limpa a tela. Requer lcd_ctx_load_default_glyphs ja chamado antes.
 * Bloqueia apenas pelo tempo dos quadros via ctx->hal.delay_us. Sem alocacao dinamica.
 */
void lcd_play_boot_animation(LCDDriverContext *ctx);

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_LCD2004_ANIM_H
