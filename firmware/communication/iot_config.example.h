#ifndef MOTIONLAB_IOT_CONFIG_LOCAL_H
#define MOTIONLAB_IOT_CONFIG_LOCAL_H
// Copy to iot_config.local.h (ignored by Git). Never commit actual credentials.
// A build embeds these values in its binary: keep binaries private as well.
#define MOTIONLAB_WIFI_SSID "YOUR_PRIVATE_WIFI"
#define MOTIONLAB_WIFI_PASSWORD "REPLACE_LOCALLY"
#define MOTIONLAB_MQTT_HOST "motionlab-broker.local"
#define MOTIONLAB_MQTT_PORT 8883
// Blank username uses the stable device_id: esp32_<station MAC, lowercase hex>.
#define MOTIONLAB_MQTT_USERNAME ""
#define MOTIONLAB_MQTT_PASSWORD "REPLACE_LOCALLY"
// Paste the public CA certificate generated for this private broker (not its key).
// MQTT hostname must match its certificate. No insecure TLS bypass is provided.
static const char motionlab_mqtt_ca_pem[] = R"PEM(-----BEGIN CERTIFICATE-----
REPLACE_WITH_YOUR_LOCAL_CA_CERTIFICATE
-----END CERTIFICATE-----
)PEM";
#define MOTIONLAB_MQTT_CA_PEM motionlab_mqtt_ca_pem
// Local NTP server or authorized network time source; no secrets here.
#define MOTIONLAB_SNTP_SERVER "pool.ntp.org"
// Testing only: TCP/1883 requires both empty CA and this explicit opt-in.
#define MOTIONLAB_ALLOW_INSECURE_LAN false
#endif
