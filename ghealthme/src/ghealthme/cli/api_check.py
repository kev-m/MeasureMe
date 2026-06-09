import os
import json
import logging
import re
from googleapiclient.discovery import build_from_document
from ghealthme.ghealth_common import load_credentials

# Setup basic logging to see refresh errors if they occur
logging.basicConfig(level=logging.INFO)

def camel_to_kebab(name):
    """Converts camelCase or PascalCase to kebab-case."""
    name = re.sub('(.)([A-Z][a-z]+)', r'\1-\2', name)
    return re.sub('([a-z0-9])([A-Z])', r'\1-\2', name).lower()

def main():
    token_path = os.environ.get('GH_TOKEN_FILE', 'storage/ghealth_tokens.json')
    creds = load_credentials(token_path)

    if not creds:
        print(f"Error: Could not load credentials from {token_path}")
        print("Run the OAuth login flow first (see GoogleHealth_setup.md)")
        return

    discovery_path = os.path.join(os.path.dirname(__file__), '..', 'health_api_discovery_rest.json')
    with open(discovery_path, encoding='utf-8') as f:
        service = build_from_document(f.read(), credentials=creds)

    d = json.load(open(discovery_path, encoding='utf-8'))
    for field in d['schemas']['DataPoint']['properties'].keys():
        if field in ('name', 'dataSource'):
            continue

        # The API expects kebab-case for the data type in the URL path
        kebab_field = camel_to_kebab(field)
        
        try:
            service.users().dataTypes().dataPoints().list(
                parent=f'users/me/dataTypes/{kebab_field}').execute()
            print(f'{field} WORKED')
        except Exception as e:
            if 'not supported' in str(e):
                print(f'{field} NOT SUPPORTED')
            else:
                print(f'{field} failed: {e}')


if __name__ == "__main__":
    main()
