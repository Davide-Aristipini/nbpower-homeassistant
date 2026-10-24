"""Build a clean installable ZIP containing only integration source files."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
output = root / 'dist'
output.mkdir(exist_ok=True)
archive_path = output / 'nbpower-integration.zip'
with zipfile.ZipFile(archive_path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
    for path in sorted((root / 'custom_components/nbpower').rglob('*')):
        if path.is_file() and path.suffix in ('.py', '.json'):
            archive.write(path, path.relative_to(root).as_posix())
print(archive_path)
