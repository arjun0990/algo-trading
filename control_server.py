
from flask import Flask, request
import threading
import time
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CMD_FILE = os.path.join(BASE_DIR, "command.txt")
app = Flask(__name__)

# Shared command state


SECRET = "1234"   # change this later


def set_command(cmd):
    with open(CMD_FILE, "w") as f:
        f.write(cmd)

    print(f"🔥 COMMAND WRITTEN TO FILE: {cmd}")

@app.route("/")
def home():
 return """
    <html>
    <head>
        <title>Algo Control</title>

        <style>
            body {
                font-family: Arial, sans-serif;
                background: #0f172a;
                color: white;
                text-align: center;
            }

            h2 {
                margin-top: 20px;
            }

            .container {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 20px;
                max-width: 500px;
                margin: 40px auto;
            }

            button {
                padding: 20px;
                font-size: 18px;
                border: none;
                border-radius: 10px;
                cursor: pointer;
                font-weight: bold;

                background: coral;
                color: white;

                transition: all 0.15s ease;
            }

            /* 🌟 HOVER EFFECT */
            button:hover {
                background: #ff7f50;   /* slightly brighter coral */
                transform: scale(1.05);
            }

            /* 🔴 CLICK EFFECT */
            button:active {
                background: #ff5733;
                transform: scale(0.95);
            }
                padding: 20px;
                font-size: 18px;
                border: none;
                border-radius: 10px;
                cursor: pointer;
                font-weight: bold;

                background: coral;
                color: white;

                transition: all 0.15s ease;
            }

            button:active {
                background: #ff5733;
                transform: scale(0.95);
            }
        </style>
    </head>

    <body>

        <h2>⚡ ALGO CONTROL</h2>

        <div class="container">

            <button onclick="send(this,'CE')">BUY CE</button>
            <button onclick="send(this,'PE')">BUY PE</button>

            <button onclick="send(this,'EXIT')">EXIT</button>
            <button onclick="send(this,'END')">END SESSION</button>

            <button onclick="send(this,'GTT_ON')">GTT ON</button>
            <button onclick="send(this,'GTT_OFF')">GTT OFF</button>

            <button onclick="send(this,'AUTO_PAUSE')">AUTO PAUSE</button>
            <button onclick="send(this,'AUTO_RESUME')">AUTO RESUME</button>

            <button onclick="send(this,'TGT_UP')">TARGET +</button>
            <button onclick="send(this,'TGT_DOWN')">TARGET -</button>

            <button onclick="send(this,'SL_UP')">SL +</button>
            <button onclick="send(this,'SL_DOWN')">SL -</button>

            <button onclick="send(this,'LOTS_UP')">LOTS +</button>
            <button onclick="send(this,'LOTS_DOWN')">LOTS -</button>

        </div>

        <script>
        function send(btn, cmd){

            // temporary color flash
            btn.style.background = "#ff5733";

            fetch('/cmd?key=1234&c=' + cmd)
                .then(res => res.text())
                .then(data => console.log(data))
                .catch(err => console.error(err));

            // revert back
            setTimeout(() => {
                btn.style.background = "coral";
            }, 200);
        }
        </script>

    </body>
    </html>
    """

@app.route("/cmd")
def cmd():
 if request.args.get("key") != SECRET:
  return "Unauthorized"


 c = request.args.get("c")
 set_command(c)
 return "OK"

def run_server():
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False,
        use_reloader=False,
        threaded=True
    )


if __name__ == "__main__":
    run_server()

