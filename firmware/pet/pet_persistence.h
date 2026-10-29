#ifndef MOTIONPET_PET_PERSISTENCE_H
#define MOTIONPET_PET_PERSISTENCE_H

#include <stdint.h>
#include <stdbool.h>
#include <stddef.h>
#include "pet/pet_state.h"

#ifdef __cplusplus
extern "C" {
#endif

#define PET_NVS_MAGIC          0x4D504554UL  // "MPET"
#define PET_NVS_SCHEMA_VERSION 1U
#define PET_NVS_MIN_AUTO_INTERVAL_MS 30000UL // Limite de gravação automática (30 s) contra desgaste da Flash

typedef enum {
    PET_NVS_OK = 0,
    PET_NVS_ERR_NOT_FOUND,
    PET_NVS_ERR_CORRUPT_CRC,
    PET_NVS_ERR_BAD_VERSION,
    PET_NVS_ERR_THROTTLED,
    PET_NVS_ERR_UNCHANGED,
    PET_NVS_ERR_IO
} PetNvsStatus;

/**
 * @brief Registro binário compacto gravado na partição NVS do ESP32 com verificação CRC32.
 */
typedef struct {
    uint32_t magic;
    uint16_t schema_version;
    uint16_t reserved;
    uint32_t generation;
    PetStateSnapshot snapshot;
    uint32_t crc32;
} PetNvsBlob;

/**
 * @brief Backend abstrato de leitura/escrita de blob (NVS real no ESP32 ou memória em testes de host).
 */
typedef struct {
    bool (*read_blob)(void *out_data, size_t expected_len);
    bool (*write_blob)(const void *data, size_t len);
} PetNvsBackendOps;

typedef struct {
    PetNvsBackendOps backend;
    PetStateSnapshot last_saved_snapshot;
    bool has_saved_baseline;
    uint32_t last_save_ts_ms;
    uint32_t save_generation;
    uint32_t total_writes;
    uint32_t skipped_unchanged;
    uint32_t throttled_writes;
    uint32_t corruption_recoveries;
    uint32_t min_auto_interval_ms;
} PetPersistenceContext;

uint32_t pet_crc32_compute(const uint8_t *data, size_t len);

bool pet_persistence_init(
    PetPersistenceContext *ctx,
    const PetNvsBackendOps *custom_backend,
    uint32_t min_auto_interval_ms
);

PetNvsStatus pet_persistence_save(
    PetPersistenceContext *ctx,
    const PetStateSnapshot *state,
    uint32_t now_ms,
    bool force_manual
);

PetNvsStatus pet_persistence_load(
    PetPersistenceContext *ctx,
    PetStateSnapshot *out_state
);

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_PET_PERSISTENCE_H
