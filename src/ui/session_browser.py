"""Session browser for viewing past recording sessions."""

import tkinter as tk
from tkinter import ttk
from typing import Optional, Callable, List, Dict
from datetime import datetime

from .transcript_view import TranscriptView


class SessionListItem(tk.Frame):
    """Individual session item in the list."""

    BG_COLOR = '#1e1e2e'
    FG_COLOR = '#cdd6f4'
    HOVER_COLOR = '#374151'
    SELECT_COLOR = '#3b82f6'

    def __init__(
        self,
        parent,
        session_id: int,
        name: str,
        start_time: datetime,
        duration_seconds: int = 0,
        speaker_count: int = 0,
        utterance_count: int = 0,
        on_select: Optional[Callable] = None,
        **kwargs
    ):
        """Initialize session list item.

        Args:
            parent: Parent widget
            session_id: Database ID of session
            name: Session name
            start_time: Session start time
            duration_seconds: Duration in seconds
            speaker_count: Number of speakers
            utterance_count: Number of utterances
            on_select: Callback when item is selected
        """
        kwargs['bg'] = self.BG_COLOR
        kwargs['highlightthickness'] = 0
        super().__init__(parent, **kwargs)
        self.session_id = session_id
        self.name = name
        self.start_time = start_time
        self.on_select = on_select
        self._selected = False

        self._setup_ui(duration_seconds, speaker_count, utterance_count)

    def _setup_ui(self, duration_seconds: int, speaker_count: int, utterance_count: int):
        """Set up the UI."""
        # Bind click events
        self.bind('<Button-1>', self._on_click)
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)

        # Date/time
        time_str = self.start_time.strftime('%Y-%m-%d %H:%M')
        self.time_label = tk.Label(
            self,
            text=time_str,
            font=('Segoe UI', 11, 'bold'),
            bg=self.BG_COLOR,
            fg=self.FG_COLOR
        )
        self.time_label.pack(anchor='w', padx=10, pady=(8, 0))
        self.time_label.bind('<Button-1>', self._on_click)

        # Session name if different from default
        if self.name and 'Overlay' not in self.name:
            self.name_label = tk.Label(
                self,
                text=self.name,
                font=('Segoe UI', 10),
                bg=self.BG_COLOR,
                fg='#a6adc8'
            )
            self.name_label.pack(anchor='w', padx=10)
            self.name_label.bind('<Button-1>', self._on_click)

        # Stats
        stats_frame = tk.Frame(self, bg=self.BG_COLOR)
        stats_frame.pack(anchor='w', fill='x', padx=10, pady=(0, 8))
        stats_frame.bind('<Button-1>', self._on_click)

        # Duration
        if duration_seconds > 0:
            mins = duration_seconds // 60
            secs = duration_seconds % 60
            duration_str = f'{mins}m {secs}s' if mins else f'{secs}s'
        else:
            duration_str = 'N/A'

        self.duration_label = tk.Label(
            stats_frame,
            text=f'{duration_str}',
            font=('Segoe UI', 9),
            bg=self.BG_COLOR,
            fg='#6b7280'
        )
        self.duration_label.pack(side='left')
        self.duration_label.bind('<Button-1>', self._on_click)

        self.speakers_label = tk.Label(
            stats_frame,
            text=f' | {speaker_count} speakers',
            font=('Segoe UI', 9),
            bg=self.BG_COLOR,
            fg='#6b7280'
        )
        self.speakers_label.pack(side='left')
        self.speakers_label.bind('<Button-1>', self._on_click)

        self.utterances_label = tk.Label(
            stats_frame,
            text=f' | {utterance_count} utterances',
            font=('Segoe UI', 9),
            bg=self.BG_COLOR,
            fg='#6b7280'
        )
        self.utterances_label.pack(side='left')
        self.utterances_label.bind('<Button-1>', self._on_click)

    def _on_click(self, event=None):
        """Handle click event."""
        if self.on_select:
            self.on_select(self.session_id)

    def _on_enter(self, event=None):
        """Handle mouse enter."""
        if not self._selected:
            self._set_bg(self.HOVER_COLOR)

    def _on_leave(self, event=None):
        """Handle mouse leave."""
        if not self._selected:
            self._set_bg(self.BG_COLOR)

    def _set_bg(self, color: str):
        """Set background color on self and all children."""
        self.config(bg=color)
        for child in self.winfo_children():
            try:
                child.config(bg=color)
                for subchild in child.winfo_children():
                    try:
                        subchild.config(bg=color)
                    except tk.TclError:
                        pass
            except tk.TclError:
                pass

    def set_selected(self, selected: bool):
        """Set selection state."""
        self._selected = selected
        if selected:
            self._set_bg(self.SELECT_COLOR)
        else:
            self._set_bg(self.BG_COLOR)


