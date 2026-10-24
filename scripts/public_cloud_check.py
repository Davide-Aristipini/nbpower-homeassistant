"""Compare evidenced public read endpoints, without an account."""
import asyncio
import argparse
import json
from pathlib import Path
from probe_cloud import api


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--negative-only', action='store_true')
    args = parser.parse_args()
    results = []
    for origin in (() if args.negative_only else ('https://c.echgr.com', 'https://g.echgr.com')):
        for endpoint in ('getUserServer', 'getQRDomains'):
            try:
                payload = {} if endpoint == 'getUserServer' else api.signed_payload({})
                response = await api.urllib_transport(origin + '/api/' + endpoint, payload)
                # Public endpoints only: no email, OTP or user session exists.
                result = {'origin': origin, 'endpoint': endpoint, 'response': response}
            except api.APIError as error:
                result = {'origin': origin, 'endpoint': endpoint, 'error': str(error)}
            results.append(result)
            print(json.dumps(result, ensure_ascii=True))
    # One negative control: distinguish signature verification from an open endpoint.
    payload = api.signed_payload({})
    payload['sig'] = '0000000000000000'
    try:
        response = await api.urllib_transport('https://c.echgr.com/api/getQRDomains', payload)
        result = {'origin': 'https://c.echgr.com', 'endpoint': 'getQRDomains',
                  'signature_negative_control': True,
                  'response_code': response.get('code')}
    except api.APIError as error:
        result = {'signature_negative_control': True, 'error': str(error)}
    results.append(result)
    print(json.dumps(result, ensure_ascii=True))
    path = Path(__file__).resolve().parents[1] / 'reports' / ('signature_negative.json' if args.negative_only else 'public_cloud.json')
    path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    asyncio.run(main())
