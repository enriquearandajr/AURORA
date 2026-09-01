import json # for output
import threading 
from http.server import HTTPServer, BaseHTTPRequestHandler # for communication with website
#Python's BaseHTTPRequestHandler processes incoming HTTP requests and dispatches them to specific handler methods
from main import run_stream # run stream function that i developed in main

# shared state across web server and DJ background thread
state = {
    "status": "stopped", # could be either stopped, initializing, running, completing, or error
    "message": "Server is ready...",
    "recently_played": [],
    "current_song": None,
    "playlist_id": None,
    "arousal": 50
}

state_lock = threading.Lock()
stop_event = threading.Event()
stream_thread = None

def update_state(new_state):
    # Callback function passed to run_stream to update global server state
    with state_lock: # used for automatic resource management, safe, MUTEX
        state.update(new_state)

def worker():
    # worker function for DJ background thread
    try:
        # status callback refers to the code progress, views the updated state
        run_stream(status_callback=update_state, stop_event=stop_event)
    except Exception as e:
        with state_lock:
            # presents error and sets state to error
            state["status"] = "error"
            state["message"] = f"Critical background thread error: {e}"

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
    
    # retrieves data
    def do_GET(self):
        if self.path == '/api/status':
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            with state_lock:
                self.wfile.write(json.dumps(state).encode('utf-8')) # write state of server
        else:
            self.send_response(404) # error
            self.end_headers()
            self.wfile.write(b"Not Found") # b is for buffer
            
    # start and stop controls
    def do_POST(self):
        global stream_thread
        if self.path == '/api/start':
            with state_lock:
                #Don't allow starting if initializing, running or completing
                if state["status"] in ["initializing", "running", "completing"]:
                    self.send_response(400) # bad request, stream is already running
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error":"Stream is already running"}).encode('utf-8'))
                    return
                
                # Allow starting if stopped, error, or complete
                # Set up thread control and initial state
                stop_event.clear()
                state["status"] = "initializing"
                state["message"] = "Initializing Stream..."
                state["recently_played"] = []
                state['current_song'] = None
                state['playlist_id'] = None

                # spawns background thread
                stream_thread = threading.Thread(target=worker, daemon=True) # runs Stream quietly in the background
                stream_thread.start()

            self.send_response(200) # send the okay to start
            self.send_header('Content-Type', 'application/json')
            self.end_headers()

            with state_lock:
                self.wfile.write(json.dumps(state).encode('utf-8'))

        elif self.path == '/api/stop':
            with state_lock:
                # If Stream is not even Running then send error for wanting to stop
                if state["status"] not in ["initializing", "running", "completing"]:
                    self.send_response(400) # error
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"error":"Stream is not running"}).encode('utf-8'))
                    return
                
                # Signal stop 
                stop_event.set()
                state["message"] = "Requesting Stream to stop..."

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            with state_lock:
                self.wfile.write(json.dumps(state).encode('utf-8'))
        
        # Block to update arousal
        elif self.path == '/api/update_arousal':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                data = json.loads(post_data.decode('utf-8'))
                new_arousal = int(data.get('arousal',50))

                # update shared state and global main.arousal
                import main
                with state_lock:
                    main.arousal = new_arousal
                    state['arousal'] = new_arousal

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"success":True, "arousal":new_arousal}).encode('utf-8'))
            except Exception as e:
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))

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
        httpd.server_close() # dont close server until Keyboard Interrupt to shut it down!!!

if __name__ == '__main__':
    run()
