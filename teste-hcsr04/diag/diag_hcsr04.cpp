// Diagnostico do HC-SR04: nao depende de pulseIn e usa o ADC do GPIO34 como voltimetro.
//
// Linha impressa a cada ~600 ms:
//   ADC34 media=NNNN min=NNNN max=NNNN mV | nivel_ocioso=0 | trig=10us | ECHO: ...
//
// "ECHO:" pode ser
//   nenhum pulso em 70 ms            -> o sensor nao respondeu ao TRIG
//   subiu em +NNNus largura=NNNus -> D cm   (medida valida)
//   subiu em +NNNus largura>=NNms   -> sem alvo (HC-SR04 ~38 ms) ou alvo muito longe
//   ja estava em nivel ALTO antes do TRIG -> ECHO preso em HIGH
//
// O mV do ADC so e confiavel entre ~150 e ~2450 mV (ESP32 classico, atenuacao 11 dB).
#include <Arduino.h>

#define TRIG 5
#define ECHO 34

static const uint32_t WINDOW_US = 70000;
static const uint32_t TRIG_WIDTHS[] = {10, 20, 50};

static void adc_stats(uint32_t &mean, uint32_t &mn, uint32_t &mx) {
  analogSetPinAttenuation(ECHO, ADC_11db);
  uint32_t sum = 0;
  mn = 99999;
  mx = 0;
  const int N = 64;
  for (int i = 0; i < N; i++) {
    uint32_t v = analogReadMilliVolts(ECHO);
    sum += v;
    if (v < mn) mn = v;
    if (v > mx) mx = v;
    delayMicroseconds(200);
  }
  mean = sum / N;
  pinMode(ECHO, INPUT);  // volta a funcao digital depois do ADC
}

void setup() {
  Serial.begin(115200);
  pinMode(TRIG, OUTPUT);
  digitalWrite(TRIG, LOW);
  pinMode(ECHO, INPUT);
  delay(1500);
  Serial.println();
  Serial.println("DIAG HC-SR04 v1 | TRIG=GPIO5 ECHO=GPIO34 | janela 70 ms");
}

void loop() {
  static uint32_t cycle = 0;
  uint32_t trig_us = TRIG_WIDTHS[cycle++ % 3];

  uint32_t mean, mn, mx;
  adc_stats(mean, mn, mx);

  digitalWrite(TRIG, LOW);
  delayMicroseconds(5);
  int idle = digitalRead(ECHO);

  digitalWrite(TRIG, HIGH);
  delayMicroseconds(trig_us);
  digitalWrite(TRIG, LOW);
  uint32_t t0 = micros();

  bool rose = false, fell = false;
  uint32_t t_rise = 0, t_fall = 0;
  int last = idle;
  while ((uint32_t)(micros() - t0) < WINDOW_US) {
    int v = digitalRead(ECHO);
    if (v != last) {
      uint32_t t = micros() - t0;
      if (v && !rose) {
        rose = true;
        t_rise = t;
      } else if (!v && rose && !fell) {
        fell = true;
        t_fall = t;
        break;
      }
      last = v;
    }
  }

  Serial.printf("ADC34 media=%4lu min=%4lu max=%4lu mV | nivel_ocioso=%d | trig=%lu us | ECHO: ",
                (unsigned long)mean, (unsigned long)mn, (unsigned long)mx, idle,
                (unsigned long)trig_us);
  if (idle) {
    Serial.println("ja estava em nivel ALTO antes do TRIG");
  } else if (!rose) {
    Serial.println("nenhum pulso em 70 ms");
  } else if (!fell) {
    Serial.printf("subiu em +%lu us largura>=%lu ms (sem alvo / alvo muito longe)\n",
                  (unsigned long)t_rise, (unsigned long)((WINDOW_US - t_rise) / 1000));
  } else {
    uint32_t w = t_fall - t_rise;
    Serial.printf("subiu em +%lu us largura=%lu us -> %.1f cm\n", (unsigned long)t_rise,
                  (unsigned long)w, w * 0.0343f / 2.0f);
  }

  delay(500);
}
