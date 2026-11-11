#include "pet/pet_state.h"
#include "common/fw_utils.h"

// Constantes idênticas a `PetConfig` em `terminal/pet/config.py`
#define CFG_HUNGER_PER_TICK            0.80
#define CFG_SLEEP_HUNGER_FACTOR        0.40
#define CFG_HAPPINESS_DECAY_PER_TICK   0.50
#define CFG_ENERGY_DECAY_PER_TICK      0.60
#define CFG_SLEEP_ENERGY_RECOVERY      3.50

#define CFG_CRITICAL_HUNGER            80.0
#define CFG_CRITICAL_ENERGY            15.0
#define CFG_CRITICAL_HAPPINESS         20.0
#define CFG_HEALTH_PENALTY_PER_TICK    1.20
#define CFG_HEALTH_REGEN_PER_TICK      0.40
#define CFG_SICK_HEALTH_THRESHOLD      35.0f

#define CFG_FEED_HUNGER_DELTA         -28.0f
#define CFG_FEED_HEALTH_BONUS           2.0f
#define CFG_FEED_XP                    12UL

#define CFG_PLAY_HAPPINESS_DELTA       22.0f
#define CFG_PLAY_ENERGY_DELTA         -14.0f
#define CFG_PLAY_HUNGER_DELTA           8.0f
#define CFG_PLAY_MIN_ENERGY            12.0f
#define CFG_PLAY_XP                    18UL

#define CFG_INTERACT_HAPPINESS_DELTA   12.0f
#define CFG_INTERACT_ENERGY_DELTA      -2.0f
#define CFG_INTERACT_XP                10UL

#define CFG_HEAL_HEALTH_DELTA          30.0f
#define CFG_HEAL_HAPPINESS_DELTA        4.0f
#define CFG_HEAL_XP                    15UL

#define CFG_REST_XP                     5UL

#define CFG_XP_PER_LEVEL               50UL
#define CFG_CHICK_MIN_LEVEL             2U
#define CFG_CYBER_ROOSTER_MIN_LEVEL     5U
#define CFG_ANIM_DEFAULT_TTL            4U

const char* pet_stage_to_string(PetStage stage) {
    switch (stage) {
        case STAGE_CHICK:         return "CHICK";
        case STAGE_CYBER_ROOSTER: return "CYBER_ROOSTER";
        case STAGE_EGG:
        default:                  return "EGG";
    }
}

PetStage pet_stage_from_string(const char *str) {
    if (!str) return STAGE_EGG;
    if (fw_strcmp(str, "CHICK") == 0)         return STAGE_CHICK;
    if (fw_strcmp(str, "CYBER_ROOSTER") == 0) return STAGE_CYBER_ROOSTER;
    return STAGE_EGG;
}

