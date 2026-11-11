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

static const char *skip_ws(const char *p) {
    while (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n') {
        ++p;
    }
    return p;
}

static const char *find_json_key(const char *json, const char *key) {
    size_t klen = fw_strlen(key);
    const char *p = json;
    bool in_str = false;
    while (*p != '\0') {
        if (*p == '\\' && in_str && p[1] != '\0') {
            p += 2;
            continue;
        }
        if (*p == '"') {
            if (!in_str) {
                // Verifica se esta chave coincide com `"key"\s*:`
                if (fw_strncmp(p + 1, key, klen) == 0 && p[1 + klen] == '"') {
                    const char *after = skip_ws(p + 2 + klen);
                    if (*after == ':') {
                        return skip_ws(after + 1);
                    }
                }
                in_str = true;
            } else {
                in_str = false;
            }
        }
        ++p;
    }
    return NULL;
}

static bool extract_json_string(const char *json, const char *key, char *out_buf, size_t cap) {
    const char *val = find_json_key(json, key);
    if (!val || *val != '"' || !out_buf || cap == 0U) return false;
    ++val;
    size_t i = 0U;
    while (*val != '\0' && *val != '"') {
        if (*val == '\\' && val[1] != '\0') {
            ++val;
        }
        if (i + 1U < cap) {
            out_buf[i++] = *val;
        }
        ++val;
    }
    if (*val != '"') return false;
    out_buf[i] = '\0';
    return true;
}

static bool extract_json_u32(const char *json, const char *key, uint32_t *out_val) {
    const char *val = find_json_key(json, key);
    if (!val || !out_val) return false;
    if (*val < '0' || *val > '9') return false;
    uint64_t acc = 0ULL;
    while (*val >= '0' && *val <= '9') {
        acc = acc * 10ULL + (uint64_t)(*val - '0');
        if (acc > 0xFFFFFFFFULL) return false;
        ++val;
    }
    // Rejeita float para campos estritamente inteiros como v, seq, ts_ms
    if (*val == '.') return false;
    *out_val = (uint32_t)acc;
    return true;
}

static bool extract_json_float(const char *json, const char *key, float *out_val) {
    const char *val = find_json_key(json, key);
    if (!val || !out_val) return false;
    double sign = 1.0;
    if (*val == '-') {
        sign = -1.0;
        ++val;
    }
    if (*val < '0' || *val > '9') return false;
    double res = 0.0;
    while (*val >= '0' && *val <= '9') {
        res = res * 10.0 + (double)(*val - '0');
        ++val;
    }
    if (*val == '.') {
        ++val;
        double frac = 0.1;
        while (*val >= '0' && *val <= '9') {
            res += (double)(*val - '0') * frac;
            frac *= 0.1;
            ++val;
        }
    }
    *out_val = (float)(res * sign);
    return true;
}

