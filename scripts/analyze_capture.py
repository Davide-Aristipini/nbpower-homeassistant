"""Extract DNS/SNI/flow metadata only; never dump HTTP or MQTT payloads."""
import argparse
from collections import Counter
import ipaddress
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--ip', required=True, help='Private IP of your charger in the capture')
    parser.add_argument('--tshark', default=shutil.which('tshark') or r'C:\Program Files\Wireshark\tshark.exe')
    args = parser.parse_args()
    address = str(ipaddress.ip_address(args.ip))
    if not args.capture.is_file() or not Path(args.tshark).is_file():
        parser.error('A capture file and an installed tshark executable are required')
    fields = ['ip.src', 'ip.dst', 'tcp.srcport', 'tcp.dstport', 'udp.srcport', 'udp.dstport',
              'dns.qry.name', 'tls.handshake.extensions_server_name']
    command = [args.tshark, '-n', '-r', str(args.capture), '-Y', f'ip.addr == {address}',
               '-T', 'fields', '-E', 'separator=\t', '-E', 'occurrence=f']
    for field in fields:
        command.extend(['-e', field])
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode:
        raise SystemExit('tshark failed; verify file format and installed version')
    flows, domains, sni = Counter(), Counter(), Counter()
    for line in result.stdout.splitlines():
        row = line.split('\t')
        row += [''] * (len(fields)-len(row))
        flows[' | '.join(row[:6])] += 1
        if row[6]:
            domains[row[6]] += 1
        if row[7]:
            sni[row[7]] += 1
    print(json.dumps({'flows': dict(flows), 'dns_queries': dict(domains), 'tls_sni': dict(sni)}, indent=2))


if __name__ == '__main__':
    main()
