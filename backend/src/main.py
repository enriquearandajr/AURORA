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
import sys
# time for spotify loop
import time

import torch

# get current path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

# path to DB logo
IMAGE_PATH = os.path.abspath(os.path.join(CURRENT_DIR,'../../frontend/media/db-black-tiny.jpg'))

TOOLS_PATH = os.path.abspath(os.path.join(CURRENT_DIR,'../tools'))
sys.path.append(TOOLS_PATH)

from mrs_utils import recommend_song, get_uri

# import secrets
secrets_path = os.path.abspath(os.path.join(CURRENT_DIR, '../../.env.dev')) # to get the env dev file
secrets = dotenv_values(secrets_path)

# list of permissions needed to access user information
SCOPE_LIST=['user-read-currently-playing','user-modify-playback-state','user-read-playback-state', 'user-read-private', 'playlist-modify-public', 'playlist-modify-private', 'ugc-image-upload']

# access spotify api using credentials (fallback for local standalone run)
sp = None
try:
    if secrets.get('SPOTIFY_CLIENT_SECRET'):
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
            client_id=secrets.get('SPOTIFY_CLIENT_ID'),
            client_secret=secrets.get('SPOTIFY_CLIENT_SECRET'), 
            redirect_uri=secrets.get('SPOTIFY_REDIRECT_URI'),
            scope=SCOPE_LIST
        ))
except Exception as e:
    print(f"Warning: Could not initialize default SpotifyOAuth client: {e}")

# access Gemini API client
client = genai.Client(api_key=secrets['GEMINI_API_KEY'])

# DEPRECATED
def prompt_user_state(state):
    return f"User is feeling {state} to the current song."

# get song uri function to add song into queue (DEPRECATED)
def get_song_uri(sp_client, song_title, song_artist):
    query = "track: "+song_title+" artist: " + song_artist
    result = sp_client.search(q=query, limit=1, type="track", market='from_token')
    tracks = result.get('tracks', {}).get('items', [])
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

# run song suggestion prompt using Gemini
def run_prompt(prompt):
    interaction = client.interactions.create(
        model = 'gemini-3-flash',
        input = prompt
    )
    return interaction.output_text

# returns playlist id
def spotify_playlist_creation(sp_client):
    user_id = sp_client.current_user()["id"]
    playlist_name = "Your Stream"
    playlist_description = "Brought to you by the Decoded Brain at UC San Diego. Your Stream will be saved to this playlist as you listen"

    new_playlist = sp_client.user_playlist_create(
        user=user_id,
        name=playlist_name,
        public=False,
        description=playlist_description
    )
    return new_playlist["id"]

