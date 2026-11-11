#ifndef MOTIONPET_PET_STATE_H
#define MOTIONPET_PET_STATE_H

#include <stdint.h>
#include <stdbool.h>
#include "gestures/gesture_classifier.h"

#ifdef __cplusplus
extern "C" {
#endif

#define PET_NAME_MAX_LEN   24
#define PET_ACTION_MAX_LEN 24

/**
 * @brief Estágios evolutivos do pet.
 */
typedef enum {
    STAGE_EGG = 0,          ///< Ovo não chocado
    STAGE_CHICK,            ///< Pintinho inicial
    STAGE_CYBER_ROOSTER     ///< Galo cibernético adulto
} PetStage;

/**
 * @brief Humor derivado do estado vital (alinhado 1:1 com terminal/pet/state.py).
 */
typedef enum {
    MOOD_ECSTATIC = 0,
    MOOD_HAPPY,
    MOOD_CONTENT,
    MOOD_HUNGRY,
    MOOD_TIRED,
    MOOD_SAD,
    MOOD_SICK,
    MOOD_SLEEPING
} PetMood;

/**
 * @brief Traço de personalidade emergente conforme histórico de cuidado.
 */
typedef enum {
    PERSONALITY_CURIOUS = 0,
    PERSONALITY_PLAYFUL,
    PERSONALITY_FOODIE,
    PERSONALITY_ZEN
} PetPersonality;

/**
 * @brief Animação visual em execução.
 */
typedef enum {
    ANIM_IDLE = 0,
    ANIM_EATING,
    ANIM_PLAYING,
    ANIM_SLEEPING,
    ANIM_PETTING,
    ANIM_HEALING,
    ANIM_EVOLVING,
    ANIM_SICK
} PetAnimation;

/**
 * @brief Comandos de controle do pet.
 */
typedef enum {
    CMD_FEED = 0,
    CMD_PLAY,
    CMD_REST,
    CMD_HEAL,
    CMD_INTERACT,
    CMD_SAVE,
    CMD_LOAD,
    CMD_RESET,
    CMD_SWITCH_MODE,
    CMD_TICK
} PetCommandType;

/**
 * @brief Contadores de cuidado para derivação da personalidade emergente.
 */
typedef struct {
    uint16_t feed;
    uint16_t play;
    uint16_t rest;
    uint16_t interact;
    uint16_t heal;
} PetCareCounters;

/**
 * @brief Snapshot completo e autoritativo do estado do pet (paridade 1:1 com Python `PetState`).
 */
typedef struct {
    char name[PET_NAME_MAX_LEN];
    float hunger;                   ///< 0.0 = totalmente saciado, 100.0 = faminto crítico
    float happiness;                ///< 0.0 = deprimido, 100.0 = radiante
    float energy;                   ///< 0.0 = exausto, 100.0 = energia máxima
    float health;                   ///< 0.0 = crítico, 100.0 = perfeito estado
    uint32_t xp;                    ///< Pontos de experiência acumulados
    uint16_t level;                 ///< Nível de evolução (1..N)
    PetStage stage;                 ///< Estágio evolutivo
    PetMood mood;                   ///< Estado emocional derivado
    PetPersonality personality;     ///< Personalidade emergente
    PetAnimation animation;         ///< Animação corrente
    uint16_t animation_ttl_ticks;   ///< Ticks restantes da animação temporária
    bool is_sleeping;               ///< Verdadeiro se estiver em repouso
    uint32_t age_ticks;             ///< Contador de ciclos biológicos vividos
    char last_action[PET_ACTION_MAX_LEN]; ///< Última ação registrada (ex: "READY", "FED")
    PetCareCounters care_counters;  ///< Histórico acumulado por tipo de cuidado
    uint32_t coins;
    float best_launch_distance_m;
    uint32_t best_launch_score;
    uint32_t total_launches;
    uint8_t launch_upgrades;       ///< Bits: SLINGSHOT_PRO, AERO_CAPE, SPRING_BOOTS
} PetStateSnapshot;

bool pet_apply_launch_match(PetStateSnapshot *pet, float distance_m, uint32_t score,
                            uint32_t coins, uint32_t xp);
bool pet_unlock_launch_upgrade(PetStateSnapshot *pet, const char *upgrade_id, uint32_t cost);

/**
 * @brief Inicializa o estado padrão do pet (Ovo novo).
 */
void pet_init(PetStateSnapshot *pet, const char *name, PetPersonality personality);

/**
 * @brief Reinicia o pet preservando ou trocando o nome (define `last_action = "RESET"`).
 */
void pet_reset(PetStateSnapshot *pet, const char *name);

/**
 * @brief Executa um ciclo temporal de simulação biológica (fome aumenta, energia decresce).
 */
void pet_tick(PetStateSnapshot *pet);

/**
 * @brief Aplica um comando administrativo ou de cuidado ao pet com tag opcional (ex: `"G:APPROA"`).
 */
bool pet_apply_command_tagged(PetStateSnapshot *pet, PetCommandType cmd, const char *source_tag);

/**
 * @brief Aplica um comando administrativo ou de cuidado ao pet.
 */
bool pet_apply_command(PetStateSnapshot *pet, PetCommandType cmd);

/**
 * @brief Reage a um evento gestual detectado com verificação de confiança mínima.
 */
bool pet_apply_gesture_event(PetStateSnapshot *pet, const GestureEvent *event, float min_confidence);

/**
 * @brief Reage a um tipo de gesto detectado (confiança implícita 1.0).
 */
bool pet_apply_gesture(PetStateSnapshot *pet, GestureType gesture);

/**
 * @brief Atualiza o humor derivado, estágio, personalidade e animação.
 */
void pet_update_derived_mood(PetStateSnapshot *pet);

/**
 * @brief Verifica se os pontos de experiência atingiram o limiar para o próximo estágio.
 */
bool pet_check_evolution(PetStateSnapshot *pet);

// Funções de conversão para strings compatíveis com o protocolo JSON Lines v1
const char* pet_stage_to_string(PetStage stage);
PetStage pet_stage_from_string(const char *str);

const char* pet_mood_to_string(PetMood mood);
PetMood pet_mood_from_string(const char *str);

const char* pet_personality_to_string(PetPersonality personality);
PetPersonality pet_personality_from_string(const char *str);

const char* pet_animation_to_string(PetAnimation anim);
PetAnimation pet_animation_from_string(const char *str);

const char* pet_command_to_string(PetCommandType cmd);
PetCommandType pet_command_from_string(const char *str);

#ifdef __cplusplus
}
#endif

#endif // MOTIONPET_PET_STATE_H
