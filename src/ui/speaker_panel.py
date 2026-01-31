"""Speaker management panel with rename/delete and Claude analysis history."""

import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from typing import Optional, Callable, Dict, List
from datetime import datetime
import json


class SpeakerListItem(tk.Frame):
    """Individual speaker item in the list."""

    BG_COLOR = '#1e1e2e'
    FG_COLOR = '#cdd6f4'
    HOVER_COLOR = '#374151'
    SELECT_COLOR = '#3b82f6'

    def __init__(
        self,
        parent,
        speaker_id: int,
        name: str,
        word_count: int = 0,
        last_seen: Optional[datetime] = None,
        sessions_count: int = 0,
        on_select: Optional[Callable] = None,
        **kwargs
    ):
        """Initialize speaker list item.

        Args:
            parent: Parent widget
            speaker_id: Database ID of speaker
            name: Display name
            word_count: Total words from this speaker
            last_seen: Last activity time
            sessions_count: Number of sessions
            on_select: Callback when item is selected
        """
        kwargs['bg'] = self.BG_COLOR
        kwargs['highlightthickness'] = 0
        super().__init__(parent, **kwargs)
        self.speaker_id = speaker_id
        self.name = name
        self.on_select = on_select
        self._selected = False

        self._setup_ui(word_count, last_seen, sessions_count)

    def _setup_ui(self, word_count: int, last_seen: Optional[datetime], sessions_count: int):
        """Set up the UI."""
        # Bind click events
        self.bind('<Button-1>', self._on_click)
        self.bind('<Enter>', self._on_enter)
        self.bind('<Leave>', self._on_leave)

        # Name label
        self.name_label = tk.Label(
            self,
            text=self.name,
            font=('Segoe UI', 11, 'bold'),
            bg=self.BG_COLOR,
            fg=self.FG_COLOR
        )
        self.name_label.pack(anchor='w', padx=10, pady=(5, 0))
        self.name_label.bind('<Button-1>', self._on_click)

        # Stats frame
        stats_frame = tk.Frame(self, bg=self.BG_COLOR)
        stats_frame.pack(anchor='w', fill='x', padx=10, pady=(0, 5))
        stats_frame.bind('<Button-1>', self._on_click)

        # Word count
        self.word_label = tk.Label(
            stats_frame,
            text=f'{word_count:,} words',
            font=('Segoe UI', 9),
            bg=self.BG_COLOR,
            fg='#6b7280'
        )
        self.word_label.pack(side='left')
        self.word_label.bind('<Button-1>', self._on_click)

        # Sessions count
        self.sessions_label = tk.Label(
            stats_frame,
            text=f' | {sessions_count} sessions',
            font=('Segoe UI', 9),
            bg=self.BG_COLOR,
            fg='#6b7280'
        )
        self.sessions_label.pack(side='left')
        self.sessions_label.bind('<Button-1>', self._on_click)

        # Last seen
        if last_seen:
            last_seen_str = last_seen.strftime('%Y-%m-%d %H:%M')
            self.last_seen_label = tk.Label(
                stats_frame,
                text=f' | Last: {last_seen_str}',
                font=('Segoe UI', 9),
                bg=self.BG_COLOR,
                fg='#6b7280'
            )
            self.last_seen_label.pack(side='left')
            self.last_seen_label.bind('<Button-1>', self._on_click)

    def _on_click(self, event=None):
        """Handle click event."""
        if self.on_select:
            self.on_select(self.speaker_id, self.name)

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

    def update_stats(self, word_count: int, sessions_count: int, last_seen: Optional[datetime] = None):
        """Update displayed statistics."""
        self.word_label.config(text=f'{word_count:,} words')
        self.sessions_label.config(text=f' | {sessions_count} sessions')
        if last_seen and hasattr(self, 'last_seen_label'):
            self.last_seen_label.config(text=f' | Last: {last_seen.strftime("%Y-%m-%d %H:%M")}')


