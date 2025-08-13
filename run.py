import tkinter as tk
from tkinter import ttk, messagebox
import threading
import sys
from game.server import GameServer
from game.client import GameClient
from game.game import run_pygame_loop

DEFAULT_PORT = 50007

def start_game(settings):
    role = settings["role"]  # "host" or "client"
    host_ip = settings["host_ip"]
    port = settings["port"]
    num_balls = settings["num_balls"]
    target_score = settings["target_score"]
    time_limit = settings["time_limit"]  # seconds; 0 = no limit

    if role == "host":
        # Start server in background thread
        server = GameServer(port=port, num_balls=num_balls, target_score=target_score, time_limit=time_limit)
        server.start()
        # Run local pygame loop as Player A (host)
        try:
            run_pygame_loop(role="A", server=server, client=None)
        finally:
            server.stop()
    else:
        # Connect as client (Player B)
        client = GameClient(host=host_ip, port=port)
        try:
            client.connect()
            run_pygame_loop(role="B", server=None, client=client)
        finally:
            client.close()


def main():
    root = tk.Tk()
    root.title("NetPong Settings")

    role_var = tk.StringVar(value="host")
    ip_var = tk.StringVar(value="127.0.0.1")
    port_var = tk.IntVar(value=DEFAULT_PORT)
    balls_var = tk.IntVar(value=1)
    target_var = tk.IntVar(value=5)
    timelimit_var = tk.IntVar(value=0)

    frm = ttk.Frame(root, padding=16)
    frm.grid(sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)

    ttk.Label(frm, text="Role:").grid(row=0, column=0, sticky="w")
    role_combo = ttk.Combobox(frm, textvariable=role_var, values=["host","client"], state="readonly", width=12)
    role_combo.grid(row=0, column=1, sticky="ew")

    ttk.Label(frm, text="Host IP (for client):").grid(row=1, column=0, sticky="w")
    ip_entry = ttk.Entry(frm, textvariable=ip_var, width=18)
    ip_entry.grid(row=1, column=1, sticky="ew")

    ttk.Label(frm, text="Port:").grid(row=2, column=0, sticky="w")
    port_entry = ttk.Entry(frm, textvariable=port_var, width=10)
    port_entry.grid(row=2, column=1, sticky="ew")

    ttk.Label(frm, text="Balls (1 or 2):").grid(row=3, column=0, sticky="w")
    balls_spin = ttk.Spinbox(frm, from_=1, to=2, textvariable=balls_var, width=6)
    balls_spin.grid(row=3, column=1, sticky="w")

    ttk.Label(frm, text="Target Score:").grid(row=4, column=0, sticky="w")
    target_spin = ttk.Spinbox(frm, from_=1, to=50, textvariable=target_var, width=6)
    target_spin.grid(row=4, column=1, sticky="w")

    ttk.Label(frm, text="Time Limit (sec, 0=∞):").grid(row=5, column=0, sticky="w")
    time_spin = ttk.Spinbox(frm, from_=0, to=3600, increment=30, textvariable=timelimit_var, width=8)
    time_spin.grid(row=5, column=1, sticky="w")

    status_lbl = ttk.Label(frm, text="Tip: Host sets Port & rules. Client needs Host IP.")
    status_lbl.grid(row=6, column=0, columnspan=2, sticky="w", pady=(8,0))

    def on_role_change(*_):
        if role_var.get() == "host":
            ip_entry.configure(state="disabled")
        else:
            ip_entry.configure(state="normal")
    role_var.trace_add("write", on_role_change)
    on_role_change()

    def on_start():
        try:
            settings = dict(
                role=role_var.get(),
                host_ip=ip_var.get(),
                port=int(port_var.get()),
                num_balls=int(balls_var.get()),
                target_score=int(target_var.get()),
                time_limit=int(timelimit_var.get()),
            )
            if settings["role"] == "client" and not settings["host_ip"]:
                messagebox.showerror("Error", "Please enter Host IP for client mode.")
                return
        except Exception as e:
            messagebox.showerror("Error", f"Invalid settings: {e}")
            return

        root.destroy()
        start_game(settings)

    start_btn = ttk.Button(frm, text="Start", command=on_start)
    start_btn.grid(row=7, column=0, columnspan=2, pady=(12,0), sticky="ew")

    root.mainloop()

if __name__ == "__main__":
    main()
