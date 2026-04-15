from flask import Flask, request, jsonify
import threading
import time
import os
import json

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CMD_FILE = os.path.join(BASE_DIR, "command.txt")
STATUS_FILE = os.path.join(BASE_DIR, "status.json")

app = Flask(__name__)

SECRET = "1234"   # change this later


# -------------------------------
# COMMAND WRITE
# -------------------------------
def set_command(cmd):
    with open(CMD_FILE, "w") as f:
        f.write(cmd)

    print(f"🔥 COMMAND WRITTEN TO FILE: {cmd}")


# -------------------------------
# STATUS API (NEW)
# -------------------------------
@app.route("/status")
def status():
    try:
        with open(STATUS_FILE, "r") as f:
            data = json.load(f)
        return jsonify(data)
    except:
        return jsonify({
            "instrument": None,
            "qty": 0,
            "pnl": 0,
            "entry_price": 0
        })


# -------------------------------
# MAIN UI
# -------------------------------
@app.route("/")
def home():
    return """
    <html>
    <head>
        <title>Algo Control</title>

        <style>
            body {
                font-family: Arial, sans-serif;
                background: #fffef6;
                color: white;
                text-align: center;
            }

            h2 {
                margin-top: 20px;
            }

            .status-box {
                background: #111827;
                padding: 20px;
                margin: 20px auto;
                width: 350px;
                border-radius: 10px;
                font-size: 18px;
                text-align: left;
            }

            .container {
                display: grid;
                grid-template-columns: repeat(2, 1fr);
                gap: 20px;
                max-width: 500px;
                margin: 30px auto;
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

            button:hover {
                background: #ff7f50;
                transform: scale(1.05);
            }

            button:active {
                background: #ff5733;
                transform: scale(0.95);
            }
        </style>
    </head>

    <body>

        <h2>⚡ ALGO CONTROL</h2>

        <!-- 🔥 STATUS BOX -->
        <div class="status-box">
            <div>Instrument: <span id="instrument">-</span></div>
            <div>Qty: <span id="qty">0</span></div>
            <div>Entry: <span id="entry">0</span></div>
            <div>PnL: <span id="pnl">0</span></div>
            <div>LTP: <span id="ltp">0</span></div>
        </div>

        <!-- 🔘 BUTTONS -->
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

            // click flash
            btn.style.background = "#ff5733";

            fetch('/cmd?key=1234&c=' + cmd)
                .then(res => res.text())
                .then(data => console.log(data))
                .catch(err => console.error(err));

            setTimeout(() => {
                btn.style.background = "coral";
            }, 200);
        }

        // 🔥 FETCH STATUS EVERY SECOND
        function fetchStatus(){
            fetch('/status')
            .then(res => res.json())
            .then(data => {

                document.getElementById("instrument").innerText = data.instrument || "-";
                document.getElementById("qty").innerText = data.qty || 0;
                document.getElementById("entry").innerText = data.entry_price || 0;
                document.getElementById("ltp").innerText = data.ltp || 0;

                let pnlEl = document.getElementById("pnl");
                pnlEl.innerText = data.pnl || 0;

                if(data.pnl > 0){
                    pnlEl.style.color = "lightgreen";
                } else if(data.pnl < 0){
                    pnlEl.style.color = "red";
                } else {
                    pnlEl.style.color = "white";
                }
                
                let ltpEl = document.getElementById("ltp");

                if(data.ltp > data.entry_price){
                    ltpEl.style.color = "lightgreen";
                } else if(data.ltp < data.entry_price){
                    ltpEl.style.color = "red";
                } else {
                    ltpEl.style.color = "white";
                }
            });
        }

        setInterval(fetchStatus, 1000);
        </script>

    </body>
    </html>
    """


# -------------------------------
# COMMAND ENDPOINT
# -------------------------------
@app.route("/cmd")
def cmd():
    if request.args.get("key") != SECRET:
        return "Unauthorized"

    c = request.args.get("c")
    set_command(c)
    return "OK"


# -------------------------------
# RUN SERVER
# -------------------------------
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