const char* pet_mood_to_string(PetMood mood) {
    switch (mood) {
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

PetMood pet_mood_from_string(const char *str) {
    if (!str) return MOOD_HAPPY;
    if (fw_strcmp(str, "ECSTATIC") == 0) return MOOD_ECSTATIC;
    if (fw_strcmp(str, "HAPPY") == 0)    return MOOD_HAPPY;
    if (fw_strcmp(str, "CONTENT") == 0)  return MOOD_CONTENT;
    if (fw_strcmp(str, "HUNGRY") == 0)   return MOOD_HUNGRY;
    if (fw_strcmp(str, "TIRED") == 0)    return MOOD_TIRED;
    if (fw_strcmp(str, "SAD") == 0)      return MOOD_SAD;
    if (fw_strcmp(str, "SICK") == 0)     return MOOD_SICK;
    if (fw_strcmp(str, "SLEEPING") == 0) return MOOD_SLEEPING;
    return MOOD_CONTENT;
}

const char* pet_personality_to_string(PetPersonality personality) {
    switch (personality) {
        case PERSONALITY_PLAYFUL: return "PLAYFUL";
        case PERSONALITY_FOODIE:  return "FOODIE";
        case PERSONALITY_ZEN:     return "ZEN";
        case PERSONALITY_CURIOUS:
        default:                  return "CURIOUS";
    }
}

PetPersonality pet_personality_from_string(const char *str) {
    if (!str) return PERSONALITY_CURIOUS;
    if (fw_strcmp(str, "PLAYFUL") == 0) return PERSONALITY_PLAYFUL;
    if (fw_strcmp(str, "FOODIE") == 0)  return PERSONALITY_FOODIE;
    if (fw_strcmp(str, "ZEN") == 0)     return PERSONALITY_ZEN;
    return PERSONALITY_CURIOUS;
}

const char* pet_animation_to_string(PetAnimation anim) {
    switch (anim) {
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

PetAnimation pet_animation_from_string(const char *str) {
    if (!str) return ANIM_IDLE;
    if (fw_strcmp(str, "EATING") == 0)   return ANIM_EATING;
    if (fw_strcmp(str, "PLAYING") == 0)  return ANIM_PLAYING;
    if (fw_strcmp(str, "SLEEPING") == 0) return ANIM_SLEEPING;
    if (fw_strcmp(str, "PETTING") == 0)  return ANIM_PETTING;
    if (fw_strcmp(str, "HEALING") == 0)  return ANIM_HEALING;
    if (fw_strcmp(str, "EVOLVING") == 0) return ANIM_EVOLVING;
    if (fw_strcmp(str, "SICK") == 0)     return ANIM_SICK;
    return ANIM_IDLE;
}

const char* pet_command_to_string(PetCommandType cmd) {
    switch (cmd) {
        case CMD_FEED:        return "FEED";
        case CMD_PLAY:        return "PLAY";
        case CMD_REST:        return "REST";
        case CMD_HEAL:        return "HEAL";
        case CMD_INTERACT:    return "INTERACT";
        case CMD_SAVE:        return "SAVE";
        case CMD_LOAD:        return "LOAD";
        case CMD_RESET:       return "RESET";
        case CMD_SWITCH_MODE: return "SWITCH_MODE";
        case CMD_TICK:
        default:              return "TICK";
    }
}

PetCommandType pet_command_from_string(const char *str) {
    if (!str) return CMD_TICK;
    if (fw_strcmp(str, "FEED") == 0)        return CMD_FEED;
    if (fw_strcmp(str, "PLAY") == 0)        return CMD_PLAY;
    if (fw_strcmp(str, "REST") == 0)        return CMD_REST;
    if (fw_strcmp(str, "HEAL") == 0)        return CMD_HEAL;
    if (fw_strcmp(str, "INTERACT") == 0)    return CMD_INTERACT;
    if (fw_strcmp(str, "SAVE") == 0)        return CMD_SAVE;
    if (fw_strcmp(str, "LOAD") == 0)        return CMD_LOAD;
    if (fw_strcmp(str, "RESET") == 0)       return CMD_RESET;
    if (fw_strcmp(str, "SWITCH_MODE") == 0) return CMD_SWITCH_MODE;
    return CMD_TICK;
}

static void clamp_all_stats(PetStateSnapshot *pet) {
    pet->hunger = fw_clamp_2dp(pet->hunger, 0.0f, 100.0f);
    pet->happiness = fw_clamp_2dp(pet->happiness, 0.0f, 100.0f);
    pet->energy = fw_clamp_2dp(pet->energy, 0.0f, 100.0f);
    pet->health = fw_clamp_2dp(pet->health, 0.0f, 100.0f);
    if (pet->level < 1U) {
        pet->level = 1U;
    }
}

static void set_prefixed_action(PetStateSnapshot *pet, const char *source_tag, const char *action) {
    char combined[48];
    size_t pos = 0U;
    if (source_tag && source_tag[0] != '\0') {
        size_t tlen = fw_strlen(source_tag);
        for (size_t i = 0U; i < tlen && pos + 2U < sizeof(combined); ++i) {
            combined[pos++] = source_tag[i];
        }
        combined[pos++] = ' ';
    }
    if (action) {
        size_t alen = fw_strlen(action);
        for (size_t i = 0U; i < alen && pos + 1U < sizeof(combined); ++i) {
            combined[pos++] = action[i];
        }
    }
    combined[pos] = '\0';
    // Trunca em 20 caracteres como `[:20]` no Python PetEngine
    fw_copy_trunc(pet->last_action, sizeof(pet->last_action), combined, 20U);
}

static void refresh_derived_fields(PetStateSnapshot *pet, bool evolved) {
    if (!pet) return;

    // 1. Estágio evolutivo coerente com o nível
    if (pet->level >= CFG_CYBER_ROOSTER_MIN_LEVEL) {
        pet->stage = STAGE_CYBER_ROOSTER;
    } else if (pet->level >= CFG_CHICK_MIN_LEVEL) {
        pet->stage = STAGE_CHICK;
    } else {
        pet->stage = STAGE_EGG;
    }

    // 2. Personalidade emergente (mesma ordem de desempate do dict Python: feed, play, rest, interact, heal)
    uint32_t total_actions = (uint32_t)pet->care_counters.feed
                           + (uint32_t)pet->care_counters.play
                           + (uint32_t)pet->care_counters.rest
                           + (uint32_t)pet->care_counters.interact
                           + (uint32_t)pet->care_counters.heal;
    if (total_actions >= 3UL) {
        uint16_t max_val = pet->care_counters.feed;
        int dom_idx = 0; // 0=feed, 1=play, 2=rest, 3=interact, 4=heal
        if (pet->care_counters.play > max_val)     { max_val = pet->care_counters.play;     dom_idx = 1; }
        if (pet->care_counters.rest > max_val)     { max_val = pet->care_counters.rest;     dom_idx = 2; }
        if (pet->care_counters.interact > max_val) { max_val = pet->care_counters.interact; dom_idx = 3; }
        if (pet->care_counters.heal > max_val)     { max_val = pet->care_counters.heal;     dom_idx = 4; }

        if (dom_idx == 1)      pet->personality = PERSONALITY_PLAYFUL;
        else if (dom_idx == 0) pet->personality = PERSONALITY_FOODIE;
        else if (dom_idx == 2) pet->personality = PERSONALITY_ZEN;
        else                   pet->personality = PERSONALITY_CURIOUS;
    }

    // 3. Humor prioritário
    if (pet->is_sleeping) {
        pet->mood = MOOD_SLEEPING;
    } else if (pet->health <= CFG_SICK_HEALTH_THRESHOLD) {
        pet->mood = MOOD_SICK;
    } else if (pet->hunger >= (float)CFG_CRITICAL_HUNGER) {
        pet->mood = MOOD_HUNGRY;
    } else if (pet->energy <= (float)CFG_CRITICAL_ENERGY) {
        pet->mood = MOOD_TIRED;
    } else if (pet->happiness <= (float)CFG_CRITICAL_HAPPINESS) {
        pet->mood = MOOD_SAD;
    } else if (pet->happiness >= 85.0f && pet->hunger <= 30.0f && pet->energy >= 60.0f && pet->health >= 80.0f) {
        pet->mood = MOOD_ECSTATIC;
    } else if (pet->happiness >= 60.0f && pet->hunger <= 55.0f) {
        pet->mood = MOOD_HAPPY;
    } else {
        pet->mood = MOOD_CONTENT;
    }

    // 4. Animação ativa
    if (evolved) {
        pet->animation = ANIM_EVOLVING;
        pet->animation_ttl_ticks = (uint16_t)(CFG_ANIM_DEFAULT_TTL + 2U);
        const char *st_str = pet_stage_to_string(pet->stage);
        char ev_buf[24];
        fw_copy_trunc(ev_buf, sizeof(ev_buf), "EVOLVED->", 9U);
        size_t base = fw_strlen(ev_buf);
        size_t i = 0U;
        while (i < 9U && st_str[i] != '\0' && (base + i + 1U) < sizeof(ev_buf)) {
            ev_buf[base + i] = st_str[i];
            ++i;
        }
        ev_buf[base + i] = '\0';
        fw_copy_trunc(pet->last_action, sizeof(pet->last_action), ev_buf, 20U);
    } else if (pet->is_sleeping) {
        pet->animation = ANIM_SLEEPING;
        pet->animation_ttl_ticks = 0U;
    } else if (pet->animation_ttl_ticks == 0U) {
        pet->animation = (pet->mood == MOOD_SICK) ? ANIM_SICK : ANIM_IDLE;
    }
}

void pet_init(PetStateSnapshot *pet, const char *name, PetPersonality personality) {
    if (!pet) return;
    const char *src_name = (name && name[0] != '\0') ? name : "Pip";
    fw_copy_trunc(pet->name, sizeof(pet->name), src_name, 12U);

    pet->hunger = 25.0f;
    pet->happiness = 80.0f;
    pet->energy = 85.0f;
    pet->health = 95.0f;
    pet->xp = 0UL;
    pet->level = 1U;
    pet->stage = STAGE_EGG;
    pet->mood = MOOD_HAPPY;
    pet->personality = personality;
    pet->animation = ANIM_IDLE;
    pet->animation_ttl_ticks = 0U;
    pet->is_sleeping = false;
    pet->age_ticks = 0UL;
    fw_copy_trunc(pet->last_action, sizeof(pet->last_action), "READY", 20U);
    pet->care_counters = PetCareCounters{0U, 0U, 0U, 0U, 0U};
    pet->coins = 0U;
    pet->best_launch_distance_m = 0.0f;
    pet->best_launch_score = 0U;
    pet->total_launches = 0U;
    pet->launch_upgrades = 0U;

    clamp_all_stats(pet);
    refresh_derived_fields(pet, false);
}

void pet_reset(PetStateSnapshot *pet, const char *name) {
    if (!pet) return;
    char keep_name[PET_NAME_MAX_LEN];
    const char *chosen = (name && name[0] != '\0') ? name : (pet->name[0] != '\0' ? pet->name : "Pip");
    fw_copy_trunc(keep_name, sizeof(keep_name), chosen, 12U);
    pet_init(pet, keep_name, PERSONALITY_CURIOUS);
    fw_copy_trunc(pet->last_action, sizeof(pet->last_action), "RESET", 20U);
    refresh_derived_fields(pet, false);
}

void pet_tick(PetStateSnapshot *pet) {
    if (!pet) return;
    pet->age_ticks += 1UL;

    double hunger = (double)pet->hunger;
    double happiness = (double)pet->happiness;
    double energy = (double)pet->energy;
    double health = (double)pet->health;

    if (pet->is_sleeping) {
        hunger += CFG_HUNGER_PER_TICK * CFG_SLEEP_HUNGER_FACTOR;
        energy += CFG_SLEEP_ENERGY_RECOVERY;
        if (energy >= 100.0) {
            energy = 100.0;
            pet->is_sleeping = false;
            fw_copy_trunc(pet->last_action, sizeof(pet->last_action), "WOKE UP", 20U);
        }
    } else {
        hunger += CFG_HUNGER_PER_TICK;
        happiness -= CFG_HAPPINESS_DECAY_PER_TICK;
        energy -= CFG_ENERGY_DECAY_PER_TICK;
    }

    bool in_distress = (hunger >= CFG_CRITICAL_HUNGER)
                    || (energy <= CFG_CRITICAL_ENERGY)
                    || (happiness <= CFG_CRITICAL_HAPPINESS);
    if (in_distress) {
        health -= CFG_HEALTH_PENALTY_PER_TICK;
    } else if (hunger < 40.0 && energy > 50.0 && happiness > 60.0) {
        health += CFG_HEALTH_REGEN_PER_TICK;
    }

    if (pet->animation_ttl_ticks > 0U) {
        pet->animation_ttl_ticks--;
    }

    pet->hunger = (float)hunger;
    pet->happiness = (float)happiness;
    pet->energy = (float)energy;
    pet->health = (float)health;

    clamp_all_stats(pet);
    refresh_derived_fields(pet, false);
}

bool pet_check_evolution(PetStateSnapshot *pet) {
    if (!pet) return false;
    PetStage prev = pet->stage;
    uint32_t calc_lvl = 1UL + (pet->xp / CFG_XP_PER_LEVEL);
    if (calc_lvl > 65535UL) calc_lvl = 65535UL;
    if ((uint16_t)calc_lvl > pet->level) {
        pet->level = (uint16_t)calc_lvl;
    }
    if (pet->level >= CFG_CYBER_ROOSTER_MIN_LEVEL) {
        pet->stage = STAGE_CYBER_ROOSTER;
    } else if (pet->level >= CFG_CHICK_MIN_LEVEL) {
        pet->stage = STAGE_CHICK;
    } else {
        pet->stage = STAGE_EGG;
    }
    return pet->stage != prev;
}

static bool grant_xp(PetStateSnapshot *pet, uint32_t amount) {
    if (amount == 0UL) return false;
    pet->xp += amount;
    return pet_check_evolution(pet);
}

static void trigger_animation(PetStateSnapshot *pet, PetAnimation anim) {
    pet->animation = anim;
    pet->animation_ttl_ticks = CFG_ANIM_DEFAULT_TTL;
}

bool pet_apply_command_tagged(PetStateSnapshot *pet, PetCommandType cmd, const char *source_tag) {
    if (!pet) return false;

    if (cmd == CMD_TICK) {
        pet_tick(pet);
        return true;
    }
    if (cmd == CMD_RESET) {
        pet_reset(pet, NULL);
        return true;
    }

    bool evolved = false;

    switch (cmd) {
        case CMD_FEED:
            if (pet->is_sleeping) pet->is_sleeping = false;
            pet->hunger += CFG_FEED_HUNGER_DELTA;
            pet->health += CFG_FEED_HEALTH_BONUS;
            pet->care_counters.feed++;
            evolved = grant_xp(pet, CFG_FEED_XP);
            trigger_animation(pet, ANIM_EATING);
            set_prefixed_action(pet, source_tag, "FED");
            break;

        case CMD_PLAY:
            if (pet->is_sleeping) pet->is_sleeping = false;
            if (pet->energy < CFG_PLAY_MIN_ENERGY) {
                set_prefixed_action(pet, source_tag, "TOO TIRED");
            } else {
                pet->happiness += CFG_PLAY_HAPPINESS_DELTA;
                pet->energy += CFG_PLAY_ENERGY_DELTA;
                pet->hunger += CFG_PLAY_HUNGER_DELTA;
                pet->care_counters.play++;
                evolved = grant_xp(pet, CFG_PLAY_XP);
                trigger_animation(pet, ANIM_PLAYING);
                set_prefixed_action(pet, source_tag, "PLAYED");
            }
            break;

        case CMD_REST:
            pet->is_sleeping = !pet->is_sleeping;
            if (pet->is_sleeping) {
                pet->care_counters.rest++;
                evolved = grant_xp(pet, CFG_REST_XP);
                pet->animation = ANIM_SLEEPING;
                pet->animation_ttl_ticks = 0U;
                set_prefixed_action(pet, source_tag, "SLEEPING");
            } else {
                pet->animation = ANIM_IDLE;
                pet->animation_ttl_ticks = 0U;
                set_prefixed_action(pet, source_tag, "AWAKE");
            }
            break;

        case CMD_INTERACT:
            if (pet->is_sleeping) {
                pet->happiness += CFG_INTERACT_HAPPINESS_DELTA * 0.5f;
                set_prefixed_action(pet, source_tag, "GENTLE PET");
            } else {
                pet->happiness += CFG_INTERACT_HAPPINESS_DELTA;
                pet->energy += CFG_INTERACT_ENERGY_DELTA;
                trigger_animation(pet, ANIM_PETTING);
                set_prefixed_action(pet, source_tag, "PETTED");
            }
            pet->care_counters.interact++;
            evolved = grant_xp(pet, CFG_INTERACT_XP);
            break;

        case CMD_HEAL:
            pet->health += CFG_HEAL_HEALTH_DELTA;
            pet->happiness += CFG_HEAL_HAPPINESS_DELTA;
            pet->care_counters.heal++;
            evolved = grant_xp(pet, CFG_HEAL_XP);
            trigger_animation(pet, ANIM_HEALING);
            set_prefixed_action(pet, source_tag, "HEALED");
            break;

        case CMD_SAVE:
        case CMD_LOAD:
        case CMD_SWITCH_MODE:
            return true;

        default:
            return false;
    }

    clamp_all_stats(pet);
    refresh_derived_fields(pet, evolved);
    return true;
}

bool pet_apply_command(PetStateSnapshot *pet, PetCommandType cmd) {
    return pet_apply_command_tagged(pet, cmd, NULL);
}

bool pet_apply_launch_match(PetStateSnapshot *pet, float distance_m, uint32_t score,
                            uint32_t coins, uint32_t xp) {
    if (!pet || pet->is_sleeping || pet->mood == MOOD_SICK || pet->energy < 10.0f ||
        !(distance_m >= 0.0f && distance_m <= 100000.0f) ||
        coins > UINT32_MAX - pet->coins || xp > UINT32_MAX - pet->xp ||
        pet->total_launches == UINT32_MAX) return false;
    // Python stores and compares records at centi-meter precision.
    distance_m = fw_clamp_2dp(distance_m, 0.0f, 100000.0f);
    bool record = distance_m > pet->best_launch_distance_m || score > pet->best_launch_score;
    if (distance_m > pet->best_launch_distance_m) pet->best_launch_distance_m = distance_m;
    if (score > pet->best_launch_score) pet->best_launch_score = score;
    pet->total_launches++;
    pet->coins += coins;
    pet->energy -= 8.0f;
    pet->hunger += 4.0f;
    pet->happiness += record ? 22.0f : 14.0f;
    pet->care_counters.play++;
    bool evolved = grant_xp(pet, xp);
    trigger_animation(pet, ANIM_PLAYING);
    FwJsonWriter action;
    jw_init(&action, pet->last_action, 21U);
    jw_puts(&action, record ? "REC! " : "LAUNCH ");
    uint32_t tenths = (uint32_t)fw_round_nonneg(distance_m * 10.0f);
    jw_put_u32(&action, tenths / 10U);
    jw_putc(&action, '.');
    jw_putc(&action, (char)('0' + tenths % 10U));
    jw_putc(&action, 'm');
    clamp_all_stats(pet);
    refresh_derived_fields(pet, evolved);
    return true;
}

bool pet_unlock_launch_upgrade(PetStateSnapshot *pet, const char *upgrade_id, uint32_t cost) {
    if (!pet || !upgrade_id) return false;
    uint8_t bit = 0U;
    uint32_t expected_cost = 0U;
    if (fw_strcmp(upgrade_id, "SLINGSHOT_PRO") == 0) { bit = 1U; expected_cost = 15U; }
    else if (fw_strcmp(upgrade_id, "AERO_CAPE") == 0) { bit = 2U; expected_cost = 25U; }
    else if (fw_strcmp(upgrade_id, "SPRING_BOOTS") == 0) { bit = 4U; expected_cost = 35U; }
    if (!bit || cost != expected_cost || (pet->launch_upgrades & bit) || pet->coins < cost) return false;
    pet->coins -= cost;
    pet->launch_upgrades |= bit;
    pet->happiness += 6.0f;
    trigger_animation(pet, ANIM_PLAYING);
    FwJsonWriter action;
    jw_init(&action, pet->last_action, 21U);
    jw_puts(&action, "UPG:");
    jw_puts(&action, upgrade_id);
    clamp_all_stats(pet);
    refresh_derived_fields(pet, false);
    return true;
}

bool pet_apply_gesture_event(PetStateSnapshot *pet, const GestureEvent *event, float min_confidence) {
    if (!pet || !event) return false;
    if (event->confidence < min_confidence) {
        return false;
    }

    PetCommandType cmd;
    const char *tag = NULL;
    switch (event->gesture) {
        case GESTURE_APPROACH: cmd = CMD_INTERACT; tag = "G:APPROA"; break;
        case GESTURE_HOLD:     cmd = CMD_FEED;     tag = "G:HOLD";   break;
        case GESTURE_RETREAT:  cmd = CMD_REST;     tag = "G:RETREA"; break;
        case GESTURE_IMPULSE:  cmd = CMD_PLAY;     tag = "G:IMPULS"; break;
        case GESTURE_DOUBLE:   cmd = CMD_HEAL;     tag = "G:DOUBLE"; break;
        case GESTURE_NEUTRAL:
        default:
            return false;
    }
    return pet_apply_command_tagged(pet, cmd, tag);
}

bool pet_apply_gesture(PetStateSnapshot *pet, GestureType gesture) {
    GestureEvent ev{};
    ev.gesture = gesture;
    ev.confidence = 1.0f;
    ev.source = GESTURE_SOURCE_TINYML;
    ev.window_ms = 600U;
    ev.timestamp_ms = 0UL;
    return pet_apply_gesture_event(pet, &ev, 0.55f);
}

void pet_update_derived_mood(PetStateSnapshot *pet) {
    if (!pet) return;
    clamp_all_stats(pet);
    refresh_derived_fields(pet, false);
}
