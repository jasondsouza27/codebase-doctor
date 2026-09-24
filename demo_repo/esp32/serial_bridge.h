#ifndef SERIAL_BRIDGE_H
#define SERIAL_BRIDGE_H

#include <Arduino.h>

struct SensorPacket {
    int sensorId;
    float temperature;
    float humidity;
    float soilMoisture;
    unsigned long timestamp;
};

class SerialBridge {
public:
    SerialBridge(long baudRate = 115200);
    bool begin();
    bool sendTelemetry(const SensorPacket& packet);
    bool processIncomingCommand(const char* cmdBuffer);
    void resetWatchdog();

private:
    long _baudRate;
    bool _connected;
};

#endif // SERIAL_BRIDGE_H
