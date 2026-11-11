#include <Arduino.h>

#define TRIG 5
#define ECHO 34

void setup() {
  Serial.begin(115200);
  pinMode(TRIG, OUTPUT);
  pinMode(ECHO, INPUT);
  digitalWrite(TRIG, LOW);
  delay(1000);
  Serial.println("TESTE HC-SR04");
}

void loop() {
  digitalWrite(TRIG, LOW);
  delayMicroseconds(5);
  digitalWrite(TRIG, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG, LOW);

  unsigned long tempo = pulseIn(ECHO, HIGH, 30000UL);

  if (tempo == 0) {
    Serial.println("TIMEOUT");
  } else {
    Serial.printf("DISTANCIA: %.1f cm\n", tempo * 0.0343f / 2.0f);
  }

  delay(300);
}
