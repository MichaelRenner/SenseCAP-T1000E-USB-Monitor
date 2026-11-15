### Example: Live Monitoring Dashboard

The screenshot shows a typical live terminal display of the SenseCAP T1000-E USB Monitor, running on Linux and connected to the tracker via `/dev/ttyACM0`.

The dashboard provides a continuously updated overview of the tracker's operating status:

- **Connection:** USB serial port, connection status, raw log filename, number of received messages, and timestamp of the latest message.
- **GNSS:** Current fix status, last successful position (latitude and longitude), number of positioning attempts, successful fixes, failures, and success rate. The example shows a 100% GNSS success rate.
- **LoRaWAN:** Network registration status (`JOINED`), frequency, spreading factor (SF12), bandwidth (125 kHz), transmit power (14 dBm), payload size, frame counter, and FPort.
- **Transmission statistics:** Number of transmissions, completed transmissions, RX1/RX2 timeouts, average transmission interval, accumulated airtime, and spreading factor distribution.
- **Recent events:** Chronological display of GNSS fixes and LoRaWAN transmissions, including timestamps, frequencies, frame counters, and payload sizes.
- **Additional diagnostics:** Previously unrecognized debug messages are collected and counted, helping identify new firmware events and potential issues.

The monitor operates entirely in **read-only mode**, requires no firmware modifications, and can run continuously for long-term diagnostics. All incoming serial messages can be logged for later analysis and offline replay.

**Note:** A completed LoRaWAN transmission does not necessarily mean that a gateway received the packet. RX1/RX2 timeouts are normal when no downlink is scheduled.
