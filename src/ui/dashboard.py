"""Main dashboard window with tabbed interface."""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable, Dict
import threading
import queue
from datetime import datetime

from .transcript_view import LiveTranscriptPanel
from .speaker_panel import SpeakerPanel
from .session_browser import SessionBrowser


class Dashboard(tk.Tk):
    """Main dashboard window for the Speech Profiler."""

    def __init__(
        self,
        on_start_capture: Optional[Callable] = None,
        on_stop_capture: Optional[Callable] = None,
        on_rename_speaker: Optional[Callable] = None,
        on_delete_speaker: Optional[Callable] = None,
        on_analyze_speaker: Optional[Callable] = None,
        on_select_speaker: Optional[Callable] = None,
        on_load_session: Optional[Callable] = None,
        on_close: Optional[Callable] = None
    ):
        """Initialize the dashboard.

        Args:
            on_start_capture: Callback when Start button is clicked
            on_stop_capture: Callback when Stop button is clicked
            on_rename_speaker: Callback(speaker_id, old_name, new_name)
            on_delete_speaker: Callback(speaker_id, name)
            on_analyze_speaker: Callback(speaker_id, name)
            on_select_speaker: Callback(speaker_id, name) when speaker selected
            on_load_session: Callback(session_id)
            on_close: Callback when window is closed
        """
        super().__init__()

        self.on_start_capture = on_start_capture
        self.on_stop_capture = on_stop_capture
        self.on_rename_speaker = on_rename_speaker
        self.on_delete_speaker = on_delete_speaker
        self.on_analyze_speaker = on_analyze_speaker
        self.on_select_speaker = on_select_speaker
        self.on_load_session = on_load_session
        self.on_close = on_close

        self._is_recording = False
        self._update_queue = queue.Queue()

        self._setup_window()
        self._setup_styles()
        self._setup_ui()

        # Start update checker
        self._check_updates()

        # Handle window close
        self.protocol('WM_DELETE_WINDOW', self._on_close)

    def _setup_window(self):
        """Configure the main window."""
        self.title('Speech Profiler - Dashboard')
        self.geometry('1200x800')
        self.minsize(800, 600)

        # Set dark theme colors globally
        bg_color = '#1e1e2e'
        fg_color = '#cdd6f4'
        self.configure(bg=bg_color)

        # Set tk option defaults for dark theme
        self.option_add('*Background', bg_color)
        self.option_add('*Foreground', fg_color)
        self.option_add('*highlightBackground', bg_color)
        self.option_add('*highlightColor', bg_color)
        self.option_add('*selectBackground', '#45475a')
        self.option_add('*selectForeground', fg_color)
        self.option_add('*troughColor', '#11111b')

        # Center on screen
        self.update_idletasks()
        width = self.winfo_width()
        height = self.winfo_height()
        x = (self.winfo_screenwidth() // 2) - (width // 2)
        y = (self.winfo_screenheight() // 2) - (height // 2)
        self.geometry(f'+{x}+{y}')

    def _setup_styles(self):
        """Configure ttk styles for dark theme."""
        style = ttk.Style()

        # Try to use a dark theme if available
        available_themes = style.theme_names()
        if 'clam' in available_themes:
            style.theme_use('clam')

        # Configure dark colors
        bg_color = '#1e1e2e'
        fg_color = '#cdd6f4'
        select_bg = '#45475a'
        accent = '#89b4fa'
        dark_bg = '#11111b'

        style.configure('.',
            background=bg_color,
            foreground=fg_color,
            fieldbackground=bg_color,
            troughcolor=dark_bg,
            borderwidth=0
        )

        style.configure('TFrame', background=bg_color)
        style.configure('TLabel', background=bg_color, foreground=fg_color)
        style.configure('TButton', background='#313244', foreground=fg_color)

        # Notebook (tabs) - fully dark, remove all borders
        style.configure('TNotebook', background=bg_color, borderwidth=0, tabmargins=[0, 0, 0, 0])
        style.configure('TNotebook.Tab', background='#313244', foreground=fg_color, padding=[10, 5], borderwidth=0)
        style.map('TNotebook.Tab',
            background=[('selected', accent)],
            foreground=[('selected', '#1e1e2e')]
        )
        # Remove notebook border - use 'border' not 'borderwidth'
        style.layout('TNotebook', [
            ('Notebook.client', {'sticky': 'nswe', 'border': 0})
        ])

        style.configure('TLabelframe', background=bg_color, foreground=fg_color)
        style.configure('TLabelframe.Label', background=bg_color, foreground=fg_color)

        style.configure('Treeview',
            background=bg_color,
            foreground=fg_color,
            fieldbackground=bg_color,
            selectbackground=select_bg
        )
        style.configure('Treeview.Heading', background='#313244', foreground=fg_color)

        style.configure('TProgressbar', background=accent, troughcolor='#313244')

        # Scrollbar - dark theme
        style.configure('TScrollbar',
            background='#313244',
            troughcolor=bg_color,
            borderwidth=0,
            arrowcolor=fg_color
        )
        style.map('TScrollbar',
            background=[('active', '#45475a'), ('pressed', '#585b70')]
        )

        # PanedWindow
        style.configure('TPanedwindow', background=bg_color)

        # Custom styles
        style.configure('Recording.TButton', background='#ef4444', foreground='white')
        style.configure('Start.TButton', background='#22c55e', foreground='white')
        style.configure('Selected.TFrame', background='#3b82f6')
        style.configure('Hover.TFrame', background='#374151')

    def _setup_ui(self):
        """Set up the main UI."""
        # Main container
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill='both', expand=True, padx=10, pady=10)

        # Create notebook (tabs) - dark themed
        self.notebook = ttk.Notebook(self.main_frame, style='TNotebook')
        self.notebook.pack(fill='both', expand=True)
        # Try to remove any internal borders
        self.notebook.configure(padding=0)

        # Tab 1: Live View - use tk.Frame for full dark control
        self.live_tab = tk.Frame(self.notebook, bg='#1e1e2e', highlightthickness=0, bd=0)
        self.notebook.add(self.live_tab, text='  Live View  ')
        self._setup_live_tab()

        # Tab 2: Speakers
        self.speakers_tab = tk.Frame(self.notebook, bg='#1e1e2e', highlightthickness=0, bd=0)
        self.notebook.add(self.speakers_tab, text='  Speakers  ')
        self._setup_speakers_tab()

        # Tab 3: Sessions
        self.sessions_tab = tk.Frame(self.notebook, bg='#1e1e2e', highlightthickness=0, bd=0)
        self.notebook.add(self.sessions_tab, text='  Sessions  ')
        self._setup_sessions_tab()

    def _setup_live_tab(self):
        """Set up the Live View tab."""
        bg_color = '#1e1e2e'
        fg_color = '#cdd6f4'

        # Control bar - use tk.Frame for dark theme
        control_frame = tk.Frame(self.live_tab, bg=bg_color, highlightthickness=0)
        control_frame.pack(fill='x', padx=5, pady=5)

        # Start/Stop button
        self.capture_btn = tk.Button(
            control_frame,
            text='Start Capture',
            command=self._toggle_capture,
            font=('Segoe UI', 10),
            fg='white',
            bg='#22c55e',
            activebackground='#16a34a',
            activeforeground='white',
            bd=0,
            padx=15,
            pady=5
        )
        self.capture_btn.pack(side='left', padx=5)

        # Status label
        self.status_label = tk.Label(
            control_frame,
            text='Idle',
            font=('Segoe UI', 10),
            fg='#f97316',
            bg=bg_color
        )
        self.status_label.pack(side='left', padx=10)

        # Claude insights panel (right side) - use tk.Frame with border
        self.insights_frame = tk.Frame(self.live_tab, bg=bg_color, highlightthickness=1, highlightbackground='#45475a')
        self.insights_frame.pack(side='right', fill='y', padx=5, pady=5)

        # Insights header
        insights_header = tk.Label(
            self.insights_frame,
            text='Claude Insights',
            font=('Segoe UI', 10, 'bold'),
            fg=fg_color,
            bg='#313244',
            padx=10,
            pady=5
        )
        insights_header.pack(fill='x')

        # Header label
        self.claude_header = tk.Label(
            self.insights_frame,
            text="🤖 Claude Analysis",
            font=('Segoe UI', 11, 'bold'),
            fg='#00ff88',
            bg='#1e1e2e'
        )
        self.claude_header.pack(anchor='w', padx=10, pady=(10, 5))

        # Rapport tip (green)
        self.rapport_label = tk.Label(
            self.insights_frame,
            text='Waiting for speech...',
            font=('Segoe UI', 10),
            fg='#00ff88',
            bg='#1e1e2e',
            wraplength=250,
            justify='left'
        )
        self.rapport_label.pack(anchor='w', padx=10, pady=3)

        # Persuade tip (orange)
        self.persuade_label = tk.Label(
            self.insights_frame,
            text='',
            font=('Segoe UI', 10),
            fg='#ff9f43',
            bg='#1e1e2e',
            wraplength=250,
            justify='left'
        )
        self.persuade_label.pack(anchor='w', padx=10, pady=3)

        # Honesty assessment (yellow)
        self.honesty_label = tk.Label(
            self.insights_frame,
            text='',
            font=('Segoe UI', 10),
            fg='#f1c40f',
            bg='#1e1e2e',
            wraplength=250,
            justify='left'
        )
        self.honesty_label.pack(anchor='w', padx=10, pady=3)

        # Deception warnings (red)
        self.deception_label = tk.Label(
            self.insights_frame,
            text='',
            font=('Segoe UI', 10, 'bold'),
            fg='#ef4444',
            bg='#1e1e2e',
            wraplength=250,
            justify='left'
        )
        self.deception_label.pack(anchor='w', padx=10, pady=(3, 10))

        # Live transcript panel
        self.live_panel = LiveTranscriptPanel(self.live_tab)
        self.live_panel.pack(fill='both', expand=True, padx=5, pady=5)

    def _setup_speakers_tab(self):
        """Set up the Speakers tab."""
        self.speaker_panel = SpeakerPanel(
            self.speakers_tab,
            on_rename=self._handle_rename,
            on_delete=self._handle_delete,
            on_analyze=self._handle_analyze,
            on_select=self._handle_speaker_select
        )
        self.speaker_panel.pack(fill='both', expand=True)

    def _setup_sessions_tab(self):
        """Set up the Sessions tab."""
        self.session_browser = SessionBrowser(
            self.sessions_tab,
            on_load_session=self._handle_load_session
        )
        self.session_browser.pack(fill='both', expand=True)

    def _toggle_capture(self):
        """Toggle audio capture on/off."""
        if self._is_recording:
            self.stop_capture()
        else:
            self.start_capture()

    def start_capture(self):
        """Start audio capture."""
        if self.on_start_capture:
            self.on_start_capture()

        self._is_recording = True
        self.capture_btn.config(text='Stop Capture', bg='#ef4444', activebackground='#dc2626')
        self.status_label.config(text='Recording...', fg='#ef4444')
        self.live_panel.set_recording_state(True)

    def stop_capture(self):
        """Stop audio capture."""
        if self.on_stop_capture:
            self.on_stop_capture()

        self._is_recording = False
        self.capture_btn.config(text='Start Capture', bg='#22c55e', activebackground='#16a34a')
        self.status_label.config(text='Idle', fg='#6b7280')
        self.live_panel.set_recording_state(False)

    def _handle_rename(self, speaker_id: int, old_name: str, new_name: str):
        """Handle speaker rename."""
        if self.on_rename_speaker:
            self.on_rename_speaker(speaker_id, old_name, new_name)

    def _handle_delete(self, speaker_id: int, name: str):
        """Handle speaker delete."""
        if self.on_delete_speaker:
            self.on_delete_speaker(speaker_id, name)

    def _handle_analyze(self, speaker_id: int, name: str):
        """Handle analyze request."""
        if self.on_analyze_speaker:
            self.on_analyze_speaker(speaker_id, name)

    def _handle_speaker_select(self, speaker_id: int, name: str):
        """Handle speaker selection - load their data."""
        if self.on_select_speaker:
            self.on_select_speaker(speaker_id, name)

    def _handle_load_session(self, session_id: int):
        """Handle session load request."""
        if self.on_load_session:
            self.on_load_session(session_id)

    def _on_close(self):
        """Handle window close."""
        if self._is_recording:
            self.stop_capture()

        if self.on_close:
            self.on_close()

        # Hide window instead of destroying (for tray operation)
        self.withdraw()

    def show(self):
        """Show the dashboard window."""
        self.deiconify()
        self.lift()
        self.focus_force()

    def hide(self):
        """Hide the dashboard window."""
        self.withdraw()

    def is_visible(self) -> bool:
        """Check if window is visible."""
        return self.state() == 'normal'

    # Public methods for updating UI from other threads

    def add_utterance(
        self,
        speaker: str,
        text: str,
        vak: Optional[str] = None,
        need: Optional[str] = None
    ):
        """Add an utterance to the live transcript (thread-safe)."""
        self._update_queue.put(('utterance', {
            'speaker': speaker,
            'text': text,
            'vak': vak,
            'need': need,
            'timestamp': datetime.now()
        }))

    def update_current_speaker(self, speaker: str, vak: Optional[str] = None, need: Optional[str] = None):
        """Update the current speaker display (thread-safe)."""
        self._update_queue.put(('current_speaker', {
            'speaker': speaker,
            'vak': vak,
            'need': need
        }))

    def update_claude_insights(self, insights: Dict):
        """Update the Claude insights panel (thread-safe)."""
        self._update_queue.put(('insights', insights))

    def add_speaker(self, speaker_id: int, name: str, word_count: int = 0, **kwargs):
        """Add a speaker to the speakers list (thread-safe)."""
        self._update_queue.put(('add_speaker', {
            'speaker_id': speaker_id,
            'name': name,
            'word_count': word_count,
            **kwargs
        }))

    def update_speaker_profile(self, speaker_id: int, profile: Dict):
        """Update a speaker's profile display (thread-safe)."""
        self._update_queue.put(('speaker_profile', {
            'speaker_id': speaker_id,
            'profile': profile
        }))

    def update_speaker_text(self, speaker_id: int, text: str):
        """Update a speaker's all text display (thread-safe)."""
        self._update_queue.put(('speaker_text', {
            'speaker_id': speaker_id,
            'text': text
        }))

    def update_speaker_analysis(self, speaker_id: int, analyses: list):
        """Update a speaker's analysis history (thread-safe)."""
        self._update_queue.put(('speaker_analysis', {
            'speaker_id': speaker_id,
            'analyses': analyses
        }))

    def add_session(self, session_id: int, name: str, start_time: datetime, **kwargs):
        """Add a session to the sessions list (thread-safe)."""
        self._update_queue.put(('add_session', {
            'session_id': session_id,
            'name': name,
            'start_time': start_time,
            **kwargs
        }))

    def load_session_transcript(self, session_name: str, start_time: datetime, utterances: list, speaker_stats: dict):
        """Load a session's transcript (thread-safe)."""
        self._update_queue.put(('session_transcript', {
            'session_name': session_name,
            'start_time': start_time,
            'utterances': utterances,
            'speaker_stats': speaker_stats
        }))

    def _check_updates(self):
        """Check for UI updates from queue."""
        try:
            while True:
                update_type, data = self._update_queue.get_nowait()
                self._process_update(update_type, data)
        except queue.Empty:
            pass

        # Schedule next check
        self.after(50, self._check_updates)

    def _process_update(self, update_type: str, data: dict):
        """Process a UI update."""
        if update_type == 'utterance':
            self.live_panel.add_utterance(
                speaker=data['speaker'],
                text=data['text'],
                vak=data.get('vak'),
                need=data.get('need'),
                timestamp=data.get('timestamp')
            )

        elif update_type == 'current_speaker':
            self.live_panel.set_current_speaker(
                speaker=data['speaker'],
                vak=data.get('vak'),
                need=data.get('need')
            )

        elif update_type == 'insights':
            insights = data

            # Update each colored label
            rapport = insights.get('rapport_tip', '')
            if rapport:
                self.rapport_label.config(text=f"💬 {rapport}")
            else:
                self.rapport_label.config(text='')

            persuade = insights.get('how_to_persuade', '')
            if persuade:
                self.persuade_label.config(text=f"🎯 {persuade}")
            else:
                self.persuade_label.config(text='')

            honesty = insights.get('honesty_assessment', '')
            if honesty:
                self.honesty_label.config(text=f"🔍 {honesty}")
            else:
                self.honesty_label.config(text='')

            deceptions = insights.get('deception_detected', [])
            if deceptions:
                self.deception_label.config(text=f"⚠️ DECEPTION: {', '.join(deceptions)}")
            else:
                self.deception_label.config(text='')

        elif update_type == 'add_speaker':
            self.speaker_panel.add_speaker(**data)

        elif update_type == 'speaker_profile':
            if self.speaker_panel.get_selected_speaker_id() == data['speaker_id']:
                self.speaker_panel.update_profile_display(data['profile'])

        elif update_type == 'speaker_text':
            if self.speaker_panel.get_selected_speaker_id() == data['speaker_id']:
                self.speaker_panel.update_all_text(data['text'])

        elif update_type == 'speaker_analysis':
            if self.speaker_panel.get_selected_speaker_id() == data['speaker_id']:
                self.speaker_panel.update_analysis_history(data['analyses'])

        elif update_type == 'add_session':
            self.session_browser.add_session(**data)

        elif update_type == 'session_transcript':
            self.session_browser.load_session_transcript(**data)


def run_dashboard():
    """Run the dashboard standalone (for testing)."""
    dashboard = Dashboard()

    # Add some test data
    dashboard.add_speaker(1, 'John Doe', word_count=1500, sessions_count=3)
    dashboard.add_speaker(2, 'Jane Smith', word_count=2300, sessions_count=5)

    dashboard.add_session(
        1, 'Meeting',
        datetime(2024, 1, 15, 10, 30),
        duration_seconds=1800,
        speaker_count=2,
        utterance_count=45
    )

    dashboard.mainloop()


if __name__ == '__main__':
    run_dashboard()
