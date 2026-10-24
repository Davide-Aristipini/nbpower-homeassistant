"""Inspect only publicly linked NBPower web assets; never authenticate."""
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parents[1]


def fetch(url):
    with urllib.request.urlopen(url, timeout=20) as response:
        return response.read().decode('utf-8', errors='replace')


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    base = 'https://echgr.com'
    html = fetch(base)
    pending = [urljoin(base, p) for p in re.findall(r'src="([^"]+\.js)"', html)
               if 'legacy' not in p]
    visited = set()
    result = []
    while pending and len(visited) < 70:
        url = pending.pop(0)
        if url in visited:
            continue
        visited.add(url)
        try:
            text = fetch(url)
        except Exception as exc:
            result.append({'url': url, 'error': type(exc).__name__})
            continue
        paths = re.findall(r'["\']([^"\']+\.js)["\']', text)
        for path in paths:
            if not path.startswith(('http', '/')) and re.fullmatch(r'[\w./-]+\.js', path):
                pending.append(urljoin(base + '/', path) if path.startswith('assets/') else urljoin(url, path))
        contexts = []
        for match in re.finditer(r'echgr|baseURL|wss?://|https?://|sendEmail|sendCode|login|Login|mqtt|\.apk|request\(|/api/|Authorization|token', text):
            context = text[max(0, match.start()-100):match.end()+180]
            if context not in contexts:
                contexts.append(context)
        result.append({'url': url, 'sha256': hashlib.sha256(text.encode()).hexdigest(),
                       'size': len(text), 'contexts': contexts})
    output = ROOT / 'reports' / 'public_web.json'
    output.parent.mkdir(exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    for item in result:
        print(item['url'], item.get('size', item.get('error')))
        for context in item.get('contexts', []):
            if any(key in context for key in ('echgr', 'baseURL', '.apk', '/api/', 'wss://')):
                print(' ', context)


if __name__ == '__main__':
    main()