def run_stream(session_id="local_user", access_token=None, refresh_token=None, status_callback=None, stop_event=None):
    # Setup session-specific spotipy client
    from spotipy.oauth2 import SpotifyPKCE
    from spotipy.cache_handler import CacheFileHandler

    if access_token:
        # Create a unique cache file path for this session
        cache_path = os.path.abspath(os.path.join(CURRENT_DIR, f'../../.cache-{session_id}'))
        auth_manager = SpotifyPKCE(
            client_id=secrets.get('SPOTIFY_CLIENT_ID'),
            redirect_uri=secrets.get('SPOTIFY_REDIRECT_URI'),
            scope=SCOPE_LIST,
            cache_handler=CacheFileHandler(cache_path=cache_path)
        )
        token_info = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_in": 3600,
            "expires_at": int(time.time()) + 3600,
            "scope": ' '.join(SCOPE_LIST)
        }
        auth_manager.cache_handler.save_token_to_cache(token_info)
        sp_client = spotipy.Spotify(auth_manager=auth_manager)
    else:
        if sp is None:
            raise Exception("Spotify client not initialized. Please connect via PKCE or configure SPOTIFY_CLIENT_SECRET.")
        sp_client = sp

    # session-local variables for thread safety
    count = 15
    recently_played = []
    time_left = 0
    stream_id = ""
    stream_is_playing = True
    queued_for_track_id = None 
    arousal = 50
    pleasure = 75

    if status_callback:
        status_callback({
            "status":"initializing",
            "message":"Initializing Spotify playlist...",
            "recently_played": recently_played,
            "current_song":None,
            "playlist_id":None
        })
    
    first_song_uri=None
    song_to_add = []

    # get currently playing song as first song
    try:
        current_playing = sp_client.current_user_playing_track()
        if current_playing and current_playing.get('is_playing'):
            current_track_name = current_playing['item']['name']
            current_track_artist = current_playing['item']['artists'][0]['name']
            first_song_uri = get_uri(current_track_name)

            if first_song_uri:
                song_to_add.append(first_song_uri)
                recently_played.append(current_track_name+ " - " + current_track_artist)
    except Exception as e:
        print(f"Error checking currently playing track: {e}")

    try:
        stream_id = spotify_playlist_creation(sp_client)
        stream_name = "Your Stream #" + stream_id[-4:] # change title to Your Stream #aaaa
        sp_client.playlist_change_details(playlist_id=stream_id, name=stream_name)
        if song_to_add:
            sp_client.playlist_add_items(playlist_id=stream_id, items=song_to_add)

        # upload cover image
        if os.path.exists(IMAGE_PATH):
            with open(IMAGE_PATH, "rb") as image_file:
                encoded_string = base64.b64encode(image_file.read()).decode("utf-8")
            
            try: 
                sp_client.playlist_upload_cover_image(stream_id, encoded_string)
                print("Cover art uploaded successfully")
            except Exception as e:
                print(f"An error occurred during cover art upload: {e}")
        else:
            print("Cover art image not found, skipping upload")
    except Exception as e:
        print(f"Error setting up Spotify playlist: {e}")
        if status_callback:
            status_callback({
                "status":"error",
                "message": f"Error setting up Spotify playlist: {e}",
                "recently_played": recently_played,
                "current_song": None,
                "playlist_id": None
            })
        return
    
    if status_callback:
        current_song_name = recently_played[0] if recently_played else None
        status_callback({
            "status":"running",
            "message":"Your Stream has started! Listening on Spotify...",
            "recently_played":recently_played,
            "current_song": current_song_name,
            "playlist_id":stream_id
        })

        # Main Polling Loop 
        while count > 0 and stream_is_playing:
            if stop_event and stop_event.is_set():
                print("Stopping Stream...")
                break
            
            try:
                current_track = sp_client.current_user_playing_track()
                if current_track and current_track.get('is_playing'):
                    current_track_name = current_track['item']['name']
                    current_track_artist = current_track['item']['artists'][0]['name']
                    current_track_id = current_track['item']['id']
                    current_song_name = current_track_name + " - " + current_track_artist # title + artist
                    time_left = calculate_time_left(current_track)
                    # update status callback on currently playing song
                    if status_callback:
                        status_callback({
                            "status":"running",
                            "message":f"Currently playing: {current_song_name}",
                            "recently_played":recently_played,
                            "current_song":current_song_name,
                            "playlist_id":stream_id
                        })
                    
                    # Check if we should search and queue a new song
                    if 0 < time_left <= 25 and queued_for_track_id != current_track_id:
                        print(f"Suggesting new song...")
                        
                        if status_callback:
                            status_callback({
                                "status":"running",
                                "message":f"Suggesting new song...",
                                "recently_played":recently_played,
                                "current_song":current_song_name,
                                "playlist_id":stream_id   
                            })
                        
                        # mark next track ID as queued so it's no longer triggered again
                        queued_for_track_id = current_track_id
                        if current_song_name not in recently_played:
                            recently_played.append(current_song_name)
                            
                        # Recommender System Call
                        rec_df, rec_queue = recommend_song(current_track_name, current_track_artist, arousal, pleasure, recently_played, 10)
                        
                        if rec_queue:
                            upcoming_song_uri = rec_queue[0]
                            new_song_title = rec_df.iloc[0]['name']
                            new_song_artist = rec_df.iloc[0]['artist']
                            recommended_song_name = f"{new_song_title} - {new_song_artist}"
                            
                            sp_client.add_to_queue(uri=upcoming_song_uri)
                            song_to_add.clear()
                            song_to_add.append(upcoming_song_uri)
                            sp_client.playlist_add_items(stream_id, song_to_add)
                            
                            recently_played.append(recommended_song_name)
                            print(f"Added {recommended_song_name} to queue!")
                            count -= 1
                            
                            if status_callback:
                                status_callback({
                                    "status":"running",
                                    "message":f"Added recommended song: {recommended_song_name}",
                                    "recently_played": recently_played,
                                    "current_song":current_song_name,
                                    "playlist_id":stream_id
                                })
                        else:
                            print(f"Could not find a playable song on Spotify for recommendation.")
                            if status_callback:
                                status_callback({
                                    "status":"running",
                                    "message":"Could not find a playable song on Spotify for recommendation",
                                    "recently_played":recently_played,
                                    "current_song":current_song_name,
                                    "playlist_id":stream_id
                                })
                # if spotify is active but no track is playing
                else:
                    if status_callback:
                        status_callback({
                            "status":"running",
                            "message":"Spotify is active but no track is currently playing or it is paused",
                            "recently_played":recently_played,
                            "current_song": None,
                            "playlist_id": stream_id
                        })
            except Exception as e:
                print(f"Error in Stream loop iteration: {e}")
                if status_callback:
                    status_callback({
                        "status":"running",
                        "message": f"Error checking Spotify {e}",
                        "recently_played":recently_played,
                        "current_song":None,
                        "playlist_id":stream_id
                    })
            time.sleep(1)
        
        # Summary section
        if recently_played:
            try:
                if status_callback:
                    status_callback({
                        "status":"completing",
                        "message":"Generating custom title...",
                        "recently_played": recently_played,
                        "current_song":None,
                        "playlist_id":stream_id
                    })
                # adds custom title to playlist 
                new_playlist_title = run_prompt(f"View the songs listed in {recently_played} and write a title for that playlist. Output ONLY the title name, nothing else.")
                sp_client.playlist_change_details(playlist_id=stream_id, name=new_playlist_title)

            except Exception as e:
                print(f"Error updating playlist title: {e}")
        print("="*40)
        print("List of songs played during your Stream: \n")
        for i in range(len(recently_played)):
            print(f"{i+1}. {recently_played[i]}")

        if status_callback:
            status_callback({
                "status":"stopped",
                "message":"Stream finished",
                "recently_played":recently_played,
                "current_song": None,
                "playlist_id":stream_id
            })

# Protect direct execution (running main on its own still works)
if __name__ == "__main__":
    run_stream()
