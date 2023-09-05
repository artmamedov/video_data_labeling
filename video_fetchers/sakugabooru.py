import requests
from bs4 import BeautifulSoup

def get_random_sakugabooru_video():
    url = "https://www.sakugabooru.com/post/random"

    # Use a session to manage the redirects
    with requests.Session() as session:
        response = session.get(url)
        response.raise_for_status()  # Raise an error for bad responses
        
        soup = BeautifulSoup(response.content, 'html.parser')
        
        # Locate the video tag and extract the source
        video_tag = soup.find('video')
        if video_tag:
            video_src = video_tag.find('source').get('src')
            return video_src
        else:
            return None


if __name__ == "__main__":
    video_url = get_random_sakugabooru_video()

    if video_url:
        print(f"Video URL: {video_url}")
    else:
        print("Could not find video.")

