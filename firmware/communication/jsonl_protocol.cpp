#include "communication/jsonl_protocol.h"
#include "common/fw_utils.h"

static const char *gesture_source_str(GestureSource src) {
    switch (src) {
        case GESTURE_SOURCE_SIM_KEYBOARD: return "sim_keyboard";
        case GESTURE_SOURCE_SIM_SENSOR:   return "sim_sensor";
        case GESTURE_SOURCE_RULE_BASELINE:return "rule_baseline";
        case GESTURE_SOURCE_TINYML:       return "tinyml";
        default:                          return "tinyml";
    }
}

static GestureSource gesture_source_parse(const char *s) {
    if (!s) return GESTURE_SOURCE_TINYML;
    if (fw_strcmp(s, "sim_keyboard") == 0)  return GESTURE_SOURCE_SIM_KEYBOARD;
    if (fw_strcmp(s, "sim_sensor") == 0)    return GESTURE_SOURCE_SIM_SENSOR;
    if (fw_strcmp(s, "rule_baseline") == 0) return GESTURE_SOURCE_RULE_BASELINE;
    return GESTURE_SOURCE_TINYML;
}

static const char *local_gesture_to_str(GestureType g) {
    switch (g) {
        case GESTURE_APPROACH: return "APPROACH";
        case GESTURE_RETREAT:  return "RETREAT";
        case GESTURE_HOLD:     return "HOLD";
        case GESTURE_IMPULSE:  return "IMPULSE";
        case GESTURE_DOUBLE:   return "DOUBLE";
        case GESTURE_NEUTRAL:
        default:               return "NEUTRAL";
    }
}

static bool local_gesture_parse(const char *s, GestureType *out_g) {
    if (!s || !out_g) return false;
    if (fw_strcmp(s, "NEUTRAL") == 0)  { *out_g = GESTURE_NEUTRAL;  return true; }
    if (fw_strcmp(s, "APPROACH") == 0) { *out_g = GESTURE_APPROACH; return true; }
    if (fw_strcmp(s, "RETREAT") == 0)  { *out_g = GESTURE_RETREAT;  return true; }
    if (fw_strcmp(s, "HOLD") == 0)     { *out_g = GESTURE_HOLD;     return true; }
    if (fw_strcmp(s, "IMPULSE") == 0)  { *out_g = GESTURE_IMPULSE;  return true; }
    if (fw_strcmp(s, "DOUBLE") == 0)   { *out_g = GESTURE_DOUBLE;   return true; }
    return false;
}

static const char *local_stage_to_str(PetStage st) {
    switch (st) {
        case STAGE_CHICK:         return "CHICK";
        case STAGE_CYBER_ROOSTER: return "CYBER_ROOSTER";
        case STAGE_EGG:
        default:                  return "EGG";
    }
}

static const char *local_mood_to_str(PetMood m) {
    switch (m) {
        case MOOD_ECSTATIC: return "ECSTATIC";
        case MOOD_HAPPY:    return "HAPPY";
        case MOOD_CONTENT:  return "CONTENT";
        case MOOD_HUNGRY:   return "HUNGRY";
        case MOOD_TIRED:    return "TIRED";
        case MOOD_SAD:      return "SAD";
        case MOOD_SICK:     return "SICK";
        case MOOD_SLEEPING: return "SLEEPING";
        default:            return "CONTENT";
    }
}

static const char *local_personality_to_str(PetPersonality p) {
    switch (p) {
        case PERSONALITY_PLAYFUL: return "PLAYFUL";
        case PERSONALITY_FOODIE:  return "FOODIE";
        case PERSONALITY_ZEN:     return "ZEN";
        case PERSONALITY_CURIOUS:
        default:                  return "CURIOUS";
    }
}

static const char *local_anim_to_str(PetAnimation a) {
    switch (a) {
        case ANIM_EATING:   return "EATING";
        case ANIM_PLAYING:  return "PLAYING";
        case ANIM_SLEEPING: return "SLEEPING";
        case ANIM_PETTING:  return "PETTING";
        case ANIM_HEALING:  return "HEALING";
        case ANIM_EVOLVING: return "EVOLVING";
        case ANIM_SICK:     return "SICK";
        case ANIM_IDLE:
        default:            return "IDLE";
    }
}

static bool local_cmd_parse(const char *s, PetCommandType *out_cmd) {
    if (!s || !out_cmd) return false;
    if (fw_strcmp(s, "FEED") == 0)        { *out_cmd = CMD_FEED;        return true; }
    if (fw_strcmp(s, "PLAY") == 0)        { *out_cmd = CMD_PLAY;        return true; }
    if (fw_strcmp(s, "REST") == 0)        { *out_cmd = CMD_REST;        return true; }
    if (fw_strcmp(s, "HEAL") == 0)        { *out_cmd = CMD_HEAL;        return true; }
    if (fw_strcmp(s, "INTERACT") == 0)    { *out_cmd = CMD_INTERACT;    return true; }
    if (fw_strcmp(s, "SAVE") == 0)        { *out_cmd = CMD_SAVE;        return true; }
    if (fw_strcmp(s, "LOAD") == 0)        { *out_cmd = CMD_LOAD;        return true; }
    if (fw_strcmp(s, "RESET") == 0)       { *out_cmd = CMD_RESET;       return true; }
    if (fw_strcmp(s, "SWITCH_MODE") == 0) { *out_cmd = CMD_SWITCH_MODE; return true; }
    if (fw_strcmp(s, "TICK") == 0)        { *out_cmd = CMD_TICK;        return true; }
    return false;
}

