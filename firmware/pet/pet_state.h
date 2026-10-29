#ifndef MOTIONPET_PET_STATE_H
#define MOTIONPET_PET_STATE_H

#include <stdint.h>
#include <stdbool.h>
#include "gestures/gesture_classifier.h"

#ifdef __cplusplus
extern "C" {
#endif

#define PET_NAME_MAX_LEN 24

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
 * @brief Snapshot completo e autoritativo do estado do pet.
 */
typedef struct {
    char name[PET_NAME_MAX_LEN];
    uint8_t hunger;         ///< 0 = totalmente saciado, 100 = faminto crítico
    uint8_t happiness;      ///< 0 = deprimido, 100 = radiante
    uint8_t energy;         ///< 0 = exausto, 100 = energia máxima
    uint8_t health;         ///< 0 = morto, 100 = perfeito estado
    uint32_t xp;            ///< Pontos de experiência acumulados
    uint16_t level;         ///< Nível de evolução (1..N)
    PetStage stage;         ///< Estágio evolutivo
    PetMood mood;           ///< Estado emocional derivado
    PetPersonality personality; ///< Personalidade
    PetAnimation animation; ///< Animação corrente
    bool is_sleeping;       ///< Verdadeiro se estiver em repouso
    uint32_t age_ticks;     ///< Contador de ciclos de vida
} PetStateSnapshot;

/**
 * @brief Inicializa o estado padrão do pet (Ovo novo).
 */
void pet_init(PetStateSnapshot *pet, const char *name, PetPersonality personality);

/**
 * @brief Executa um ciclo temporal de simulação biológica (fome aumenta, energia decresce).
 */
void pet_tick(PetStateSnapshot *pet);

/**
 * @brief Aplica um comando administrativo ou de cuidado ao pet.
 */
bool pet_apply_command(PetStateSnapshot *pet, PetCommandType cmd);

/**
 * @brief Reage a um evento gestual detectado.
 */
bool pet_apply_gesture(PetStateSnapshot *pet, GestureType gesture);

/**
 * @brief Atualiza o humor derivado com base nos atributos vitais correntes.
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
