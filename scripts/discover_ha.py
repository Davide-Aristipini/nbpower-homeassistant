"""Read the unauthenticated WebSocket greeting of specified HA hosts."""
import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import socket
import struct


def receive_exact(sock, size):
    data = b''
    while len(data) < size:
        chunk = sock.recv(size-len(data))
        if not chunk:
            raise ValueError('Incomplete frame')
        data += chunk
    return data


def probe(host):
    with socket.create_connection((host, 8123), timeout=5) as sock:
        key = base64.b64encode(os.urandom(16)).decode()
        sock.sendall((f'GET /api/websocket HTTP/1.1\r\nHost: {host}:8123\r\n'
                      'Upgrade: websocket\r\nConnection: Upgrade\r\n'
                      f'Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n').encode())
        header = b''
        while not header.endswith(b'\r\n\r\n') and len(header) < 16384:
            header += receive_exact(sock, 1)
        expected = base64.b64encode(hashlib.sha1((key+'258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode()).digest())
        if not header.startswith(b'HTTP/1.1 101') or expected not in header:
            raise ValueError('WebSocket handshake rejected')
        first, second = receive_exact(sock, 2)
        if first & 15 != 1 or second & 128:
            raise ValueError('Unexpected WebSocket frame')
        size = second & 127
        if size == 126:
            size = struct.unpack('!H', receive_exact(sock, 2))[0]
        if size > 4096 or size == 127:
            raise ValueError('Greeting too large')
        greeting = json.loads(receive_exact(sock, size))
        return {'host': host, 'port': 8123, 'type': greeting.get('type'), 'ha_version': greeting.get('ha_version')}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('hosts', nargs='+', help='Home Assistant host addresses')
    args = parser.parse_args()
    results = []
    for host in args.hosts:
        try:
            results.append(probe(host))
        except (OSError, ValueError):
            results.append({'host': host, 'error': 'Greeting unavailable'})
    print(json.dumps(results, indent=2))
    output = Path(__file__).resolve().parents[1] / 'reports' / 'home_assistant.json'
    output.write_text(json.dumps(results, indent=2), encoding='utf-8')
