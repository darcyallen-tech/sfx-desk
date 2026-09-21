"""SFX Desk main window â€” compact always-on-top companion."""
from __future__ import annotations

import threading
import webbrowser
from datetime import datetime, timezone
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

import customtkinter as ctk

from app.engines.base import (
    empty_cuda_cache,
    moss_gguf_vram_status,
    moss_vram_status,
    probe_vram,
    woosh_vram_status,
    woosh_flow_vram_status,
)
from app.generate import DEFAULT_CFG, DEFAULT_STEPS, generate_sfx, unload_all, unload_gguf_server, unload_torch_engines
from app.library import SfxLibrary
from app.prompt_builder import (
    INTENSITIES,
    MICS,
    SPEEDS,
    SPACES,
    TEXTURES,
    TYPES,
    build_prompt,
    default_negative_prompt,
    migrate_space_mic,
)
from app import __version__
from app import settings as prefs
from app.update_check import check_for_update
from app.setup_check import SA3_LICENSE_URL, check_setup

try:
    import sounddevice as sd
    import soundfile as sf
except Exception:  # pragma: no cover
    sd = None
    sf = None

ENGINE_LABELS = [
    "SA3 Small-SFX",
    "MOSS v2",
    "Woosh DFlow",
    "Woosh Flow",
]
ENGINE_KEYS = {
    "SA3 Small-SFX": "sa3",
    "MOSS v2": "moss",
    "MOSS GGUF (SLOWER)": "moss_gguf",
    "Woosh DFlow": "woosh_dflow",
    "Woosh Flow": "woosh_flow",
}

FAT_MIN = (300, 420)
SKINNY_MIN = (300, 280)
FAT_SIZE = "340x635"
SKINNY_SIZE = "340x405"


class SfxDeskApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"SFX Desk {__version__}")
        self._cfg = prefs.load()

        self.geometry(str(self._cfg.get("geometry") or FAT_SIZE))
        self.minsize(*FAT_MIN)
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        self.library = SfxLibrary()
        self.always_on_top = tk.BooleanVar(value=bool(self._cfg.get("always_on_top", True)))
        self.keep_loaded = tk.BooleanVar(value=bool(self._cfg.get("keep_loaded", True)))
        self.batch_count = tk.IntVar(value=int(self._cfg.get("batch_count", 1) or 1))
        self.fav_only = tk.BooleanVar(value=bool(self._cfg.get("fav_only", False)))
        self.auto_send = tk.BooleanVar(value=bool(self._cfg.get("auto_send", False)))
        self.skinny = tk.BooleanVar(value=bool(self._cfg.get("skinny", False)))
        self.moss_force = tk.BooleanVar(value=bool(self._cfg.get("moss_force_enable", False)))
        self._vram_info = probe_vram()
        self._moss = moss_vram_status(force_enable=bool(self.moss_force.get()), info=self._vram_info)
        self._gguf = moss_gguf_vram_status(force_enable=False, info=self._vram_info)
        self._woosh = woosh_vram_status(force_enable=False, info=self._vram_info)
        self._woosh_flow = woosh_flow_vram_status(force_enable=False, info=self._vram_info)
        self.selected_id: int | None = None
        self.last_wav: Path | None = None
        self.busy = False
        self.clip_rows: list[dict] = []
        self._fat_geometry = str(self._cfg.get("geometry") or FAT_SIZE)
        self._skinny_geometry = str(self._cfg.get("skinny_geometry") or SKINNY_SIZE)
        self._update_url: str | None = None

        self._build()
        self._apply_saved_builder()
        self._bind_hotkeys()
        self._apply_topmost()
        self._sync_prompt()
        self._refresh_library()
        self._apply_skinny(initial=True)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        # CTk can boot at a stub size before layout settles
        self.after(100, self._force_geometry)
        self.after(150, self._boot_vram_status)
        self.after(400, self._maybe_setup_nudge)
        self.after(2500, lambda: self._schedule_update_check(force=False))

    def _force_geometry(self) -> None:
        geo = self._skinny_geometry if self.skinny.get() else self._fat_geometry
        try:
            size = geo.split("+")[0]
            cur = self.geometry()
            if "+" in cur:
                self.geometry(f"{size}+{cur.split('+', 1)[1]}")
            else:
                self.geometry(size)
        except Exception:
            self.geometry(SKINNY_SIZE if self.skinny.get() else FAT_SIZE)

    def _engine_key(self) -> str:
        return ENGINE_KEYS.get(self.engine.get(), "sa3")

    def _typing_focus(self) -> bool:
        w = self.focus_get()
        if w is None:
            return False
        name = w.winfo_class()
        low = name.lower()
        return name in {"Text", "Entry", "TEntry"} or "text" in low or "entry" in low

    def _set_status(self, msg: str) -> None:
        self.status.configure(text=msg)
        self.update_idletasks()

    def _build(self) -> None:
        pad = {"padx": 6, "pady": 2}
        tiny = ctk.CTkFont(size=11)

        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=6, pady=(6, 2))
        ctk.CTkLabel(top, text="SFX Desk", font=ctk.CTkFont(size=14, weight="bold")).pack(
            side="left", padx=4
        )
        ctk.CTkLabel(
            top, text=f"v{__version__}", font=ctk.CTkFont(size=10), text_color="gray"
        ).pack(side="left", padx=(0, 4))
        ctk.CTkButton(
            top,
            text="Check",
            width=28,
            height=24,
            command=lambda: self._schedule_update_check(force=True),
        ).pack(side="left", padx=2)
        ctk.CTkCheckBox(
            top, text="Skinny", variable=self.skinny, command=self._toggle_skinny, width=70
        ).pack(side="right", padx=2)
        ctk.CTkCheckBox(
            top, text="On top", variable=self.always_on_top, command=self._apply_topmost, width=70
        ).pack(side="right", padx=2)

        row = ctk.CTkFrame(self)
        row.pack(fill="x", **pad)
        self.engine = ctk.CTkOptionMenu(
            row, values=ENGINE_LABELS, command=self._on_engine_change, width=178, height=26
        )
        eng = str(self._cfg.get("engine") or ENGINE_LABELS[0])
        self.engine.set(eng if eng in ENGINE_LABELS else ENGINE_LABELS[0])
        self.engine.pack(side="left", padx=(6, 4), pady=4)
        ctk.CTkCheckBox(row, text="Keep", variable=self.keep_loaded, width=55).pack(
            side="left", padx=2
        )
        self.moss_force_cb = ctk.CTkCheckBox(
            row, text="Force MOSS", variable=self.moss_force, command=self._on_moss_force, width=90
        )
        self.moss_force_cb.pack(side="left", padx=2)
        ctk.CTkButton(row, text="Unload", width=58, height=26, command=self._unload).pack(
            side="right", padx=(2, 6), pady=4
        )
        ctk.CTkButton(row, text="Cache", width=52, height=26, command=self._clear_cache).pack(
            side="right", padx=2, pady=4
        )

        grid = ctk.CTkFrame(self)
        grid.pack(fill="x", **pad)
        specs = [
            ("Type", "kind", TYPES, "whoosh"),
            ("Tex", "texture", TEXTURES, "airy"),
            ("Space", "space", SPACES, "dry"),
            ("Mic", "mic", MICS, "natural"),
            ("Speed", "speed", SPEEDS, "fast"),
            ("Power", "intensity", INTENSITIES, "medium"),
        ]
        for i, (label, attr, values, default) in enumerate(specs):
            r, c = divmod(i, 2)
            cell = ctk.CTkFrame(grid, fg_color="transparent")
            cell.grid(row=r, column=c, sticky="ew", padx=4, pady=2)
            ctk.CTkLabel(cell, text=label, font=tiny, width=40).pack(side="left")
            menu = ctk.CTkOptionMenu(
                cell, values=values, command=lambda _v: self._sync_prompt(), height=26
            )
            menu.set(default if default in values else values[0])
            menu.pack(side="left", fill="x", expand=True)
            setattr(self, attr, menu)
        grid.columnconfigure(0, weight=1)
        grid.columnconfigure(1, weight=1)

        extra_row = ctk.CTkFrame(self, fg_color="transparent")
        extra_row.pack(fill="x", padx=6, pady=(1, 2))
        ctk.CTkLabel(extra_row, text="Extra", font=tiny, width=40).pack(side="left")
        self.extra = ctk.CTkEntry(
            extra_row,
            placeholder_text="optional detail, e.g. glass debris trail",
            height=26,
        )
        self.extra.pack(side="left", fill="x", expand=True, padx=(4, 4))
        self.extra.bind("<KeyRelease>", lambda _evt: self._sync_prompt())

        dur = ctk.CTkFrame(self, fg_color="transparent")
        dur.pack(fill="x", padx=6, pady=2)
        ctk.CTkLabel(dur, text="Dur", font=tiny, width=28).pack(side="left")
        self.duration = ctk.CTkSlider(
            dur, from_=1, to=15, number_of_steps=14, command=self._on_dur, height=16
        )
        self.duration.set(4)
        self.duration.pack(side="left", fill="x", expand=True, padx=4)
        self.duration_lbl = ctk.CTkLabel(dur, text="4.0s", width=40, font=tiny)
        self.duration_lbl.pack(side="left", padx=(0, 4))

        prompt_h = int(self._cfg.get("prompt_height", 72))
        prompt_h = max(44, min(280, prompt_h))
        self.prompt = ctk.CTkTextbox(self, height=prompt_h)
        self.prompt.pack(fill="x", padx=6, pady=(2, 0))
        self._prompt_height = prompt_h

        # Drag grip to resize prompt box height
        self._prompt_grip = ctk.CTkFrame(self, height=8, cursor="sb_v_double_arrow", fg_color="#2a3444")
        self._prompt_grip.pack(fill="x", padx=10, pady=(0, 2))
        self._prompt_grip.pack_propagate(False)
        grip_bar = ctk.CTkFrame(self._prompt_grip, height=2, width=36, fg_color="#6a7a90")
        grip_bar.place(relx=0.5, rely=0.5, anchor="center")
        for w in (self._prompt_grip, grip_bar):
            w.bind("<ButtonPress-1>", self._prompt_resize_start)
            w.bind("<B1-Motion>", self._prompt_resize_drag)
            w.bind("<ButtonRelease-1>", self._prompt_resize_end)

        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.pack(fill="x", padx=6, pady=2)
        self.gen_btn = ctk.CTkButton(
            actions, text="Generate", width=90, height=28, command=self._on_generate
        )
        self.gen_btn.pack(side="left", padx=2)
        ctk.CTkLabel(actions, text="Batch", font=tiny, width=40).pack(side="left", padx=(8, 2))
        self.batch_menu = ctk.CTkOptionMenu(
            actions,
            values=[str(i) for i in range(1, 9)],
            width=52,
            height=28,
            command=lambda v: self.batch_count.set(int(v)),
        )
        self.batch_menu.set(str(max(1, min(8, int(self.batch_count.get() or 1)))))
        self.batch_menu.pack(side="left", padx=2)
        ctk.CTkButton(actions, text="Play", width=56, height=28, command=self._play_last).pack(
            side="left", padx=2
        )
        ctk.CTkButton(
            actions, text="Send", width=56, height=28, command=self._send_resolve
        ).pack(side="left", padx=2)
        ctk.CTkCheckBox(actions, text="Auto-send", variable=self.auto_send, width=90).pack(
            side="right", padx=4
        )

        self.status = ctk.CTkLabel(
            self,
            text="Ready - Enter gen / Space play / S send",
            anchor="w",
            font=tiny,
            height=18,
            cursor="hand2",
        )
        self.status.pack(fill="x", padx=8, pady=(0, 2))
        self.status.bind("<Button-1>", self._on_status_click)
        self.status.bind("<Button-3>", lambda _e: self._schedule_update_check(force=True))

        self.lib_frame = ctk.CTkFrame(self)
        self.lib_frame.pack(fill="both", expand=True, padx=6, pady=(2, 6))

        filters = ctk.CTkFrame(self.lib_frame, fg_color="transparent")
        filters.pack(fill="x", padx=4, pady=4)
        self.cat = ctk.CTkOptionMenu(
            filters,
            values=["all"] + TYPES,
            command=lambda _v: self._refresh_library(),
            width=90,
            height=26,
        )
        self.cat.set("all")
        self.cat.pack(side="left", padx=2)
        ctk.CTkCheckBox(
            filters, text="Fav", variable=self.fav_only, command=self._refresh_library, width=45
        ).pack(side="left", padx=2)
        self.search = ctk.CTkEntry(filters, placeholder_text="Search...", height=26)
        self.search.pack(side="left", fill="x", expand=True, padx=2)
        self.search.bind("<KeyRelease>", lambda _e: self._refresh_library())

        self.listbox = tk.Listbox(
            self.lib_frame,
            height=6,
            bg="#1e1e1e",
            fg="#ddd",
            selectmode=tk.EXTENDED,
            font=("Segoe UI", 9),
        )
        self.listbox.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.listbox.bind("<<ListboxSelect>>", self._on_select)

        lib_btns = ctk.CTkFrame(self.lib_frame, fg_color="transparent")
        lib_btns.pack(fill="x", padx=4, pady=(0, 4))
        ctk.CTkButton(lib_btns, text="Fav", width=50, height=26, command=self._toggle_fav).pack(
            side="left", padx=2
        )
        ctk.CTkButton(lib_btns, text="Play", width=50, height=26, command=self._play_selected).pack(
            side="left", padx=2
        )
        ctk.CTkButton(
            lib_btns, text="Del", width=50, height=26, command=self._delete_selected
        ).pack(side="left", padx=2)
        ctk.CTkLabel(
            lib_btns, text="Ctrl+click multi / bin only", text_color="gray", font=tiny
        ).pack(side="right", padx=4)

    def _apply_saved_builder(self) -> None:
        cfg = self._cfg
        saved_space, saved_mic = migrate_space_mic(
            str(cfg.get("space", "dry")), str(cfg.get("mic", "natural"))
        )
        saved_values = {
            "kind": str(cfg.get("kind", "")),
            "texture": str(cfg.get("texture", "")),
            "space": saved_space,
            "mic": saved_mic,
            "speed": str(cfg.get("speed", "")),
            "intensity": str(cfg.get("intensity", "medium")),
        }
        for attr, choices in (
            ("kind", TYPES),
            ("texture", TEXTURES),
            ("space", SPACES),
            ("mic", MICS),
            ("speed", SPEEDS),
            ("intensity", INTENSITIES),
        ):
            val = saved_values.get(attr, "")
            widget = getattr(self, attr)
            if val in choices:
                widget.set(val)
        extra = str(cfg.get("extra", ""))
        if extra:
            self.extra.insert(0, extra)
        try:
            dur = float(cfg.get("duration", 4.0))
        except (TypeError, ValueError):
            dur = 4.0
        dur = max(1.0, min(15.0, dur))
        self.duration.set(dur)
        self.duration_lbl.configure(text=f"{dur:.1f}s")
        cat = str(cfg.get("category", "all"))
        if cat in (["all"] + TYPES):
            self.cat.set(cat)

    def _bind_hotkeys(self) -> None:
        self.bind("<Return>", self._hot_generate)
        self.bind("<KP_Enter>", self._hot_generate)
        self.bind("<Control-Return>", self._hot_generate)
        self.bind("<space>", self._hot_play)
        self.bind("<KeyPress-s>", self._hot_send)
        self.bind("<KeyPress-S>", self._hot_send)

    def _hot_generate(self, evt=None):
        if evt is not None and getattr(evt, "keysym", "") == "Return" and self._typing_focus():
            if not (evt.state & 0x4):
                return None
        self._on_generate()
        return "break"

    def _hot_play(self, _evt=None):
        if self._typing_focus():
            return None
        self._play_last()
        return "break"

    def _hot_send(self, _evt=None):
        if self._typing_focus():
            return None
        self._send_resolve()
        return "break"

    def _toggle_skinny(self) -> None:
        self._apply_skinny(initial=False)

    def _apply_skinny(self, initial: bool = False) -> None:
        def _with_pos(size_geo: str) -> str:
            size = size_geo.split("+")[0] if "+" in size_geo else size_geo
            try:
                cur = self.geometry()
                if "+" in cur:
                    return f"{size}+{cur.split('+', 1)[1]}"
            except Exception:
                pass
            return size

        if self.skinny.get():
            if not initial:
                try:
                    self._fat_geometry = self.geometry()
                except Exception:
                    pass
            self.lib_frame.pack_forget()
            self.minsize(*SKINNY_MIN)
            self.geometry(_with_pos(self._skinny_geometry))
            self._set_status("Skinny - Enter gen / Space play / S send")
        else:
            if not initial:
                try:
                    self._skinny_geometry = self.geometry()
                except Exception:
                    pass
            # Always re-pack so the library reliably returns
            self.lib_frame.pack_forget()
            self.lib_frame.pack(fill="both", expand=True, padx=6, pady=(2, 6))
            self.minsize(*FAT_MIN)
            self.geometry(_with_pos(self._fat_geometry))
            self._set_status("Ready - Enter gen / Space play / S send")

    def _safe_geo(self, value: str, fallback: str) -> str:
        try:
            size = str(value).split("+")[0]
            w, h = size.lower().split("x", 1)
            wi, hi = int(float(w)), int(float(h))
            if wi < 280 or hi < 250:
                return fallback
            if "+" in str(value):
                return f"{wi}x{hi}+" + str(value).split("+", 1)[1]
            return f"{wi}x{hi}"
        except Exception:
            return fallback

    def _collect_settings(self) -> dict:
        try:
            geo = self.geometry()
        except Exception:
            geo = FAT_SIZE
        if self.skinny.get():
            skinny_geo = geo
            fat_geo = self._fat_geometry
        else:
            fat_geo = geo
            skinny_geo = self._skinny_geometry
        return {
            "geometry": self._safe_geo(fat_geo, FAT_SIZE),
            "skinny_geometry": self._safe_geo(skinny_geo, SKINNY_SIZE),
            "skinny": bool(self.skinny.get()),
            "engine": self.engine.get(),
            "keep_loaded": bool(self.keep_loaded.get()),
            "batch_count": max(1, min(8, int(self.batch_count.get() or 1))),
            "always_on_top": bool(self.always_on_top.get()),
            "auto_send": bool(self.auto_send.get()),
            "moss_force_enable": bool(self.moss_force.get()),
            "moss_gguf_server": str(self._cfg.get("moss_gguf_server", "")),
            "moss_gguf_model": str(self._cfg.get("moss_gguf_model", "")),
            "moss_gguf_port": int(self._cfg.get("moss_gguf_port") or 8765),
            "woosh_models_root": str(self._cfg.get("woosh_models_root", "")),
            "duration": float(self.duration.get()),
            "kind": self.kind.get(),
            "texture": self.texture.get(),
            "space": self.space.get(),
            "mic": self.mic.get(),
            "speed": self.speed.get(),
            "intensity": self.intensity.get(),
            "extra": self.extra.get().strip(),
            "prompt_height": int(getattr(self, "_prompt_height", 72)),
            "category": self.cat.get(),
            "fav_only": bool(self.fav_only.get()),
            "check_updates": bool(self._cfg.get("check_updates", True)),
            "skipped_update": str(self._cfg.get("skipped_update", "")),
            "last_update_check": str(self._cfg.get("last_update_check", "")),
        }

    def _on_close(self) -> None:
        prefs.save(self._collect_settings())
        # Stop orphan moss-tts-server so next launch does not look pre-loaded.
        try:
            unload_gguf_server()
        except Exception:
            pass
        self.destroy()



    def _schedule_update_check(self, force: bool = False) -> None:
        if not force and not bool(self._cfg.get("check_updates", True)):
            return
        if not force:
            last = str(self._cfg.get("last_update_check") or "")
            if last:
                try:
                    prev = datetime.fromisoformat(last)
                    if prev.tzinfo is None:
                        prev = prev.replace(tzinfo=timezone.utc)
                    age = datetime.now(timezone.utc) - prev
                    if age.total_seconds() < 12 * 3600:
                        return
                except Exception:
                    pass
        if force:
            self._set_status("Checking for updates...")

        def work() -> None:
            info = check_for_update(__version__)
            self.after(0, lambda: self._on_update_result(info, force=force))

        threading.Thread(target=work, daemon=True).start()

    def _on_update_result(self, info, force: bool = False) -> None:
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        self._cfg["last_update_check"] = now
        try:
            prefs.save(self._collect_settings())
        except Exception:
            pass
        if info is None:
            self._update_url = None
            if force:
                self._set_status(f"Up to date (v{__version__})")
            return
        skipped = str(self._cfg.get("skipped_update") or "")
        tag = str(getattr(info, "tag", "") or "")
        if tag and tag.lstrip("v") == skipped.lstrip("v") and not force:
            return
        self._update_url = info.html_url
        self._set_status(f"Update {tag} available - click status to open")

    def _on_status_click(self, _event=None) -> None:
        url = getattr(self, "_update_url", None)
        if url:
            try:
                webbrowser.open(url)
            except Exception:
                pass

    def _maybe_setup_nudge(self) -> None:
        try:
            st = check_setup()
        except Exception:
            return
        if st.ready_for_sa3:
            return
        # One soft dialog â€” never stores tokens
        msg = "Setup incomplete:\n\n" + "\n".join(f"- {m}" for m in st.messages[:5])
        msg += (
            "\n\nOpen the SA3 license page now?\n"
            "Then run scripts\\hf_login.bat (browser login preferred)."
        )
        if messagebox.askyesno("SFX Desk setup", msg):
            import webbrowser
            webbrowser.open(SA3_LICENSE_URL)

    def _boot_vram_status(self) -> None:
        self._refresh_moss_gate(announce=True)

    def _refresh_moss_gate(self, announce: bool = False) -> None:
        self._vram_info = probe_vram()
        self._moss = moss_vram_status(
            force_enable=bool(self.moss_force.get()), info=self._vram_info
        )
        self._gguf = moss_gguf_vram_status(force_enable=False, info=self._vram_info)
        self._woosh = woosh_vram_status(force_enable=False, info=self._vram_info)
        self._woosh_flow = woosh_flow_vram_status(force_enable=False, info=self._vram_info)
        try:
            if self._moss["enough"]:
                self.moss_force_cb.pack_forget()
                if self.moss_force.get():
                    self.moss_force.set(False)
            else:
                if not self.moss_force_cb.winfo_ismapped():
                    self.moss_force_cb.pack(side="left", padx=2)
        except Exception:
            pass
        key = self._engine_key()
        if key == "moss" and not self._moss["unlocked"]:
            self.engine.set(ENGINE_LABELS[0])
            self._sync_prompt()
        if announce:
            gpu = self._vram_info.get("message") or "GPU unknown"
            self._set_status(f"{gpu} | {self._moss['tip']}")

    def _on_moss_force(self) -> None:
        if self.moss_force.get():
            ok = messagebox.askyesno(
                "SFX Desk",
                "Enable MOSS anyway?\n\n"
                "MOSS needs ~16 GB VRAM. On 16 GB cards: close Resolve, generate, "
                "Unload, then open Resolve and Send.\n\n"
                "~24 GB is comfortable keeping Resolve open.\n\n"
                "Continue?",
            )
            if not ok:
                self.moss_force.set(False)
        self._refresh_moss_gate(announce=True)

    def _on_engine_change(self, _value: str) -> None:
        key = ENGINE_KEYS.get(_value, "sa3")
        if key == "moss" and not self._moss.get("unlocked"):
            go = messagebox.askyesno(
                "SFX Desk",
                "MOSS needs ~16 GB VRAM.\n\n"
                f"{self._moss.get('tip', '')}\n\n"
                "Enable MOSS anyway (Force MOSS)?\n"
                "Otherwise stay on SA3 Small-SFX.",
            )
            if go:
                self.moss_force.set(True)
                self._moss = moss_vram_status(force_enable=True, info=self._vram_info)
                try:
                    if not self.moss_force_cb.winfo_ismapped():
                        self.moss_force_cb.pack(side="left", padx=2)
                except Exception:
                    pass
            else:
                self.engine.set(ENGINE_LABELS[0])
                self._sync_prompt()
                self._set_status(self._moss.get("tip", "Stay on SA3."))
                return
        if key == "moss_gguf" and not getattr(self, "_gguf", {}).get("unlocked", True):
            messagebox.showwarning(
                "SFX Desk",
                "MOSS GGUF needs ~12 GB VRAM.\n\n"
                f"{getattr(self, '_gguf', {}).get('tip', '')}",
            )
            self.engine.set(ENGINE_LABELS[0])
            self._sync_prompt()
            return
        if key == "woosh_dflow" and not getattr(self, "_woosh", {}).get("unlocked", True):
            messagebox.showwarning(
                "SFX Desk",
                "Woosh DFlow needs ~6 GB VRAM.\n\n"
                f"{getattr(self, '_woosh', {}).get('tip', '')}",
            )
            self.engine.set(ENGINE_LABELS[0])
            self._sync_prompt()
            return
        if key == "woosh_flow" and not getattr(self, "_woosh_flow", {}).get("unlocked", True):
            messagebox.showwarning(
                "SFX Desk",
                "Woosh Flow needs ~10 GB VRAM.\n\n"
                f"{getattr(self, '_woosh_flow', {}).get('tip', '')}",
            )
            self.engine.set(ENGINE_LABELS[0])
            self._sync_prompt()
            return
        self._sync_prompt()
        if key == "moss":
            tip = self._moss.get("tip", "MOSS selected.")
            if self._moss.get("forced"):
                tip = "Force MOSS on - " + tip
        elif key == "moss_gguf":
            tip = getattr(self, "_gguf", {}).get(
                "tip",
                "MOSS GGUF (SLOWER): quality option, often minutes per clip.",
            )
        elif key == "woosh_dflow":
            tip = getattr(self, "_woosh", {}).get(
                "tip",
                "Woosh DFlow: distilled T2A, 4 steps, free-text prompts (~6 GB).",
            )
        elif key == "woosh_flow":
            tip = getattr(self, "_woosh_flow", {}).get(
                "tip",
                "Woosh Flow: full T2A, 50 steps, CFG 4.5 (~10â€“12 GB).",
            )
        else:
            tip = "SA3: ~1s gens, light VRAM. Fine with Resolve open."
        self._set_status(tip)

    def _on_dur(self, value: float) -> None:
        self.duration_lbl.configure(text=f"{float(value):.1f}s")

    def _apply_topmost(self) -> None:
        self.attributes("-topmost", bool(self.always_on_top.get()))

    def _prompt_resize_start(self, event) -> None:
        self._prompt_resize_y = event.y_root
        self._prompt_resize_h = int(self.prompt.winfo_height())

    def _prompt_resize_drag(self, event) -> None:
        if not hasattr(self, "_prompt_resize_y"):
            return
        dy = event.y_root - self._prompt_resize_y
        new_h = max(44, min(280, self._prompt_resize_h + dy))
        if abs(new_h - getattr(self, "_prompt_height", 0)) < 2:
            return
        self._prompt_height = new_h
        self.prompt.configure(height=new_h)

    def _prompt_resize_end(self, _event=None) -> None:
        try:
            self._prompt_height = max(44, min(280, int(self.prompt.winfo_height())))
        except Exception:
            pass

    def _sync_prompt(self) -> None:

        p = build_prompt(
            self.kind.get(),
            self.texture.get(),
            self.space.get(),
            self.speed.get(),
            extra=self.extra.get().strip(),
            engine=self._engine_key(),
            mic=self.mic.get(),
            intensity=self.intensity.get(),
        )
        self.prompt.delete("1.0", "end")
        self.prompt.insert("1.0", p)

    def _unload(self) -> None:
        try:
            self._set_status(unload_all())
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("SFX Desk", str(e))

    def _clear_cache(self) -> None:
        try:
            self._set_status(empty_cuda_cache())
        except Exception as e:  # noqa: BLE001
            messagebox.showerror("SFX Desk", str(e))

    def _on_generate(self) -> None:
        if self.busy:
            return
        prompt = self.prompt.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("SFX Desk", "Prompt is empty.")
            return
        seconds = float(self.duration.get())
        category = self.kind.get()
        engine = self._engine_key()
        if engine == "moss" and not self._moss.get("unlocked"):
            messagebox.showwarning(
                "SFX Desk",
                "MOSS is locked - needs ~16 GB VRAM (or enable Force MOSS).\n"
                "Use SA3 Small-SFX, or close Resolve and Force MOSS knowing the risk.",
            )
            return
        if engine == "moss_gguf" and not getattr(self, "_gguf", {}).get("unlocked", True):
            messagebox.showwarning(
                "SFX Desk",
                "MOSS GGUF is locked - needs ~12 GB VRAM.\n"
                "Use SA3 Small-SFX for fast gens.",
            )
            return
        if engine == "woosh_dflow" and not getattr(self, "_woosh", {}).get("unlocked", True):
            messagebox.showwarning(
                "SFX Desk",
                "Woosh DFlow is locked - needs ~6 GB VRAM.\n"
                "Use SA3 Small-SFX for fast gens.",
            )
            return
        if engine == "woosh_flow" and not getattr(self, "_woosh_flow", {}).get("unlocked", True):
            messagebox.showwarning(
                "SFX Desk",
                "Woosh Flow is locked - needs ~10 GB VRAM.\n"
                "Use Woosh DFlow (~6 GB) or SA3 Small-SFX.",
            )
            return
        keep = bool(self.keep_loaded.get())
        steps = DEFAULT_STEPS.get(engine, 50)
        cfg_scale = DEFAULT_CFG.get(engine, 4.0)

        # GGUF: release torch CUDA on the UI thread BEFORE the worker starts
        # moss-tts-server. Never call torch.cuda / empty cache from the GGUF
        # worker â€” that races the server and AV-crashes python.exe.
        if engine == "moss_gguf":
            self._set_status("Freeing SA3/MOSS/Woosh VRAM for GGUF...")
            try:
                self._set_status(unload_torch_engines())
            except Exception as e:  # noqa: BLE001
                self._set_status(f"Torch unload warning: {e}")
            self.update_idletasks()
        elif engine in ("woosh_dflow", "woosh_flow"):
            # Stop GGUF server only when one is actually up (avoids taskkill CMD flash).
            try:
                from app.engines import moss_gguf

                if moss_gguf.server_active():
                    self._set_status(unload_gguf_server())
            except Exception as e:  # noqa: BLE001
                self._set_status(f"GGUF stop warning: {e}")
            self.update_idletasks()

        self.busy = True
        self.gen_btn.configure(state="disabled")
        batch_n = max(1, min(8, int(self.batch_count.get() or 1)))
        self._set_status("Generating..." if batch_n == 1 else f"Batch 1/{batch_n}â€¦")

        def work() -> None:
            import time as _time
            import random as _random

            batch_clips: list[dict] = []
            last_elapsed = None
            try:
                for i in range(batch_n):
                    def cb(m: str, _i=i) -> None:
                        prefix = "" if batch_n == 1 else f"Batch {_i + 1}/{batch_n}â€¦ "
                        self.after(0, lambda msg=m, p=prefix: self._set_status(p + msg))

                    if batch_n > 1:
                        self.after(
                            0,
                            lambda _i=i: self._set_status(f"Batch {_i + 1}/{batch_n}â€¦"),
                        )
                    seed = _random.randint(0, 2**31 - 1)
                    # Keep engine warm across the whole batch; unload only after last
                    # item when Keep is off.
                    keep_this = True if (keep or i < batch_n - 1) else False
                    t0 = _time.perf_counter()
                    wav = generate_sfx(
                        prompt,
                        seconds=seconds,
                        steps=steps,
                        cfg_scale=cfg_scale,
                        negative_prompt=default_negative_prompt(),
                        engine=engine,
                        keep_loaded=keep_this,
                        status_cb=cb,
                        seed=seed,
                    )
                    elapsed = _time.perf_counter() - t0
                    clip = self.library.add_clip(
                        wav,
                        prompt,
                        category,
                        duration=seconds,
                        gen_elapsed=elapsed,
                        seed=seed,
                    )
                    batch_clips.append(clip)
                    last_elapsed = elapsed
                    self.last_wav = Path(clip["path"])
                    # Refresh library after each seed so rows appear live
                    self.after(0, self._refresh_library)
                clips = list(batch_clips)
                self.after(
                    0,
                    lambda c=clips, e=last_elapsed: self._after_generate(c, e, batch_n=batch_n),
                )
            except Exception as e:  # noqa: BLE001
                self.after(0, lambda err=e: self._generate_failed(err))

        threading.Thread(target=work, daemon=True).start()

    def _format_elapsed(self, seconds: float) -> str:
        """Human elapsed for status + library rows.

        <10s â†’ one decimal (1.2s); 10â€“59s â†’ whole seconds (12s); â‰¥60s â†’ 5m 51s.
        """
        seconds = float(seconds)
        if seconds < 10:
            rounded = round(seconds, 1)
            if rounded < 10:
                return f"{rounded:.1f}s"
            seconds = rounded
        if seconds < 60:
            whole = int(round(seconds))
            if whole < 60:
                return f"{whole}s"
            seconds = float(whole)
        total = int(round(seconds))
        mins, rem = divmod(total, 60)
        return f"{mins}m {rem}s"

    def _after_generate(
        self,
        clips: dict | list[dict] | None,
        elapsed: float | None = None,
        batch_n: int = 1,
    ) -> None:
        self.busy = False
        self.gen_btn.configure(state="normal")
        kept = "kept loaded" if self.keep_loaded.get() else "unloaded"
        if isinstance(clips, dict):
            clip_list = [clips]
        else:
            clip_list = list(clips or [])
        if not clip_list:
            self._set_status("Generate finished")
            return
        clip = clip_list[-1]
        if elapsed is None:
            suffix = f"Saved: {clip.get('filename')} ({kept})"
        else:
            suffix = (
                f"Saved: {clip.get('filename')} in {self._format_elapsed(elapsed)} ({kept})"
            )
        if batch_n > 1:
            self._set_status(f"Batch {batch_n}/{batch_n} done - {suffix}")
        else:
            self._set_status(suffix)
        self._refresh_library()
        # Preview last clip only
        self._play_path(clip["path"])
        if self.auto_send.get():
            raw_paths = [Path(c["path"]) for c in clip_list if c.get("path")]
            seen: set[str] = set()
            paths: list[Path] = []
            for p in raw_paths:
                key = str(p.resolve()).lower() if p.exists() else str(p).lower()
                if key in seen:
                    continue
                seen.add(key)
                paths.append(p)
            collided = len(raw_paths) - len(paths)
            self._send_paths(paths, quiet=True)
            if len(paths) > 1 or collided:
                note = f"Auto-sent {len(paths)} unique clips"
                if collided:
                    note += f" (warn: {collided} path collisions)"
                self._set_status(f"Batch {batch_n}/{batch_n} done - {note} ({kept})")


    def _generate_failed(self, err: Exception) -> None:
        self.busy = False
        self.gen_btn.configure(state="normal")
        self._set_status("Generate failed")
        messagebox.showerror("SFX Desk", str(err))

    def _refresh_library(self) -> None:
        self.clip_rows = self.library.list_clips(
            category=self.cat.get(),
            favorites_only=bool(self.fav_only.get()),
            query=self.search.get(),
        )
        self.listbox.delete(0, tk.END)
        for row in self.clip_rows:
            star = "* " if row.get("favorite") else ""
            snippet = str(row.get("prompt", ""))[:40]
            label = f"{star}[{row['category']}] {row['filename']} - {snippet}"
            gen_elapsed = row.get("gen_elapsed")
            if gen_elapsed is not None:
                try:
                    label = f"{label} - in {self._format_elapsed(float(gen_elapsed))}"
                except (TypeError, ValueError):
                    pass
            self.listbox.insert(tk.END, label)

    def _selected_rows(self) -> list[dict]:
        sel = self.listbox.curselection()
        return [self.clip_rows[i] for i in sel if 0 <= i < len(self.clip_rows)]

    def _on_select(self, _evt=None) -> None:
        rows = self._selected_rows()
        if not rows:
            self.selected_id = None
            return
        row = rows[-1]
        self.selected_id = row["id"]
        self.last_wav = Path(row["path"])

    def _toggle_fav(self) -> None:
        if self.selected_id is None:
            return
        clip = self.library.get(self.selected_id)
        self.library.set_favorite(self.selected_id, not bool(clip.get("favorite")))
        self._refresh_library()

    def _delete_selected(self) -> None:
        rows = self._selected_rows()
        if not rows and self.selected_id is None:
            return
        ids = [r["id"] for r in rows] if rows else [self.selected_id]
        n = len(ids)
        q = f"Delete {n} clip(s)?" if n > 1 else "Delete this clip?"
        if messagebox.askyesno("SFX Desk", q):
            for cid in ids:
                self.library.delete(cid)
            self.selected_id = None
            self._refresh_library()

    def _play_path(self, path: str | Path) -> None:
        if sd is None or sf is None:
            messagebox.showinfo(
                "SFX Desk",
                f"Saved to:\n{path}\n(Install sounddevice/soundfile to preview in-app)",
            )
            return
        data, sr = sf.read(str(path), dtype="float32")
        sd.stop()
        sd.play(data, sr)

    def _play_last(self) -> None:
        if self.last_wav and self.last_wav.exists():
            self._play_path(self.last_wav)
        else:
            messagebox.showinfo("SFX Desk", "Nothing to play yet.")

    def _play_selected(self) -> None:
        if self.selected_id is None:
            return
        clip = self.library.get(self.selected_id)
        self._play_path(clip["path"])

    def _send_paths(self, paths: list[Path], quiet: bool = False) -> None:
        seen: set[str] = set()
        unique: list[Path] = []
        for p in paths:
            if not p.exists():
                continue
            key = str(p.resolve()).lower()
            if key in seen:
                continue
            seen.add(key)
            unique.append(p)
        paths = unique
        if not paths:
            if not quiet:
                messagebox.showwarning("SFX Desk", "Select or generate a clip first.")
            return
        try:
            from app.resolve_send import send_wavs_to_resolve

            msg = send_wavs_to_resolve(paths, place_on_timeline=False)
            prefix = "Auto-sent: " if quiet else ""
            self._set_status(prefix + msg)
        except Exception as e:  # noqa: BLE001
            if quiet:
                self._set_status(f"Auto-send failed: {e}")
            else:
                messagebox.showerror("SFX Desk", str(e))

    def _send_resolve(self) -> None:
        rows = self._selected_rows()
        paths: list[Path] = []
        if rows:
            paths = [Path(r["path"]) for r in rows]
        elif self.last_wav and self.last_wav.exists():
            paths = [self.last_wav]
        self._send_paths(paths, quiet=False)

