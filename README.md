# SenseCAP T1000-E USB Diagnostic Monitor

A small, **read-only Python terminal dashboard** for the **Seeed Studio SenseCAP T1000-E LoRaWAN tracker** on Linux.

It listens to the tracker's USB CDC/ACM serial debug output, displays GNSS and LoRaWAN statistics, saves timestamped raw logs, and can analyze saved logs offline. GNSS coordinates can also be exported to CSV.

**No flashing, no firmware changes, no commands sent to the device.**

> **Compatibility:** Developed and tested against debug messages captured from a T1000-E running LoRaWAN firmware. It is **not** a Meshtastic CLI, and other firmware versions may emit different message formats. Tested using a real 7,576-line overnight recording; USB device details and examples below are from that test setup, not guaranteed identifiers for every tracker.

## Features

- Live terminal dashboard refreshed at a configurable interval
- LoRaWAN join state, FPort, last transmit time, frequency, SF, bandwidth, TX power, payload length, FCntUp
- TX count, TX-done events, RX1/RX2 timeouts, mean TX interval, total airtime and SF distribution
- GNSS search starts/ends, fixes, failures, last coordinates, and observed fix success rate
- Latest firmware-reported GPS / Wi-Fi / BLE scan lengths
- Recent events and counts of otherwise unrecognized debug message types
- Timestamped raw logging in live mode
- Offline replay of previously recorded monitor logs
- CSV export of GNSS positions with timestamps **in replay mode**
- Automatic retry every two seconds if the serial port cannot be opened or disconnects
- Uses only the Python standard library for replay; live mode additionally needs `pyserial`

The counters describe **messages seen by this monitor**. They do not represent the device's lifetime statistics. A `TX DONE` event means the radio finished transmitting; it is **not** proof that a gateway or The Things Network received the uplink. RX1/RX2 timeouts are expected when no downlink is scheduled.

## Requirements

- Linux computer (for example, Ubuntu, KDE neon, or Debian)
- Python 3
- SenseCAP T1000-E LoRaWAN device connected over a data-capable USB cable
- `python3-serial` (or the equivalent `pyserial` package) for live mode
- A terminal capable of displaying UTF-8 and ANSI cursor/clear-screen codes

No additional packages are needed for **offline replay**.

## Installation

Download or clone this repository, then enter its directory:

```bash
git clone https://github.com/YOUR-USERNAME/YOUR-REPOSITORY.git
cd YOUR-REPOSITORY
```

Replace the placeholder URL and directory with your actual repository name after publishing.

For Debian, Ubuntu or KDE neon:

```bash
sudo apt update
sudo apt install python3 python3-serial
```

