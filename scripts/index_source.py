"""Create searchable excerpts from the public application (not executable JS)."""
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
source = (root / 'research' / 'app-service.js').read_text(encoding='utf-8')
patterns = [r'https://g\.echgr\.com/', r'https://c\.echgr\.com/',
            r'uni\.request', r'\.request\(', r'connectSocket', r'sendSocketMessage',
            r'getStorageSync\(', r'email', r'Email', r'baseURL']
chunks = []
positions = set()
for pattern in patterns:
    for match in re.finditer(pattern, source):
        start, end = max(0, match.start()-500), min(len(source), match.end()+1800)
        if any(abs(start-other) < 250 for other in positions):
            continue
        positions.add(start)
        chunks.append(f'\nOFFSET {start} PATTERN {pattern}\n' + source[start:end])
(root / 'research' / 'network-excerpts.txt').write_text('\n'.join(chunks).replace(';', ';\n'), encoding='utf-8')
print(f'{len(chunks)} excerpts indexed')
for name, start, end in [('transport', 539000, 550000), ('netmode', 1328500, 1361087)]:
    (root / 'research' / (name + '.txt')).write_text(source[start:end].replace(';', ';\n').replace('},{key:', '},\n{key:'), encoding='utf-8')
endpoints = sorted(set(re.findall(r'\.send\("([A-Za-z0-9_]+)"', source)))
(root / 'research' / 'endpoints.json').write_text(__import__('json').dumps(endpoints, indent=2), encoding='utf-8')
targeted = []
for needle in ['hex_md5_16:', 'hex_md5_16=', 'getBindedChargers', 'calcMeterDB:', 'getChargerKey', 'changeAmp', 'changePWM', 'stopCharge:function', 'startCharge:function', 'getNBPNetStatus', 'activeTime', 'maxAmp', 'chargerMaxAmp=', 'chargerMaxAmp:', 'sendCommand(!0,47', 'sendCommand(!1,47', 'sendCommand:function', 'checkChargePwd:function', 'amp2PwmRange:function']:
    for match in re.finditer(re.escape(needle), source):
        targeted.append('\nNEEDLE ' + needle + ' OFFSET ' + str(match.start()) + '\n' + source[max(0,match.start()-200):match.end()+2500])
(root / 'research' / 'details.txt').write_text('\n'.join(targeted).replace(';', ';\n'), encoding='utf-8')
