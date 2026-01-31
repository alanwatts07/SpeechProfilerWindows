"""Compact real-time overlay for speech profiling."""

import tkinter as tk
from typing import Optional, Callable, Dict

# Communication tips
VAK_TIPS = {
    "visual": "Use: see, look, picture, imagine",
    "auditory": "Use: hear, sounds, listen, tell",
    "kinesthetic": "Use: feel, touch, grasp, handle",
}

NEED_TIPS = {
    "significance": "Acknowledge their achievements",
    "approval": "Give genuine compliments",
    "acceptance": "Use inclusive language (we, us)",
    "intelligence": "Ask for their analysis",
    "power": "Give them choices and control",
    "pity": "Show empathy and understanding",
}


class Overlay(tk.Tk):
    """Compact floating overlay showing real-time speaker info."""

    def __init__(
        self,
        on_open_dashboard: Optional[Callable] = None,
        on_toggle_capture: Optional[Callable] = None,
        on_close: Optional[Callable] = None,
        on_settings: Optional[Callable] = None
    ):
        super().__init__()

        self.on_open_dashboard = on_open_dashboard
        self.on_toggle_capture = on_toggle_capture
        self.on_close = on_close
        self.on_settings = on_settings

        self._is_recording = False
        self._setup_window()
        self._create_widgets()

        # Handle window close
        self.protocol('WM_DELETE_WINDOW', self._handle_close)

    def _setup_window(self):
        """Configure the overlay window."""
        self.title("Speech Profiler")
        self.attributes('-topmost', True)
        self.attributes('-alpha', 0.92)
        self.overrideredirect(True)  # No window decorations

        # Position in bottom-right corner
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        self.window_width = 380
        x = screen_width - self.window_width - 20
        y = screen_height - 400

        self.geometry(f"{self.window_width}x350+{x}+{y}")
        self.configure(bg='#1a1a2e')

        # Make draggable
        self.bind('<Button-1>', self._start_drag)
        self.bind('<B1-Motion>', self._drag)

        self._drag_x = 0
        self._drag_y = 0

    def _start_drag(self, event):
        self._drag_x = event.x
        self._drag_y = event.y

    def _drag(self, event):
        x = self.winfo_x() + event.x - self._drag_x
        y = self.winfo_y() + event.y - self._drag_y
        self.geometry(f"+{x}+{y}")

    def _create_widgets(self):
        """Create overlay widgets."""
        # Main frame
        frame = tk.Frame(self, bg='#1a1a2e', padx=10, pady=10)
        frame.pack(fill='both', expand=True)

        # Header with buttons
        header = tk.Frame(frame, bg='#1a1a2e')
        header.pack(fill='x')

        self.speaker_label = tk.Label(
            header,
            text="Ready",
            font=('Segoe UI', 14, 'bold'),
            fg='#00d9ff',
            bg='#1a1a2e'
        )
        self.speaker_label.pack(side='left')

        # Close button
        close_btn = tk.Button(
            header,
            text="X",
            font=('Segoe UI', 9),
            fg='white',
            bg='#ff4757',
            bd=0,
            width=2,
            command=self._handle_close
        )
        close_btn.pack(side='right', padx=2)

        # Settings button
        settings_btn = tk.Button(
            header,
            text="Settings",
            font=('Segoe UI', 9),
            fg='white',
            bg='#6366f1',
            bd=0,
            command=self._open_settings
        )
        settings_btn.pack(side='right', padx=2)

        # Dashboard button
        dash_btn = tk.Button(
            header,
            text="Dashboard",
            font=('Segoe UI', 9),
            fg='white',
            bg='#3b82f6',
            bd=0,
            command=self._open_dashboard
        )
        dash_btn.pack(side='right', padx=2)

        # Record button
        self.record_btn = tk.Button(
            header,
            text="Start",
            font=('Segoe UI', 9),
            fg='white',
            bg='#22c55e',
            bd=0,
            width=5,
            command=self._toggle_capture
        )
        self.record_btn.pack(side='right', padx=2)

        # Confidence/word count
        self.info_label = tk.Label(
            frame,
            text="",
            font=('Segoe UI', 9),
            fg='#888',
            bg='#1a1a2e'
        )
        self.info_label.pack(anchor='w')

        # Separator
        tk.Frame(frame, height=1, bg='#333').pack(fill='x', pady=8)

        # VAK and Need
        self.vak_label = tk.Label(
            frame,
            text="VAK: -",
            font=('Segoe UI', 11),
            fg='white',
            bg='#1a1a2e'
        )
        self.vak_label.pack(anchor='w')

        self.need_label = tk.Label(
            frame,
            text="Need: -",
            font=('Segoe UI', 11),
            fg='white',
            bg='#1a1a2e'
        )
        self.need_label.pack(anchor='w')

        # Tip
        self.tip_label = tk.Label(
            frame,
            text="",
            font=('Segoe UI', 10),
            fg='#ffd700',
            bg='#1a1a2e',
            wraplength=350,
            justify='left'
        )
        self.tip_label.pack(anchor='w', pady=(5, 0))

        # Separator before Claude
        tk.Frame(frame, height=1, bg='#444').pack(fill='x', pady=8)

        # Claude header
        self.claude_header = tk.Label(
            frame,
            text="Claude Analysis",
            font=('Segoe UI', 10, 'bold'),
            fg='#00ff88',
            bg='#1a1a2e'
        )
        self.claude_header.pack(anchor='w')

        # Rapport (green)
        self.rapport_label = tk.Label(
            frame,
            text="Waiting for speech...",
            font=('Segoe UI', 10),
            fg='#00ff88',
            bg='#1a1a2e',
            wraplength=350,
            justify='left'
        )
        self.rapport_label.pack(anchor='w', pady=2)

        # Persuade (orange)
        self.persuade_label = tk.Label(
            frame,
            text="",
            font=('Segoe UI', 10),
            fg='#ff9f43',
            bg='#1a1a2e',
            wraplength=350,
            justify='left'
        )
        self.persuade_label.pack(anchor='w', pady=2)

        # Deception (red)
        self.deception_label = tk.Label(
            frame,
            text="",
            font=('Segoe UI', 10, 'bold'),
            fg='#ef4444',
            bg='#1a1a2e',
            wraplength=350,
            justify='left'
        )
        self.deception_label.pack(anchor='w', pady=2)

    def _toggle_capture(self):
        """Toggle recording."""
        if self.on_toggle_capture:
            self.on_toggle_capture()

    def _open_dashboard(self):
        """Open the dashboard."""
        if self.on_open_dashboard:
            self.on_open_dashboard()

    def _open_settings(self):
        """Open settings."""
        if self.on_settings:
            self.on_settings()

    def _handle_close(self):
        """Handle close button."""
        if self.on_close:
            self.on_close()
        self.destroy()

    def set_recording(self, is_recording: bool):
        """Update recording state."""
        self._is_recording = is_recording
        if is_recording:
            self.record_btn.config(text="Stop", bg='#ef4444')
            self.speaker_label.config(text="Listening...")
        else:
            self.record_btn.config(text="Start", bg='#22c55e')
            self.speaker_label.config(text="Ready")

    def update_speaker(
        self,
        speaker: str,
        confidence: float = 0,
        word_count: int = 0,
        vak: Optional[str] = None,
        need: Optional[str] = None
    ):
        """Update current speaker display."""
        self.speaker_label.config(text=speaker)

        # Info line
        info_parts = []
        if word_count > 0:
            info_parts.append(f"{word_count:,} words")
        if 0 < confidence < 1:
            info_parts.append(f"Match: {confidence:.0%}")
        self.info_label.config(text=" | ".join(info_parts))

        # VAK
        if vak:
            emoji = {"visual": "eye", "auditory": "ear", "kinesthetic": "hand"}.get(vak, "")
            self.vak_label.config(text=f"VAK: {vak.capitalize()}")
            tip = VAK_TIPS.get(vak, "")
            if tip:
                self.tip_label.config(text=f"Tip: {tip}")
        else:
            self.vak_label.config(text="VAK: analyzing...")

        # Need
        if need:
            self.need_label.config(text=f"Need: {need.capitalize()}")
            need_tip = NEED_TIPS.get(need, "")
            if need_tip and not vak:
                self.tip_label.config(text=f"Tip: {need_tip}")
        else:
            self.need_label.config(text="Need: analyzing...")

    def update_claude_insights(self, insights: Dict):
        """Update Claude insights display."""
        rapport = insights.get('rapport_tip', '')
        if rapport:
            self.rapport_label.config(text=f"Rapport: {rapport}")
        else:
            self.rapport_label.config(text="")

        persuade = insights.get('how_to_persuade', '')
        if persuade:
            self.persuade_label.config(text=f"Persuade: {persuade}")
        else:
            self.persuade_label.config(text="")

        deceptions = insights.get('deception_detected', [])
        if deceptions:
            self.deception_label.config(text=f"DECEPTION: {', '.join(deceptions)}")
        else:
            self.deception_label.config(text="")
