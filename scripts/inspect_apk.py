"""Download manufacturer-linked APK and extract public network code for research."""
import hashlib
import io
import json
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    url = 'https://c.echgr.com/nbpower.apk'
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(150 * 1024 * 1024)
    archive = zipfile.ZipFile(io.BytesIO(data))
    output = ROOT / 'research'
    output.mkdir(exist_ok=True)
    report = {'url': url, 'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data), 'files': []}
    for name in archive.namelist():
        if not name.endswith(('.js', '.json', '.html')) or not name.startswith('assets/'):
            continue
        raw = archive.read(name)
        text = raw.decode('utf-8', errors='replace')
        domains = sorted(set(re.findall(r'(?:https?|wss?)://[a-zA-Z0-9._:/-]+', text)))
        if domains or 'app-service.js' in name:
            report['files'].append({'name': name, 'size': len(raw), 'urls': domains})
            print(name, len(raw), json.dumps(domains, ensure_ascii=False))
        if name.endswith(('app-service.js', 'manifest.json')):
            # Only static, public app resources, never a user session.
            (output / Path(name).name).write_text(text, encoding='utf-8')
    target = ROOT / 'reports' / 'apk.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('APK SHA256:', report['sha256'])


if __name__ == '__main__':
    main()