static void jw_begin_envelope(FwJsonWriter *w, JsonlContext *ctx, const char *msg_type, uint32_t ts_ms) {
    uint32_t seq = ctx->seq_tx++;
    jw_puts(w, "{\"v\":1,\"seq\":");
    jw_put_u32(w, seq);
    jw_puts(w, ",\"type\":");
    jw_put_escaped_str(w, msg_type);
    jw_puts(w, ",\"ts_ms\":");
    jw_put_u32(w, ts_ms);
    jw_puts(w, ",\"data\":{");
}

static bool jw_finish_envelope(FwJsonWriter *w, JsonlContext *ctx) {
    jw_puts(w, "}}\n");
    if (w->overflow) {
        // Reverte incremento de seq caso o buffer fornecido seja pequeno demais
        ctx->seq_tx--;
        return false;
    }
    return true;
}

void jsonl_init(JsonlContext *ctx) {
    if (!ctx) return;
    ctx->seq_tx = 1UL;
    ctx->seq_rx_last = 0UL;
    ctx->dropped_frames = 0UL;
    ctx->parse_errors = 0UL;
    ctx->has_rx_seq = false;
}

bool jsonl_serialize_sensor_frame(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const SensorRawFrame *frame
) {
    if (!ctx || !buffer || !frame) return false;
    FwJsonWriter w;
    jw_init(&w, buffer, max_len);
    jw_begin_envelope(&w, ctx, "sensor_frame", ts_ms);

    jw_puts(&w, "\"distance_cm\":");
    if (frame->valid_ultrasonic && frame->distance_cm >= 0.0f) {
        jw_put_fixed(&w, frame->distance_cm, 2U);
    } else {
        jw_puts(&w, "null");
    }

    jw_puts(&w, ",\"ir_detected\":");
    jw_put_bool(&w, frame->ir_detected);

    float pn = frame->pot_norm;
    if (pn < 0.0f) pn = 0.0f;
    if (pn > 1.0f) pn = 1.0f;
    jw_puts(&w, ",\"pot_norm\":");
    jw_put_fixed(&w, pn, 4U);

    jw_puts(&w, ",\"valid_ultrasonic\":");
    jw_put_bool(&w, frame->valid_ultrasonic && frame->distance_cm >= 0.0f);

    // Dados brutos de diagnostico da mesma amostra; nao alteram a captura.
    jw_puts(&w, ",\"echo_duration_us\":");
    jw_put_u32(&w, frame->echo_duration_us);
    jw_puts(&w, ",\"acquire_duration_us\":");
    jw_put_u32(&w, frame->acquire_duration_us);

    return jw_finish_envelope(&w, ctx);
}

bool jsonl_serialize_gesture_event(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const GestureEvent *event
) {
    if (!ctx || !buffer || !event) return false;
    FwJsonWriter w;
    jw_init(&w, buffer, max_len);
    jw_begin_envelope(&w, ctx, "gesture_event", ts_ms);

    jw_puts(&w, "\"gesture\":");
    jw_put_escaped_str(&w, local_gesture_to_str(event->gesture));

    float conf = event->confidence;
    if (conf < 0.0f) conf = 0.0f;
    if (conf > 1.0f) conf = 1.0f;
    jw_puts(&w, ",\"confidence\":");
    jw_put_fixed(&w, conf, 4U);

    jw_puts(&w, ",\"source\":");
    jw_put_escaped_str(&w, gesture_source_str(event->source));

    uint32_t win = (event->window_ms > 0U) ? (uint32_t)event->window_ms : 600UL;
    jw_puts(&w, ",\"window_ms\":");
    jw_put_u32(&w, win);

    return jw_finish_envelope(&w, ctx);
}

