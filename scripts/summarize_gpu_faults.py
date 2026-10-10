#!/usr/bin/env python3
"""Summarize Asahi GPU timeout/fault reports from a kernel log (plain or .gz).

Parses the driver's "GPU timeout" blocks and their optional FaultInfo
records, then prints/writes counts, time span, timeout-counter range,
halted/recovery tallies and fault field histograms. Reusable for any dmesg
capture taken around a risky probe. No GPU access.
"""
import argparse
import collections
import gzip
import json
from pathlib import Path
import re
import sys

STAMP = re.compile(r'^\[(?P<t>[^\]]+)\] asahi [0-9a-f]+\.gpu: ?(?P<msg>.*)$')


def parse(lines):
    timeouts, faults, events = [], [], collections.Counter()
    current = None; fault = None
    for raw in lines:
        line = raw.rstrip('\n')
        m = STAMP.match(line)
        if fault is not None:
            body = line.strip() if not m else ''
            if body.startswith('}') or m:
                faults.append(fault); fault = None
            else:
                kv = re.match(r'(\w+): (.*?),?$', body)
                if kv: fault[kv.group(1)] = kv.group(2)
                elif body.startswith(('0x', 'UL1C', 'TA', 'VDM')) or '(' in body:
                    fault.setdefault('unit_detail', []).append(body.rstrip(','))
                if not m: continue
        if not m: continue
        t, msg = m.group('t'), m.group('msg').strip()
        if 'GPU timeout' in msg:
            current = {'time': t}; timeouts.append(current)
        elif msg.startswith('Timeout count:') and current is not None:
            current['count'] = int(msg.split(':')[1])
        elif msg.startswith('Event slot:') and current is not None:
            current['slot'] = int(msg.split(':')[1])
        elif msg.startswith('Fault info:'):
            fault = {'time': t}
            if current is not None: current['fault'] = True
        elif msg.startswith(('Halted:', 'Attempting recovery')):
            events[msg] += 1
    if fault is not None: faults.append(fault)
    return timeouts, faults, events


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('log', type=Path)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    opener = gzip.open if a.log.suffix == '.gz' else open
    with opener(a.log, 'rt', errors='replace') as f:
        timeouts, faults, events = parse(f)
    hist = lambda key: dict(collections.Counter(x.get(key, '?') for x in faults).most_common())
    summary = {
        'source': str(a.log), 'timeouts': len(timeouts), 'timeouts_with_fault': sum(1 for t in timeouts if t.get('fault')),
        'fault_records': len(faults), 'first': timeouts[0]['time'] if timeouts else None,
        'last': timeouts[-1]['time'] if timeouts else None,
        'timeout_counter_range': [min(t['count'] for t in timeouts), max(t['count'] for t in timeouts)] if timeouts else None,
        'recovery_events': dict(events),
        'fault_fields': {k: hist(k) for k in ('reason', 'read', 'level', 'sideband', 'unit_code', 'address')},
        'distinct_vm_slots': len({x.get('vm_slot') for x in faults}),
    }
    text = json.dumps(summary, indent=1)
    if a.output: a.output.write_text(text+'\n')
    print(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
