"""Bloodborne-inspired look for the Tk launcher: palette, fonts, ttk styles.

Everything visual lives here so the pages in ``ui.py`` and the panel modules
describe structure only.  The palette is Yharnam at night: near-black blue
ground, bone parchment text, lamp gold for headings and the active choice,
old blood for the one primary action.
"""

from __future__ import annotations

from typing import Any, Callable

# Ground and surfaces.
THEME_BACKGROUND = "#0c0f15"      # window ground
THEME_SIDEBAR = "#080a0f"         # navigation rail, one step darker
THEME_PANEL = "#151a23"           # entries, text wells, raised buttons
THEME_PANEL_HOVER = "#1d2430"
THEME_BORDER = "#262d3a"
THEME_BORDER_SOFT = "#1b212b"     # hairline dividers
# Text.
THEME_FOREGROUND = "#e2dcc8"      # parchment
THEME_MUTED = "#8a93a3"
THEME_DIM = "#5d6674"             # section captions and rarely-needed hints
# Accents.
THEME_BLOOD = "#8f1d24"
THEME_BLOOD_ACTIVE = "#b3242c"
THEME_GOLD = "#c9a95a"
THEME_GOLD_DIM = "#8f7a45"
THEME_ON_BLOOD = "#f6efe0"        # text on the blood-red primary
# Health tones for the live-status dot.
THEME_OK = "#5f9e6e"
THEME_WARN = "#c8963c"
THEME_BAD = "#b3242c"

FONT_BODY = ("Segoe UI", 10)
FONT_SMALL = ("Segoe UI", 9)
FONT_CAPTION = ("Segoe UI", 8, "bold")
FONT_BRAND = ("Georgia", 13, "bold")
FONT_PAGE_TITLE = ("Georgia", 20)
FONT_NAV = ("Segoe UI", 11)
FONT_PRIMARY = ("Segoe UI", 11, "bold")
FONT_MONO = ("Consolas", 9)

SIDEBAR_WIDTH = 212