Alternatively, in a Python virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install pyserial
```

The script has no non-standard dependencies in replay mode. There is no need to use `sudo` just to run Python, provided your user has access to the serial device.

## Identify the USB serial device

Plug the tracker into your Linux machine and check:

```bash
lsusb
sudo dmesg | tail -40
ls -l /dev/ttyACM* /dev/ttyUSB* 2>/dev/null
```

On the test device, Linux reported:

```text
idVendor=1915, idProduct=520f
Product: nRF52 USB CDC Demo
Manufacturer: Nordic Semiconductor
cdc_acm ... ttyACM0: USB ACM device
```

This resulted in the serial port `/dev/ttyACM0`. Your system may assign a different port, such as `/dev/ttyACM1`.

You may find a persistent symlink (if your system creates one) with:

```bash
ls -l /dev/serial/by-id/ 2>/dev/null
```

Such a symlink can be passed directly to `--port` and may be more stable than a numbered `/dev/ttyACM*` device.

### Serial port permissions (Linux)

Check your port and groups:

```bash
ls -l /dev/ttyACM0
id -nG
```

On many Debian/Ubuntu-derived systems, the port belongs to group `dialout`. If your account is not a member, add it (replace `$USER` with the intended account if needed):

```bash
sudo usermod -aG dialout "$USER"
```

**Log out and back in** (or start a new login session) before testing the new group membership. Verify with `id -nG`.

A quick temporary alternative in a new shell is `newgrp dialout`, if that group exists. Group ownership differs by distribution, so inspect `ls -l` first rather than assuming `dialout` everywhere.

**Avoid** permanently changing `/dev/ttyACM0` permissions with `chmod 666`: such changes are usually lost on reconnection and unnecessarily grant access to all local users. Likewise, avoid routine execution of the monitor as root. When run as root, the default log is written to root's **current working directory**, which can make the file hard to find later.

If you still receive `Permission denied`, verify the port owner/group and check for local policies or modem-management services.

### Close other serial terminal programs

Do not leave `picocom`, `minicom`, or another serial monitor connected to the same device while running this program. Concurrent readers can steal data from each other.

Check which process is using the port:

```bash
fuser -v /dev/ttyACM0
```

Exit `picocom` with **Ctrl+A**, then **Ctrl+X** before starting this monitor. If necessary, close the stale process using its PID (prefer a normal `kill` over forced termination).

## Usage

### Live dashboard

```bash
bin/python3 t1000e_monitor.py --port /dev/ttyACM0
```

The default baud rate is **115200** and the dashboard refreshes every **1 second**. The script keeps running until **Ctrl+C**. No serial commands are sent.

The raw messages are logged to a file such as `t1000e_20261115_123456.log` **in the current working directory**. Each line is prefixed with a local timestamp including your timezone offset.

### Choose the raw log location

```bash
bin/python3 t1000e_monitor.py --port /dev/ttyACM0 --log logs/tracker.log
```

Create the `logs` directory yourself first (`mkdir -p logs`). If the destination file already exists, the program **appends** to it. The file may contain location information; see [Privacy](#privacy).

### Refresh the dashboard every two seconds

```bash
bin/python3 t1000e_monitor.py --interval 2
```

### Use a different serial device or baud rate

```bash
bin/python3 t1000e_monitor.py --port /dev/ttyACM1 --baud 115200
```

### Replay an existing recording

```bash
bin/python3 t1000e_monitor.py --replay t1000e_20261114_212441.log
```

Replay reads the entire existing log, prints a final summary, and **does not open USB**. It expects the timestamped log format produced by this monitor, for example:

```text
2026-11-14T21:39:09+01:00 lat: 50687356, lon: 7154802
```

A plain `picocom` capture without these timestamps is not a supported replay format.

### Export GNSS positions as CSV

```bash
bin/python3 t1000e_monitor.py \
  --replay t1000e_20261114_212441.log \
  --csv positions.csv