bool jsonl_serialize_pet_state(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const PetStateSnapshot *state
) {
    if (!ctx || !buffer || !state) return false;
    FwJsonWriter w;
    jw_init(&w, buffer, max_len);
    jw_begin_envelope(&w, ctx, "pet_state", ts_ms);

    jw_puts(&w, "\"name\":");
    jw_put_escaped_str(&w, state->name[0] ? state->name : "Pip");
    jw_puts(&w, ",\"hunger\":");
    jw_put_fixed(&w, state->hunger, 2U);
    jw_puts(&w, ",\"happiness\":");
    jw_put_fixed(&w, state->happiness, 2U);
    jw_puts(&w, ",\"energy\":");
    jw_put_fixed(&w, state->energy, 2U);
    jw_puts(&w, ",\"health\":");
    jw_put_fixed(&w, state->health, 2U);
    jw_puts(&w, ",\"xp\":");
    jw_put_u32(&w, state->xp);
    jw_puts(&w, ",\"level\":");
    jw_put_u32(&w, (uint32_t)(state->level >= 1U ? state->level : 1U));
    jw_puts(&w, ",\"stage\":");
    jw_put_escaped_str(&w, local_stage_to_str(state->stage));
    jw_puts(&w, ",\"mood\":");
    jw_put_escaped_str(&w, local_mood_to_str(state->mood));
    jw_puts(&w, ",\"personality\":");
    jw_put_escaped_str(&w, local_personality_to_str(state->personality));
    jw_puts(&w, ",\"animation\":");
    jw_put_escaped_str(&w, local_anim_to_str(state->animation));
    jw_puts(&w, ",\"animation_ttl_ticks\":");
    jw_put_u32(&w, (uint32_t)state->animation_ttl_ticks);
    jw_puts(&w, ",\"is_sleeping\":");
    jw_put_bool(&w, state->is_sleeping);
    jw_puts(&w, ",\"age_ticks\":");
    jw_put_u32(&w, state->age_ticks);
    jw_puts(&w, ",\"last_action\":");
    jw_put_escaped_str(&w, state->last_action[0] ? state->last_action : "READY");

    jw_puts(&w, ",\"care_counters\":{\"feed\":");
    jw_put_u32(&w, (uint32_t)state->care_counters.feed);
    jw_puts(&w, ",\"play\":");
    jw_put_u32(&w, (uint32_t)state->care_counters.play);
    jw_puts(&w, ",\"rest\":");
    jw_put_u32(&w, (uint32_t)state->care_counters.rest);
    jw_puts(&w, ",\"interact\":");
    jw_put_u32(&w, (uint32_t)state->care_counters.interact);
    jw_puts(&w, ",\"heal\":");
    jw_put_u32(&w, (uint32_t)state->care_counters.heal);
    jw_putc(&w, '}');

    jw_puts(&w, ",\"coins\":");
    jw_put_u32(&w, state->coins);
    jw_puts(&w, ",\"best_launch_distance_m\":");
    jw_put_fixed(&w, state->best_launch_distance_m, 2U);
    jw_puts(&w, ",\"best_launch_score\":");
    jw_put_u32(&w, state->best_launch_score);
    jw_puts(&w, ",\"total_launches\":");
    jw_put_u32(&w, state->total_launches);
    jw_puts(&w, ",\"unlocked_upgrades\":[");
    bool comma = false;
    if (state->launch_upgrades & 1U) { jw_put_escaped_str(&w, "SLINGSHOT_PRO"); comma = true; }
    if (state->launch_upgrades & 2U) { if (comma) jw_putc(&w, ','); jw_put_escaped_str(&w, "AERO_CAPE"); comma = true; }
    if (state->launch_upgrades & 4U) { if (comma) jw_putc(&w, ','); jw_put_escaped_str(&w, "SPRING_BOOTS"); }
    jw_putc(&w, ']');

    return jw_finish_envelope(&w, ctx);
}

bool jsonl_serialize_lcd_frame(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const LCDFrameBuffer *lcd
) {
    if (!ctx || !buffer || !lcd) return false;
    FwJsonWriter w;
    jw_init(&w, buffer, max_len);
    jw_begin_envelope(&w, ctx, "lcd_frame", ts_ms);

    jw_puts(&w, "\"lines\":[");
    for (int r = 0; r < LCD_ROWS; ++r) {
        if (r > 0) jw_putc(&w, ',');
        char exact20[LCD_COLS + 1];
        bool ended = false;
        for (int c = 0; c < LCD_COLS; ++c) {
            char ch = lcd->lines[r][c];
            if (ch == '\0') ended = true;
            if (ended) {
                exact20[c] = ' ';
            } else {
                unsigned char uc = (unsigned char)ch;
                exact20[c] = (uc >= 0x20U && uc <= 0x7EU) ? ch : '?';
            }
        }
        exact20[LCD_COLS] = '\0';
        jw_put_escaped_str(&w, exact20);
    }
    jw_putc(&w, ']');

    return jw_finish_envelope(&w, ctx);
}

bool jsonl_serialize_ack(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    uint32_t ack_seq,
    const char *status
) {
    if (!ctx || !buffer) return false;
    FwJsonWriter w;
    jw_init(&w, buffer, max_len);
    jw_begin_envelope(&w, ctx, "ack", ts_ms);

    jw_puts(&w, "\"ack_seq\":");
    jw_put_u32(&w, ack_seq);
    jw_puts(&w, ",\"status\":");
    jw_put_escaped_str(&w, status ? status : "ok");

    return jw_finish_envelope(&w, ctx);
}

bool jsonl_serialize_error_ex(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const char *err_code,
    const char *err_message,
    int64_t ref_seq
) {
    if (!ctx || !buffer) return false;
    FwJsonWriter w;
    jw_init(&w, buffer, max_len);
    jw_begin_envelope(&w, ctx, "error", ts_ms);

    jw_puts(&w, "\"code\":");
    jw_put_escaped_str(&w, err_code ? err_code : "ERR_UNKNOWN");
    jw_puts(&w, ",\"message\":");
    jw_put_escaped_str(&w, err_message ? err_message : "error");
    jw_puts(&w, ",\"ref_seq\":");
    if (ref_seq >= 0) {
        jw_put_u32(&w, (uint32_t)ref_seq);
    } else {
        jw_puts(&w, "null");
    }

    return jw_finish_envelope(&w, ctx);
}

bool jsonl_serialize_error(
    JsonlContext *ctx,
    char *buffer,
    size_t max_len,
    uint32_t ts_ms,
    const char *err_code,
    const char *err_message
) {
    return jsonl_serialize_error_ex(ctx, buffer, max_len, ts_ms, err_code, err_message, -1);
}

