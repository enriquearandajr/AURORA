import json # for output
import threading 
import time
import urllib.parse
import os
from http.server import HTTPServer, BaseHTTPRequestHandler # for communication with website
#Python's BaseHTTPRequestHandler processes incoming HTTP requests and dispatches them to specific handler methods
from main import run_stream, secrets # run stream function and secrets that i developed in main

# Paths relative to this file
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SITE_HTML_PATH = os.path.abspath(os.path.join(BASE_DIR, '../../frontend/app/site.html'))
MEDIA_DIR = os.path.abspath(os.path.join(BASE_DIR, '../../frontend/media'))

# sessions dictionary to support multiple users running their streams concurrently
# format: { session_id: { "status": ..., "message": ..., "recently_played": ..., "current_song": ..., "playlist_id": ..., "stop_event": threading.Event(), "stream_thread": threading.Thread(), "last_active": float } }
sessions = {}
sessions_lock = threading.Lock()

def get_session(session_id):
    with sessions_lock:
        if session_id not in sessions:
            sessions[session_id] = {
                "status": "stopped",
                "message": "Server is ready...",
                "recently_played": [],
                "current_song": None,
                "playlist_id": None,
                "stop_event": threading.Event(),
                "stream_thread": None,
                "last_active": time.time()
            }
        else:
            sessions[session_id]["last_active"] = time.time()
        return sessions[session_id]

def update_session_state(session_id, new_state):
    with sessions_lock:
        if session_id in sessions:
            for k, v in new_state.items():
                if k not in ["stop_event", "stream_thread"]:
                    sessions[session_id][k] = v
            sessions[session_id]["last_active"] = time.time()

def worker(session_id, access_token, refresh_token, session_stop_event):
    # worker function for DJ background thread
    try:
        def callback(new_state):
            update_session_state(session_id, new_state)

        run_stream(
            session_id=session_id,
            access_token=access_token,
            refresh_token=refresh_token,
            status_callback=callback,
            stop_event=session_stop_event
        )
    except Exception as e:
        with sessions_lock:
            if session_id in sessions:
                sessions[session_id]["status"] = "error"
                sessions[session_id]["message"] = f"Critical background thread error: {e}"

class DJBrain(BaseHTTPRequestHandler): 
    def end_headers(self):
        #enable CORS ( Cross-Origin Resource Sharing ) for frontend
        self.send_header('Access-Control-Allow-Origin', '*') # let them know it's okay to load data 
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        super().end_headers()

    # sends pre-flight request before POST to verify permissions
    def do_OPTIONS(self):
        self.send_response(200) # Send 200=OKAY to HTTPS
        self.end_headers()
    
    # retrieves data & serves static pages
    def do_GET(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        if path == '/' or path == '/index.html' or path == '/site.html':
            try:
                with open(SITE_HTML_PATH, 'rb') as f:
                    content = f.read()
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(content)
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(f"Error loading UI: {e}".encode('utf-8'))
        elif path.startswith('/media/'):
            filename = path[7:] # strip '/media/'
            filename = os.path.basename(filename) # prevent directory traversal
            file_path = os.path.join(MEDIA_DIR, filename)
            if os.path.exists(file_path):
                try:
                    with open(file_path, 'rb') as f:
                        content = f.read()
                    self.send_response(200)
                    if file_path.endswith('.jpg') or file_path.endswith('.jpeg'):
                        self.send_header('Content-Type', 'image/jpeg')
                    elif file_path.endswith('.png'):
                        self.send_header('Content-Type', 'image/png')
                    else:
                        self.send_header('Content-Type', 'application/octet-stream')
                    self.end_headers()
                    self.wfile.write(content)
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(b"Error reading file")
            else:
                self.send_response(404)
                self.end_headers()
                self.wfile.write(b"Media Not Found")
        elif path == '/api/config':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            config_data = {
                "spotify_client_id": secrets.get('SPOTIFY_CLIENT_ID'),
                "spotify_redirect_uri": secrets.get('SPOTIFY_REDIRECT_URI')
            }
            self.wfile.write(json.dumps(config_data).encode('utf-8'))
        elif path == '/api/status':
            query = urllib.parse.parse_qs(parsed_url.query)
            session_id = query.get('session_id', [None])[0]
            if not session_id:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing session_id parameter"}).encode('utf-8'))
                return

            session = get_session(session_id)
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            serializable_state = {
                "status": session["status"],
                "message": session["message"],
                "recently_played": session["recently_played"],
                "current_song": session["current_song"],
                "playlist_id": session["playlist_id"]
            }
            self.wfile.write(json.dumps(serializable_state).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")
            
    # start and stop controls (expect JSON bodies with session_id)
    def do_POST(self):
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path

        content_length = int(self.headers.get('Content-Length', 0))
        body_data = {}
        if content_length > 0:
            try:
                body_data = json.loads(self.rfile.read(content_length).decode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b"Invalid JSON body")
                return

        if path == '/api/start':
            session_id = body_data.get("session_id")
            access_token = body_data.get("access_token")
            refresh_token = body_data.get("refresh_token")

            if not session_id or not access_token:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing session_id or access_token"}).encode('utf-8'))
                return

            session = get_session(session_id)
            with sessions_lock:
                #Don't allow starting if initializing, running or completing
                if session["status"] in ["initializing", "running", "completing"]:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error":"Stream is already running for this session"}).encode('utf-8'))
                    return
                
                # Allow starting if stopped, error, or complete
                session["stop_event"].clear()
                session["status"] = "initializing"
                session["message"] = "Initializing Stream..."
                session["recently_played"] = []
                session['current_song'] = None
                session['playlist_id'] = None

                # spawn background thread for this specific user
                t = threading.Thread(
                    target=worker, 
                    args=(session_id, access_token, refresh_token, session["stop_event"]), 
                    daemon=True
                )
                session["stream_thread"] = t
                t.start()

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            serializable_state = {
                "status": session["status"],
                "message": session["message"],
                "recently_played": session["recently_played"],
                "current_song": session["current_song"],
                "playlist_id": session["playlist_id"]
            }
            self.wfile.write(json.dumps(serializable_state).encode('utf-8'))

        elif path == '/api/stop':
            session_id = body_data.get("session_id")
            if not session_id:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": "Missing session_id"}).encode('utf-8'))
                return

            session = get_session(session_id)
            with sessions_lock:
                if session["status"] not in ["initializing", "running", "completing"]:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error":"Stream is not running for this session"}).encode('utf-8'))
                    return
                
                session["stop_event"].set()
                session["message"] = "Requesting Stream to stop..."

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            
            serializable_state = {
                "status": session["status"],
                "message": session["message"],
                "recently_played": session["recently_played"],
                "current_song": session["current_song"],
                "playlist_id": session["playlist_id"]
            }
            self.wfile.write(json.dumps(serializable_state).encode('utf-8'))

        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"Not Found")

# Starts server socket, sets up TCP socket to port 5005
def run(server_class=HTTPServer, handler_class=DJBrain, port=5005): # port 5005 to avoid Mac's 5000 AirPlay port
    server_address = ('', port)
    httpd = server_class(server_address, handler_class)
    print(f"Starting Brain DJ Interface on port {port}...")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server.")
        httpd.server_close()

if __name__ == '__main__':
    run()
