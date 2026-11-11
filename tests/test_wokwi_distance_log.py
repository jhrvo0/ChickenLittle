import json

import pytest

from hardware.wokwi.verify_distances import verify_distances


def frame(distance, valid=True):
    return json.dumps({"type": "sensor_frame", "data": {"distance_cm": distance, "valid_ultrasonic": valid}})


def test_wokwi_log_requires_ordered_valid_distances():
    assert verify_distances(["boot text", frame(24.9), frame(300.1)]) == (24.9, 300.1)
    for lines in ([frame(300), frame(25)], [frame(25), frame(25)], [frame(25, False), frame(300)],
                  [frame(25), frame(300, False)], [frame(True), frame(300)]):
        with pytest.raises(ValueError):
            verify_distances(lines)
