"""Low-impact local TCP connect diagnostics. Does not send device commands."""
import argparse
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import socket
import subprocess
import time

PORTS = [80, 443, 8080, 8443, 8000, 5000, 1883, 8883, 502, 9000]
ROOT = Path(__file__).resolve().parents[1]


def tcp_probe(host, port, timeout=2):
    start = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            state = 'open'
        error = None
    except ConnectionRefusedError as exc:
        state, error = 'closed', exc.errno
    except (socket.timeout, TimeoutError) as exc:
        state, error = 'timeout', exc.errno
    except OSError as exc:
        state, error = 'unreachable_or_filtered', exc.errno
    return {'port': port, 'state': state, 'error': error,
            'elapsed_ms': round((time.monotonic()-start)*1000)}


def powershell(command):
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                            capture_output=True, text=True, timeout=20)
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='Private IPv4 address of your charger')
    args = parser.parse_args()
    ip = ipaddress.ip_address(args.host)
    if not ip.is_private or ip.version != 4:
        parser.error('Specify a private IPv4 address')
    report = {'timestamp': datetime.now(timezone.utc).isoformat(), 'target': str(ip),
              'ports': [], 'dns': {}}
    report['adapters'] = powershell('Get-NetAdapter | Select-Object Name,Status,InterfaceDescription,MacAddress | ConvertTo-Json')
    report['addresses'] = powershell('Get-NetIPAddress -AddressFamily IPv4 | Select-Object InterfaceAlias,IPAddress,PrefixLength | ConvertTo-Json')
    report['routes'] = powershell('Get-NetRoute -AddressFamily IPv4 | Select-Object DestinationPrefix,NextHop,InterfaceAlias,RouteMetric | ConvertTo-Json')
    for port in PORTS:
        report['ports'].append(tcp_probe(str(ip), port))
        time.sleep(.1)
    report['arp'] = powershell(f"Get-NetNeighbor -IPAddress '{ip}' | Select-Object IPAddress,LinkLayerAddress,State,InterfaceAlias | ConvertTo-Json")
    for name in ('echgr.com', 'g.echgr.com', 'c.echgr.com', 'homeassistant.local'):
        try:
            report['dns'][name] = sorted({item[4][0] for item in socket.getaddrinfo(name, None)})
        except socket.gaierror:
            report['dns'][name] = []
    output = ROOT / 'reports' / 'network.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'target': report['target'], 'ports': report['ports'], 'arp': report['arp']}, indent=2))
    print('Report:', output)


if __name__ == '__main__':
    main()
