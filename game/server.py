import socket, threading, time, traceback
from .common import (
    WIDTH, HEIGHT, BALL_RADIUS, PADDLE_SPEED, PADDLE_LEN, PADDLE_THICK,
    send_json_line, recv_json_lines, clamp, reflect_ball, reset_ball,
    paddle_rect, rect_contains_x, rect_contains_y, make_initial_balls,
    initial_paddles, PLAYER_EDGES, EDGE_ORIENT, TICK_RATE, Atomic
)

class GameServer:
    """
    Authoritative server:
      - Accepts one client
      - Steps physics at fixed rate
      - Applies inputs from Player A (local) and Player B (remote)
      - Broadcasts state snapshots
    """
    def __init__(self, port=50007, num_balls=1, target_score=5, time_limit=0):
        self.port = port
        self.num_balls = num_balls
        self.target_score = target_score
        self.time_limit = time_limit  # 0 means no limit
        self._thread = None
        self._stop = threading.Event()

        self.client_sock = None
        self.client_addr = None

        # Shared state for host renderer (Player A)
        self.latest_state = Atomic(None)

        # Inputs
        self.input_A = {"top": 0, "right": 0}   # -1,0,1 movement intents
        self.input_B = {"bottom": 0, "left": 0}

        # Protect input_B (comes from network thread)
        self._input_lock = threading.Lock()

        # Game state (server-owned)
        self.paddles = initial_paddles()
        self.balls = make_initial_balls(self.num_balls)
        self.scoreA = 0
        self.scoreB = 0
        self.paused = False
        self.start_time = None  # set after both players ready

    def start(self):
        self._thread = threading.Thread(target=self._run, name="GameServer", daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()
        try:
            if self.client_sock:
                self.client_sock.close()
        except: pass

    # --- API for host pygame loop ---
    def set_input_A(self, keyvec: dict):
        # keyvec: {"top": -1|0|1, "right": -1|0|1}
        self.input_A = keyvec

    def toggle_pause(self):
        self.paused = not self.paused

    # --- Internal networking ---
    def _accept_client(self, listener):
        listener.settimeout(0.5)
        while not self._stop.is_set():
            try:
                sock, addr = listener.accept()
                self.client_sock = sock
                self.client_addr = addr
                return True
            except socket.timeout:
                continue
            except OSError:
                return False
        return False

    def _recv_client_loop(self):
        try:
            for msg in recv_json_lines(self.client_sock):
                if self._stop.is_set():
                    break
                t = msg.get("type")
                if t == "hello":
                    # ignore; we already proceed
                    pass
                elif t == "input":
                    # update input_B
                    with self._input_lock:
                        # sanitize to -1/0/1
                        nb = {}
                        for k in ("bottom","left"):
                            v = int(msg.get("keys",{}).get(k,0))
                            if v < -1: v=-1
                            if v > 1: v=1
                            nb[k]=v
                        self.input_B = nb
                else:
                    # ignore unknown
                    pass
        except Exception:
            # client disconnected or error
            try:
                if self.client_sock:
                    self.client_sock.close()
            except: pass
            self.client_sock = None

    def _broadcast(self, obj):
        # to client
        if self.client_sock:
            try:
                send_json_line(self.client_sock, obj)
            except Exception:
                try:
                    self.client_sock.close()
                except: pass
                self.client_sock = None
        # to host renderer
        self.latest_state.set(obj)

    # --- Physics & scoring ---
    def _apply_inputs(self, dt):
        # Player A
        self.paddles["top"]   = clamp(self.paddles["top"]   + self.input_A["top"]   * PADDLE_SPEED * dt,   PADDLE_LEN/2, WIDTH - PADDLE_LEN/2)
        self.paddles["right"] = clamp(self.paddles["right"] + self.input_A["right"] * PADDLE_SPEED * dt,   PADDLE_LEN/2, HEIGHT - PADDLE_LEN/2)
        # Player B
        with self._input_lock:
            inpB = dict(self.input_B)
        self.paddles["bottom"] = clamp(self.paddles["bottom"] + inpB["bottom"] * PADDLE_SPEED * dt, PADDLE_LEN/2, WIDTH - PADDLE_LEN/2)
        self.paddles["left"]   = clamp(self.paddles["left"]   + inpB["left"]   * PADDLE_SPEED * dt, PADDLE_LEN/2, HEIGHT - PADDLE_LEN/2)

    def _step_balls(self, dt):
        scored = None  # "A" or "B"
        for ball in self.balls:
            # Integrate
            ball["x"] += ball["vx"] * dt
            ball["y"] += ball["vy"] * dt

            # Collisions with edges/paddles:
            # TOP edge (belongs to A)
            if ball["vy"] < 0 and ball["y"] - BALL_RADIUS <= 0:
                pr = paddle_rect("top", self.paddles["top"])
                if rect_contains_x(pr, ball["x"]):
                    # bounce
                    ball["y"] = BALL_RADIUS
                    reflect_ball(ball, "y")
                else:
                    scored = "B"  # B scores, A loses
            # BOTTOM edge (belongs to B)
            elif ball["vy"] > 0 and ball["y"] + BALL_RADIUS >= HEIGHT:
                pr = paddle_rect("bottom", self.paddles["bottom"])
                if rect_contains_x(pr, ball["x"]):
                    ball["y"] = HEIGHT - BALL_RADIUS
                    reflect_ball(ball, "y")
                else:
                    scored = "A"
            # LEFT edge (belongs to B)
            if ball["vx"] < 0 and ball["x"] - BALL_RADIUS <= 0:
                pr = paddle_rect("left", self.paddles["left"])
                if rect_contains_y(pr, ball["y"]):
                    ball["x"] = BALL_RADIUS
                    reflect_ball(ball, "x")
                else:
                    scored = "A"
            # RIGHT edge (belongs to A)
            elif ball["vx"] > 0 and ball["x"] + BALL_RADIUS >= WIDTH:
                pr = paddle_rect("right", self.paddles["right"])
                if rect_contains_y(pr, ball["y"]):
                    ball["x"] = WIDTH - BALL_RADIUS
                    reflect_ball(ball, "x")
                else:
                    scored = "B"

        if scored:
            if scored == "A":
                self.scoreA += 1
            else:
                self.scoreB += 1
            # reset all balls to center with new random directions
            for b in self.balls:
                reset_ball(b)

    def _make_state_obj(self, kind="state"):
        elapsed = 0
        remaining = None
        if self.start_time is not None:
            elapsed = time.time() - self.start_time
            remaining = max(0, self.time_limit - int(elapsed)) if self.time_limit > 0 else None
        return {
            "type": kind,
            "paddles": self.paddles,
            "balls": self.balls,
            "score": {"A": self.scoreA, "B": self.scoreB},
            "paused": self.paused,
            "width": WIDTH, "height": HEIGHT,
            "paddle_len": PADDLE_LEN, "paddle_thick": PADDLE_THICK,
            "ball_radius":  BALL_RADIUS,
            "target_score": self.target_score,
            "time_limit":   self.time_limit,
            "time_remaining": remaining
        }

    def _check_gameover(self):
        if self.target_score and (self.scoreA >= self.target_score or self.scoreB >= self.target_score):
            winner = "A" if self.scoreA > self.scoreB else "B"
            self._broadcast({"type":"game_over","winner":winner,"score":{"A":self.scoreA,"B":self.scoreB}})
            return True
        if self.time_limit > 0 and self.start_time is not None:
            elapsed = time.time() - self.start_time
            if elapsed >= self.time_limit:
                # decide winner by score (tie -> A wins by default or declare draw)
                if self.scoreA > self.scoreB: winner = "A"
                elif self.scoreB > self.scoreA: winner = "B"
                else: winner = "draw"
                self._broadcast({"type":"game_over","winner":winner,"score":{"A":self.scoreA,"B":self.scoreB}})
                return True
        return False

    def _run(self):
        # Listen
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("", self.port))
        listener.listen(1)

        # Wait for client
        accepted = self._accept_client(listener)
        if not accepted and self._stop.is_set():
            listener.close()
            return

        # Spawn client recv thread
        if self.client_sock:
            th = threading.Thread(target=self._recv_client_loop, name="ServerClientRecv", daemon=True)
            th.start()
            # send settings + initial state
            send_json_line(self.client_sock, {
                "type":"settings",
                "width": WIDTH, "height": HEIGHT,
                "num_balls": self.num_balls,
                "target_score": self.target_score,
                "time_limit": self.time_limit
            })

        # Announce start to both (host via latest_state)
        self.start_time = time.time()
        start_state = self._make_state_obj(kind="start")
        self._broadcast(start_state)
        if self.client_sock:
            send_json_line(self.client_sock, start_state)

        # Physics loop
        last = time.perf_counter()
        acc = 0.0
        dt = 1.0 / TICK_RATE
        while not self._stop.is_set():
            now = time.perf_counter()
            acc += (now - last)
            last = now

            # Fixed-step update
            while acc >= dt:
                if not self.paused:
                    self._apply_inputs(dt)
                    self._step_balls(dt)
                acc -= dt

            # Send state each frame
            st = self._make_state_obj(kind="state")
            self._broadcast(st)

            if self._check_gameover():
                break

            time.sleep(0.001)  # be gentle

        try:
            listener.close()
        except: pass