static bool extract_json_bool(const char *json, const char *key, bool *out_val) {
    const char *val = find_json_key(json, key);
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
    const char *p = find_json_key(data, "lines");
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
        if (*num >= '0' && *num <= '9') {
            uint32_t ms = 0UL;
            while (*num >= '0' && *num <= '9') {
                ms = ms * 10UL + (uint32_t)(*num - '0');
                ++num;
            }
            out_p->kind = RX_MSG_ACQ_SET_PERIOD;
            out_p->param_u32 = ms;
            return true;
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

    // Verifica balanceamento básico de chaves e aspas
    int brace_depth = 0;
    bool in_quotes = false;
    for (size_t i = 0U; i < len; ++i) {
        if (clean[i] == '\\' && in_quotes && (i + 1U < len)) {
            ++i;
            continue;
        }
        if (clean[i] == '"') {
            in_quotes = !in_quotes;
        } else if (!in_quotes) {
            if (clean[i] == '{') brace_depth++;
            else if (clean[i] == '}') brace_depth--;
            if (brace_depth < 0) break;
        }
    }
    if (in_quotes || brace_depth != 0) {
        ctx->parse_errors++;
        fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "ERR_JSON_PARSE", 23U);
        fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Unbalanced JSON syntax", 63U);
        return false;
    }

    uint32_t v = 0UL, seq = 0UL, ts_ms = 0UL;
    char msg_type[32];
    const char *data_ptr = find_json_key(clean, "data");
    if (!extract_json_u32(clean, "v", &v) ||
        !extract_json_u32(clean, "seq", &seq) ||
        !extract_json_u32(clean, "ts_ms", &ts_ms) ||
        !extract_json_string(clean, "type", msg_type, sizeof(msg_type)) ||
        !data_ptr || *data_ptr != '{') {
        ctx->parse_errors++;
        fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "BAD_FRAME", 23U);
        fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Missing envelope fields", 63U);
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
        if (!extract_json_string(data_ptr, "command", cmd_str, sizeof(cmd_str))) {
            ctx->parse_errors++;
            fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "ERR_UNKNOWN_CMD", 23U);
            fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Missing command string", 63U);
            return false;
        }

        // Comandos estendidos de controle de coleta / diagnóstico no firmware
        if (fw_strcmp(cmd_str, "START_COLLECTION") == 0) {
            out_parsed->kind = RX_MSG_ACQ_START;
            uint32_t p_ms = 0UL;
            if (extract_json_u32(data_ptr, "period_ms", &p_ms) && p_ms > 0UL) {
                out_parsed->param_u32 = p_ms;
            }
            return true;
        }
        if (fw_strcmp(cmd_str, "STOP_COLLECTION") == 0) {
            out_parsed->kind = RX_MSG_ACQ_STOP;
            return true;
        }
        if (fw_strcmp(cmd_str, "SET_PERIOD") == 0) {
            uint32_t p_ms = 0UL;
            if (!extract_json_u32(data_ptr, "period_ms", &p_ms) || p_ms == 0UL) {
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
            if (!extract_json_bool(data_ptr, "enabled", &en)) {
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
            if (!extract_json_string(data_ptr, "mode", out_parsed->mode_arg, sizeof(out_parsed->mode_arg))) {
                fw_copy_trunc(out_parsed->mode_arg, sizeof(out_parsed->mode_arg), "MOTION_PET", 19U);
            }
        }
        if (pcmd == CMD_PLAY) {
            char minigame[20] = {};
            if (extract_json_string(data_ptr, "minigame", minigame, sizeof(minigame))) {
                char action[24] = {};
                bool ok = fw_strcmp(minigame, "PET_LAUNCH") == 0 &&
                    extract_json_string(data_ptr, "action", action, sizeof(action));
                if (ok && fw_strcmp(action, "MATCH_RESULT") == 0) {
                    out_parsed->launch.action = LAUNCH_MATCH_RESULT;
                    ok = extract_json_float(data_ptr, "distance_m", &out_parsed->launch.distance_m) &&
                        out_parsed->launch.distance_m >= 0.0f && out_parsed->launch.distance_m <= 100000.0f &&
                        extract_json_u32(data_ptr, "score", &out_parsed->launch.score) &&
                        extract_json_u32(data_ptr, "coins_earned", &out_parsed->launch.coins_earned) &&
                        extract_json_u32(data_ptr, "xp_earned", &out_parsed->launch.xp_earned);
                } else if (ok && fw_strcmp(action, "UNLOCK_UPGRADE") == 0) {
                    out_parsed->launch.action = LAUNCH_UNLOCK_UPGRADE;
                    ok = extract_json_string(data_ptr, "upgrade_id", out_parsed->launch.upgrade_id, sizeof(out_parsed->launch.upgrade_id)) &&
                        extract_json_u32(data_ptr, "cost", &out_parsed->launch.cost);
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
        if (!extract_json_string(data_ptr, "gesture", g_str, sizeof(g_str)) ||
            !local_gesture_parse(g_str, &gt) ||
            !extract_json_float(data_ptr, "confidence", &conf) ||
            conf < 0.0f || conf > 1.0f) {
            ctx->parse_errors++;
            fw_copy_trunc(out_parsed->error_code, sizeof(out_parsed->error_code), "EXEC_ERR", 23U);
            fw_copy_trunc(out_parsed->error_msg, sizeof(out_parsed->error_msg), "Invalid gesture_event payload", 63U);
            return false;
        }
        if (!extract_json_string(data_ptr, "source", src_str, sizeof(src_str))) {
            fw_copy_trunc(src_str, sizeof(src_str), "sim_keyboard", 23U);
        }
        extract_json_u32(data_ptr, "window_ms", &win_ms);
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
