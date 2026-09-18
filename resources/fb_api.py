"""API function to get list of last active clients that will be used for home activiti scrape
"""
import requests
import base64
import json

from resources.variables import (
    FB_API_KEY,
    FB_ENDPOINT
)


def get_people_to_check():
    if not FB_API_KEY:
        raise RuntimeError(
            "FB_API_KEY is not set. Add it to the .env file or export it first."
        )

    api_bytes = FB_API_KEY.encode("ascii")
    creds64 = base64.b64encode(api_bytes)
    creds_string = creds64.decode("ascii")

    headers = {"accept": "application/json",
            "authorization": f"Basic {creds_string}"
            }

    # peeps_endpoint = "https://api.followupboss.com/v1/people?sort=lastActivity&limit=100&offset=0&smartListId=128&includeTrash=false&includeUnclaimed=True"
    response = requests.get(FB_ENDPOINT, headers=headers)
    to_format = json.loads(response.content)

    clients = []

    for client in to_format['people']:
        email = (client.get('emails') or [{}])[0].get('value', '')
        clients.append({'id':client['id'],'name':client['name'],'email':email,'viewed_homes':[]})

    return clients
