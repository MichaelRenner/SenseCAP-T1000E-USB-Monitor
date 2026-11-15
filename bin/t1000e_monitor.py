#!/usr/bin/env python3

# (C) Michael Renner <michael.renner@gmx.de>
# Version 0.1

"""Read-only SenseCAP T1000-E (LoRaWAN) USB serial diagnostics monitor.

Live:   python3 t1000e_monitor.py --port /dev/ttyACM0
Replay: python3 t1000e_monitor.py --replay t1000e_20261114_212441.log

Live mode requires pyserial; replay mode uses only the Python standard library.
"""

import argparse
from collections import Counter, deque
import csv
from datetime import datetime
import re
import sys
import time

TX_RE = re.compile(
    r'Tx\s+LoRa at\s+(\d+)\s*ms:\s*freq:(\d+),\s*SF(\d+),\s*BW(\d+),'
    r'\s*len\s+(\d+)\s+bytes\s+(-?\d+)\s+dBm,\s*fcnt_up\s+(\d+),\s*toa\s*=\s*(\d+)',
    re.IGNORECASE,
)
POSITION_RE = re.compile(r'lat:\s*(-?\d+),\s*lon:\s*(-?\d+)', re.IGNORECASE)
TIMESTAMPED_LINE_RE = re.compile(r'^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d[^ ]*)\s+(.*)$')


def now_iso():
    return datetime.now().astimezone().isoformat(timespec='seconds')


def parse_timestamp(value):
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def clean_line(value):
    return ' '.join(value.split())


