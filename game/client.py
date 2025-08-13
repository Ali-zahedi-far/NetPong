import socket, threading, time
from .common import send_json_line, recv_json_lines, Atomic

class GameClient:
    """
    Lightweight client:
      - Connects to host
      - Sends input states
      - Receives state snapshots
    """
    def __init__(self, host="127.0.0.1", port=50007):
        self.host = host
        self.port = port
        self.sock = None
        self._recv_thread = None
        self._stop = threading.Event()
        self.state = Atomic(None)      # latest state from server
        self.game_over = Atomic(None)  # {"winner":..., "score":...}

    def connect(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.connect((self.host, self.port))
        send_json_line(self.sock, {"type":"hello","who":"client"})
        self._recv_thread = threading.Thread(target=self._recv_loop, name="ClientRecv", daemon=True)
        self._recv_thread.start()

    def _recv_loop(self):
        try:
            for msg in recv_json_lines(self.sock):
                t = msg.get("type")
                if t in ("settings","start","state"):
                    self.state.set(msg)
                elif t == "game_over":
                    self.game_over.set(msg)
                    break
        except Exception:
            pass
        finally:
            try:
                self.sock.close()
            except: pass

    def send_input(self, keys: dict):
        # keys: {"bottom":-1|0|1, "left":-1|0|1}
        try:
            send_json_line(self.sock, {"type":"input","keys":keys})
        except Exception:
            pass

    def close(self):
        self._stop.set()
        try:
            if self.sock:
                self.sock.close()
        except: pass