// ---------------- Parser estático zero-heap para linhas recebidas ----------------
//
// Duas etapas, ambas sem alocação dinâmica:
//   1. jv_validate_line(): valida a sintaxe JSON estrita (RFC 8259) da linha inteira, com
//      profundidade máxima fixa (JV_MAX_DEPTH) e sem lixo após o objeto raiz.
//   2. obj_find(): como o texto já é válido, procura uma chave apenas entre os membros
//      DIRETOS de um objeto (nunca em objetos/arrays aninhados) e acusa chave duplicada.

#define JV_MAX_DEPTH 8

static const char *skip_ws(const char *p) {
    while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n') {
        ++p;
    }
    return p;
}

static bool jv_is_digit(char c) { return c >= '0' && c <= '9'; }

static bool jv_is_hex(char c) {
    return jv_is_digit(c) || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F');
}

// `*pp` aponta para a aspa de abertura; avança para depois da aspa de fechamento.
static bool jv_string(const char **pp) {
    const char *p = *pp + 1;
    while (*p != '\0') {
        unsigned char c = (unsigned char)*p;
        if (c == '"') {
            *pp = p + 1;
            return true;
        }
        if (c < 0x20U) return false;
        if (c == '\\') {
            ++p;
            switch (*p) {
                case '"': case '\\': case '/': case 'b': case 'f': case 'n': case 'r': case 't':
                    break;
                case 'u':
                    for (int i = 1; i <= 4; ++i) {
                        if (!jv_is_hex(p[i])) return false;
                    }
                    p += 4;
                    break;
                default:
                    return false;
            }
        }
        ++p;
    }
    return false;
}

// number = [-] (0 | 1-9 digits) [. digits] [(e|E) [+|-] digits]
static bool jv_number(const char **pp) {
    const char *p = *pp;
    if (*p == '-') ++p;
    if (*p == '0') {
        ++p;
    } else if (*p >= '1' && *p <= '9') {
        while (jv_is_digit(*p)) ++p;
    } else {
        return false;
    }
    if (*p == '.') {
        ++p;
        if (!jv_is_digit(*p)) return false;
        while (jv_is_digit(*p)) ++p;
    }
    if (*p == 'e' || *p == 'E') {
        ++p;
        if (*p == '+' || *p == '-') ++p;
        if (!jv_is_digit(*p)) return false;
        while (jv_is_digit(*p)) ++p;
    }
    *pp = p;
    return true;
}

static bool jv_value(const char **pp, int depth);

static bool jv_literal(const char **pp, const char *word) {
    size_t n = fw_strlen(word);
    if (fw_strncmp(*pp, word, n) != 0) return false;
    *pp += n;
    return true;
}

static bool jv_object(const char **pp, int depth) {
    const char *p = skip_ws(*pp + 1);
    if (*p == '}') {
        *pp = p + 1;
        return true;
    }
    for (;;) {
        p = skip_ws(p);
        if (*p != '"' || !jv_string(&p)) return false;
        p = skip_ws(p);
        if (*p != ':') return false;
        p = skip_ws(p + 1);
        if (!jv_value(&p, depth + 1)) return false;
        p = skip_ws(p);
        if (*p == ',') {
            ++p;
            continue;
        }
        if (*p == '}') {
            *pp = p + 1;
            return true;
        }
        return false;
    }
}

static bool jv_array(const char **pp, int depth) {
    const char *p = skip_ws(*pp + 1);
    if (*p == ']') {
        *pp = p + 1;
        return true;
    }
    for (;;) {
        p = skip_ws(p);
        if (!jv_value(&p, depth + 1)) return false;
        p = skip_ws(p);
        if (*p == ',') {
            ++p;
            continue;
        }
        if (*p == ']') {
            *pp = p + 1;
            return true;
        }
        return false;
    }
}

static bool jv_value(const char **pp, int depth) {
    if (depth > JV_MAX_DEPTH) return false;
    switch (**pp) {
        case '{': return jv_object(pp, depth);
        case '[': return jv_array(pp, depth);
        case '"': return jv_string(pp);
        case 't': return jv_literal(pp, "true");
        case 'f': return jv_literal(pp, "false");
        case 'n': return jv_literal(pp, "null");
        default:  return jv_number(pp);
    }
}

// A linha inteira deve ser exatamente um objeto JSON válido (sem lixo depois).
static bool jv_validate_line(const char *line) {
    const char *p = line;
    if (*p != '{') return false;
    if (!jv_object(&p, 1)) return false;
    return *skip_ws(p) == '\0';
}

// Pula um valor de um texto JÁ validado por jv_validate_line().
static const char *jv_skip_value(const char *p) {
    if (*p == '"') {
        ++p;
        while (*p != '\0' && *p != '"') {
            if (*p == '\\' && p[1] != '\0') ++p;
            ++p;
        }
        return (*p == '"') ? p + 1 : p;
    }
    if (*p == '{' || *p == '[') {
        int depth = 0;
        while (*p != '\0') {
            if (*p == '"') {
                p = jv_skip_value(p);
                continue;
            }
            if (*p == '{' || *p == '[') ++depth;
            else if (*p == '}' || *p == ']') --depth;
            ++p;
            if (depth == 0) break;
        }
        return p;
    }
    while (*p != '\0' && *p != ',' && *p != '}' && *p != ']' &&
           *p != ' ' && *p != '\t' && *p != '\r' && *p != '\n') {
        ++p;
    }
    return p;
}

