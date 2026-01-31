"""Live and historical transcript view component."""

import tkinter as tk
from tkinter import ttk
from typing import Optional, List, Dict
from datetime import datetime


class TranscriptView(tk.Frame):
    """Widget for displaying live transcript stream and historical transcripts."""

    def __init__(self, parent, **kwargs):
        """Initialize transcript view.

        Args:
            parent: Parent widget
        """
        kwargs.setdefault('bg', '#1e1e2e')
        kwargs.setdefault('highlightthickness', 0)
        super().__init__(parent, **kwargs)
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI components."""
        bg_color = '#1e1e2e'

        # Main frame with scrollable text
        self.text_frame = tk.Frame(self, bg=bg_color, highlightthickness=0)
        self.text_frame.pack(fill='both', expand=True)

        # Scrollbar - dark themed
        self.scrollbar = tk.Scrollbar(
            self.text_frame,
            bg='#313244',
            troughcolor=bg_color,
            activebackground='#45475a',
            highlightthickness=0,
            bd=0
        )
        self.scrollbar.pack(side='right', fill='y')

        # Text widget for transcript
        self.text = tk.Text(
            self.text_frame,
            wrap='word',
            font=('Consolas', 10),
            bg=bg_color,
            fg='#cdd6f4',
            insertbackground='white',
            selectbackground='#45475a',
            yscrollcommand=self.scrollbar.set,
            state='disabled',
            padx=10,
            pady=10,
            highlightthickness=0,
            bd=0
        )
        self.text.pack(side='left', fill='both', expand=True)
        self.scrollbar.config(command=self.text.yview)

        # Configure tags for styling
        self.text.tag_configure('speaker', foreground='#89b4fa', font=('Consolas', 10, 'bold'))
        self.text.tag_configure('timestamp', foreground='#6c7086', font=('Consolas', 9))
        self.text.tag_configure('text', foreground='#cdd6f4')
        self.text.tag_configure('vak_visual', foreground='#f9e2af')
        self.text.tag_configure('vak_auditory', foreground='#a6e3a1')
        self.text.tag_configure('vak_kinesthetic', foreground='#f5c2e7')
        self.text.tag_configure('need', foreground='#fab387')
        self.text.tag_configure('highlight', background='#45475a')

        # Auto-scroll flag
        self._auto_scroll = True

        # Bind scroll events
        self.text.bind('<MouseWheel>', self._on_scroll)
        self.text.bind('<Button-4>', self._on_scroll)
        self.text.bind('<Button-5>', self._on_scroll)

    def _on_scroll(self, event):
        """Handle scroll events to disable auto-scroll when user scrolls up."""
        # Check if scrolled to bottom
        self._auto_scroll = self.text.yview()[1] >= 0.99

    def add_utterance(
        self,
        speaker: str,
        text: str,
        timestamp: Optional[datetime] = None,
        vak: Optional[str] = None,
        need: Optional[str] = None
    ):
        """Add a new utterance to the transcript.

        Args:
            speaker: Speaker name
            text: Transcribed text
            timestamp: Time of utterance (defaults to now)
            vak: Detected VAK modality
            need: Detected social need
        """
        if timestamp is None:
            timestamp = datetime.now()

        self.text.config(state='normal')

        # Add timestamp
        time_str = timestamp.strftime('%H:%M:%S')
        self.text.insert('end', f'[{time_str}] ', 'timestamp')

        # Add speaker name
        self.text.insert('end', f'{speaker}', 'speaker')

        # Add VAK/Need badges if available
        if vak:
            vak_tag = f'vak_{vak.lower()}'
            vak_emoji = {'visual': ' [V]', 'auditory': ' [A]', 'kinesthetic': ' [K]'}.get(vak.lower(), '')
            self.text.insert('end', vak_emoji, vak_tag)

        if need:
            need_short = need[:3].upper()
            self.text.insert('end', f' [{need_short}]', 'need')

        self.text.insert('end', ': ', 'speaker')

        # Add text
        self.text.insert('end', f'{text}\n\n', 'text')

        self.text.config(state='disabled')

        # Auto-scroll to bottom if enabled
        if self._auto_scroll:
            self.text.see('end')

    def clear(self):
        """Clear the transcript."""
        self.text.config(state='normal')
        self.text.delete('1.0', 'end')
        self.text.config(state='disabled')

    def load_utterances(self, utterances: List[Dict]):
        """Load a list of utterances (for historical view).

        Args:
            utterances: List of dicts with speaker, text, timestamp, vak, need keys
        """
        self.clear()

        for u in utterances:
            self.add_utterance(
                speaker=u.get('speaker', 'Unknown'),
                text=u.get('text', ''),
                timestamp=u.get('timestamp'),
                vak=u.get('vak'),
                need=u.get('need')
            )

    def set_auto_scroll(self, enabled: bool):
        """Enable or disable auto-scrolling.

        Args:
            enabled: Whether to auto-scroll
        """
        self._auto_scroll = enabled

    def highlight_speaker(self, speaker: str):
        """Highlight all utterances from a specific speaker.

        Args:
            speaker: Speaker name to highlight
        """
        self.text.tag_remove('highlight', '1.0', 'end')

        start = '1.0'
        while True:
            pos = self.text.search(f'{speaker}:', start, stopindex='end')
            if not pos:
                break

            # Find the line containing this speaker
            line_start = f'{pos.split(".")[0]}.0'
            line_end = f'{int(pos.split(".")[0]) + 1}.0'

            # Find the next blank line (utterance separator)
            next_blank = self.text.search(r'\n\n', pos, stopindex='end', regexp=True)
            if next_blank:
                line_end = next_blank

            self.text.tag_add('highlight', line_start, line_end)
            start = line_end


class LiveTranscriptPanel(tk.Frame):
    """Panel containing live transcript with status indicators."""

    def __init__(self, parent, **kwargs):
        # Set dark background
        kwargs.setdefault('bg', '#1e1e2e')
        kwargs.setdefault('highlightthickness', 0)
        """Initialize live transcript panel.

        Args:
            parent: Parent widget
        """
        super().__init__(parent, **kwargs)
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI components."""
        bg_color = '#1e1e2e'
        fg_color = '#cdd6f4'

        # Status bar at top - use tk.Frame for dark theme
        self.status_frame = tk.Frame(self, bg=bg_color, highlightthickness=0)
        self.status_frame.pack(fill='x', padx=5, pady=5)

        # Recording indicator
        self.recording_indicator = tk.Label(
            self.status_frame,
            text='',
            font=('Segoe UI', 10),
            bg=bg_color,
            fg='#6b7280'
        )
        self.recording_indicator.pack(side='left')

        # Current speaker
        self.current_speaker_label = tk.Label(
            self.status_frame,
            text='No speaker detected',
            font=('Segoe UI', 10, 'bold'),
            bg=bg_color,
            fg=fg_color
        )
        self.current_speaker_label.pack(side='left', padx=(10, 0))

        # VAK/Need badges
        self.badges_frame = tk.Frame(self.status_frame, bg=bg_color)
        self.badges_frame.pack(side='right')

        self.vak_label = tk.Label(
            self.badges_frame,
            text='',
            font=('Segoe UI', 9),
            bg=bg_color,
            fg='#f9e2af'
        )
        self.vak_label.pack(side='left', padx=2)

        self.need_label = tk.Label(
            self.badges_frame,
            text='',
            font=('Segoe UI', 9),
            bg=bg_color,
            fg='#fab387'
        )
        self.need_label.pack(side='left', padx=2)

        # Transcript view
        self.transcript = TranscriptView(self)
        self.transcript.pack(fill='both', expand=True, padx=5, pady=5)

    def set_recording_state(self, recording: bool):
        """Update recording indicator.

        Args:
            recording: Whether currently recording
        """
        if recording:
            self.recording_indicator.config(
                text='REC',
                fg='#ef4444'
            )
        else:
            self.recording_indicator.config(
                text='IDLE',
                fg='#6b7280'
            )

    def set_current_speaker(self, speaker: str, vak: Optional[str] = None, need: Optional[str] = None):
        """Update current speaker display.

        Args:
            speaker: Current speaker name
            vak: Current VAK modality
            need: Current social need
        """
        self.current_speaker_label.config(text=speaker)

        # Update VAK badge
        if vak:
            vak_colors = {
                'visual': '#f59e0b',
                'auditory': '#10b981',
                'kinesthetic': '#ec4899'
            }
            self.vak_label.config(
                text=f' {vak.upper()[0]} ',
                bg=vak_colors.get(vak.lower(), '#6b7280'),
                fg='white'
            )
        else:
            self.vak_label.config(text='', bg='#1e1e2e')

        # Update need badge
        if need:
            self.need_label.config(
                text=f' {need[:3].upper()} ',
                bg='#f97316',
                fg='white'
            )
        else:
            self.need_label.config(text='', bg='#1e1e2e')

    def add_utterance(self, speaker: str, text: str, **kwargs):
        """Add utterance to transcript.

        Args:
            speaker: Speaker name
            text: Transcribed text
            **kwargs: Additional arguments passed to TranscriptView.add_utterance
        """
        self.transcript.add_utterance(speaker, text, **kwargs)

    def clear(self):
        """Clear the transcript."""
        self.transcript.clear()
        self.current_speaker_label.config(text='No speaker detected')
        self.vak_label.config(text='')
        self.need_label.config(text='')
