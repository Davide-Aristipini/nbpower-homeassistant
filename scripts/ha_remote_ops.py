"""Run inside HA Core over authorized SSH; never print auth material."""
import argparse
import asyncio
import importlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
import zipfile


def core_api(path):
    token = os.environ.get('SUPERVISOR_TOKEN') or os.environ.get('HASSIO_TOKEN')
    if not token:
        return {'error': 'Supervisor API unavailable'}
    try:
        request = Request('http://supervisor/core/api/' + path,
                          headers={'Authorization': 'Bearer ' + token})
        with urlopen(request, timeout=15) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, ValueError):
        return {'error': 'Core API request failed'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['inspect', 'install', 'check', 'status', 'cloud', 'solar'])
    parser.add_argument('--archive', default='/tmp/nbpower-integration.zip')
    args = parser.parse_args()
    target = Path('/config/custom_components/nbpower')
    if args.action == 'inspect':
        config = core_api('config')
        print(json.dumps({'existing_nbpower': target.exists(),
                          'config_writable': os.access('/config', os.W_OK),
                          'ha_version': config.get('version'),
                          'supervisor_api': 'error' not in config}))
    elif args.action == 'install':
        if target.exists():
            raise SystemExit('Existing nbpower directory: inspect before updating')
        if not Path('/config').is_dir():
            raise SystemExit('Config directory unavailable')
        with zipfile.ZipFile(args.archive) as archive:
            for entry in archive.infolist():
                path = Path(entry.filename)
                if '..' in path.parts or not entry.filename.startswith('custom_components/nbpower/'):
                    raise SystemExit('Unexpected archive member')
            archive.extractall('/config')
        print('NBPower integration installed')
    elif args.action == 'check':
        sys.path.insert(0, '/config')
        modules = ['api', 'config_flow', 'coordinator', 'sensor', 'binary_sensor']
        for name in modules:
            importlib.import_module('custom_components.nbpower.' + name)
        print(json.dumps({'imports_verified': modules}))
    elif args.action == 'status':
        entries = core_api('config/config_entries/entry')
        if isinstance(entries, list):
            print(json.dumps([{'domain': e.get('domain'), 'state': e.get('state'),
                               'reason': e.get('reason')} for e in entries if e.get('domain') == 'nbpower']))
        else:
            # Authorized host access also permits a narrow read-only check of
            # the configured integration and its recorder states. Never output
            # config-entry data, which contains account credentials.
            config_path = Path('/config/.storage/core.config_entries')
            registry_path = Path('/config/.storage/core.entity_registry')
            if not config_path.is_file() or not registry_path.is_file():
                print(json.dumps(entries))
                return
            configured = json.loads(config_path.read_text())['data']['entries']
            own_ids = {e['entry_id'] for e in configured if e.get('domain') == 'nbpower'}
            entities = json.loads(registry_path.read_text())['data']['entities']
            own_entities = [e for e in entities if e.get('config_entry_id') in own_ids]
            result = {'configured_entries': len(own_ids), 'entities': []}
            database = Path('/config/home-assistant_v2.db')
            connection = sqlite3.connect(f'file:{database}?mode=ro', uri=True, timeout=5) if database.is_file() else None
            try:
                for entity in own_entities:
                    item = {'entity_id': entity['entity_id'], 'disabled_by': entity.get('disabled_by')}
                    if connection:
                        row = connection.execute('SELECT state, last_updated_ts FROM states WHERE metadata_id = '
                            '(SELECT metadata_id FROM states_meta WHERE entity_id = ?) ORDER BY state_id DESC LIMIT 1',
                            (entity['entity_id'],)).fetchone()
                        if row:
                            item.update(state=row[0], last_recorded=row[1])
                    result['entities'].append(item)
            finally:
                if connection:
                    connection.close()
            print(json.dumps(result))
    elif args.action == 'cloud':
        configured = json.loads(Path('/config/.storage/core.config_entries').read_text())['data']['entries']
        own = next((e for e in configured if e.get('domain') == 'nbpower'), None)
        if not own:
            raise SystemExit('NBPower not configured')
        sys.path.insert(0, '/config')
        api = importlib.import_module('custom_components.nbpower.api')
        async def read_status():
            data = own['data']
            client = api.NBPowerClient(access_token=data['access_token'],
                                      refresh_token=data.get('refresh_token'), user_server=data['user_server'])
            try:
                response = await client.status(data['imei'])
                values = api.parse_heartbeat(response.get('heartDB', {}).get('data'))
                active = response.get('activeTime')
                values['cloud_timestamp'] = active
                values['age_seconds'] = round(time.time() - active/1000, 1) if isinstance(active, (int, float)) else None
                print(json.dumps(values))
            except api.APIError as error:
                print(json.dumps({'error': str(error)}))
        asyncio.run(read_status())
    elif args.action == 'solar':
        states = core_api('states')
        if not isinstance(states, list):
            print(json.dumps(states))
            return
        # Entity identity, unit and value only: no attributes containing credentials.
        words = ('solar', 'fotovolta', 'inverter', 'grid', 'rete', 'export', 'import', 'surplus', 'battery', 'batteria')
        selected = []
        for state in states:
            entity = state.get('entity_id', '')
            name = str(state.get('attributes', {}).get('friendly_name', ''))
            if entity.startswith('sensor.') and any(word in (entity+' '+name).lower() for word in words):
                selected.append({'entity_id': entity, 'name': name, 'value': state.get('state'),
                                 'unit': state.get('attributes', {}).get('unit_of_measurement')})
        print(json.dumps(selected, ensure_ascii=True))


if __name__ == '__main__':
    main()