def apply_theme(root: Any, ttk: Any) -> None:
    """Configure every ttk style the launcher uses on ``root``."""
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except Exception:  # noqa: BLE001 - keep whatever theme Tk has
        pass
    root.configure(bg=THEME_BACKGROUND)
    # The combobox dropdown is a plain Tk listbox; it only listens to options.
    root.option_add("*TCombobox*Listbox.background", THEME_PANEL)
    root.option_add("*TCombobox*Listbox.foreground", THEME_FOREGROUND)
    root.option_add("*TCombobox*Listbox.selectBackground", THEME_BLOOD)
    root.option_add("*TCombobox*Listbox.selectForeground", THEME_FOREGROUND)
    root.option_add("*TCombobox*Listbox.borderWidth", 0)
    root.option_add("*TCombobox*Listbox.font", FONT_BODY)

    style.configure(
        ".",
        background=THEME_BACKGROUND, foreground=THEME_FOREGROUND,
        fieldbackground=THEME_PANEL, bordercolor=THEME_BORDER,
        darkcolor=THEME_BACKGROUND, lightcolor=THEME_BACKGROUND,
        troughcolor=THEME_PANEL, focuscolor=THEME_BACKGROUND,
        selectbackground=THEME_BLOOD, selectforeground=THEME_FOREGROUND,
        font=FONT_BODY,
    )
    style.configure("TFrame", background=THEME_BACKGROUND)
    style.configure("Sidebar.TFrame", background=THEME_SIDEBAR)
    style.configure("Panel.TFrame", background=THEME_PANEL)

    style.configure("TLabel", background=THEME_BACKGROUND, foreground=THEME_FOREGROUND)
    style.configure("Muted.TLabel", foreground=THEME_MUTED)
    style.configure("Dim.TLabel", foreground=THEME_DIM, font=FONT_SMALL)
    style.configure("Title.TLabel", foreground=THEME_GOLD, font=FONT_PAGE_TITLE)
    style.configure("Section.TLabel", foreground=THEME_GOLD_DIM, font=FONT_CAPTION)
    style.configure("Field.TLabel", foreground=THEME_MUTED)
    style.configure("Panel.TLabel", background=THEME_PANEL)
    style.configure("PanelMuted.TLabel", background=THEME_PANEL, foreground=THEME_MUTED)
    style.configure("PanelTitle.TLabel", background=THEME_PANEL, foreground=THEME_GOLD,
                    font=("Segoe UI", 12, "bold"))

    style.configure(
        "TEntry", fieldbackground=THEME_PANEL, foreground=THEME_FOREGROUND,
        insertcolor=THEME_FOREGROUND, bordercolor=THEME_BORDER,
        lightcolor=THEME_BORDER, darkcolor=THEME_BORDER, padding=(8, 5),
    )
    style.map(
        "TEntry",
        bordercolor=[("focus", THEME_GOLD)], lightcolor=[("focus", THEME_GOLD)],
        darkcolor=[("focus", THEME_GOLD)],
        fieldbackground=[("disabled", THEME_BACKGROUND)],
        foreground=[("disabled", THEME_DIM)],
    )
    style.configure(
        "TCombobox", fieldbackground=THEME_PANEL, background=THEME_PANEL,
        foreground=THEME_FOREGROUND, arrowcolor=THEME_MUTED, bordercolor=THEME_BORDER,
        lightcolor=THEME_BORDER, darkcolor=THEME_BORDER, padding=(8, 4),
    )
    style.map(
        "TCombobox",
        fieldbackground=[("readonly", THEME_PANEL)], foreground=[("readonly", THEME_FOREGROUND)],
        bordercolor=[("focus", THEME_GOLD)], arrowcolor=[("active", THEME_GOLD)],
        selectbackground=[("readonly", THEME_PANEL)],
        selectforeground=[("readonly", THEME_FOREGROUND)],
    )

    # Buttons: flat surfaces, no bevel. Three weights -- panel (default),
    # ghost (outlined secondary) and accent (the one blood-red primary).
    style.configure(
        "TButton", background=THEME_PANEL, foreground=THEME_FOREGROUND,
        bordercolor=THEME_BORDER, lightcolor=THEME_PANEL, darkcolor=THEME_PANEL,
        padding=(12, 6), relief="flat", borderwidth=1, focuscolor=THEME_PANEL,
    )
    style.map(
        "TButton",
        background=[("disabled", THEME_BACKGROUND), ("pressed", THEME_BORDER),
                    ("active", THEME_PANEL_HOVER)],
        lightcolor=[("active", THEME_PANEL_HOVER)], darkcolor=[("active", THEME_PANEL_HOVER)],
        foreground=[("disabled", THEME_DIM)],
        bordercolor=[("disabled", THEME_BORDER_SOFT), ("active", THEME_GOLD_DIM)],
    )
    style.configure(
        "Ghost.TButton", background=THEME_BACKGROUND, lightcolor=THEME_BACKGROUND,
        darkcolor=THEME_BACKGROUND, bordercolor=THEME_BORDER, focuscolor=THEME_BACKGROUND,
    )
    style.map(
        "Ghost.TButton",
        background=[("disabled", THEME_BACKGROUND), ("active", THEME_PANEL)],
        lightcolor=[("active", THEME_PANEL)], darkcolor=[("active", THEME_PANEL)],
        bordercolor=[("disabled", THEME_BORDER_SOFT), ("active", THEME_GOLD_DIM)],
        foreground=[("disabled", THEME_DIM)],
    )
    style.configure(
        "Accent.TButton", background=THEME_BLOOD, foreground=THEME_ON_BLOOD,
        bordercolor=THEME_BLOOD, lightcolor=THEME_BLOOD, darkcolor=THEME_BLOOD,
        font=FONT_PRIMARY, padding=(18, 8), focuscolor=THEME_BLOOD,
    )
    style.map(
        "Accent.TButton",
        background=[("disabled", THEME_PANEL), ("active", THEME_BLOOD_ACTIVE)],
        lightcolor=[("disabled", THEME_PANEL), ("active", THEME_BLOOD_ACTIVE)],
        darkcolor=[("disabled", THEME_PANEL), ("active", THEME_BLOOD_ACTIVE)],
        bordercolor=[("disabled", THEME_BORDER), ("active", THEME_BLOOD_ACTIVE)],
        foreground=[("disabled", THEME_DIM)],
    )
    style.configure(
        "Link.TButton", background=THEME_BACKGROUND, foreground=THEME_GOLD_DIM,
        bordercolor=THEME_BACKGROUND, lightcolor=THEME_BACKGROUND, darkcolor=THEME_BACKGROUND,
        padding=(4, 2), font=FONT_SMALL, focuscolor=THEME_BACKGROUND,
    )
    style.map(
        "Link.TButton",
        foreground=[("disabled", THEME_DIM), ("active", THEME_GOLD)],
        background=[("active", THEME_BACKGROUND)],
        lightcolor=[("active", THEME_BACKGROUND)], darkcolor=[("active", THEME_BACKGROUND)],
        bordercolor=[("active", THEME_BACKGROUND)],
    )

    style.configure(
        "TCheckbutton", background=THEME_BACKGROUND, foreground=THEME_FOREGROUND,
        indicatorbackground=THEME_PANEL, indicatorforeground=THEME_FOREGROUND,
        indicatormargin=(0, 2, 8, 2), focuscolor=THEME_BACKGROUND, padding=(0, 2),
    )
    style.map(
        "TCheckbutton",
        background=[("active", THEME_BACKGROUND)],
        indicatorbackground=[("disabled", THEME_BACKGROUND), ("selected", THEME_BLOOD),
                             ("active", THEME_PANEL_HOVER)],
        indicatorforeground=[("disabled", THEME_DIM), ("selected", THEME_ON_BLOOD)],
        foreground=[("disabled", THEME_DIM)],
    )
    style.configure("Heading.TCheckbutton", font=("Segoe UI", 11, "bold"))

    style.configure(
        "Horizontal.TProgressbar", background=THEME_BLOOD, troughcolor=THEME_PANEL,
        bordercolor=THEME_PANEL, lightcolor=THEME_BLOOD, darkcolor=THEME_BLOOD, thickness=3,
    )
    style.configure(
        "Vertical.TScrollbar", background=THEME_BORDER, troughcolor=THEME_BACKGROUND,
        bordercolor=THEME_BACKGROUND, arrowcolor=THEME_MUTED, lightcolor=THEME_BORDER,
        darkcolor=THEME_BORDER, arrowsize=10, width=10,
    )
    style.map(
        "Vertical.TScrollbar",
        background=[("active", THEME_GOLD_DIM), ("disabled", THEME_BACKGROUND)],
        arrowcolor=[("disabled", THEME_BACKGROUND)],
    )
    # Scrollbars without arrows read as a modern thin track.
    try:
        style.layout(
            "Vertical.TScrollbar",
            [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
                ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"}),
            ]})],
        )
    except Exception:  # noqa: BLE001
        pass

    # The page switcher is a notebook with its tab strip removed: the sidebar
    # drives it, so clam never draws a tab box or a border around the client.
    style.configure(
        "Pages.TNotebook", background=THEME_BACKGROUND, bordercolor=THEME_BACKGROUND,
        lightcolor=THEME_BACKGROUND, darkcolor=THEME_BACKGROUND, borderwidth=0,
        tabmargins=(0, 0, 0, 0), padding=0,
    )
    style.configure(
        "Pages.TNotebook.Tab", background=THEME_BACKGROUND, foreground=THEME_MUTED,
        bordercolor=THEME_BACKGROUND, focuscolor=THEME_BACKGROUND, padding=(0, 0),
    )
    style.map(
        "Pages.TNotebook.Tab",
        background=[("selected", THEME_BACKGROUND), ("active", THEME_BACKGROUND)],
        foreground=[("selected", THEME_GOLD), ("active", THEME_FOREGROUND)],
    )
    try:
        style.layout("Pages.TNotebook.Tab", [])
        style.layout("Pages.TNotebook", [("Notebook.client", {"sticky": "nswe"})])
    except Exception:  # noqa: BLE001
        pass
    style.configure("TLabelframe", background=THEME_BACKGROUND, bordercolor=THEME_BORDER_SOFT)
    style.configure("TLabelframe.Label", background=THEME_BACKGROUND, foreground=THEME_GOLD_DIM,
                    font=FONT_CAPTION)