```

The output contains the columns `timestamp,latitude,longitude`. The timestamp uses ISO 8601 including the timezone offset. The latitude and longitude values are decimal degrees; the debug output's integer coordinates are divided by **1,000,000**. This scale was verified against the sample device's known decoded positions; verify the format when using different firmware.

**CSV export currently works only with `--replay`.** You can export a live session afterwards by replaying its saved log. The CSV file is overwritten if it already exists.

## All command-line options

| Option | Default | Description |
| --- | --- | --- |
| `-h`, `--help` | — | Show the full built-in help and exit |
| `--port DEVICE` | `/dev/ttyACM0` | Linux serial device for live monitoring; ignored in replay mode |
| `--baud RATE` | `115200` | Serial baud rate (positive integer); ignored in replay mode |
| `--log FILE` | `t1000e_YYYYMMDD_HHMMSS.log` | Write/appended timestamped raw debug messages in live mode |
| `--replay FILE` | Not set | Offline analysis of an existing monitor log; no USB connection |
| `--csv FILE` | Not set | Export positions to CSV; requires `--replay` |
| `--interval SECONDS` | `1.0` | Live dashboard refresh interval; must be greater than zero |

`--log` and `--replay` cannot be combined. `--csv` without `--replay` is rejected.

## Understanding the output

The terminal contains four sections:

**GNSS:** Last reported state, last successful position, attempts started and ended, fixes and failures, and the ratio `fixes / (fixes + failures)`. This is the **observed** success rate, not a hardware-quality score. A previous successful coordinate is retained even if the latest attempt fails; check the status and fix timestamp before using it as a current position. Firmware-reported scan lengths are **not** satellite counts.

**LoRaWAN:** Last reported join state and radio parameters, counts of transmit messages and TX-done events, timeouts, mean interval and accumulated transmit airtime. The cumulative airtime is the sum of firmware-reported `toa` values for parsed transmissions, **not** duty-cycle compliance analysis.

**Recent events:** A small rolling list showing received GNSS coordinates, GNSS failures and transmit events.

**Other message types:** Normalized messages not yet recognized by the parser. These help extend compatibility when a new firmware version adds debug output.

The dashboard can remain empty until the device produces another debug message. This is normal; it does not send a command to prompt the tracker.

## Automatic reconnection

In live mode the monitor retries every **2 seconds** if opening or reading the serial device fails. It retains its counters in memory and continues writing to the same raw log after reconnection.

This does **not** guarantee continuous coverage: messages produced while USB is disconnected will be missing. If the operating system assigns a different numbered device after reconnecting, start with a stable `/dev/serial/by-id/...` link when available, or restart using the new `--port`.

A permissions error may also cause repeated retries; fix the device permissions rather than waiting for that error to disappear.

## Troubleshooting

**`Permission denied` when opening `/dev/ttyACM0`**

Check `ls -l /dev/ttyACM0` and `id -nG`. Add your user to the device-owning group as described above and start a new login session.

**No lines arrive, dashboard stays blank**

Check that the cable supports data, inspect `sudo dmesg | tail -40`, verify the selected port, and check `fuser -v /dev/ttyACM0`. There may simply be no new messages yet. Some firmware builds do not emit the same USB diagnostics.

**`device reports readiness to read but returned no data`**

This is a `pyserial` read error. It can be caused by USB resets/disconnections or conflicting serial readers. The monitor will try reconnecting; check the kernel log and ensure no other serial terminal owns the port.

**`No such file or directory`**

The device may have been unplugged or re-enumerated. Find its current name in `dmesg` or `/dev/serial/by-id/`.

**The log seems to be missing**

The default log goes to the **current working directory**, not automatically to your home directory. If you ran the program from a root shell, look in that shell's working directory (often `/root`). Supply `--log /absolute/path/to/file.log` to avoid ambiguity.

**GNSS status says "No fix" even though coordinates exist**

The dashboard retains the most recent successful position while showing the status of the latest GNSS attempt. Compare `Last fix` to the current time. A failed search is not necessarily a tracker fault.

**No downlinks / RX timeouts**

RX timeouts are common when there is no scheduled downlink. They do not prove failed uplinks. Check your network server for received uplinks and radio link metrics.

## Tested with an overnight capture

An example capture from November 14–15, 2026 yielded:

| Metric | Observed value |
| --- | ---: |
| Raw lines | 7,576 |
| GNSS searches started / ended | 165 / 165 |
| GNSS fixes / failures | 161 / 4 |
| GNSS observed fix rate | 97.6% |
| LoRaWAN TX records | 165 |
| TX-done messages | 164 |
| Average TX interval | 299.98 s |
| Total reported TX airtime | 298.16 s |
| Spreading factor | SF12 on all 165 TX records |

The recording ends in the middle of the final radio exchange, explaining why the last TX is not followed by a TX-done event in that file. These measurements describe **one** setup, not expected performance for all deployments.

## Privacy

**Raw logs and exported CSV files can reveal precise physical locations**, times of presence and radio activity. Review or anonymize coordinates before publishing an example log on GitHub. The provided `.gitignore` excludes common generated logs and CSV files by default.

## Limitations and contributions

- This is a parser for **observed firmware debug strings**, not a documented USB command protocol or a full LoRaWAN decoder.
- It does not show satellite count or HDOP unless a future firmware's messages support those values and the parser is updated.
- It does not guarantee that a transmitted frame was received by a gateway.
- It does not retrieve historical records from the device: only messages emitted while connected are observed.
- It currently does not export live GNSS positions directly to CSV. Save a log, then use replay.
- The terminal display is optimized for interactive ANSI-compatible terminals rather than redirected output or narrow windows.

Pull requests for other firmware versions, reproducible debug message examples (with private coordinates redacted), additional statistics and tests are welcome.

## License

Before publishing, add a `LICENSE` file and state your chosen license here (for example, MIT). **No license is granted merely by making a GitHub repository public.**
