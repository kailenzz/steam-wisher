import sys
import os
import requests
import tkinter as tk
from tkinter import ttk, messagebox
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
from pathlib import Path
import threading
import time
import webbrowser

load_dotenv(dotenv_path=Path(__file__).parent / ".env")
API_KEY = os.getenv("STEAM_API_KEY")

STEAM_API_BASE = "https://api.steampowered.com"

# ── Colores tema oscuro Steam ─────────────────────────────────────────────────
BG          = "#0f1923"
BG_CARD     = "#1b2838"
BG_ROW_ALT  = "#172030"
ACCENT      = "#1a9fff"
ACCENT2     = "#66c0f4"
GREEN       = "#4caf50"
RED         = "#f44336"
YELLOW      = "#ffc107"
TEXT        = "#c7d5e0"
TEXT_DIM    = "#7a8fa6"
TEXT_BRIGHT = "#ffffff"
BORDER      = "#2a475e"

# ── API helpers ───────────────────────────────────────────────────────────────

def resolve_vanity_url(vanity_name: str) -> str | None:
    url = f"{STEAM_API_BASE}/ISteamUser/ResolveVanityURL/v1/"
    params = {"key": API_KEY, "vanityurl": vanity_name}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        result = r.json().get("response", {})
        if result.get("success") == 1:
            return result["steamid"]
    except Exception:
        pass
    return None


def fetch_game_details(app_id: str) -> tuple[str, dict]:
    """Devuelve (app_id, {name, price, discount, original_price, currency, on_sale})."""
    url = "https://store.steampowered.com/api/appdetails"
    params = {"appids": app_id, "filters": "basic,price_overview", "cc": "es", "l": "spanish"}
    try:
        r = requests.get(url, params=params, timeout=8)
        data = r.json().get(app_id, {}).get("data", {})
        name = data.get("name", f"App {app_id}")
        po = data.get("price_overview", {})
        if po:
            discount = po.get("discount_percent", 0)
            final    = po.get("final", 0) / 100
            initial  = po.get("initial", 0) / 100
            currency = po.get("currency", "EUR")
            return app_id, {
                "name": name,
                "price": final,
                "original_price": initial,
                "discount": discount,
                "currency": currency,
                "on_sale": discount > 0,
                "free": False,
            }
        elif data.get("is_free"):
            return app_id, {"name": name, "price": 0, "original_price": 0,
                            "discount": 0, "currency": "", "on_sale": False, "free": True}
        else:
            return app_id, {"name": name, "price": None, "original_price": None,
                            "discount": 0, "currency": "", "on_sale": False, "free": False}
    except Exception:
        return app_id, {"name": f"App {app_id}", "price": None, "original_price": None,
                        "discount": 0, "currency": "", "on_sale": False, "free": False}


def get_wishlist(steam_id: str, progress_cb=None) -> list[dict]:
    url = f"{STEAM_API_BASE}/IWishlistService/GetWishlist/v1"
    params = {"key": API_KEY, "steamid": steam_id}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        return []

    items = data.get("response", {}).get("items", [])
    if not items:
        return []

    app_ids = [str(item.get("appid", "")) for item in items]
    details = {}
    total = len(app_ids)

    with ThreadPoolExecutor(max_workers=12) as ex:
        futures = {ex.submit(fetch_game_details, aid): aid for aid in app_ids}
        done = 0
        for future in as_completed(futures):
            app_id, info = future.result()
            details[app_id] = info
            done += 1
            if progress_cb:
                progress_cb(done, total)

    games = []
    for item in items:
        app_id = str(item.get("appid", ""))
        info = details.get(app_id, {"name": f"App {app_id}"})
        games.append({
            "app_id":   app_id,
            "title":    info.get("name", f"App {app_id}"),
            "priority": item.get("priority", 0),
            **info,
        })
    games.sort(key=lambda g: g["priority"])
    return games


# ── Aplicación principal ──────────────────────────────────────────────────────

class SteamMonitorApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Steam Wishlist Monitor")
        self.geometry("1100x720")
        self.minsize(800, 500)
        self.configure(bg=BG)

        self.wishlist: list[dict] = []
        self.filter_var = tk.StringVar(value="all")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._apply_filters())
        self.sort_col = "priority"
        self.sort_asc = True
        self.auto_refresh = False
        self._refresh_job = None

        self._setup_styles()
        self._build_ui()

    # ── Estilos ───────────────────────────────────────────────────────────────

    def _setup_styles(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=BG_CARD)

        style.configure("Treeview",
            background=BG_CARD, foreground=TEXT,
            fieldbackground=BG_CARD, rowheight=36,
            borderwidth=0, font=("Consolas", 10))
        style.configure("Treeview.Heading",
            background=BG, foreground=ACCENT2,
            borderwidth=0, font=("Consolas", 10, "bold"),
            relief="flat")
        style.map("Treeview",
            background=[("selected", "#2a4a6b")],
            foreground=[("selected", TEXT_BRIGHT)])
        style.map("Treeview.Heading",
            background=[("active", BG_CARD)])

        style.configure("Accent.TButton",
            background=ACCENT, foreground=TEXT_BRIGHT,
            font=("Consolas", 10, "bold"), borderwidth=0,
            focusthickness=0, padding=(14, 8))
        style.map("Accent.TButton",
            background=[("active", ACCENT2), ("pressed", "#0d7acc")])

        style.configure("Ghost.TButton",
            background=BG_CARD, foreground=TEXT,
            font=("Consolas", 10), borderwidth=1,
            focusthickness=0, padding=(10, 6))
        style.map("Ghost.TButton",
            background=[("active", BORDER)])

        style.configure("TEntry",
            fieldbackground=BG_CARD, foreground=TEXT_BRIGHT,
            insertcolor=ACCENT2, bordercolor=BORDER,
            font=("Consolas", 11))

        style.configure("TProgressbar",
            troughcolor=BG_CARD, background=ACCENT,
            borderwidth=0, thickness=4)

        style.configure("TScrollbar",
            background=BORDER, troughcolor=BG_CARD,
            borderwidth=0, arrowcolor=TEXT_DIM)

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        header = tk.Frame(self, bg=BG_CARD, height=60)
        header.pack(fill="x", side="top")
        header.pack_propagate(False)

        tk.Label(header, text="⬡  STEAM WISHLIST MONITOR",
                 bg=BG_CARD, fg=ACCENT2,
                 font=("Consolas", 14, "bold")).pack(side="left", padx=20, pady=15)

        self.status_lbl = tk.Label(header, text="",
                                   bg=BG_CARD, fg=TEXT_DIM,
                                   font=("Consolas", 9))
        self.status_lbl.pack(side="right", padx=20)

        # Separador
        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # Panel superior – login + controles
        top = tk.Frame(self, bg=BG, pady=12)
        top.pack(fill="x", padx=20)

        tk.Label(top, text="Usuario / SteamID64", bg=BG, fg=TEXT_DIM,
                 font=("Consolas", 9)).grid(row=0, column=0, sticky="w")

        self.user_entry = tk.Entry(top, bg=BG_CARD, fg=TEXT_BRIGHT,
                                   insertbackground=ACCENT2, relief="flat",
                                   font=("Consolas", 12), width=28,
                                   highlightthickness=1,
                                   highlightbackground=BORDER,
                                   highlightcolor=ACCENT)
        self.user_entry.grid(row=1, column=0, padx=(0, 10), ipady=6)
        self.user_entry.bind("<Return>", lambda _: self._start_load())

        self.load_btn = ttk.Button(top, text="▶  Cargar", style="Accent.TButton",
                                   command=self._start_load)
        self.load_btn.grid(row=1, column=1, padx=(0, 8))

        self.refresh_btn = ttk.Button(top, text="↺  Refrescar precios",
                                      style="Ghost.TButton",
                                      command=self._start_refresh,
                                      state="disabled")
        self.refresh_btn.grid(row=1, column=2, padx=(0, 8))

        # Auto-refresh toggle
        self.auto_var = tk.BooleanVar(value=False)
        self.auto_chk = tk.Checkbutton(top, text="Auto cada 30 min",
                                       variable=self.auto_var,
                                       bg=BG, fg=TEXT_DIM,
                                       selectcolor=BG_CARD,
                                       activebackground=BG,
                                       activeforeground=TEXT,
                                       font=("Consolas", 9),
                                       command=self._toggle_auto)
        self.auto_chk.grid(row=1, column=3, padx=(0, 20))

        # Filtros y búsqueda
        filter_frame = tk.Frame(self, bg=BG, pady=8)
        filter_frame.pack(fill="x", padx=20)

        tk.Label(filter_frame, text="Filtrar:", bg=BG, fg=TEXT_DIM,
                 font=("Consolas", 9)).pack(side="left")

        for label, val in [("Todos", "all"), ("En oferta", "sale"), ("Sin precio", "no_price")]:
            rb = tk.Radiobutton(filter_frame, text=label, value=val,
                                variable=self.filter_var,
                                bg=BG, fg=TEXT, selectcolor=BG_CARD,
                                activebackground=BG, activeforeground=ACCENT2,
                                font=("Consolas", 10), cursor="hand2",
                                command=self._apply_filters)
            rb.pack(side="left", padx=(8, 0))

        # Búsqueda
        tk.Label(filter_frame, text="  Buscar:", bg=BG, fg=TEXT_DIM,
                 font=("Consolas", 9)).pack(side="left", padx=(20, 4))
        search_entry = tk.Entry(filter_frame, textvariable=self.search_var,
                                bg=BG_CARD, fg=TEXT_BRIGHT,
                                insertbackground=ACCENT2, relief="flat",
                                font=("Consolas", 11), width=24,
                                highlightthickness=1,
                                highlightbackground=BORDER,
                                highlightcolor=ACCENT)
        search_entry.pack(side="left", ipady=4)

        # Stats bar
        self.stats_frame = tk.Frame(self, bg=BG_CARD, pady=6)
        self.stats_frame.pack(fill="x", padx=20, pady=(0, 8))

        self.stat_total = self._stat_label("0 juegos", "Total")
        self.stat_sale  = self._stat_label("0 en oferta", "Ofertas")
        self.stat_save  = self._stat_label("0.00 €", "Mayor descuento")
        self.stat_pct   = self._stat_label("0%", "% max descuento")

        # Progress bar
        self.progress = ttk.Progressbar(self, style="TProgressbar",
                                        mode="determinate", maximum=100)
        self.progress.pack(fill="x", padx=20, pady=(0, 4))
        self.progress_lbl = tk.Label(self, text="", bg=BG, fg=TEXT_DIM,
                                     font=("Consolas", 8))
        self.progress_lbl.pack()

        # Tabla principal
        table_frame = tk.Frame(self, bg=BG)
        table_frame.pack(fill="both", expand=True, padx=20, pady=(4, 0))

        cols = ("priority", "title", "discount", "price", "original", "app_id")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings",
                                 selectmode="browse")

        headers = {
            "priority": ("#", 40),
            "title":    ("Título", 380),
            "discount": ("Descuento", 100),
            "price":    ("Precio", 90),
            "original": ("P. original", 100),
            "app_id":   ("App ID", 90),
        }
        for col, (label, width) in headers.items():
            self.tree.heading(col, text=label,
                              command=lambda c=col: self._sort_by(c))
            self.tree.column(col, width=width, anchor="center" if col != "title" else "w")

        self.tree.tag_configure("sale",    background="#1a3020", foreground=GREEN)
        self.tree.tag_configure("big_sale", background="#1a2a10", foreground="#7cfc00")
        self.tree.tag_configure("normal",  background=BG_CARD,   foreground=TEXT)
        self.tree.tag_configure("alt",     background=BG_ROW_ALT, foreground=TEXT)
        self.tree.tag_configure("free",    background="#1a1a3a",  foreground=ACCENT2)
        self.tree.tag_configure("no_price", background=BG_CARD,   foreground=TEXT_DIM)

        vsb = ttk.Scrollbar(table_frame, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self._open_store_page)

        # Footer
        footer = tk.Frame(self, bg=BG_CARD, height=28)
        footer.pack(fill="x", side="bottom")
        footer.pack_propagate(False)
        tk.Label(footer,
                 text="Doble clic → abrir en Steam Store  |  Click columna → ordenar",
                 bg=BG_CARD, fg=TEXT_DIM, font=("Consolas", 8)).pack(side="left", padx=12)

    def _stat_label(self, value: str, label: str) -> tk.Label:
        f = tk.Frame(self.stats_frame, bg=BG_CARD, padx=16, pady=4)
        f.pack(side="left", padx=(0, 2))
        tk.Label(f, text=label, bg=BG_CARD, fg=TEXT_DIM,
                 font=("Consolas", 8)).pack()
        lbl = tk.Label(f, text=value, bg=BG_CARD, fg=TEXT_BRIGHT,
                       font=("Consolas", 11, "bold"))
        lbl.pack()
        return lbl

    # ── Carga ─────────────────────────────────────────────────────────────────

    def _start_load(self):
        if not API_KEY:
            messagebox.showerror("Error", "No se encontró STEAM_API_KEY en .env")
            return
        user = self.user_entry.get().strip()
        if not user:
            messagebox.showwarning("Aviso", "Introduce un nombre de usuario o SteamID64.")
            return
        self.load_btn.config(state="disabled")
        self.refresh_btn.config(state="disabled")
        self.wishlist.clear()
        self._clear_table()
        self._set_status("Resolviendo usuario...")
        threading.Thread(target=self._load_worker, args=(user,), daemon=True).start()

    def _load_worker(self, user: str):
        if user.isdigit() and len(user) == 17:
            steam_id = user
        else:
            steam_id = resolve_vanity_url(user)
            if not steam_id:
                self.after(0, lambda: self._on_error("Usuario no encontrado o perfil privado."))
                return

        self.after(0, lambda: self._set_status(f"Cargando wishlist para {steam_id}..."))

        def progress_cb(done, total):
            pct = int(done / total * 100)
            self.after(0, lambda p=pct, d=done, t=total:
                       self._update_progress(p, f"Obteniendo precios: {d}/{t}"))

        games = get_wishlist(steam_id, progress_cb=progress_cb)
        self.after(0, lambda: self._on_loaded(games))

    def _start_refresh(self):
        if not self.wishlist:
            return
        self.refresh_btn.config(state="disabled")
        self._set_status("Actualizando precios...")
        threading.Thread(target=self._refresh_worker, daemon=True).start()

    def _refresh_worker(self):
        app_ids = [g["app_id"] for g in self.wishlist]
        total = len(app_ids)
        details = {}

        with ThreadPoolExecutor(max_workers=12) as ex:
            futures = {ex.submit(fetch_game_details, aid): aid for aid in app_ids}
            done = 0
            for future in as_completed(futures):
                app_id, info = future.result()
                details[app_id] = info
                done += 1
                pct = int(done / total * 100)
                self.after(0, lambda p=pct, d=done, t=total:
                           self._update_progress(p, f"Actualizando: {d}/{t}"))

        for game in self.wishlist:
            info = details.get(game["app_id"], {})
            game.update(info)

        self.after(0, self._after_refresh)

    def _after_refresh(self):
        self._apply_filters()
        self._update_stats()
        self._update_progress(0, "")
        self.refresh_btn.config(state="normal")
        self._set_status(f"Precios actualizados — {time.strftime('%H:%M:%S')}")

    def _on_loaded(self, games: list):
        if not games:
            self._on_error("Wishlist vacía o perfil privado.")
            return
        self.wishlist = games
        self._apply_filters()
        self._update_stats()
        self._update_progress(0, "")
        self.load_btn.config(state="normal")
        self.refresh_btn.config(state="normal")
        self._set_status(f"{len(games)} juegos cargados — {time.strftime('%H:%M:%S')}")

    def _on_error(self, msg: str):
        self.load_btn.config(state="normal")
        self.refresh_btn.config(state="normal")
        self._update_progress(0, "")
        self._set_status(f"Error: {msg}")
        messagebox.showerror("Error", msg)

    # ── Tabla ─────────────────────────────────────────────────────────────────

    def _populate_table(self, games: list):
        self._clear_table()
        for i, g in enumerate(games):
            tag = self._row_tag(g, i)
            disc_txt = self._discount_text(g)
            price_txt = self._price_text(g, "price")
            orig_txt  = self._price_text(g, "original_price")
            self.tree.insert("", "end",
                iid=g["app_id"],
                values=(
                    g.get("priority", 0) or i + 1,
                    g["title"],
                    disc_txt,
                    price_txt,
                    orig_txt,
                    g["app_id"],
                ),
                tags=(tag,))

    def _clear_table(self):
        for item in self.tree.get_children():
            self.tree.delete(item)

    def _row_tag(self, g: dict, i: int) -> str:
        if g.get("free"):       return "free"
        if g.get("price") is None: return "no_price"
        d = g.get("discount", 0)
        if d >= 50:  return "big_sale"
        if d > 0:    return "sale"
        return "normal" if i % 2 == 0 else "alt"

    def _discount_text(self, g: dict) -> str:
        if g.get("free"):       return "GRATIS"
        d = g.get("discount", 0)
        if d > 0:               return f"-{d}%"
        if g.get("price") is None: return "—"
        return ""

    def _price_text(self, g: dict, key: str) -> str:
        if g.get("free"):       return "0.00 €"
        v = g.get(key)
        if v is None:           return "—"
        cur = g.get("currency", "EUR")
        sym = {"EUR": "€", "USD": "$", "GBP": "£"}.get(cur, cur)
        return f"{v:.2f} {sym}"

    def _apply_filters(self, *_):
        filt   = self.filter_var.get()
        search = self.search_var.get().lower()
        result = []
        for g in self.wishlist:
            if filt == "sale"     and not g.get("on_sale") and not g.get("free"):
                continue
            if filt == "no_price" and g.get("price") is not None:
                continue
            if search and search not in g["title"].lower():
                continue
            result.append(g)
        self._populate_table(result)

    def _sort_by(self, col: str):
        if self.sort_col == col:
            self.sort_asc = not self.sort_asc
        else:
            self.sort_col = col
            self.sort_asc = True

        def key(g):
            v = g.get(col)
            if v is None:
                return (1, 0)
            if isinstance(v, (int, float)):
                return (0, v)
            return (0, str(v).lower())

        self.wishlist.sort(key=key, reverse=not self.sort_asc)
        self._apply_filters()

    def _update_stats(self):
        total    = len(self.wishlist)
        on_sale  = [g for g in self.wishlist if g.get("on_sale")]
        max_disc = max((g.get("discount", 0) for g in self.wishlist), default=0)
        max_save = max(
            (g.get("original_price", 0) - g.get("price", 0)
             for g in self.wishlist if g.get("on_sale") and g.get("price") is not None),
            default=0.0)

        self.stat_total.config(text=f"{total}")
        self.stat_sale.config(text=f"{len(on_sale)}", fg=GREEN if on_sale else TEXT_BRIGHT)
        self.stat_save.config(text=f"{max_save:.2f} €")
        self.stat_pct.config(text=f"{max_disc}%", fg=GREEN if max_disc >= 50 else YELLOW if max_disc > 0 else TEXT_BRIGHT)

    # ── Utilidades ────────────────────────────────────────────────────────────

    def _open_store_page(self, event):
        sel = self.tree.focus()
        if sel:
            webbrowser.open(f"https://store.steampowered.com/app/{sel}")

    def _set_status(self, msg: str):
        self.status_lbl.config(text=msg)

    def _update_progress(self, pct: int, label: str):
        self.progress["value"] = pct
        self.progress_lbl.config(text=label)

    def _toggle_auto(self):
        if self.auto_var.get():
            self._schedule_refresh()
        else:
            if self._refresh_job:
                self.after_cancel(self._refresh_job)
                self._refresh_job = None

    def _schedule_refresh(self):
        if not self.auto_var.get():
            return
        self._start_refresh()
        self._refresh_job = self.after(30 * 60 * 1000, self._schedule_refresh)


if __name__ == "__main__":
    app = SteamMonitorApp()
    app.mainloop()