class SpeakerPanel(tk.Frame):
    """Panel for managing speakers with list and details view."""

    BG_COLOR = '#1e1e2e'
    FG_COLOR = '#cdd6f4'
    SECONDARY_FG = '#a6adc8'
    BTN_BG = '#313244'
    BTN_HOVER = '#45475a'

    def __init__(
        self,
        parent,
        on_rename: Optional[Callable] = None,
        on_delete: Optional[Callable] = None,
        on_analyze: Optional[Callable] = None,
        on_select: Optional[Callable] = None,
        **kwargs
    ):
        """Initialize speaker panel.

        Args:
            parent: Parent widget
            on_rename: Callback(speaker_id, old_name, new_name) when speaker is renamed
            on_delete: Callback(speaker_id, name) when speaker is deleted
            on_analyze: Callback(speaker_id, name) to trigger Claude analysis
            on_select: Callback(speaker_id, name) when speaker is selected
        """
        kwargs.setdefault('bg', self.BG_COLOR)
        kwargs.setdefault('highlightthickness', 0)
        super().__init__(parent, **kwargs)

        self.on_rename = on_rename
        self.on_delete = on_delete
        self.on_analyze = on_analyze
        self.on_select = on_select

        self._speakers: Dict[int, SpeakerListItem] = {}
        self._selected_speaker_id: Optional[int] = None

        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI."""
        # Use PanedWindow for resizable split
        self.paned = tk.PanedWindow(self, orient='horizontal', bg=self.BG_COLOR, sashwidth=4, sashrelief='flat', bd=0)
        self.paned.pack(fill='both', expand=True)

        # Left side: Speaker list
        self.list_frame = tk.Frame(self.paned, bg=self.BG_COLOR, highlightthickness=0)
        self.paned.add(self.list_frame, stretch='always')

        # List header
        list_header = tk.Frame(self.list_frame, bg=self.BG_COLOR)
        list_header.pack(fill='x', padx=5, pady=5)

        tk.Label(
            list_header,
            text='Speakers',
            font=('Segoe UI', 12, 'bold'),
            bg=self.BG_COLOR,
            fg=self.FG_COLOR
        ).pack(side='left')

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

        # Right side: Speaker details
        self.detail_frame = tk.Frame(self.paned, bg=self.BG_COLOR, highlightthickness=0)
        self.paned.add(self.detail_frame, stretch='always')

        self._setup_detail_view()

    def _setup_detail_view(self):
        """Set up the detail view for selected speaker."""
        # Header with name and actions
        header = tk.Frame(self.detail_frame, bg=self.BG_COLOR)
        header.pack(fill='x', padx=10, pady=10)

        self.detail_name = tk.Label(
            header,
            text='Select a speaker',
            font=('Segoe UI', 14, 'bold'),
            bg=self.BG_COLOR,
            fg=self.FG_COLOR
        )
        self.detail_name.pack(side='left')

        # Action buttons
        actions = tk.Frame(header, bg=self.BG_COLOR)
        actions.pack(side='right')

        self.rename_btn = tk.Button(
            actions,
            text='Rename',
            command=self._do_rename,
            state='disabled',
            bg=self.BTN_BG,
            fg=self.FG_COLOR,
            activebackground=self.BTN_HOVER,
            activeforeground=self.FG_COLOR,
            bd=0,
            padx=10,
            pady=4
        )
        self.rename_btn.pack(side='left', padx=2)

        self.analyze_btn = tk.Button(
            actions,
            text='Analyze Now',
            command=self._do_analyze,
            state='disabled',
            bg='#22c55e',
            fg='white',
            activebackground='#16a34a',
            activeforeground='white',
            bd=0,
            padx=10,
            pady=4
        )
        self.analyze_btn.pack(side='left', padx=2)

        self.delete_btn = tk.Button(
            actions,
            text='Delete',
            command=self._do_delete,
            state='disabled',
            bg='#ef4444',
            fg='white',
            activebackground='#dc2626',
            activeforeground='white',
            bd=0,
            padx=10,
            pady=4
        )
        self.delete_btn.pack(side='left', padx=2)

        # Notebook for tabs - use ttk but with dark theme style
        style = ttk.Style()
        style.configure('Dark.TNotebook', background=self.BG_COLOR)
        style.configure('Dark.TNotebook.Tab', background='#313244', foreground=self.FG_COLOR, padding=[10, 4])
        style.map('Dark.TNotebook.Tab',
                  background=[('selected', '#45475a')],
                  foreground=[('selected', self.FG_COLOR)])

        self.detail_notebook = ttk.Notebook(self.detail_frame, style='Dark.TNotebook')
        self.detail_notebook.pack(fill='both', expand=True, padx=10, pady=5)

        # Profile tab
        self.profile_tab = tk.Frame(self.detail_notebook, bg=self.BG_COLOR)
        self.detail_notebook.add(self.profile_tab, text='Profile')
        self._setup_profile_tab()

        # Text tab
        self.text_tab = tk.Frame(self.detail_notebook, bg=self.BG_COLOR)
        self.detail_notebook.add(self.text_tab, text='All Text')
        self._setup_text_tab()

        # Analysis history tab
        self.analysis_tab = tk.Frame(self.detail_notebook, bg=self.BG_COLOR)
        self.detail_notebook.add(self.analysis_tab, text='Claude Analysis')
        self._setup_analysis_tab()

    def _setup_profile_tab(self):
        """Set up the profile summary tab."""
        # VAK section
        vak_frame = tk.LabelFrame(self.profile_tab, text='VAK Modality', bg=self.BG_COLOR, fg=self.FG_COLOR, font=('Segoe UI', 10, 'bold'))
        vak_frame.pack(fill='x', padx=5, pady=5)

        vak_colors = {'Visual': '#f9e2af', 'Auditory': '#a6e3a1', 'Kinesthetic': '#f5c2e7'}
        self.vak_labels = {}
        for vak in ['Visual', 'Auditory', 'Kinesthetic']:
            frame = tk.Frame(vak_frame, bg=self.BG_COLOR)
            frame.pack(fill='x', padx=5, pady=2)

            tk.Label(frame, text=f'{vak}:', width=12, anchor='w', bg=self.BG_COLOR, fg=self.FG_COLOR).pack(side='left')

            # Custom progress bar using Canvas
            progress = tk.Canvas(frame, width=150, height=16, bg='#313244', highlightthickness=0)
            progress.pack(side='left', padx=5)
            progress.bar_color = vak_colors[vak]
            progress.create_rectangle(0, 0, 0, 16, fill=progress.bar_color, tags='bar')

            label = tk.Label(frame, text='0%', width=6, bg=self.BG_COLOR, fg=self.SECONDARY_FG)
            label.pack(side='left')

            self.vak_labels[vak.lower()] = (progress, label)

        # Social needs section
        needs_frame = tk.LabelFrame(self.profile_tab, text='Social Needs', bg=self.BG_COLOR, fg=self.FG_COLOR, font=('Segoe UI', 10, 'bold'))
        needs_frame.pack(fill='x', padx=5, pady=5)

        self.need_labels = {}
        for need in ['Significance', 'Approval', 'Acceptance', 'Intelligence', 'Pity', 'Power']:
            frame = tk.Frame(needs_frame, bg=self.BG_COLOR)
            frame.pack(fill='x', padx=5, pady=2)

            tk.Label(frame, text=f'{need}:', width=12, anchor='w', bg=self.BG_COLOR, fg=self.FG_COLOR).pack(side='left')

            # Custom progress bar using Canvas
            progress = tk.Canvas(frame, width=150, height=16, bg='#313244', highlightthickness=0)
            progress.pack(side='left', padx=5)
            progress.bar_color = '#fab387'
            progress.create_rectangle(0, 0, 0, 16, fill=progress.bar_color, tags='bar')

            label = tk.Label(frame, text='0%', width=6, bg=self.BG_COLOR, fg=self.SECONDARY_FG)
            label.pack(side='left')

            self.need_labels[need.lower()] = (progress, label)

        # Communication patterns
        comm_frame = tk.LabelFrame(self.profile_tab, text='Communication', bg=self.BG_COLOR, fg=self.FG_COLOR, font=('Segoe UI', 10, 'bold'))
        comm_frame.pack(fill='x', padx=5, pady=5)

        self.comm_labels = {}
        for pattern in ['Certainty', 'Complexity', 'Sentiment']:
            frame = tk.Frame(comm_frame, bg=self.BG_COLOR)
            frame.pack(fill='x', padx=5, pady=2)

            tk.Label(frame, text=f'{pattern}:', width=12, anchor='w', bg=self.BG_COLOR, fg=self.FG_COLOR).pack(side='left')
            label = tk.Label(frame, text='-', bg=self.BG_COLOR, fg=self.SECONDARY_FG)
            label.pack(side='left')

            self.comm_labels[pattern.lower()] = label

    def _setup_text_tab(self):
        """Set up the all text tab."""
        # Scrollable text view
        text_frame = tk.Frame(self.text_tab, bg=self.BG_COLOR)
        text_frame.pack(fill='both', expand=True, padx=5, pady=5)

        scrollbar = tk.Scrollbar(
            text_frame,
            bg='#313244',
            troughcolor=self.BG_COLOR,
            activebackground='#45475a',
            highlightthickness=0,
            bd=0
        )
        scrollbar.pack(side='right', fill='y')

        self.all_text = tk.Text(
            text_frame,
            wrap='word',
            font=('Consolas', 10),
            bg=self.BG_COLOR,
            fg=self.FG_COLOR,
            insertbackground='white',
            selectbackground='#45475a',
            state='disabled',
            yscrollcommand=scrollbar.set,
            highlightthickness=0,
            bd=0,
            padx=10,
            pady=10
        )
        self.all_text.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=self.all_text.yview)

    def _setup_analysis_tab(self):
        """Set up the Claude analysis history tab."""
        # Scrollable list of analyses
        analysis_frame = tk.Frame(self.analysis_tab, bg=self.BG_COLOR)
        analysis_frame.pack(fill='both', expand=True, padx=5, pady=5)

        scrollbar = tk.Scrollbar(
            analysis_frame,
            bg='#313244',
            troughcolor=self.BG_COLOR,
            activebackground='#45475a',
            highlightthickness=0,
            bd=0
        )
        scrollbar.pack(side='right', fill='y')

        self.analysis_text = tk.Text(
            analysis_frame,
            wrap='word',
            font=('Segoe UI', 10),
            bg=self.BG_COLOR,
            fg=self.FG_COLOR,
            insertbackground='white',
            selectbackground='#45475a',
            state='disabled',
            yscrollcommand=scrollbar.set,
            highlightthickness=0,
            bd=0,
            padx=10,
            pady=10
        )
        self.analysis_text.pack(side='left', fill='both', expand=True)
        scrollbar.config(command=self.analysis_text.yview)

        # Configure tags
        self.analysis_text.tag_configure('header', font=('Segoe UI', 11, 'bold'), foreground='#89b4fa')
        self.analysis_text.tag_configure('label', foreground='#a6adc8', font=('Segoe UI', 10, 'bold'))
        self.analysis_text.tag_configure('value', foreground=self.FG_COLOR)
        self.analysis_text.tag_configure('warning', foreground='#f38ba8')
        self.analysis_text.tag_configure('positive', foreground='#a6e3a1')

    def _on_list_configure(self, event=None):
        """Handle list container resize."""
        self.list_canvas.configure(scrollregion=self.list_canvas.bbox('all'))

    def _on_canvas_configure(self, event=None):
        """Handle canvas resize."""
        self.list_canvas.itemconfig(self.list_window, width=event.width)

    def add_speaker(
        self,
        speaker_id: int,
        name: str,
        word_count: int = 0,
        last_seen: Optional[datetime] = None,
        sessions_count: int = 0
    ):
        """Add a speaker to the list.

        Args:
            speaker_id: Database ID
            name: Display name
            word_count: Total words
            last_seen: Last activity
            sessions_count: Number of sessions
        """
        if speaker_id in self._speakers:
            # Update existing
            self._speakers[speaker_id].update_stats(word_count, sessions_count, last_seen)
            return

        item = SpeakerListItem(
            self.list_container,
            speaker_id=speaker_id,
            name=name,
            word_count=word_count,
            last_seen=last_seen,
            sessions_count=sessions_count,
            on_select=self._on_speaker_select
        )
        item.pack(fill='x', pady=1)

        self._speakers[speaker_id] = item

    def remove_speaker(self, speaker_id: int):
        """Remove a speaker from the list."""
        if speaker_id in self._speakers:
            self._speakers[speaker_id].destroy()
            del self._speakers[speaker_id]

            if self._selected_speaker_id == speaker_id:
                self._selected_speaker_id = None
                self._clear_detail_view()

    def update_speaker(self, speaker_id: int, name: str = None, word_count: int = None, **kwargs):
        """Update speaker information."""
        if speaker_id not in self._speakers:
            return

        item = self._speakers[speaker_id]

        if name:
            item.name = name
            item.name_label.config(text=name)

        if word_count is not None:
            item.word_label.config(text=f'{word_count:,} words')

    def _on_speaker_select(self, speaker_id: int, name: str):
        """Handle speaker selection."""
        # Update selection state
        for sid, item in self._speakers.items():
            item.set_selected(sid == speaker_id)

        self._selected_speaker_id = speaker_id

        # Update detail view
        self.detail_name.config(text=name)
        self.rename_btn.config(state='normal')
        self.analyze_btn.config(state='normal')
        self.delete_btn.config(state='normal')

        # Notify main app to load speaker data
        if self.on_select:
            self.on_select(speaker_id, name)

    def _clear_detail_view(self):
        """Clear the detail view."""
        self.detail_name.config(text='Select a speaker')
        self.rename_btn.config(state='disabled')
        self.analyze_btn.config(state='disabled')
        self.delete_btn.config(state='disabled')

        # Clear profile
        for progress, label in self.vak_labels.values():
            progress.delete('bar')
            progress.create_rectangle(0, 0, 0, 16, fill=progress.bar_color, tags='bar')
            label.config(text='0%')

        for progress, label in self.need_labels.values():
            progress.delete('bar')
            progress.create_rectangle(0, 0, 0, 16, fill=progress.bar_color, tags='bar')
            label.config(text='0%')

        for label in self.comm_labels.values():
            label.config(text='-')

        # Clear text
        self.all_text.config(state='normal')
        self.all_text.delete('1.0', 'end')
        self.all_text.config(state='disabled')

        # Clear analysis
        self.analysis_text.config(state='normal')
        self.analysis_text.delete('1.0', 'end')
        self.analysis_text.config(state='disabled')

    def update_profile_display(self, profile: Dict):
        """Update the profile tab with speaker data.

        Args:
            profile: Dictionary with vak, needs, communication pattern data
        """
        # Update VAK
        vak_scores = profile.get('vak', {})
        for vak, (progress, label) in self.vak_labels.items():
            score = vak_scores.get(vak, 0)
            # Update canvas progress bar
            width = int(score * 150)
            progress.delete('bar')
            progress.create_rectangle(0, 0, width, 16, fill=progress.bar_color, tags='bar')
            label.config(text=f'{score:.0%}')

        # Update needs
        needs = profile.get('needs', {})
        for need, (progress, label) in self.need_labels.items():
            score = needs.get(need, 0)
            # Update canvas progress bar
            width = int(score * 150)
            progress.delete('bar')
            progress.create_rectangle(0, 0, width, 16, fill=progress.bar_color, tags='bar')
            label.config(text=f'{score:.0%}')

        # Update communication
        comm = profile.get('communication', {})
        if 'certainty' in comm:
            self.comm_labels['certainty'].config(text=f'{comm["certainty"]:.0%}')
        if 'complexity' in comm:
            self.comm_labels['complexity'].config(text=f'{comm["complexity"]:.1f}')
        if 'sentiment' in comm:
            sent = comm['sentiment']
            sent_text = 'Positive' if sent > 0.2 else 'Negative' if sent < -0.2 else 'Neutral'
            self.comm_labels['sentiment'].config(text=sent_text)

    def update_all_text(self, text: str):
        """Update the all text tab.

        Args:
            text: All text from speaker
        """
        self.all_text.config(state='normal')
        self.all_text.delete('1.0', 'end')
        self.all_text.insert('1.0', text)
        self.all_text.config(state='disabled')

    def update_analysis_history(self, analyses: List[Dict]):
        """Update the analysis history tab.

        Args:
            analyses: List of analysis results with timestamp, word_count, insights
        """
        self.analysis_text.config(state='normal')
        self.analysis_text.delete('1.0', 'end')

        if not analyses:
            self.analysis_text.insert('end', 'No Claude analyses yet.\n\nClick "Analyze Now" to generate insights.')
            self.analysis_text.config(state='disabled')
            return

        for i, analysis in enumerate(analyses):
            timestamp = analysis.get('timestamp')
            if isinstance(timestamp, datetime):
                time_str = timestamp.strftime('%Y-%m-%d %H:%M')
            else:
                time_str = str(timestamp)

            word_count = analysis.get('word_count', 0)
            insights = analysis.get('insights', {})

            # Header
            self.analysis_text.insert('end', f'\n Analysis at {time_str} ({word_count:,} words)\n', 'header')
            self.analysis_text.insert('end', '-' * 50 + '\n\n')

            # Insights
            if insights.get('personality_summary'):
                self.analysis_text.insert('end', 'Personality: ', 'label')
                self.analysis_text.insert('end', f'{insights["personality_summary"]}\n\n', 'value')

            if insights.get('communication_style'):
                self.analysis_text.insert('end', 'Style: ', 'label')
                self.analysis_text.insert('end', f'{insights["communication_style"]}\n\n', 'value')

            if insights.get('likely_values'):
                values = ', '.join(insights['likely_values'])
                self.analysis_text.insert('end', 'Values: ', 'label')
                self.analysis_text.insert('end', f'{values}\n\n', 'value')

            if insights.get('rapport_tip'):
                self.analysis_text.insert('end', 'Rapport Tip: ', 'label')
                self.analysis_text.insert('end', f'{insights["rapport_tip"]}\n\n', 'positive')

            if insights.get('how_to_persuade'):
                self.analysis_text.insert('end', 'How to Persuade: ', 'label')
                self.analysis_text.insert('end', f'{insights["how_to_persuade"]}\n\n', 'value')

            if insights.get('honesty_assessment'):
                self.analysis_text.insert('end', 'Honesty: ', 'label')
                honesty = insights['honesty_assessment']
                tag = 'warning' if 'manipulative' in honesty.lower() or 'evasive' in honesty.lower() else 'value'
                self.analysis_text.insert('end', f'{honesty}\n\n', tag)

            if insights.get('deception_detected'):
                deceptions = insights['deception_detected']
                if deceptions:
                    self.analysis_text.insert('end', 'Deception Patterns: ', 'label')
                    self.analysis_text.insert('end', f'{", ".join(deceptions)}\n\n', 'warning')

            if insights.get('specific_red_flags'):
                self.analysis_text.insert('end', 'Red Flags: ', 'label')
                self.analysis_text.insert('end', f'{insights["specific_red_flags"]}\n\n', 'warning')

            if i < len(analyses) - 1:
                self.analysis_text.insert('end', '\n' + '=' * 50 + '\n')

        self.analysis_text.config(state='disabled')

    def _do_rename(self):
        """Handle rename button click."""
        if self._selected_speaker_id is None:
            return

        item = self._speakers.get(self._selected_speaker_id)
        if not item:
            return

        old_name = item.name
        new_name = simpledialog.askstring(
            'Rename Speaker',
            f'Enter new name for "{old_name}":',
            initialvalue=old_name
        )

        if new_name and new_name != old_name:
            if self.on_rename:
                self.on_rename(self._selected_speaker_id, old_name, new_name)

            # Update UI
            item.name = new_name
            item.name_label.config(text=new_name)
            self.detail_name.config(text=new_name)

    def _do_delete(self):
        """Handle delete button click."""
        if self._selected_speaker_id is None:
            return

        item = self._speakers.get(self._selected_speaker_id)
        if not item:
            return

        name = item.name
        if messagebox.askyesno(
            'Delete Speaker',
            f'Are you sure you want to delete "{name}"?\n\n'
            'This will remove all their data including:\n'
            '- All utterances/transcripts\n'
            '- All profile data\n'
            '- All Claude analyses\n\n'
            'This action cannot be undone.',
            icon='warning'
        ):
            if self.on_delete:
                self.on_delete(self._selected_speaker_id, name)

            self.remove_speaker(self._selected_speaker_id)

    def _do_analyze(self):
        """Handle analyze button click."""
        if self._selected_speaker_id is None:
            return

        item = self._speakers.get(self._selected_speaker_id)
        if not item:
            return

        if self.on_analyze:
            self.on_analyze(self._selected_speaker_id, item.name)

    def get_selected_speaker_id(self) -> Optional[int]:
        """Get the currently selected speaker ID."""
        return self._selected_speaker_id

    def clear(self):
        """Clear all speakers from the list."""
        for item in self._speakers.values():
            item.destroy()
        self._speakers.clear()
        self._selected_speaker_id = None
        self._clear_detail_view()
