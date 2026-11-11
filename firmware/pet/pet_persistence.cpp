#include "pet/pet_persistence.h"
#include "common/fw_utils.h"

#ifdef ARDUINO
#include <Preferences.h>

static bool esp32_nvs_read_blob(void *out_data, size_t expected_len) {
    Preferences prefs;
    if (!prefs.begin("motionpet", true)) {
        return false;
    }
    size_t actual = prefs.getBytesLength("pet_v1");
    if (actual != expected_len) {
        prefs.end();
        return false;
    }
    size_t read_n = prefs.getBytes("pet_v1", out_data, expected_len);
    prefs.end();
    return (read_n == expected_len);
}

static bool esp32_nvs_write_blob(const void *data, size_t len) {
    Preferences prefs;
    if (!prefs.begin("motionpet", false)) {
        return false;
    }
    size_t written = prefs.putBytes("pet_v1", data, len);
    prefs.end();
    return (written == len);
}
#endif // ARDUINO

// The original v1 layout is frozen here; the prefix check prevents a future edit
// to PetStateSnapshot from silently corrupting the migration.
typedef struct {
    char name[PET_NAME_MAX_LEN];
    float hunger, happiness, energy, health;
    uint32_t xp;
    uint16_t level;
    PetStage stage;
    PetMood mood;
    PetPersonality personality;
    PetAnimation animation;
    uint16_t animation_ttl_ticks;
    bool is_sleeping;
    uint32_t age_ticks;
    char last_action[PET_ACTION_MAX_LEN];
    PetCareCounters care_counters;
} PetStateSnapshotV1;
static_assert(sizeof(PetStateSnapshotV1) == offsetof(PetStateSnapshot, coins),
              "Legacy NVS snapshot prefix layout changed");

// Keep the v1 blob layout for non-destructive migration of existing NVS saves.
typedef struct {
    uint32_t magic;
    uint16_t schema_version;
    uint16_t reserved;
    uint32_t generation;
    uint8_t snapshot[offsetof(PetStateSnapshot, coins)];
    uint32_t crc32;
} PetNvsBlobV1;

uint32_t pet_crc32_compute(const uint8_t *data, size_t len) {
    uint32_t crc = 0xFFFFFFFFUL;
    for (size_t i = 0U; i < len; ++i) {
        crc ^= (uint32_t)data[i];
        for (int b = 0; b < 8; ++b) {
            uint32_t mask = (crc & 1UL) ? 0xEDB88320UL : 0UL;
            crc = (crc >> 1U) ^ mask;
        }
    }
    return ~crc;
}

static bool snapshots_equal(const PetStateSnapshot *a, const PetStateSnapshot *b) {
    if (fw_strcmp(a->name, b->name) != 0) return false;
    if (a->hunger != b->hunger) return false;
    if (a->happiness != b->happiness) return false;
    if (a->energy != b->energy) return false;
    if (a->health != b->health) return false;
    if (a->xp != b->xp) return false;
    if (a->level != b->level) return false;
    if (a->stage != b->stage) return false;
    if (a->mood != b->mood) return false;
    if (a->personality != b->personality) return false;
    if (a->is_sleeping != b->is_sleeping) return false;
    if (a->age_ticks != b->age_ticks) return false;
    if (a->care_counters.feed != b->care_counters.feed) return false;
    if (a->care_counters.play != b->care_counters.play) return false;
    if (a->care_counters.rest != b->care_counters.rest) return false;
    if (a->care_counters.interact != b->care_counters.interact) return false;
    if (a->care_counters.heal != b->care_counters.heal) return false;
    if (a->coins != b->coins || a->best_launch_distance_m != b->best_launch_distance_m ||
        a->best_launch_score != b->best_launch_score || a->total_launches != b->total_launches ||
        a->launch_upgrades != b->launch_upgrades) return false;
    return true;
}

static bool sanitize_loaded_snapshot(PetStateSnapshot *s) {
    if ((int)s->stage < (int)STAGE_EGG || (int)s->stage > (int)STAGE_CYBER_ROOSTER) return false;
    if ((int)s->mood < (int)MOOD_ECSTATIC || (int)s->mood > (int)MOOD_SLEEPING) return false;
    if ((int)s->personality < (int)PERSONALITY_CURIOUS || (int)s->personality > (int)PERSONALITY_ZEN) return false;
    if ((int)s->animation < (int)ANIM_IDLE || (int)s->animation > (int)ANIM_SICK) return false;
    if (!(s->best_launch_distance_m >= 0.0f && s->best_launch_distance_m <= 100000.0f) ||
        (s->launch_upgrades & ~7U) != 0U) return false;

    s->name[PET_NAME_MAX_LEN - 1U] = '\0';
    if (s->name[0] == '\0') {
        fw_copy_trunc(s->name, sizeof(s->name), "Pip", 12U);
    }
    s->last_action[PET_ACTION_MAX_LEN - 1U] = '\0';
    if (s->last_action[0] == '\0') {
        fw_copy_trunc(s->last_action, sizeof(s->last_action), "READY", 20U);
    }
    pet_update_derived_mood(s);
    return true;
}

bool pet_persistence_init(
    PetPersistenceContext *ctx,
    const PetNvsBackendOps *custom_backend,
    uint32_t min_auto_interval_ms
) {
    if (!ctx) return false;
    ctx->last_saved_snapshot = PetStateSnapshot{};
    ctx->has_saved_baseline = false;
    ctx->last_save_ts_ms = 0UL;
    ctx->save_generation = 0UL;
    ctx->total_writes = 0UL;
    ctx->skipped_unchanged = 0UL;
    ctx->throttled_writes = 0UL;
    ctx->corruption_recoveries = 0UL;
    ctx->min_auto_interval_ms = min_auto_interval_ms;

    if (custom_backend != NULL) {
        ctx->backend = *custom_backend;
        return (ctx->backend.read_blob != NULL && ctx->backend.write_blob != NULL);
    }

#ifdef ARDUINO
    ctx->backend.read_blob = esp32_nvs_read_blob;
    ctx->backend.write_blob = esp32_nvs_write_blob;
    return true;
#else
    return false;
#endif
}

