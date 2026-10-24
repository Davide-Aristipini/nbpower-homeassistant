"""Read-only CLI: no credentials in arguments, files, output or logs."""
import argparse
import asyncio
import getpass
import importlib.util
import json
from pathlib import Path

path = Path(__file__).resolve().parents[1] / 'custom_components' / 'nbpower' / 'api.py'
spec = importlib.util.spec_from_file_location('nbpower_api', path)
api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(api)


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--discover', action='store_true', help='Public server discovery only')
    args = parser.parse_args()
    client = api.NBPowerClient()
    print('Server:', await client.discover())
    if args.discover:
        return
    email = input('Email account NBPower (non salvata): ').strip()
    await client.request_otp(email)
    otp = getpass.getpass('OTP ricevuto via email (nascosto): ')
    await client.login(email, otp)
    del otp
    chargers = await client.chargers()
    for index, charger in enumerate(chargers):
        print(index, charger.get('mac', 'NBPower'))
    if not chargers:
        print('Nessuna colonnina associata.')
        return
    selected = 0 if len(chargers) == 1 else int(input('Indice colonnina: '))
    if not 0 <= selected < len(chargers):
        raise api.APIError('Invalid selection')
    result = api.telemetry(await client.status(str(chargers[selected]['imei'])))
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except api.APIError as error:
        print('Esito:', str(error))
        raise SystemExit(1) from None
