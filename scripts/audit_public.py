"""Audit staged text without printing potential secret values."""
import re
import subprocess


def git(*args):
    return subprocess.check_output(['git', *args])


def main():
    paths = git('diff', '--cached', '--name-only', '--diff-filter=ACM').decode().splitlines()
    patterns = {
        'private_ip': re.compile(r'\b(?:192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})\b'),
        'device_identifier': re.compile(r'NBPower-[0-9a-fA-F]{12}\b'),
        'github_token': re.compile(r'gh[pousr]_[A-Za-z0-9]{20,}'),
        'private_key': re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'),
        'email': re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b'),
        'windows_home_path': re.compile(r'[A-Za-z]:[\\/](?:Users|Lavoro)[\\/]'),
    }
    findings = []
    for path in paths:
        if path.startswith(('reports/', 'research/', 'private/', 'dist/')) or path in ('docs/REPORT.md', 'docs/DEPLOYMENT_PRIVATE.md'):
            findings.append((path, 'private_artifact'))
            continue
        content = git('show', ':' + path).decode('utf-8', errors='replace')
        for label, pattern in patterns.items():
            for match in pattern.finditer(content):
                if label == 'email' and match.group().endswith('.invalid'):
                    continue
                if label == 'email' and path == 'tests/test_api.py' and match.group() == ('secret@' + 'g.echgr.com'):
                    # Deliberately fake URL userinfo in the server-origin rejection test.
                    continue
                findings.append((path, label))
                break
    for path, label in findings:
        print(f'REVIEW REQUIRED: {path}: {label}')
    if findings:
        raise SystemExit(1)
    print(f'Public-content audit passed for {len(paths)} staged files')


if __name__ == '__main__':
    main()
