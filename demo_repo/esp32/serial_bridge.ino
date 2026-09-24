#include "serial_bridge.h"
#include <WiFi.h>

#define BUFFER_SIZE 128
#define SENSOR_PIN 34

SerialBridge bridge(115200);

void setup() {
    Serial.begin(115200);
    // Timeout counter to avoid infinite hang if headless
    unsigned long start = millis();
    while (!Serial && millis() - start < 3000) {
        // Wait for serial monitor connection with timeout
    }
    Serial.println("<READY>");
    bridge.begin();
}

int readSensor(int pin) {
    return analogRead(pin);
}

void loop() {
    // Non-blocking telemetry acquisition
    SensorPacket packet;
    packet.sensorId = 1;
    packet.soilMoisture = (float)readSensor(SENSOR_PIN);
    packet.temperature = 24.5;
    packet.humidity = 60.2;
    packet.timestamp = millis();

    bridge.sendTelemetry(packet);

    // Process commands if available
    if (Serial.available() > 0) {
        char buffer[BUFFER_SIZE];
        int len = Serial.readBytesUntil('\n', buffer, BUFFER_SIZE - 1);
        buffer[len] = '\0';
        bridge.processIncomingCommand(buffer);
    }

    delay(10); // Short non-blocking yield
}