# --- widget helpers -------------------------------------------------------


def text_well(tk: Any, parent: Any, **kwargs: Any) -> Any:
    """A read-only log/status text area in the panel colour, no bevel."""
    options = dict(
        wrap="word", state="disabled", relief="flat", borderwidth=0, highlightthickness=0,
        bg=THEME_PANEL, fg=THEME_FOREGROUND, insertbackground=THEME_FOREGROUND,
        selectbackground=THEME_BLOOD, selectforeground=THEME_FOREGROUND,
        font=FONT_MONO, padx=10, pady=8,
    )
    options.update(kwargs)
    return tk.Text(parent, **options)


def autohide(bar: Any) -> Callable[[str, str], None]:
    """A ``yscrollcommand`` that shows ``bar`` only when there is overflow."""
    def _command(first: str, last: str) -> None:
        if float(first) <= 0.0 and float(last) >= 1.0:
            bar.grid_remove()
        else:
            bar.grid()
        bar.set(first, last)
    return _command


def section(ttk: Any, parent: Any, row: int, title: str, *, columnspan: int = 3,
            first: bool = False) -> int:
    """An uppercase gold caption over a hairline; returns the next free row."""
    ttk.Label(parent, text=title.upper(), style="Section.TLabel").grid(
        row=row, column=0, columnspan=columnspan, sticky="w", pady=((0 if first else 18), 2)
    )
    ttk.Frame(parent, height=1, style="Panel.TFrame").grid(
        row=row + 1, column=0, columnspan=columnspan, sticky="ew", pady=(0, 8)
    )
    return row + 2


