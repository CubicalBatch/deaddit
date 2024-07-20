import json
import requests
import sys

# Set the API endpoints
USER_API_ENDPOINT = "http://localhost:5000/api/ingest/user"
SUBDEADDIT_API_ENDPOINT = "http://localhost:5000/api/ingest"

# Set the paths to your JSON files
USERS_JSON_FILE = "users.json"
SUBDEADDITS_JSON_FILE = "subdeaddits_base.json"

def ingest_users(json_file):
    # Read the JSON file
    try:
        with open(json_file, 'r') as file:
            data = json.load(file)
    except FileNotFoundError:
        print(f"Error: JSON file '{json_file}' not found.")
        return
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in file '{json_file}'.")
        return

    # Process each user
    for user in data.get('users', []):
        # Send POST request to the API
        try:
            response = requests.post(USER_API_ENDPOINT, json=user)
            # response.raise_for_status()  # Raise an exception for bad status codes
            
            # Check the response
            result = response.json()
            if result.get('message') == "User created successfully":
                print(f"User '{user['username']}' ingested successfully.")
            else:
                print(f"Error ingesting user '{user['username']}': {result.get('error', 'Unknown error')}")
        except requests.RequestException as e:
            print(f"Error ingesting user '{user['username']}': {str(e)}")

    print("User ingestion process completed.")

def ingest_subdeaddits(json_file):
    # Read the JSON file
    try:
        with open(json_file, 'r') as file:
            data = json.load(file)
    except FileNotFoundError:
        print(f"Error: JSON file '{json_file}' not found.")
        return
    except json.JSONDecodeError:
        print(f"Error: Invalid JSON in file '{json_file}'.")
        return

    # Send POST request to the API
    try:
        response = requests.post(SUBDEADDIT_API_ENDPOINT, json=data)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        # Check the response
        result = response.json()
        if result.get('message') == "Posts and comments created successfully":
            print("Subdeaddits ingested successfully.")
            for item in result.get('added', []):
                print(f"- {item}")
        else:
            print(f"Error ingesting subdeaddits: {result.get('error', 'Unknown error')}")
    except requests.RequestException as e:
        print(f"Error ingesting subdeaddits: {str(e)}")

    print("Subdeaddit ingestion process completed.")

if __name__ == "__main__":
    print("Starting subdeaddit ingestion...")
    ingest_subdeaddits(SUBDEADDITS_JSON_FILE)
    print("\nStarting user ingestion...")
    ingest_users(USERS_JSON_FILE)