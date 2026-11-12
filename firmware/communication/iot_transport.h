#ifndef MOTIONLAB_IOT_TRANSPORT_H
#define MOTIONLAB_IOT_TRANSPORT_H
#include <stddef.h>
#include <stdint.h>
#include "sensors/sensor_types.h"

// ESP32 adapter: initialize before acquisition starts; enqueue never performs I/O.
void iot_transport_start(void);
void iot_transport_acquire(const SensorRawFrame *frame, uint64_t acquisition_ms, bool valid_ir);
void iot_transport_diag(char *output, size_t capacity);
#endif