def field(ttk: Any, parent: Any, row: int, label: str, variable: Any, *,
          browse: Callable[[], None] | None = None, browse_text: str = "Browse…",
          trailing: str | None = None, entry_kwargs: dict | None = None):
    """Label | entry | (browse button or muted trailing note). Returns widgets."""
    name = ttk.Label(parent, text=label, style="Field.TLabel")
    name.grid(row=row, column=0, sticky="w", padx=(0, 14), pady=4)
    entry = ttk.Entry(parent, textvariable=variable, **(entry_kwargs or {}))
    entry.grid(row=row, column=1, sticky="ew", pady=4)
    button = None
    if browse is not None:
        button = ttk.Button(parent, text=browse_text, command=browse, style="Ghost.TButton")
        button.grid(row=row, column=2, padx=(8, 0), pady=4, sticky="ew")
    elif trailing:
        ttk.Label(parent, text=trailing, style="Dim.TLabel").grid(
            row=row, column=2, sticky="w", padx=(10, 0)
        )
    return name, entry, button


def option(ttk: Any, parent: Any, row: int, text: str, variable: Any, *,
           caption: str | None = None, command: Callable[[], None] | None = None,
           columnspan: int = 3, indent: int = 0):
    """A checkbox with an optional one-line caption under it.

    Returns ``(checkbutton, row_frame)``: the button for enable/disable, the
    frame for show/hide, so a caption never outlives its control.
    """
    holder = ttk.Frame(parent)
    holder.grid(row=row, column=0, columnspan=columnspan, sticky="ew", padx=(indent, 0), pady=(2, 2))
    holder.columnconfigure(0, weight=1)
    box = ttk.Checkbutton(holder, text=text, variable=variable, command=command)
    box.grid(row=0, column=0, sticky="w")
    if caption:
        ttk.Label(holder, text=caption, style="Dim.TLabel").grid(
            row=1, column=0, sticky="w", padx=(26, 0), pady=(0, 2)
        )
    return box, holder


