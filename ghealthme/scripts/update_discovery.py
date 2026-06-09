import os
import json
import requests

def get_discovery_url():
    # The Google Health (Health Connect) REST API discovery URL
    # Historically it's often found via the main discovery service
    return "https://health.googleapis.com/$discovery/rest?version=v4"

def main():
    url = get_discovery_url()
    print(f"Fetching discovery document from: {url}")
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        
        # Save to the specific location
        target_path = "src/ghealthme/health_api_discovery_rest.json"
        
        # Ensure directory exists (though we know it does)
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        
        with open(target_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
            
        print(f"Successfully updated {target_path}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()