// `obj` aponta para o '{' de um objeto já validado. Devolve o início do valor do membro
// direto `key`, ou NULL se ausente. Chave repetida no mesmo objeto => NULL e *dup = true.
static const char *obj_find(const char *obj, const char *key, bool *dup) {
    if (dup) *dup = false;
    if (!obj || *obj != '{') return NULL;
    size_t klen = fw_strlen(key);
    const char *found = NULL;
    const char *p = skip_ws(obj + 1);
    while (*p == '"') {
        const char *name = p + 1;
        const char *after = jv_skip_value(p);
        bool match = (size_t)(after - 1 - name) == klen && fw_strncmp(name, key, klen) == 0;
        p = skip_ws(after);
        if (*p != ':') return NULL;
        p = skip_ws(p + 1);
        if (match) {
            if (found) {
                if (dup) *dup = true;
                return NULL;
            }
            found = p;
        }
        p = skip_ws(jv_skip_value(p));
        if (*p != ',') break;
        p = skip_ws(p + 1);
    }
    return found;
}

// Parâmetros de comando: membro de `data` ou, na falta, de `data.payload` (formato do app).
static const char *param_find(const char *data, const char *key) {
    bool dup = false;
    const char *v = obj_find(data, key, &dup);
    if (v || dup) return v;
    const char *payload = obj_find(data, "payload", &dup);
    if (!payload || *payload != '{') return NULL;
    return obj_find(payload, key, &dup);
}

// Devolve true se o valor é uma string que cabe inteira em out_buf (sem truncar).
static bool extract_string_at(const char *val, char *out_buf, size_t cap) {
    if (!val || *val != '"' || !out_buf || cap == 0U) return false;
    ++val;
    size_t i = 0U;
    while (*val != '\0' && *val != '"') {
        if (*val == '\\' && val[1] != '\0') {
            ++val;
        }
        if (i + 1U >= cap) return false;
        out_buf[i++] = *val;
        ++val;
    }
    if (*val != '"') return false;
    out_buf[i] = '\0';
    return true;
}

// Inteiro sem sinal estrito: 0 | [1-9][0-9]*, sem fração/expoente, cabendo em uint32_t.
static bool extract_u32_at(const char *val, uint32_t *out_val) {
    if (!val || !out_val || !jv_is_digit(*val)) return false;
    uint64_t acc = 0ULL;
    while (jv_is_digit(*val)) {
        acc = acc * 10ULL + (uint64_t)(*val - '0');
        if (acc > 0xFFFFFFFFULL) return false;
        ++val;
    }
    if (*val == '.' || *val == 'e' || *val == 'E') return false;
    *out_val = (uint32_t)acc;
    return true;
}

// Número JSON completo (sinal, fração e expoente); rejeita valores fora do alcance de float.
static bool extract_float_at(const char *val, float *out_val) {
    if (!val || !out_val) return false;
    bool neg = false;
    if (*val == '-') {
        neg = true;
        ++val;
    }
    if (!jv_is_digit(*val)) return false;
    uint64_t mant = 0ULL;
    int exp10 = 0;
    while (jv_is_digit(*val)) {
        if (mant < 100000000000000000ULL) mant = mant * 10ULL + (uint64_t)(*val - '0');
        else ++exp10;
        ++val;
    }
    if (*val == '.') {
        ++val;
        while (jv_is_digit(*val)) {
            if (mant < 100000000000000000ULL) {
                mant = mant * 10ULL + (uint64_t)(*val - '0');
                --exp10;
            }
            ++val;
        }
    }
    if (*val == 'e' || *val == 'E') {
        ++val;
        bool eneg = false;
        if (*val == '+' || *val == '-') {
            eneg = (*val == '-');
            ++val;
        }
        int e = 0;
        while (jv_is_digit(*val)) {
            if (e < 1000) e = e * 10 + (*val - '0');
            ++val;
        }
        exp10 += eneg ? -e : e;
    }
    if (exp10 > 308 || exp10 < -400) return false;
    double res = (double)mant;
    for (int i = 0; i < exp10; ++i) res *= 10.0;
    for (int i = 0; i > exp10; --i) res /= 10.0;
    if (res > 3.0e38) return false;
    *out_val = (float)(neg ? -res : res);
    return true;
}

static bool extract_bool_at(const char *val, bool *out_val) {
    if (!val || !out_val) return false;
    if (fw_strncmp(val, "true", 4U) == 0) {
        *out_val = true;
        return true;
    }
    if (fw_strncmp(val, "false", 5U) == 0) {
        *out_val = false;
        return true;
    }
    return false;
}

