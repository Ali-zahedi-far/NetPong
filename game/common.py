import json, threading, random, math, time, socket

# --- Constants ---
WIDTH = 600
HEIGHT = 600

PADDLE_LEN = 160
PADDLE_THICK = 12
PADDLE_SPEED = 300.0  # px/s

BALL_RADIUS = 8
BALL_SPEED = 160.0  # px/s

TICK_RATE = 60.0  # physics Hz

# Ownership of edges
PLAYER_EDGES = {
    "A": ["top", "right"],
    "B": ["bottom", "left"]
}

# For convenience: orientation of each edge
EDGE_ORIENT = {
    "top": "h",     # horizontal paddle, moves along x
    "bottom": "h",
    "left": "v",    # vertical paddle, moves along y
    "right": "v",
}

# --- Thread-safe shared objects helper ---
class Atomic:
    """A simple atomic container with a lock (for shared state)."""
    def __init__(self, value=None):
        self._v = value
        self._lock = threading.Lock()
    def get(self):
        with self._lock:
            return self._v
    def set(self, v):
        with self._lock:
            self._v = v

# --- JSON line helpers ---
def send_json_line(sock: socket.socket, obj: dict):
    data = (json.dumps(obj, separators=(',',':')) + "\n").encode("utf-8")
    sock.sendall(data)

def recv_json_lines(sock: socket.socket):
    """Generator that yields decoded JSON objects per line from a blocking socket."""
    f = sock.makefile("r", encoding="utf-8", newline="\n")
    while True:
        line = f.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue

# --- Physics helpers ---
def clamp(val, lo, hi):
    return max(lo, min(hi, val))

def random_ball_velocity():
    # Random direction, avoid too axis-aligned angles
    angle = random.uniform(0, 2*math.pi)
    # ensure not too close to 0, 90, 180, 270 degrees
    for _ in range(10):
        deg = abs((angle*180/math.pi) % 90)
        if 12 < deg < 78:
            break
        angle = random.uniform(0, 2*math.pi)
    vx = BALL_SPEED * math.cos(angle)
    vy = BALL_SPEED * math.sin(angle)
    return vx, vy

def make_initial_balls(n):
    balls = []
    for _ in range(n):
        vx, vy = random_ball_velocity()
        balls.append({"x": WIDTH/2, "y": HEIGHT/2, "vx": vx, "vy": vy})
    return balls

def paddle_rect(edge, pos):
    """Return rectangle (x1,y1,x2,y2) of paddle at a given 'pos' (center along movement axis)."""
    if edge == "top":
        x1 = clamp(pos - PADDLE_LEN/2, 0, WIDTH - PADDLE_LEN)
        x2 = x1 + PADDLE_LEN
        return x1, 0, x2, PADDLE_THICK
    if edge == "bottom":
        x1 = clamp(pos - PADDLE_LEN/2, 0, WIDTH - PADDLE_LEN)
        x2 = x1 + PADDLE_LEN
        return x1, HEIGHT - PADDLE_THICK, x2, HEIGHT
    if edge == "left":
        y1 = clamp(pos - PADDLE_LEN/2, 0, HEIGHT - PADDLE_LEN)
        y2 = y1 + PADDLE_LEN
        return 0, y1, PADDLE_THICK, y2
    if edge == "right":
        y1 = clamp(pos - PADDLE_LEN/2, 0, HEIGHT - PADDLE_LEN)
        y2 = y1 + PADDLE_LEN
        return WIDTH - PADDLE_THICK, y1, WIDTH, y2
    raise ValueError("invalid edge")

def rect_contains_x(r, x):
    return r[0] <= x <= r[2]

def rect_contains_y(r, y):
    return r[1] <= y <= r[3]

def reflect_ball(ball, axis):
    if axis == "x":
        ball["vx"] = -ball["vx"]
    else:
        ball["vy"] = -ball["vy"]

def reset_ball(ball):
    ball["x"] = WIDTH/2
    ball["y"] = HEIGHT/2
    ball["vx"], ball["vy"] = random_ball_velocity()

def initial_paddles():
    # center paddles
    return {
        "top": WIDTH/2,
        "bottom": WIDTH/2,
        "left": HEIGHT/2,
        "right": HEIGHT/2
    }