def scroll_page(tk: Any, ttk: Any, host: Any, *, padding: tuple[int, int, int, int] = (28, 22, 28, 22)) -> Any:
    """Fill ``host`` with a themed vertical-scrolling body frame and return it.

    The wheel is bound while the pointer is over this page only, so stacked
    pages never fight over it.  The body tracks the canvas width, so entries
    stretch and captions wrap with the window.
    """
    host.columnconfigure(0, weight=1)
    host.rowconfigure(0, weight=1)
    canvas = tk.Canvas(host, highlightthickness=0, borderwidth=0, background=THEME_BACKGROUND)
    canvas.grid(row=0, column=0, sticky="nsew")
    bar = ttk.Scrollbar(host, orient="vertical", command=canvas.yview)
    bar.grid(row=0, column=1, sticky="ns")
    canvas.configure(yscrollcommand=bar.set)
    body = ttk.Frame(canvas, padding=padding)
    body.columnconfigure(1, weight=1)
    window = canvas.create_window((0, 0), window=body, anchor="nw")

    def _resize_body(_event: Any = None) -> None:
        canvas.configure(scrollregion=canvas.bbox("all"))
        # Hide the bar when everything fits; a scrollbar on a short page is
        # noise. Compare against the canvas's real height, which is 1 until
        # it is mapped, so the decision is re-made on every canvas resize.
        height = canvas.winfo_height()
        if height <= 1:
            return
        if body.winfo_reqheight() > height:
            bar.grid()
        else:
            bar.grid_remove()
            canvas.yview_moveto(0)

    body.bind("<Configure>", _resize_body)
    canvas.bind(
        "<Configure>",
        lambda event: (canvas.itemconfigure(window, width=event.width), _resize_body()),
    )

    def _wheel(event: Any) -> str:
        if body.winfo_reqheight() > canvas.winfo_height():
            canvas.yview_scroll(-int(event.delta / 120), "units")
        return "break"

    canvas.bind("<Enter>", lambda _e: canvas.bind_all("<MouseWheel>", _wheel))
    canvas.bind("<Leave>", lambda _e: canvas.unbind_all("<MouseWheel>"))
    return body


def page_header(ttk: Any, body: Any, title: str, caption: str | None = None) -> int:
    ttk.Label(body, text=title, style="Title.TLabel").grid(
        row=0, column=0, columnspan=3, sticky="w"
    )
    if caption:
        ttk.Label(body, text=caption, style="Muted.TLabel").grid(
            row=1, column=0, columnspan=3, sticky="w", pady=(2, 14)
        )
        return 2
    return 1


class Sidebar:
    """The left navigation rail: brand, page list, live health, version.

    It drives a tab-less ``ttk.Notebook``: clicking an item selects the tab,
    and ``<<NotebookTabChanged>>`` keeps the highlight honest when code
    selects a page (a finished seed generation jumps back to Play).
    """

    def __init__(self, tk: Any, ttk: Any, parent: Any, notebook: Any, *,
                 brand: str, product: str, version: str) -> None:
        self.tk = tk
        self.notebook = notebook
        self.items: dict[str, tuple[Any, Any, Any]] = {}
        rail = tk.Frame(parent, bg=THEME_SIDEBAR, width=SIDEBAR_WIDTH)
        rail.grid(row=0, column=0, sticky="nsw")
        rail.grid_propagate(False)
        rail.columnconfigure(0, weight=1)
        rail.rowconfigure(2, weight=1)
        self.rail = rail

        brand_block = tk.Frame(rail, bg=THEME_SIDEBAR)
        brand_block.grid(row=0, column=0, sticky="ew", padx=16, pady=(24, 18))
        tk.Label(
            brand_block, text=" ".join(brand.upper()), bg=THEME_SIDEBAR, fg=THEME_GOLD_DIM,
            font=FONT_CAPTION, anchor="w",
        ).pack(fill="x")
        tk.Label(
            brand_block, text=product, bg=THEME_SIDEBAR, fg=THEME_GOLD,
            font=FONT_BRAND, anchor="w",
        ).pack(fill="x")
        tk.Frame(brand_block, bg=THEME_BLOOD, height=2).pack(fill="x", pady=(10, 0))

        self.nav = tk.Frame(rail, bg=THEME_SIDEBAR)
        self.nav.grid(row=1, column=0, sticky="ew")

        footer = tk.Frame(rail, bg=THEME_SIDEBAR)
        footer.grid(row=3, column=0, sticky="ew", padx=20, pady=(12, 18))
        footer.columnconfigure(1, weight=1)
        self.dot = tk.Canvas(footer, width=10, height=10, bg=THEME_SIDEBAR, highlightthickness=0)
        self.dot.grid(row=0, column=0, sticky="nw", pady=(4, 0))
        self._dot = self.dot.create_oval(1, 1, 9, 9, fill=THEME_DIM, outline="")
        self.health = tk.Label(
            footer, text="", bg=THEME_SIDEBAR, fg=THEME_MUTED, font=FONT_SMALL,
            anchor="w", justify="left", wraplength=SIDEBAR_WIDTH - 60,
        )
        self.health.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        tk.Label(
            footer, text=version, bg=THEME_SIDEBAR, fg=THEME_DIM, font=FONT_SMALL, anchor="w",
        ).grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        notebook.bind("<<NotebookTabChanged>>", lambda _e: self._sync(), add="+")

    def populate(self) -> None:
        """Build one item per notebook page, in the notebook's order."""
        for child in self.nav.winfo_children():
            child.destroy()
        self.items.clear()
        for tab in self.notebook.tabs():
            label = self.notebook.tab(tab, "text")
            row = self.tk.Frame(self.nav, bg=THEME_SIDEBAR, cursor="hand2")
            row.pack(fill="x")
            marker = self.tk.Frame(row, bg=THEME_SIDEBAR, width=3)
            marker.pack(side="left", fill="y")
            text = self.tk.Label(
                row, text=label, bg=THEME_SIDEBAR, fg=THEME_MUTED, font=FONT_NAV,
                anchor="w", padx=17, pady=9,
            )
            text.pack(side="left", fill="x", expand=True)
            for widget in (row, marker, text):
                widget.bind("<Button-1>", lambda _e, t=tab: self.notebook.select(t))
                widget.bind("<Enter>", lambda _e, t=tab: self._hover(t, True))
                widget.bind("<Leave>", lambda _e, t=tab: self._hover(t, False))
            self.items[tab] = (row, marker, text)
        self._sync()

    def _hover(self, tab: str, inside: bool) -> None:
        if tab == self.notebook.select():
            return
        row, marker, text = self.items[tab]
        colour = THEME_PANEL if inside else THEME_SIDEBAR
        for widget in (row, marker, text):
            widget.configure(bg=colour)
        text.configure(fg=THEME_FOREGROUND if inside else THEME_MUTED)

    def _sync(self) -> None:
        current = self.notebook.select()
        for tab, (row, marker, text) in self.items.items():
            active = tab == current
            colour = THEME_PANEL if active else THEME_SIDEBAR
            row.configure(bg=colour)
            text.configure(bg=colour, fg=THEME_GOLD if active else THEME_MUTED)
            marker.configure(bg=THEME_GOLD if active else colour)

    def set_health(self, text: str) -> None:
        self.health.configure(text=text)
        self.dot.itemconfigure(self._dot, fill=health_tone(text))