// Atalhos por chave: membro direto de `obj` (envelope, `data` ou gesto) ...
static bool obj_string(const char *obj, const char *key, char *out, size_t cap) {
    bool dup = false;
    return extract_string_at(obj_find(obj, key, &dup), out, cap);
}
static bool obj_u32(const char *obj, const char *key, uint32_t *out) {
    bool dup = false;
    return extract_u32_at(obj_find(obj, key, &dup), out);
}
static bool obj_float(const char *obj, const char *key, float *out) {
    bool dup = false;
    return extract_float_at(obj_find(obj, key, &dup), out);
}
// ... e parâmetros de comando (`data` ou `data.payload`).
static bool param_string(const char *data, const char *key, char *out, size_t cap) {
    return extract_string_at(param_find(data, key), out, cap);
}
static bool param_u32(const char *data, const char *key, uint32_t *out) {
    return extract_u32_at(param_find(data, key), out);
}
static bool param_float(const char *data, const char *key, float *out) {
    return extract_float_at(param_find(data, key), out);
}
static bool param_bool(const char *data, const char *key, bool *out) {
    return extract_bool_at(param_find(data, key), out);
}

static void record_rx_seq(JsonlContext *ctx, uint32_t seq) {
    if (ctx->has_rx_seq && seq > ctx->seq_rx_last + 1UL) {
        ctx->dropped_frames += (seq - ctx->seq_rx_last - 1UL);
    }
    ctx->seq_rx_last = seq;
    ctx->has_rx_seq = true;
}

// Aceita exatamente quatro linhas ASCII de 20 colunas, inclusive aspas e barras
// invertidas escapadas conforme JSON. Não trunca quadros malformados.
static bool parse_lcd_lines(const char *data, LCDFrameBuffer *out) {
    bool dup = false;
    const char *p = obj_find(data, "lines", &dup);
    if (!p || *p++ != '[') return false;
    for (unsigned row = 0; row < LCD_ROWS; ++row) {
        p = skip_ws(p);
        if (*p++ != '"') return false;
        unsigned col = 0;
        while (*p && *p != '"') {
            unsigned char ch = (unsigned char)*p++;
            if (ch == '\\') {
                ch = (unsigned char)*p++;
                if (ch != '"' && ch != '\\' && ch != '/') return false;
            }
            if (ch < 0x20U || ch > 0x7eU || col >= LCD_COLS) return false;
            out->lines[row][col++] = (char)ch;
        }
        if (*p++ != '"' || col != LCD_COLS) return false;
        out->lines[row][LCD_COLS] = '\0';
        p = skip_ws(p);
        if (*p++ != (row + 1U == LCD_ROWS ? ']' : ',')) return false;
    }
    return true;
}

static void clear_parsed(JsonlRxParsed *p) {
    p->kind = RX_MSG_INVALID;
    p->seq = 0UL;
    p->pet_cmd = CMD_TICK;
    p->mode_arg[0] = '\0';
    p->launch = LaunchCommand{};
    p->injected_gesture.gesture = GESTURE_NEUTRAL;
    p->injected_gesture.confidence = 0.0f;
    p->injected_gesture.source = GESTURE_SOURCE_SIM_KEYBOARD;
    p->injected_gesture.window_ms = 600U;
    p->injected_gesture.timestamp_ms = 0UL;
    p->param_u32 = 0UL;
    p->param_bool = false;
    p->error_code[0] = '\0';
    p->error_msg[0] = '\0';
}

static bool parse_plain_bench_command(const char *trimmed, JsonlRxParsed *out_p) {
    // Suporta comandos curtos de bancada: START, STOP, PERIOD <ms>, IR ON, IR OFF, DIAG
    if (fw_stricmp(trimmed, "START") == 0 || fw_stricmp(trimmed, "CMD:START") == 0) {
        out_p->kind = RX_MSG_ACQ_START;
        return true;
    }
    if (fw_stricmp(trimmed, "STOP") == 0 || fw_stricmp(trimmed, "CMD:STOP") == 0) {
        out_p->kind = RX_MSG_ACQ_STOP;
        return true;
    }
    if (fw_stricmp(trimmed, "DIAG") == 0 || fw_stricmp(trimmed, "STATUS") == 0) {
        out_p->kind = RX_MSG_DIAG_REQUEST;
        return true;
    }
    if (fw_stricmp(trimmed, "IR ON") == 0) {
        out_p->kind = RX_MSG_ACQ_SET_IR;
        out_p->param_bool = true;
        return true;
    }
    if (fw_stricmp(trimmed, "IR OFF") == 0) {
        out_p->kind = RX_MSG_ACQ_SET_IR;
        out_p->param_bool = false;
        return true;
    }
    if (fw_strncmp(trimmed, "PERIOD ", 7U) == 0 || fw_strncmp(trimmed, "period ", 7U) == 0) {
        const char *num = skip_ws(trimmed + 7);
        uint32_t ms = 0UL;
        // Somente digitos ate o fim da linha ("PERIOD 12abc" e estouro de uint32_t sao rejeitados).
        if (extract_u32_at(num, &ms)) {
            const char *rest = num;
            while (jv_is_digit(*rest)) ++rest;
            if (*rest == '\0') {
                out_p->kind = RX_MSG_ACQ_SET_PERIOD;
                out_p->param_u32 = ms;
                return true;
            }
        }
    }
    return false;
}

