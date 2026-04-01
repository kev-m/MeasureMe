import os
import json
from googleapiclient.discovery import build_from_document
import google.oauth2.credentials

def main():
    with open('storage/ghealth_tokens.json') as f:
        token_info = json.load(f)

    creds = google.oauth2.credentials.Credentials.from_authorized_user_info(
        token_info)

    discovery_path = os.path.join(os.path.dirname(__file__), '..', 'health_api_discovery_rest.json')
    with open(discovery_path, encoding='utf-8') as f:
        service = build_from_document(f.read(), credentials=creds)

    d = json.load(open(discovery_path, encoding='utf-8'))
    for field in d['schemas']['DataPoint']['properties'].keys():
        if field in ('name', 'dataSource'):
            continue
        try:
            service.users().dataTypes().dataPoints().list(
                parent=f'users/me/dataTypes/{field}').execute()
            print(f'{field} WORKED')
        except Exception as e:
            if 'not supported' in str(e):
                print(f'{field} NOT SUPPORTED')
            else:
                print(f'{field} failed: {e}')


if __name__ == "__main__":
    main()
