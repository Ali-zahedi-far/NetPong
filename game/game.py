import pygame, time, sys
from .common import (
    WIDTH, HEIGHT, PADDLE_LEN, PADDLE_THICK, BALL_RADIUS,
    paddle_rect, PLAYER_EDGES
)
from .server import GameServer

# Render helpers
def draw_text(screen, txt, pos, size=24, color=(255,255,255)):
    font = pygame.font.SysFont(None, size)
    s = font.render(txt, True, color)
    screen.blit(s, pos)

def run_pygame_loop(role: str=None, server=None, client=None, mode: str='network'):
    """
    role: 'A' or 'B' when networked. mode: 'network' or 'local'
    """
    """
    role: "A" for host player's renderer, "B" for client
    server: GameServer when role=="A"
    client: GameClient when role=="B"
    """
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption(f"NetPong — Player {role}")
    clock = pygame.time.Clock()

    # Key mapping per role
    if mode == 'local':
        def get_input_local():
            keys = pygame.key.get_pressed()
            # Player A: top (A/D), right (W/S)
            top = (-1 if keys[pygame.K_a] else 0) + (1 if keys[pygame.K_d] else 0)
            right = (-1 if keys[pygame.K_w] else 0) + (1 if keys[pygame.K_s] else 0)
            top = -1 if top < 0 else (1 if top > 0 else 0)
            right = -1 if right < 0 else (1 if right > 0 else 0)
            # Player B: bottom (Left/Right), left (Up/Down)
            bottom = (-1 if keys[pygame.K_LEFT] else 0) + (1 if keys[pygame.K_RIGHT] else 0)
            left   = (-1 if keys[pygame.K_UP] else 0) + (1 if keys[pygame.K_DOWN] else 0)
            bottom = -1 if bottom < 0 else (1 if bottom > 0 else 0)
            left   = -1 if left < 0 else (1 if left > 0 else 0)
            return {"top": top, "right": right, "bottom": bottom, "left": left}

    if role == "A":
        # A: top (A/D), right (W/S)
        def get_input():
            keys = pygame.key.get_pressed()
            top = (-1 if keys[pygame.K_a] else 0) + (1 if keys[pygame.K_d] else 0)
            right = (-1 if keys[pygame.K_w] else 0) + (1 if keys[pygame.K_s] else 0)
            # clamp to -1..1
            top = -1 if top < 0 else (1 if top > 0 else 0)
            right = -1 if right < 0 else (1 if right > 0 else 0)
            return {"top": top, "right": right}
    else:
        # B: bottom (Left/Right), left (Up/Down)
        def get_input():
            keys = pygame.key.get_pressed()
            bottom = (-1 if keys[pygame.K_LEFT] else 0) + (1 if keys[pygame.K_RIGHT] else 0)
            left   = (-1 if keys[pygame.K_UP] else 0) + (1 if keys[pygame.K_DOWN] else 0)
            bottom = -1 if bottom < 0 else (1 if bottom > 0 else 0)
            left   = -1 if left < 0 else (1 if left > 0 else 0)
            return {"bottom": bottom, "left": left}

    # Game loop
    game_over = None
    paused = False

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    pygame.quit()
                    return
                if role == "A" and event.key == pygame.K_p and server is not None:
                    server.toggle_pause()

        # Gather and send/apply inputs
        if mode == 'local':
            inp = get_input_local()
            # apply to server inputs directly
            server.set_input_A({"top": inp['top'], "right": inp['right']})
            with server._input_lock:
                server.input_B = {"bottom": inp['bottom'], "left": inp['left']}
            # step physics manually
            # use fixed dt based on clock
            dt = clock.get_time() / 1000.0
            if dt <= 0:
                dt = 1.0/60.0
            if not server.paused:
                server._apply_inputs(dt)
                server._step_balls(dt)
            state = server._make_state_obj(kind='state')
        else:
            inp = get_input()
            if role == "A" and server is not None:
                server.set_input_A(inp)
                state = server.latest_state.get()
            else:
                # client: send input to server
                if client is not None:
                    try:
                        client.send_input(inp)
                    except Exception:
                        pass
                    state = client.state.get()
                    go = client.game_over.get()
                    if go is not None:
                        game_over = go

        # Clear
        screen.fill((10, 12, 24))

        # If we have a state, draw it
        if state:
            # Draw arena outline
            pygame.draw.rect(screen, (200,200,200), pygame.Rect(0,0,WIDTH,HEIGHT), width=2)

            # Balls
            for b in state.get("balls", []):
                pygame.draw.circle(screen, (240,240,240), (int(b["x"]), int(b["y"])), state["ball_radius"])

            # Paddles
            paddles = state.get("paddles", {})
            colors = {"top":(80,180,255), "right":(80,180,255), "bottom":(255,140,80), "left":(255,140,80)}
            for edge, pos in paddles.items():
                r = paddle_rect(edge, pos)
                pygame.draw.rect(screen, colors[edge], pygame.Rect(int(r[0]),int(r[1]), int(r[2]-r[0]), int(r[3]-r[1])))

            # HUD: scores & time
            sc = state.get("score", {"A":0,"B":0})
            draw_text(screen, f"A: {sc['A']}   B: {sc['B']}", (10, 8), size=28)
            if state.get("time_limit", 0):
                tr = state.get("time_remaining")
                draw_text(screen, f"Time: {tr:>3}s", (WIDTH-140, 8), size=28)

            if state.get("paused"):
                draw_text(screen, "PAUSED (P)", (WIDTH//2 - 70, HEIGHT//2 - 12), size=28)

        # Game over banner (for client; host gets via state then broadcast too)
        if game_over:
            draw_text(screen, "GAME OVER", (WIDTH//2 - 80, HEIGHT//2 - 30), size=36)
            w = game_over.get("winner")
            sc = game_over.get("score",{})
            if w == "draw":
                draw_text(screen, f"Draw!  A:{sc.get('A',0)}  B:{sc.get('B',0)}", (WIDTH//2 - 110, HEIGHT//2 + 10), size=28)
            else:
                draw_text(screen, f"Winner: {w}   A:{sc.get('A',0)}  B:{sc.get('B',0)}", (WIDTH//2 - 140, HEIGHT//2 + 10), size=28)

        pygame.display.flip()
        clock.tick(60)
