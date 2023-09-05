import requests

GIPHY_API_URL = "https://api.giphy.com/v1/gifs/random"
API_KEY = "0UTRbFtkMxAplrohufYco5IY74U8hOes"  # One I found online, couldn't get a login into Giphy

def get_random_gif():
    response = requests.get(GIPHY_API_URL, params={"api_key": API_KEY}, timeout=60)
    if response.status_code == 200:
        gif_url = response.json()["data"]["url"]
        return gif_url
    else:
        print(f"Failed to fetch GIF. Status code: {response.status_code}")
        return None