def health_tone(text: str) -> str:
    """Map a client-health sentence to the dot colour; wording is the API."""
    lowered = text.lower()
    if "delivery ready" in lowered or lowered.startswith("ready"):
        return THEME_OK
    if any(word in lowered for word in ("not running", "no live status", "not connected",
                                        "stopped", "unresponsive", "disconnected", "did not")):
        return THEME_BAD
    if any(word in lowered for word in ("running", "waiting", "connecting", "building",
                                        "checking", "paused", "unverified", "no prepared")):
        return THEME_WARN
    return THEME_DIM


class Dialogs:
    """A themed drop-in for ``tkinter.messagebox``.

    Same call shape as the stock module (``showerror(title, message, parent=...)``,
    ``askyesno(...) -> bool``) so every existing ``self.messagebox.showerror(...)``
    call site works unchanged; only what ``self.messagebox`` points at changes.
    The stock dialogs render as an unthemed white OS window no matter how dark
    the rest of the app is, which is exactly the jarring flash this replaces.
    """

    _KIND_STYLE = {
        "error": (THEME_BAD, "✕"),      # heavy multiplication x
        "warning": (THEME_WARN, "⚠"),   # warning sign
        "info": (THEME_GOLD, "ℹ"),      # information source
        "question": (THEME_GOLD, "?"),
    }

    def __init__(self, tk: Any, ttk: Any, default_parent: Any) -> None:
        self.tk = tk
        self.ttk = ttk
        self.default_parent = default_parent

    def showerror(self, title: str, message: str, *, parent: Any = None) -> None:
        self._modal("error", title, message, parent, buttons=("OK",))

    def showwarning(self, title: str, message: str, *, parent: Any = None) -> None:
        self._modal("warning", title, message, parent, buttons=("OK",))

    def showinfo(self, title: str, message: str, *, parent: Any = None) -> None:
        self._modal("info", title, message, parent, buttons=("OK",))

    def askyesno(self, title: str, message: str, *, parent: Any = None) -> bool:
        choice = self._modal("question", title, message, parent, buttons=("No", "Yes"))
        return choice == "Yes"

    def _modal(self, kind: str, title: str, message: str, parent: Any, *, buttons: tuple[str, ...]) -> str | None:
        tk, ttk = self.tk, self.ttk
        owner = parent or self.default_parent
        colour, glyph = self._KIND_STYLE[kind]
        window = tk.Toplevel(owner)
        window.withdraw()
        window.title(title)
        window.transient(owner)
        window.resizable(False, False)
        window.configure(bg=THEME_BACKGROUND)
        window.protocol("WM_DELETE_WINDOW", lambda: None)

        outer = ttk.Frame(window, padding=20)
        outer.grid(row=0, column=0, sticky="nsew")
        window.columnconfigure(0, weight=1)
        window.rowconfigure(0, weight=1)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        badge = tk.Canvas(header, width=28, height=28, bg=THEME_BACKGROUND, highlightthickness=0)
        badge.grid(row=0, column=0, sticky="n", padx=(0, 14))
        badge.create_oval(1, 1, 27, 27, fill=colour, outline="")
        badge.create_text(14, 15, text=glyph, fill=THEME_BACKGROUND, font=("Segoe UI", 12, "bold"))
        ttk.Label(header, text=title, style="Title.TLabel", font=("Georgia", 15)).grid(
            row=0, column=1, sticky="w"
        )

        # Long text (a traceback, a multi-line doctor report) gets a scrolling
        # read-only well instead of an unbounded Label, so the window never
        # grows past the screen and short text never grows a needless scrollbar.
        lines = message.count("\n") + 1
        body_height = min(max(lines, 2), 14)
        body_frame = ttk.Frame(outer)
        body_frame.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        body_frame.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1)
        body = text_well(tk, body_frame, height=body_height, width=56)
        body.configure(state="normal")
        body.insert("1.0", message.rstrip())
        body.configure(state="disabled")
        body.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(body_frame, orient="vertical", command=body.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        body.configure(yscrollcommand=autohide(scrollbar))

        result: dict[str, str] = {}

        def choose(value: str) -> None:
            result["value"] = value
            window.destroy()

        actions = ttk.Frame(outer)
        actions.grid(row=2, column=0, sticky="e", pady=(16, 0))
        default_button = None
        for index, label in enumerate(buttons):
            style = "Accent.TButton" if index == len(buttons) - 1 else "Ghost.TButton"
            button = ttk.Button(actions, text=label, style=style, command=lambda v=label: choose(v))
            button.grid(row=0, column=index, padx=(8 if index else 0, 0))
            default_button = button
        window.bind("<Return>", lambda _e: choose(buttons[-1]))
        window.bind("<Escape>", lambda _e: choose(buttons[0]))

        window.update_idletasks()
        if owner is not None and owner.winfo_viewable():
            x = owner.winfo_rootx() + (owner.winfo_width() - window.winfo_reqwidth()) // 2
            y = owner.winfo_rooty() + (owner.winfo_height() - window.winfo_reqheight()) // 3
            window.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        window.deiconify()
        window.lift()
        window.grab_set()
        window.focus_set()
        if default_button is not None:
            default_button.focus_set()
        window.wait_window()
        return result.get("value")


def enable_dark_titlebar(window: Any) -> None:
    """Ask Windows to draw ``window``'s native title bar in dark mode.

    Without this, every Tk top-level (the main window, every themed dialog,
    every settings Toplevel) keeps the stock light title bar and border no
    matter how dark the body is -- exactly the washed-out strip across the
    top of an otherwise dark window. Windows-only and best-effort: any
    failure here is cosmetic, never worth losing the window over.
    """
    import sys

    if sys.platform != "win32":
        return
    try:
        import ctypes

        window.update_idletasks()
        # winfo_id() on Tk/Windows returns the drawing-surface HWND, a child
        # of the real decorated frame; GetParent walks up to that frame,
        # which is the window DWM actually paints a title bar for.
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        # 20 on Windows 10 2004+/11; 19 on the original 1809-1909 builds.
        for attribute in (20, 19):
            value = ctypes.c_int(1)
            result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd, attribute, ctypes.byref(value), ctypes.sizeof(value)
            )
            if result == 0:
                break
    except Exception:  # noqa: BLE001 - title bar colour is cosmetic only
        pass
