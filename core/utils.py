LOG_FILE = "trade_log.txt"

from datetime import datetime

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(msg)
    with open("log.txt", "a", encoding="utf-8") as f:
        f.write(f"[{ts}] {msg}\n")


def round_to_tick(price):
    return round(price * 20) / 20


def manual_exit_pressed():
    try:
        import msvcrt
        if msvcrt.kbhit():
            if msvcrt.getch().lower() == b'q':
                return True
    except:
        pass
    return False