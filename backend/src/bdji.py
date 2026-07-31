## Imports

# for security importing keys
from dotenv import dotenv_values
# Spotify API for Python
import spotipy
# Login for Spotify API
from spotipy.oauth2 import SpotifyOAuth
# Gemini API for song recommendation
from google import genai
# turn jpg image to base 64 bytes
import base64
# os for filepaths
import os
import time



# get current path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# import secrets
secrets_path = os.path.abspath(os.path.join(CURRENT_DIR, '../../.env.dev')) # to get the env dev file
secrets = dotenv_values(secrets_path)


# list of permissions needed to access user information
SCOPE_LIST=['user-read-currently-playing','user-modify-playback-state','user-read-playback-state', 'user-read-private', 'playlist-modify-public', 'playlist-modify-private', 'ugc-image-upload']

# path to DB logo
IMAGE_PATH = os.path.abspath(os.path.join(CURRENT_DIR,'../../frontend/media/db-black-tiny.jpg'))

# access spotify api using credentials
sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=secrets['SPOTIFY_CLIENT_ID'],
client_secret=secrets['SPOTIFY_CLIENT_SECRET'], redirect_uri=secrets['SPOTIFY_REDIRECT_URI'],scope=SCOPE_LIST))

# counter for how many songs to be added to queue
# subtracts by 1 after every song
count=15
# list of recently played songs for Gemini to avoid
recently_played=[]

# time left variable initialization
time_left = 0


def prompt_user_state(state):
    return f"User is feeling {state} to the current song."

# get song uri function to add that song into queue
def get_song_uri(song_title, song_artist):
    query = "track: "+ song_title + " artist: " + song_artist
    # Agent suggested to add market variable to prevent unplayable tracks from being added
    result = sp.search(q=query, limit=1, type="track", market='from_token')
    tracks=result.get('tracks', {}).get('items', [])
    if tracks: 
        song_uri = tracks[0]['uri']
        return song_uri

# function to calculate time left of song in seconds
def calculate_time_left(track):
    duration_ms = track['item']['duration_ms']
    progress_ms = track['progress_ms']
    time_left_ms = duration_ms - progress_ms
    time_left = int(time_left_ms/1000)
    return time_left

# run song suggestion prompt
def run_prompt(prompt):
    interaction = client.interactions.create(
        model = 'gemini-3.6-flash', # switched from gemini-3.5-flash, will try gemini-2.5-flash for higher ceiling
        input = prompt
    )
    return interaction.output_text

# find songs that match similar tempo and follows Camelot Wheel
camelot_mode = False
camelot_prompt = ""
if camelot_mode:
    camelot_prompt = "When searching for song, follow the Camelot wheel and tempo of current song for next song. "


# returns playlist id
def spotify_playlist_creation():
    user_id = sp.current_user()["id"]
    playlist_name = "Your Stream"
    playlist_description = "Brought to you by the Decoded Brain at UC San Diego. Your Stream will be saved to this playlist as you listen"

    new_playlist = sp.user_playlist_create(
        user=user_id,
        name = playlist_name,
        public=False,
        description=playlist_description
    )
    return new_playlist["id"]

first_song_uri= None
song_to_add = []

if sp.current_user_playing_track() and sp.current_user_playing_track().get('is_playing'):
    first_song_uri = get_song_uri(sp.current_user_playing_track()['item']['name'], sp.current_user_playing_track()['item']['artists'][0]['name'])
    song_to_add.append(first_song_uri)

stream_id = spotify_playlist_creation()
stream_name = "Your Stream #" + stream_id[-4:]
sp.playlist_change_details(playlist_id=stream_id, name=stream_name) # change title to Your Stream #abcd
sp.playlist_add_items(playlist_id=stream_id, items=song_to_add)
# upload cover image
with open(IMAGE_PATH, "rb") as image_file:
    # read raw bytes and convert as Base64 bytes, then decode to string
    encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
try:
    sp.playlist_upload_cover_image(stream_id, encoded_string)
    print("Cover art uploaded successful.")
except Exception as e:
    print(f"An error occurred: {e}")


# run mode
# runs while count is still above 0
# runs for how many times specified by the user
# currently set manually, but ideally goal is to play indefinitely until user stops stream
while count > 0:
    current_track=sp.current_user_playing_track()
    if current_track and current_track.get('is_playing'):
        current_track_name=current_track['item']['name']
        current_track_artist=current_track['item']['artists'][0]['name']
    
        time_left = calculate_time_left(current_track)
    time.sleep(1)
    # when time left reaches 25 seconds, search for new song to add to queue based on user's mood
    if time_left == 25:
        recently_played.append(current_track_name + " by " + current_track_artist)
        client=genai.Client(api_key=secrets['GEMINI_API_KEY'])

        # user state to be injected into prompt
        state_prompt = prompt_user_state('pleasure')

        # prompt for Gemini API to find similar songs
        prompt = f"{state_prompt} Find a song that matches user state and is similar to {current_track_name} by {current_track_artist}.{camelot_prompt}**Important**: Reply with only the song name and artist of the song in this format: Title: <insert title>\n Artist: <insert artist name>. Verify the song is not part of this list, if it is try again: {recently_played}."

        output = run_prompt(prompt)
        
        # Agent suggest to add strip at the end to clean the string
        new_song_artist = output.split(':')[-1].strip()
        new_song_title = output.split(':')[1].split('Artist')[0].strip()
        
        # Agent suggested adding conditions to make sure we're not adding null values to queue 
        upcoming_song_uri = get_song_uri(new_song_title, new_song_artist)
        if upcoming_song_uri:
            sp.add_to_queue(uri=upcoming_song_uri)
            song_to_add.clear()
            song_to_add.append(upcoming_song_uri)
            sp.playlist_add_items(stream_id, song_to_add)
            print(f"Added {new_song_title} by {new_song_artist} to queue!")
            count-=1
        else: 
            print(f"Could not find a playable song on Spotify for: {new_song_title} by {new_song_artist}")

# SUMMARY SECTION

new_playlist_title = run_prompt(f"View the songs listed in {recently_played} and write a title for that playlist. Output ONLY the title name, nothing else.")
sp.playlist_change_details(playlist_id=stream_id, name=new_playlist_title) # change title to AI-generated title based on songs


print("=" * 40)
print("List of songs played during your Stream: \n")
for i in range(len(recently_played)):
    print(f"{i+1}. {recently_played[i]}")