PetNvsStatus pet_persistence_save(
    PetPersistenceContext *ctx,
    const PetStateSnapshot *state,
    uint32_t now_ms,
    bool force_manual
) {
    if (!ctx || !state || !ctx->backend.write_blob) {
        return PET_NVS_ERR_IO;
    }

    // 1. Proteção de desgaste da Flash: ignora gravação se estado significativo não mudou
    if (ctx->has_saved_baseline && snapshots_equal(&ctx->last_saved_snapshot, state)) {
        ctx->skipped_unchanged++;
        return PET_NVS_ERR_UNCHANGED;
    }

    // 2. Limitação de frequência para saves automáticos periódicos
    if (!force_manual && ctx->has_saved_baseline && ctx->min_auto_interval_ms > 0UL) {
        uint32_t elapsed = (now_ms >= ctx->last_save_ts_ms) ? (now_ms - ctx->last_save_ts_ms) : 0UL;
        if (elapsed < ctx->min_auto_interval_ms) {
            ctx->throttled_writes++;
            return PET_NVS_ERR_THROTTLED;
        }
    }

    PetNvsBlob blob{};
    blob.magic = PET_NVS_MAGIC;
    blob.schema_version = PET_NVS_SCHEMA_VERSION;
    blob.reserved = 0U;
    blob.generation = ctx->save_generation + 1UL;
    blob.snapshot = *state;
    blob.snapshot.name[PET_NAME_MAX_LEN - 1U] = '\0';
    blob.snapshot.last_action[PET_ACTION_MAX_LEN - 1U] = '\0';

    size_t payload_bytes = offsetof(PetNvsBlob, crc32);
    blob.crc32 = pet_crc32_compute((const uint8_t *)&blob, payload_bytes);

    if (!ctx->backend.write_blob(&blob, sizeof(PetNvsBlob))) {
        return PET_NVS_ERR_IO;
    }

    ctx->save_generation = blob.generation;
    ctx->last_saved_snapshot = *state;
    ctx->has_saved_baseline = true;
    ctx->last_save_ts_ms = now_ms;
    ctx->total_writes++;
    return PET_NVS_OK;
}

PetNvsStatus pet_persistence_load(
    PetPersistenceContext *ctx,
    PetStateSnapshot *out_state
) {
    if (!ctx || !out_state || !ctx->backend.read_blob) {
        return PET_NVS_ERR_IO;
    }

    PetNvsBlob blob{};
    if (!ctx->backend.read_blob(&blob, sizeof(PetNvsBlob))) {
        PetNvsBlobV1 old{};
        if (!ctx->backend.read_blob(&old, sizeof(old))) return PET_NVS_ERR_NOT_FOUND;
        if (old.magic != PET_NVS_MAGIC || old.schema_version != 1U ||
            pet_crc32_compute((const uint8_t *)&old, offsetof(PetNvsBlobV1, crc32)) != old.crc32) {
            ctx->corruption_recoveries++;
            pet_init(out_state, "Pip", PERSONALITY_CURIOUS);
            return PET_NVS_ERR_CORRUPT_CRC;
        }
        PetStateSnapshot candidate{};
        uint8_t *bytes = (uint8_t *)&candidate;
        for (size_t i = 0; i < sizeof(old.snapshot); ++i) bytes[i] = old.snapshot[i];
        if (!sanitize_loaded_snapshot(&candidate)) {
            ctx->corruption_recoveries++;
            pet_init(out_state, "Pip", PERSONALITY_CURIOUS);
            return PET_NVS_ERR_CORRUPT_CRC;
        }
        *out_state = candidate;
        // Do not establish a saved baseline: the next auto-save upgrades the record to v2.
        ctx->has_saved_baseline = false;
        ctx->save_generation = old.generation;
        return PET_NVS_OK;
    }

    if (blob.magic != PET_NVS_MAGIC) {
        ctx->corruption_recoveries++;
        pet_init(out_state, "Pip", PERSONALITY_CURIOUS);
        return PET_NVS_ERR_CORRUPT_CRC;
    }

    if (blob.schema_version != PET_NVS_SCHEMA_VERSION) {
        ctx->corruption_recoveries++;
        pet_init(out_state, "Pip", PERSONALITY_CURIOUS);
        return PET_NVS_ERR_BAD_VERSION;
    }

    size_t payload_bytes = offsetof(PetNvsBlob, crc32);
    uint32_t expected_crc = pet_crc32_compute((const uint8_t *)&blob, payload_bytes);
    if (expected_crc != blob.crc32) {
        ctx->corruption_recoveries++;
        pet_init(out_state, "Pip", PERSONALITY_CURIOUS);
        return PET_NVS_ERR_CORRUPT_CRC;
    }

    PetStateSnapshot candidate = blob.snapshot;
    if (!sanitize_loaded_snapshot(&candidate)) {
        ctx->corruption_recoveries++;
        pet_init(out_state, "Pip", PERSONALITY_CURIOUS);
        return PET_NVS_ERR_CORRUPT_CRC;
    }

    *out_state = candidate;
    ctx->last_saved_snapshot = candidate;
    ctx->has_saved_baseline = true;
    ctx->save_generation = blob.generation;
    return PET_NVS_OK;
}
