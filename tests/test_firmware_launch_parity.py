"""Compare the real firmware domain and JSON command path with the Python engine."""

import ctypes

from terminal.communication.protocol import CommandType, MessageType, PetCommandPayload, ProtocolCodec
from terminal.pet.engine import PetEngine
from terminal.pet.state import PetState
from tests.test_firmware_cycle3 import fw_lib, _cpp_pet_snapshot_as_payload


def test_launch_result_and_purchase_match_python_engine(fw_lib: ctypes.CDLL) -> None:
    codec = ProtocolCodec()
    fw_lib.fw_jsonl_reset()
    fw_lib.fw_pet_init(b"Launch", 0)
    engine = PetEngine(PetState(name="Launch"))

    def send(payload: dict) -> bool:
        command = PetCommandPayload(CommandType.PLAY, payload)
        return fw_lib.fw_pet_launch_command(codec.encode(MessageType.PET_COMMAND, command.to_dict()).encode())

    for distance, score, coins, xp in [(64.52, 980, 18, 25), (30.25, 400, 5, 12)]:
        assert send({"minigame": "PET_LAUNCH", "action": "MATCH_RESULT", "distance_m": distance,
                     "score": score, "coins_earned": coins, "xp_earned": xp})
        engine.apply_launch_match(distance, score, coins, xp)
        assert _cpp_pet_snapshot_as_payload(fw_lib, codec).to_dict() == engine.state.to_dict()

    assert send({"minigame": "PET_LAUNCH", "action": "UNLOCK_UPGRADE",
                 "upgrade_id": "SLINGSHOT_PRO", "cost": 15})
    assert engine.unlock_launch_upgrade("SLINGSHOT_PRO", 15)[0]
    assert _cpp_pet_snapshot_as_payload(fw_lib, codec).to_dict() == engine.state.to_dict()


def test_loading_v1_clears_prior_baseline_before_auto_migration(fw_lib: ctypes.CDLL) -> None:
    fw_lib.fw_nvs_reset(30_000)
    fw_lib.fw_pet_init(b"Legacy", 0)
    assert fw_lib.fw_nvs_save_current_pet(1_000, True) == 0
    # Loading the old format into an already-used persistence context must still
    # force a rewrite, even when its snapshot matches the existing baseline.
    fw_lib.fw_nvs_make_legacy_save()
    assert fw_lib.fw_nvs_load_into_current_pet() == 0
    assert fw_lib.fw_nvs_save_current_pet(2_000, False) == 0


def test_corrupt_v1_is_not_migrated(fw_lib: ctypes.CDLL) -> None:
    fw_lib.fw_nvs_reset(30_000)
    fw_lib.fw_pet_init(b"Legacy", 0)
    fw_lib.fw_nvs_make_legacy_save()
    fw_lib.fw_nvs_corrupt_byte(20, 0x01)
    assert fw_lib.fw_nvs_load_into_current_pet() == 2  # CRC error
