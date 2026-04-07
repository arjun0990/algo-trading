
from flask import Flask, request
import threading
import time

app = Flask(__name__)

# Shared command state

last_command = None
last_time = 0

SECRET = "1234"   # change this later

def set_command(cmd):
 global last_command, last_time
 last_command = cmd
 last_time = time.time()
 print(f"🔥 COMMAND RECEIVED FROM WEB: {cmd}")

def get_command():
 global last_command
 return last_command
 
def clear_command():
    global last_command
    last_command = None

@app.route("/")
def home():
 return """ <h2>ALGO CONTROL</h2>
	<button onclick="send('CE')">BUY CE</button><br><br>
	<button onclick="send('PE')">BUY PE</button><br><br>

	<button onclick="send('EXIT')">EXIT</button><br><br>
	<button onclick="send('END')">END SESSION</button><br><br>

	<button onclick="send('GTT_ON')">GTT ON</button>
	<button onclick="send('GTT_OFF')">GTT OFF</button><br><br>

	<button onclick="send('AUTO_PAUSE')">AUTO PAUSE</button>
	<button onclick="send('AUTO_RESUME')">AUTO RESUME</button><br><br>

	<button onclick="send('TGT_UP')">TARGET +</button>
	<button onclick="send('TGT_DOWN')">TARGET -</button><br><br>

	<button onclick="send('SL_UP')">SL +</button>
	<button onclick="send('SL_DOWN')">SL -</button><br><br>

	<button onclick="send('LOTS_UP')">LOTS +</button>
	<button onclick="send('LOTS_DOWN')">LOTS -</button>

	<script>
	function send(cmd){
    	fetch('/cmd?key=1234&c=' + cmd)
	}
	</script>
	"""


@app.route("/cmd")
def cmd():
 if request.args.get("key") != SECRET:
  return "Unauthorized"


 c = request.args.get("c")
 set_command(c)
 return "OK"


def run_server():
 app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)

if __name__ == "__main__":
    run_server()