class Tracker:
    """Collect statistics from firmware diagnostic text without writing to USB."""

    def __init__(self):
        self.counts = Counter()
        self.fields = {}
        self.recent = deque(maxlen=6)
        self.unknown = Counter()
        self.spreading_factors = Counter()
        self.positions = []  # (ISO timestamp, latitude, longitude)
        self.last_tx_time = None
        self.tx_intervals = []
        self.total_airtime_ms = 0

    def note(self, timestamp, message):
        self.recent.append(f'{timestamp[11:19]} {message}')

    def feed(self, timestamp, raw):
        self.counts['raw_lines'] += 1
        line = clean_line(raw)
        if not line:
            return
        self.counts['nonempty_lines'] += 1
        fields = self.fields
        fields['last_seen'] = timestamp

        match = re.search(r'Modem status:\s*(\S+)', line, re.IGNORECASE)
        if match:
            fields['modem'] = match.group(1)
            return
        if 'gnss begin,' in line.lower():
            self.counts['gnss_starts'] += 1
            fields['gnss_status'] = 'Searching'
            return
        if 'gnss end,' in line.lower():
            self.counts['gnss_ends'] += 1
            return
        if 'gnss fix fail' in line.lower():
            self.counts['gnss_fails'] += 1
            fields['gnss_status'] = 'No fix (last attempt)'
            self.note(timestamp, 'GNSS: no fix')
            return
        match = POSITION_RE.search(line)
        if match:
            latitude = int(match.group(1)) / 1_000_000
            longitude = int(match.group(2)) / 1_000_000
            if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                self.counts['gnss_fixes'] += 1
                fields.update(latitude=latitude, longitude=longitude,
                              gnss_status='Fix', last_fix=timestamp)
                self.positions.append((timestamp, latitude, longitude))
                self.note(timestamp, f'GNSS: {latitude:.6f}, {longitude:.6f}')
            return

        for name, pattern in (
            ('gps_scan', r'tracker_gps_scan_len:\s*(\d+)'),
            ('wifi_scan', r'tracker_wifi_scan_len:\s*(\d+)'),
            ('ble_scan', r'tracker_ble_scan_len:\s*(\d+)'),
            ('scan_count', r'scan_result_num:\s*(\d+)'),
            ('fport', r'User Tx LORa on FPort\s+(\d+)'),
            ('uplink_count', r'Uplink count:\s*(\d+)'),
        ):
            match = re.search(pattern, line, re.IGNORECASE)
            if match:
                fields[name] = int(match.group(1))
                return

        match = TX_RE.search(line)
        if match:
            _, frequency, sf, bandwidth, payload_size, power, frame_counter, airtime = map(int, match.groups())
            self.counts['tx'] += 1
            self.spreading_factors[sf] += 1
            self.total_airtime_ms += airtime
            instant = parse_timestamp(timestamp)
            if instant and self.last_tx_time:
                seconds = (instant - self.last_tx_time).total_seconds()
                if 0 < seconds < 86_400:
                    self.tx_intervals.append(seconds)
            if instant:
                self.last_tx_time = instant
            fields.update(last_tx=timestamp, frequency=frequency / 1_000_000,
                          sf=sf, bw=bandwidth, payload_len=payload_size, power=power,
                          fcnt=frame_counter, airtime=airtime)
            self.note(timestamp, f'TX SF{sf} {frequency / 1_000_000:.3f} MHz '
                                 f'FCnt {frame_counter} ({payload_size} B)')
            return

        if 'TX Done status:' in line:
            self.counts['tx_done'] += 1
            fields['tx_status'] = line.split('TX Done status:', 1)[1].strip()
            return
        if 'RX1 Timeout' in line:
            self.counts['rx1_timeouts'] += 1
            return
        if 'RX2 Timeout' in line:
            self.counts['rx2_timeouts'] += 1
            return

        # Known noise: do not report these as previously unseen message types.
        if (line.startswith('INFO: ######') or line.startswith('Timer will expire')
                or line.startswith('send end,') or line.startswith('Open RX')
                or line.startswith('*') or line.startswith('INFO: Request uplink')
                or line.startswith('Send Payload') or line.startswith('TX DONE')):
            return
        canonical = re.sub(r'-?\d+(?:\.\d+)?', '#', line)
        self.unknown[canonical] += 1

    def render(self, source, log_path, connection):
        fields, counts = self.fields, self.counts
        attempts = counts['gnss_fixes'] + counts['gnss_fails']
        success_rate = (f'{100 * counts["gnss_fixes"] / attempts:.1f}%'
                        if attempts else '—')
        interval = (f'{sum(self.tx_intervals) / len(self.tx_intervals):.2f} s'
                    if self.tx_intervals else '—')
        position = (f'{fields["latitude"]:.6f}, {fields["longitude"]:.6f}'
                    if 'latitude' in fields else '—')
        sf_distribution = (', '.join(f'SF{sf}: {count}'
                                     for sf, count in sorted(self.spreading_factors.items())) or '—')
        frequency = (f'{fields["frequency"]:.3f} MHz' if 'frequency' in fields else '—')
        rows = [
            'T1000-E USB MONITOR  |  Read-only  |  Ctrl+C to quit',
            '=' * 77,
            f'Source: {source}  |  Connection: {connection}',
            f'Raw log: {log_path or "(replay; no log written)"}',
            f'Lines received: {counts["raw_lines"]}  |  Last message: {fields.get("last_seen", "—")}',
            '', 'GNSS', '-' * 77,
            f'Status: {fields.get("gnss_status", "—")}  |  Last fix: {fields.get("last_fix", "—")}',
            f'Position (latitude, longitude): {position}',
            f'Searches started: {counts["gnss_starts"]}  |  Ended: {counts["gnss_ends"]}',
            f'Fixes: {counts["gnss_fixes"]}  |  Failures: {counts["gnss_fails"]}  |  Success rate: {success_rate}',
            f'GPS / Wi-Fi / BLE scan lengths (latest): '
            f'{fields.get("gps_scan", "—")} / {fields.get("wifi_scan", "—")} / {fields.get("ble_scan", "—")}',
            f'Scan results (latest): {fields.get("scan_count", "—")}',
            '', 'LORAWAN', '-' * 77,
            f'Modem: {fields.get("modem", "—")}  |  FPort: {fields.get("fport", "—")}',
            f'Last TX: {fields.get("last_tx", "—")}',
            f'Frequency: {frequency}  |  SF: {fields.get("sf", "—")}  |  BW: {fields.get("bw", "—")} kHz',
            f'TX power: {fields.get("power", "—")} dBm  |  Payload: '
            f'{fields.get("payload_len", "—")} B  |  FCntUp: {fields.get("fcnt", "—")}',
            f'TX: {counts["tx"]}  |  TX done: {counts["tx_done"]}  |  '
            f'RX1 / RX2 timeouts: {counts["rx1_timeouts"]} / {counts["rx2_timeouts"]}',
            f'Mean TX interval: {interval}  |  Total TX airtime: {self.total_airtime_ms / 1000:.2f} s',
            f'Spreading factors: {sf_distribution}',
            '', 'RECENT EVENTS', '-' * 77,
            *(list(self.recent) or ['No events yet']),
            '', 'OTHER MESSAGE TYPES (TOP 4)', '-' * 77,
            *(f'{count:5d} × {kind}' for kind, count in self.unknown.most_common(4)),
            '', 'Note: TX done does not prove that a gateway received the uplink.',
            'Note: RX1/RX2 timeouts are normal when no downlink is scheduled.',
        ]
        return '\n'.join(rows)