bool jsonl_parse_incoming_line(
    JsonlContext *ctx,
    const char *line,
    JsonlRxParsed *out_parsed
) {
    if (!ctx || !out_parsed) return false;
    clear_parsed(out_parsed);

    if (!line) {
        ctx->parse_errors++;
        fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "BAD_FRAME", 23U);
        fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Null line", 63U);
        return false;
    }

    const char *s = skip_ws(line);
    size_t len = fw_strlen(s);
    while (len > 0U && (s[len - 1U] == ' ' || s[len - 1U] == '\t' || s[len - 1U] == '\r' || s[len - 1U] == '\n')) {
        --len;
    }
    if (len == 0U || len >= JSONL_LINE_BUFFER_SIZE) {
        ctx->parse_errors++;
        fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "BAD_FRAME", 23U);
        fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Empty or oversized line", 63U);
        return false;
    }

    char clean[JSONL_LINE_BUFFER_SIZE];
    fw_copy_trunc(clean, sizeof(clean), s, len);

    // 1. Verifica atalhos textuais de bancada caso não inicie com '{'
    if (clean[0] != '{') {
        if (parse_plain_bench_command(clean, out_parsed)) {
            return true;
        }
        ctx->parse_errors++;
        fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "ERR_JSON_PARSE", 23U);
        fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Malformed JSON object", 63U);
        return false;
    }

    if (clean[len - 1U] != '}') {
        ctx->parse_errors++;
        fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "ERR_JSON_PARSE", 23U);
        fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Unterminated JSON object", 63U);
        return false;
    }

    // Sintaxe JSON estrita: virgulas/dois-pontos obrigatorios, numeros e escapes validos,
    // profundidade limitada e nenhum lixo depois do objeto raiz.
    if (!jv_validate_line(clean)) {
        ctx->parse_errors++;
        fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "ERR_JSON_PARSE", 23U);
        fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Malformed JSON syntax", 63U);
        return false;
    }

    uint32_t v = 0UL, seq = 0UL, ts_ms = 0UL;
    char msg_type[32];
    bool data_dup = false;
    const char *data_ptr = obj_find(clean, "data", &data_dup);
    if (!obj_u32(clean, "v", &v) ||
        !obj_u32(clean, "seq", &seq) ||
        !obj_u32(clean, "ts_ms", &ts_ms) ||
        !obj_string(clean, "type", msg_type, sizeof(msg_type)) ||
        !data_ptr || *data_ptr != '{') {
        ctx->parse_errors++;
        fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "BAD_FRAME", 23U);
        fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Missing or invalid envelope fields", 63U);
        return false;
    }

    if (v != JSONL_PROTOCOL_VERSION) {
        ctx->parse_errors++;
        fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "BAD_VERSION", 23U);
        fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Unsupported protocol version", 63U);
        return false;
    }

    record_rx_seq(ctx, seq);
    out_parsed->seq = seq;

    if (fw_strcmp(msg_type, "pet_command") == 0) {
        char cmd_str[32];
        if (!obj_string(data_ptr, "command", cmd_str, sizeof(cmd_str))) {
            ctx->parse_errors++;
            fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "ERR_UNKNOWN_CMD", 23U);
            fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Missing command string", 63U);
            return false;
        }

        // Comandos estendidos de controle de coleta / diagnóstico no firmware
        if (fw_strcmp(cmd_str, "START_COLLECTION") == 0) {
            out_parsed->kind = RX_MSG_ACQ_START;
            uint32_t p_ms = 0UL;
            if (param_find(data_ptr, "period_ms")) {
                if (!param_u32(data_ptr, "period_ms", &p_ms)) {
                    ctx->parse_errors++;
                    fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "EXEC_ERR", 23U);
                    fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Invalid period_ms", 63U);
                    return false;
                }
                if (p_ms > 0UL) out_parsed->param_u32 = p_ms;
            }
            return true;
        }
        if (fw_strcmp(cmd_str, "STOP_COLLECTION") == 0) {
            out_parsed->kind = RX_MSG_ACQ_STOP;
            return true;
        }
        if (fw_strcmp(cmd_str, "SET_PERIOD") == 0) {
            uint32_t p_ms = 0UL;
            if (!param_u32(data_ptr, "period_ms", &p_ms) || p_ms == 0UL) {
                ctx->parse_errors++;
                fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "EXEC_ERR", 23U);
                fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Invalid period_ms", 63U);
                return false;
            }
            out_parsed->kind = RX_MSG_ACQ_SET_PERIOD;
            out_parsed->param_u32 = p_ms;
            return true;
        }
        if (fw_strcmp(cmd_str, "SET_IR") == 0) {
            bool en = true;
            if (!param_bool(data_ptr, "enabled", &en)) {
                ctx->parse_errors++;
                fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "EXEC_ERR", 23U);
                fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Invalid enabled flag", 63U);
                return false;
            }
            out_parsed->kind = RX_MSG_ACQ_SET_IR;
            out_parsed->param_bool = en;
            return true;
        }
        if (fw_strcmp(cmd_str, "DIAG") == 0 || fw_strcmp(cmd_str, "STATUS") == 0) {
            out_parsed->kind = RX_MSG_DIAG_REQUEST;
            return true;
        }

        PetCommandType pcmd = CMD_TICK;
        if (!local_cmd_parse(cmd_str, &pcmd)) {
            ctx->parse_errors++;
            fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "ERR_UNKNOWN_CMD", 23U);
            fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Unknown pet command", 63U);
            return false;
        }
        out_parsed->kind = RX_MSG_PET_COMMAND;
        out_parsed->pet_cmd = pcmd;
        if (pcmd == CMD_SWITCH_MODE) {
            if (!param_find(data_ptr, "mode")) {
                fw_copy_trunc(out_parsed->mode_arg, sizeof(out_parsed->mode_arg), "MOTION_PET", 19U);
            } else if (!param_string(data_ptr, "mode", out_parsed->mode_arg, sizeof(out_parsed->mode_arg))) {
                ctx->parse_errors++;
                fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "EXEC_ERR", 23U);
                fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Invalid mode", 63U);
                return false;
            }
        }
        if (pcmd == CMD_PLAY) {
            char minigame[20] = {};
            if (param_find(data_ptr, "minigame")) {
                char action[24] = {};
                bool ok = param_string(data_ptr, "minigame", minigame, sizeof(minigame)) &&
                    fw_strcmp(minigame, "PET_LAUNCH") == 0 &&
                    param_string(data_ptr, "action", action, sizeof(action));
                if (ok && fw_strcmp(action, "MATCH_RESULT") == 0) {
                    out_parsed->launch.action = LAUNCH_MATCH_RESULT;
                    ok = param_float(data_ptr, "distance_m", &out_parsed->launch.distance_m) &&
                        out_parsed->launch.distance_m >= 0.0f && out_parsed->launch.distance_m <= 100000.0f &&
                        param_u32(data_ptr, "score", &out_parsed->launch.score) &&
                        param_u32(data_ptr, "coins_earned", &out_parsed->launch.coins_earned) &&
                        param_u32(data_ptr, "xp_earned", &out_parsed->launch.xp_earned);
                } else if (ok && fw_strcmp(action, "UNLOCK_UPGRADE") == 0) {
                    out_parsed->launch.action = LAUNCH_UNLOCK_UPGRADE;
                    ok = param_string(data_ptr, "upgrade_id", out_parsed->launch.upgrade_id, sizeof(out_parsed->launch.upgrade_id)) &&
                        param_u32(data_ptr, "cost", &out_parsed->launch.cost);
                } else { ok = false; }
                if (!ok) {
                    ctx->parse_errors++;
                    fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "EXEC_ERR", 23U);
                    fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Invalid Pet Launch payload", 63U);
                    return false;
                }
            }
        }
        return true;
    }

    if (fw_strcmp(msg_type, "lcd_frame") == 0) {
        if (!parse_lcd_lines(data_ptr, &out_parsed->lcd_frame)) {
            ctx->parse_errors++;
            fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "BAD_FRAME", 23U);
            fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Invalid LCD frame", 63U);
            return false;
        }
        out_parsed->kind = RX_MSG_LCD_FRAME;
        return true;
    }

    if (fw_strcmp(msg_type, "gesture_event") == 0) {
        char g_str[24];
        char src_str[24];
        float conf = 0.0f;
        uint32_t win_ms = 600UL;
        GestureType gt = GESTURE_NEUTRAL;
        bool dup = false;
        if (!obj_string(data_ptr, "gesture", g_str, sizeof(g_str)) ||
            !local_gesture_parse(g_str, &gt) ||
            !obj_float(data_ptr, "confidence", &conf) ||
            conf < 0.0f || conf > 1.0f) {
            ctx->parse_errors++;
            fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "EXEC_ERR", 23U);
            fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Invalid gesture_event payload", 63U);
            return false;
        }
        // `source` e `window_ms` sao opcionais, mas se presentes precisam ser validos.
        bool opt_ok = true;
        if (obj_find(data_ptr, "source", &dup)) {
            opt_ok = obj_string(data_ptr, "source", src_str, sizeof(src_str));
        } else if (dup) {
            opt_ok = false;
        } else {
            fw_copy_trunc(src_str, sizeof(src_str), "sim_keyboard", 23U);
        }
        if (opt_ok && (obj_find(data_ptr, "window_ms", &dup) || dup)) {
            opt_ok = obj_u32(data_ptr, "window_ms", &win_ms) && win_ms <= 0xFFFFUL;
        }
        if (!opt_ok) {
            ctx->parse_errors++;
            fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "EXEC_ERR", 23U);
            fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Invalid gesture_event payload", 63U);
            return false;
        }
        out_parsed->kind = RX_MSG_GESTURE_INJECT;
        out_parsed->injected_gesture.gesture = gt;
        out_parsed->injected_gesture.confidence = conf;
        out_parsed->injected_gesture.source = gesture_source_parse(src_str);
        out_parsed->injected_gesture.window_ms = (uint16_t)(win_ms > 0UL ? win_ms : 600UL);
        out_parsed->injected_gesture.timestamp_ms = ts_ms;
        return true;
    }

    ctx->parse_errors++;
    fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "ERR_UNKNOWN_TYPE", 23U);
    fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Unsupported inbound message type", 63U);
    return false;
}

bool jsonl_parse_pet_command(
    JsonlContext *ctx,
    const char *line,
    PetCommandType *out_cmd,
    uint32_t *out_seq
) {
    JsonlRxParsed parsed;
    if (!jsonl_parse_incoming_line(ctx, line, &parsed)) {
        return false;
    }
    if (parsed.kind != RX_MSG_PET_COMMAND) {
        return false;
    }
    if (out_cmd) *out_cmd = parsed.pet_cmd;
    if (out_seq) *out_seq = parsed.seq;
    return true;
}