class SessionBrowser(tk.Frame):
    """Browser for viewing past recording sessions."""

    BG_COLOR = '#1e1e2e'
    FG_COLOR = '#cdd6f4'
    SECONDARY_FG = '#a6adc8'

    def __init__(
        self,
        parent,
        on_load_session: Optional[Callable] = None,
        **kwargs
    ):
        """Initialize session browser.

        Args:
            parent: Parent widget
            on_load_session: Callback(session_id) when session is selected for viewing
        """
        kwargs.setdefault('bg', self.BG_COLOR)
        kwargs.setdefault('highlightthickness', 0)
        super().__init__(parent, **kwargs)

        self.on_load_session = on_load_session
        self._sessions: Dict[int, SessionListItem] = {}
        self._selected_session_id: Optional[int] = None

        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI."""
        # Use PanedWindow for resizable split
        self.paned = tk.PanedWindow(self, orient='horizontal', bg=self.BG_COLOR, sashwidth=4, sashrelief='flat', bd=0)
        self.paned.pack(fill='both', expand=True)

        # Left side: Session list
        self.list_frame = tk.Frame(self.paned, bg=self.BG_COLOR, highlightthickness=0)
        self.paned.add(self.list_frame, stretch='always')

        # List header
        list_header = tk.Frame(self.list_frame, bg=self.BG_COLOR)
        list_header.pack(fill='x', padx=5, pady=5)

        tk.Label(
            list_header,
            text='Sessions',
            font=('Segoe UI', 12, 'bold'),
            bg=self.BG_COLOR,
            fg=self.FG_COLOR
        ).pack(side='left')

        # Filter by speaker (combobox) - keep ttk for combobox but style it
        filter_frame = tk.Frame(list_header, bg=self.BG_COLOR)
        filter_frame.pack(side='right')

        tk.Label(filter_frame, text='Filter: ', bg=self.BG_COLOR, fg=self.FG_COLOR).pack(side='left')

        self.filter_var = tk.StringVar(value='All speakers')
        style = ttk.Style()
        style.configure('Dark.TCombobox', fieldbackground='#313244', background='#313244', foreground=self.FG_COLOR)
        self.filter_combo = ttk.Combobox(
            filter_frame,
            textvariable=self.filter_var,
            values=['All speakers'],
            state='readonly',
            width=15,
            style='Dark.TCombobox'
        )
        self.filter_combo.pack(side='left')
        self.filter_combo.bind('<<ComboboxSelected>>', self._on_filter_change)

        # Scrollable list
        self.list_canvas = tk.Canvas(self.list_frame, bg=self.BG_COLOR, highlightthickness=0)
        self.list_scrollbar = tk.Scrollbar(
            self.list_frame,
            orient='vertical',
            command=self.list_canvas.yview,
            bg='#313244',
            troughcolor=self.BG_COLOR,
            activebackground='#45475a',
            highlightthickness=0,
            bd=0
        )
        self.list_container = tk.Frame(self.list_canvas, bg=self.BG_COLOR)

        self.list_canvas.configure(yscrollcommand=self.list_scrollbar.set)

        self.list_scrollbar.pack(side='right', fill='y')
        self.list_canvas.pack(side='left', fill='both', expand=True)

        self.list_window = self.list_canvas.create_window((0, 0), window=self.list_container, anchor='nw')

        self.list_container.bind('<Configure>', self._on_list_configure)
        self.list_canvas.bind('<Configure>', self._on_canvas_configure)

        # Right side: Session transcript
        self.detail_frame = tk.Frame(self.paned, bg=self.BG_COLOR, highlightthickness=0)
        self.paned.add(self.detail_frame, stretch='always')

        self._setup_detail_view()

    def _setup_detail_view(self):
        """Set up the detail view for selected session."""
        # Header
        header = tk.Frame(self.detail_frame, bg=self.BG_COLOR)
        header.pack(fill='x', padx=10, pady=10)

        self.detail_title = tk.Label(
            header,
            text='Select a session',
            font=('Segoe UI', 14, 'bold'),
            bg=self.BG_COLOR,
            fg=self.FG_COLOR
        )
        self.detail_title.pack(side='left')

        self.detail_info = tk.Label(
            header,
            text='',
            font=('Segoe UI', 10),
            bg=self.BG_COLOR,
            fg='#6b7280'
        )
        self.detail_info.pack(side='left', padx=(10, 0))

        # Session stats
        self.stats_frame = tk.Frame(self.detail_frame, bg=self.BG_COLOR)
        self.stats_frame.pack(fill='x', padx=10)

        # Speaker breakdown
        self.speakers_frame = tk.LabelFrame(self.stats_frame, text='Speakers', bg=self.BG_COLOR, fg=self.FG_COLOR, font=('Segoe UI', 10, 'bold'))
        self.speakers_frame.pack(side='left', padx=5, pady=5)

        self.speaker_stats_label = tk.Label(
            self.speakers_frame,
            text='',
            justify='left',
            bg=self.BG_COLOR,
            fg=self.SECONDARY_FG
        )
        self.speaker_stats_label.pack(padx=5, pady=5)

        # Transcript view
        self.transcript = TranscriptView(self.detail_frame)
        self.transcript.pack(fill='both', expand=True, padx=10, pady=5)

    def _on_list_configure(self, event=None):
        """Handle list container resize."""
        self.list_canvas.configure(scrollregion=self.list_canvas.bbox('all'))

    def _on_canvas_configure(self, event=None):
        """Handle canvas resize."""
        self.list_canvas.itemconfig(self.list_window, width=event.width)

    def _on_filter_change(self, event=None):
        """Handle filter selection change."""
        # This would be implemented to filter sessions by speaker
        # For now, just a placeholder
        pass

    def add_session(
        self,
        session_id: int,
        name: str,
        start_time: datetime,
        duration_seconds: int = 0,
        speaker_count: int = 0,
        utterance_count: int = 0
    ):
        """Add a session to the list.

        Args:
            session_id: Database ID
            name: Session name
            start_time: Session start time
            duration_seconds: Duration in seconds
            speaker_count: Number of speakers
            utterance_count: Number of utterances
        """
        if session_id in self._sessions:
            return

        item = SessionListItem(
            self.list_container,
            session_id=session_id,
            name=name,
            start_time=start_time,
            duration_seconds=duration_seconds,
            speaker_count=speaker_count,
            utterance_count=utterance_count,
            on_select=self._on_session_select
        )
        item.pack(fill='x', pady=1)

        self._sessions[session_id] = item

    def _on_session_select(self, session_id: int):
        """Handle session selection."""
        # Update selection state
        for sid, item in self._sessions.items():
            item.set_selected(sid == session_id)

        self._selected_session_id = session_id

        # Notify callback
        if self.on_load_session:
            self.on_load_session(session_id)

    def load_session_transcript(
        self,
        session_name: str,
        start_time: datetime,
        utterances: List[Dict],
        speaker_stats: Dict[str, int]
    ):
        """Load and display a session's transcript.

        Args:
            session_name: Session name for header
            start_time: Session start time
            utterances: List of utterance dicts
            speaker_stats: Dict of speaker -> word count
        """
        # Update header
        time_str = start_time.strftime('%Y-%m-%d %H:%M')
        self.detail_title.config(text=f'{session_name}')
        self.detail_info.config(text=f'{time_str}')

        # Update speaker stats
        stats_text = ''
        for speaker, word_count in sorted(speaker_stats.items(), key=lambda x: -x[1]):
            stats_text += f'{speaker}: {word_count:,} words\n'
        self.speaker_stats_label.config(text=stats_text or 'No speakers')

        # Load transcript
        self.transcript.clear()
        for u in utterances:
            self.transcript.add_utterance(
                speaker=u.get('speaker', 'Unknown'),
                text=u.get('text', ''),
                timestamp=u.get('timestamp'),
                vak=u.get('vak'),
                need=u.get('need')
            )

    def update_filter_speakers(self, speakers: List[str]):
        """Update the speaker filter dropdown.

        Args:
            speakers: List of speaker names
        """
        values = ['All speakers'] + sorted(speakers)
        self.filter_combo['values'] = values

    def clear(self):
        """Clear all sessions from the list."""
        for item in self._sessions.values():
            item.destroy()
        self._sessions.clear()
        self._selected_session_id = None

        self.detail_title.config(text='Select a session')
        self.detail_info.config(text='')
        self.speaker_stats_label.config(text='')
        self.transcript.clear()

    def get_selected_session_id(self) -> Optional[int]:
        """Get the currently selected session ID."""
        return self._selected_session_id