def replay(path, tracker, csv_path):
    with open(path, encoding='utf-8', errors='replace') as source:
        for record in source:
            match = TIMESTAMPED_LINE_RE.match(record.rstrip('\r\n'))
            if match:
                tracker.feed(match.group(1), match.group(2))
    if csv_path:
        with open(csv_path, 'w', newline='', encoding='utf-8') as target:
            writer = csv.writer(target)
            writer.writerow(['timestamp', 'latitude', 'longitude'])
            writer.writerows(tracker.positions)
    print(tracker.render(path, None, 'REPLAY COMPLETE'))
    if csv_path:
        print(f'\nExported {len(tracker.positions)} positions to {csv_path}')


def live(args, tracker):
    try:
        import serial
    except ImportError:
        sys.exit('Missing dependency: pyserial. Install with: sudo apt install python3-serial')
    log_path = args.log or f't1000e_{datetime.now():%Y%m%d_%H%M%S}.log'
    with open(log_path, 'a', encoding='utf-8', buffering=1) as target:
        while True:
            try:
                with serial.Serial(args.port, args.baud, timeout=0.3,
                                   rtscts=False, dsrdtr=False) as device:
                    last_draw = 0
                    while True:
                        data = device.readline()
                        if data:
                            stamp = now_iso()
                            raw = data.decode('utf-8', errors='replace').rstrip('\r\n')
                            target.write(f'{stamp} {raw}\n')
                            tracker.feed(stamp, raw)
                        if time.monotonic() - last_draw >= args.interval:
                            print('\x1b[H\x1b[J' + tracker.render(args.port, log_path, 'CONNECTED'),
                                  end='\n', flush=True)
                            last_draw = time.monotonic()
            except (serial.SerialException, OSError) as error:
                print('\x1b[H\x1b[J' + tracker.render(args.port, log_path,
                                                       f'DISCONNECTED: {error}'),
                      flush=True)
                time.sleep(2)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--port', default='/dev/ttyACM0', metavar='DEVICE',
                        help='Serial device for live monitoring (default: /dev/ttyACM0)')
    parser.add_argument('--baud', type=int, default=115200, metavar='RATE',
                        help='Serial baud rate (default: 115200)')
    parser.add_argument('--log', metavar='FILE',
                        help='Append live raw messages to FILE (default: dated file in current directory)')
    parser.add_argument('--replay', metavar='FILE',
                        help='Analyze an existing timestamped monitor log instead of opening USB')
    parser.add_argument('--csv', metavar='FILE',
                        help='Export GNSS positions to CSV (requires --replay)')
    parser.add_argument('--interval', type=float, default=1.0, metavar='SECONDS',
                        help='Live display refresh period in seconds (default: 1.0)')
    args = parser.parse_args(argv)
    if args.interval <= 0:
        parser.error('--interval must be greater than zero')
    if args.baud <= 0:
        parser.error('--baud must be greater than zero')
    if args.csv and not args.replay:
        parser.error('--csv requires --replay')
    if args.replay and args.log:
        parser.error('--log is only supported in live mode')
    tracker = Tracker()
    try:
        if args.replay:
            replay(args.replay, tracker, args.csv)
        else:
            live(args, tracker)
    except KeyboardInterrupt:
        print('\nMonitor stopped.')
    except (OSError, UnicodeError) as error:
        sys.exit(f'Error: {error}')


if __name__ == '__main__':
    main()
