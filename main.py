"""Windows Speech Profiler - Main Entry Point.

Standalone Windows application with:
- WASAPI loopback audio capture (no Voicemeeter needed)
- System tray operation
- Real-time transcript streaming
- Speaker management with rename/delete
- Claude analysis integration
- Session history browsing
"""

# Early debug - write to file before any imports
from pathlib import Path
_debug_file = Path(__file__).parent / "data" / "startup_debug.txt"
_debug_file.parent.mkdir(exist_ok=True)
with open(_debug_file, 'w') as f:
    f.write("Starting up...\n")

import sys
import logging
import threading
import queue
import time
import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict

import numpy as np

# Set up logging to both console and file
LOG_FILE = Path(__file__).parent / "data" / "profiler.log"
LOG_FILE.parent.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Console
        logging.FileHandler(LOG_FILE, mode='w', encoding='utf-8')  # File
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"Logging to: {LOG_FILE}")

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.config import config, DATA_DIR
from src.storage.database import init_db, get_db
from src.storage.models import Speaker, Session, Utterance, SpeakerProfile, AnalysisHistory
from src.audio.wasapi_capture import WASAPICapture, PYAUDIO_AVAILABLE
from src.audio.audio_processor import AudioProcessor, AudioChunk
from src.audio.speaker_identifier import SpeakerIdentifier, RESEMBLYZER_AVAILABLE
from src.profiling.linguistic_analyzer import LinguisticAnalyzer
from src.analysis.claude_analyzer import ClaudeAnalyzer, get_vak_tip, get_need_tip
from src.ui.dashboard import Dashboard
from src.ui.overlay import Overlay
from src.ui.system_tray import SystemTray, PYSTRAY_AVAILABLE


class SpeechProfiler:
    """Main application controller for the Speech Profiler."""

    def __init__(self):
        """Initialize the profiler application."""
        self.db = init_db()

        # Audio components
        self.capture: Optional[WASAPICapture] = None
        self.processor = AudioProcessor()
        self.identifier = SpeakerIdentifier() if RESEMBLYZER_AVAILABLE else None
        self.analyzer = LinguisticAnalyzer(use_spacy=False)
        self.claude = ClaudeAnalyzer()

        # State
        self.running = False
        self.current_session: Optional[Session] = None
        self.current_session_db_id: Optional[int] = None

        # Speaker tracking
        self.speaker_profiles: Dict[str, dict] = {}  # speaker_name -> profile data
        self.speaker_texts: Dict[str, list] = {}  # speaker_name -> list of texts
        self.speaker_db_ids: Dict[str, int] = {}  # speaker_name -> db id
        self.last_claude_word_count: Dict[str, int] = {}  # speaker_name -> word count at last analysis
        self.claude_insights: Dict[str, dict] = {}  # speaker_name -> latest insights

        # Voice embeddings for speaker matching
        self.known_voices: Dict[str, np.ndarray] = {}
        self.session_voices: Dict[str, list] = {}  # session-local unknown speakers
        self.unknown_counter = 0
        self.similarity_threshold = 0.85  # Higher = stricter matching (0.70 still caused false matches)

        # Load voice embeddings
        self._load_voice_embeddings()

        # Rebuild speaker profiles from database
        self._rebuild_speaker_profiles()

        # Processing queue
        self.audio_queue = queue.Queue()
        self.process_thread: Optional[threading.Thread] = None

        # UI components
        self.overlay: Optional[Overlay] = None
        self.dashboard: Optional[Dashboard] = None
        self.tray: Optional[SystemTray] = None
        self.current_speaker: Optional[str] = None  # Track for overlay updates

        # Session start time
        self.session_start_time: Optional[datetime] = None

    def _load_voice_embeddings(self):
        """Load registered voice embeddings from file."""
        embeddings_file = DATA_DIR / "voice_embeddings.json"
        if embeddings_file.exists():
            try:
                with open(embeddings_file) as f:
                    data = json.load(f)
                    self.known_voices = {
                        name: np.array(emb) for name, emb in data.items()
                    }
                logger.info(f"Loaded {len(self.known_voices)} voice embeddings")
            except Exception as e:
                logger.warning(f"Failed to load voice embeddings: {e}")

    def _save_voice_embeddings(self):
        """Save voice embeddings to file."""
        embeddings_file = DATA_DIR / "voice_embeddings.json"
        try:
            data = {
                name: emb.tolist() for name, emb in self.known_voices.items()
            }
            with open(embeddings_file, 'w') as f:
                json.dump(data, f)
            logger.info(f"Saved {len(self.known_voices)} voice embeddings")
        except Exception as e:
            logger.error(f"Failed to save voice embeddings: {e}")

    def _rebuild_speaker_profiles(self):
        """Rebuild speaker profiles from all stored utterances."""
        logger.info("Rebuilding speaker profiles from database...")

        try:
            with self.db.get_session() as session:
                # Get all speakers
                speakers = session.query(Speaker).all()

                for speaker in speakers:
                    name = speaker.display_name
                    speaker_id = speaker.id

                    # Get all utterances for this speaker
                    utterances = session.query(Utterance).filter_by(
                        speaker_db_id=speaker_id
                    ).all()

                    if not utterances:
                        continue

                    # Initialize profile
                    self.speaker_profiles[name] = {
                        'vak_scores': {'visual': 0, 'auditory': 0, 'kinesthetic': 0},
                        'need_scores': {},
                        'word_count': 0,
                    }
                    self.speaker_texts[name] = []
                    self.speaker_db_ids[name] = speaker_id

                    # Analyze all text
                    all_text = []
                    for utt in utterances:
                        all_text.append(utt.text)
                        self.speaker_texts[name].append(utt.text)

                    # Run linguistic analysis on combined text
                    combined_text = ' '.join(all_text)
                    if combined_text.strip():
                        analysis = self.analyzer.analyze(combined_text)

                        profile = self.speaker_profiles[name]
                        profile['word_count'] = len(combined_text.split())

                        if analysis:
                            for mod, score in analysis.vak_scores.items():
                                profile['vak_scores'][mod] = score
                            for need, score in analysis.social_needs.items():
                                profile['need_scores'][need] = score

                    logger.debug(f"Rebuilt profile for {name}: {len(utterances)} utterances")

                logger.info(f"Rebuilt profiles for {len(speakers)} speakers")

        except Exception as e:
            logger.error(f"Failed to rebuild speaker profiles: {e}")

    def _match_speaker(self, embedding: np.ndarray) -> tuple:
        """Match embedding to known or session speakers."""
        from scipy.spatial.distance import cosine

        best_match = None
        best_score = 0.0
        all_scores = []

        # First check registered voices
        for name, known_emb in self.known_voices.items():
            similarity = 1 - cosine(embedding, known_emb)
            all_scores.append((name, similarity, 'known'))
            if similarity > best_score and similarity > self.similarity_threshold:
                best_match = name
                best_score = similarity

        # If no registered match, check session voices
        if best_match is None:
            for name, emb_list in self.session_voices.items():
                avg_emb = np.mean(emb_list, axis=0)
                similarity = 1 - cosine(embedding, avg_emb)
                all_scores.append((name, similarity, 'session'))
                if similarity > best_score and similarity > self.similarity_threshold:
                    best_match = name
                    best_score = similarity

        # Log all scores for debugging
        if all_scores:
            scores_str = ', '.join([f"{n}:{s:.3f}" for n, s, _ in sorted(all_scores, key=lambda x: -x[1])[:5]])
            logger.debug(f"Speaker match scores (threshold={self.similarity_threshold}): {scores_str}")

        # If match found in session, add to their embedding list
        if best_match and best_match in self.session_voices:
            self.session_voices[best_match].append(embedding)
            if len(self.session_voices[best_match]) > 10:
                self.session_voices[best_match] = self.session_voices[best_match][-10:]

        # If still no match, create new unknown speaker
        if best_match is None:
            self.unknown_counter += 1
            best_match = f"Unknown {self.unknown_counter}"
            self.session_voices[best_match] = [embedding]
            best_score = 1.0
            logger.info(f"New speaker detected: {best_match}")
        else:
            logger.debug(f"Matched speaker: {best_match} (score={best_score:.3f})")

        return best_match, best_score

    def _audio_callback(self, chunk: AudioChunk):
        """Handle incoming audio chunks."""
        self.audio_queue.put(chunk)

    def _process_audio(self):
        """Background thread for processing audio."""
        buffer = []
        last_process_time = time.time()

        while self.running:
            try:
                # Collect audio chunks
                while not self.audio_queue.empty():
                    try:
                        chunk = self.audio_queue.get_nowait()
                        buffer.append(chunk.data)
                    except queue.Empty:
                        break

                # Process every 2 seconds for faster speaker switching
                if time.time() - last_process_time > 2 and buffer:
                    audio_data = np.concatenate(buffer)
                    sample_rate = 16000  # Our target rate

                    logger.info(f"Processing {len(audio_data)/sample_rate:.1f}s of audio...")

                    result = self._process_chunk(audio_data, sample_rate)

                    if result and result.get('text'):
                        self._handle_result(result)

                    buffer = []
                    last_process_time = time.time()

                time.sleep(0.1)

            except Exception as e:
                logger.error(f"Processing error: {e}", exc_info=True)

    def _process_chunk(self, audio_data: np.ndarray, sample_rate: int) -> Optional[dict]:
        """Process an audio chunk - identify speaker and transcribe."""
        result = {
            'speaker': 'Unknown',
            'confidence': 0.0,
            'text': '',
            'vak': None,
            'need': None,
        }

        # Identify speaker
        if self.identifier and len(audio_data) > sample_rate:
            try:
                embedding = self.identifier.extract_embedding(audio_data, sample_rate)
                if embedding is not None:
                    speaker, confidence = self._match_speaker(embedding)
                    result['speaker'] = speaker
                    result['confidence'] = confidence
            except Exception as e:
                logger.debug(f"Speaker identification failed: {e}")

        # Transcribe
        try:
            transcription = self.processor.transcribe(audio_data, sample_rate)
            text = transcription.text.strip()
            result['text'] = text

            if text and len(text.split()) > 3:
                # Analyze text
                analysis = self.analyzer.analyze(text)

                result['vak'] = analysis.get_dominant_vak()
                top_needs = analysis.get_top_needs(1)
                result['need'] = top_needs[0] if top_needs else None
                result['analysis'] = analysis
                result['deception_score'] = getattr(analysis, 'deception_score', 0)
                result['politician_score'] = getattr(analysis, 'politician_score', 0)

        except Exception as e:
            logger.error(f"Transcription error: {e}", exc_info=True)

        return result

    def _handle_result(self, result: dict):
        """Handle a processing result - update state and UI."""
        speaker = result['speaker']
        text = result['text']
        vak = result.get('vak')
        need = result.get('need')
        analysis = result.get('analysis')

        # Initialize speaker tracking if needed
        if speaker not in self.speaker_profiles:
            self.speaker_profiles[speaker] = {
                'vak_scores': {'visual': 0, 'auditory': 0, 'kinesthetic': 0},
                'need_scores': {},
                'word_count': 0,
            }
            self.speaker_texts[speaker] = []
            self.last_claude_word_count[speaker] = 0

            # Create speaker in database
            self._create_speaker_in_db(speaker)

        # Update speaker profile
        profile = self.speaker_profiles[speaker]
        if analysis:
            for mod, score in analysis.vak_scores.items():
                profile['vak_scores'][mod] += score
            for n, score in analysis.social_needs.items():
                profile['need_scores'][n] = profile['need_scores'].get(n, 0) + score
            profile['word_count'] += analysis.word_count

            # Track deception scores
            if result.get('deception_score', 0) > 0:
                old_dec = profile.get('deception_score', 0)
                profile['deception_score'] = old_dec * 0.7 + result['deception_score'] * 0.3
            if result.get('politician_score', 0) > 0:
                old_pol = profile.get('politician_score', 0)
                profile['politician_score'] = old_pol * 0.7 + result['politician_score'] * 0.3

            # Recalculate dominant VAK and need
            total_vak = sum(profile['vak_scores'].values())
            if total_vak > 0:
                profile['vak'] = max(profile['vak_scores'], key=profile['vak_scores'].get)
            if profile['need_scores']:
                profile['need'] = max(profile['need_scores'], key=profile['need_scores'].get)

        self.speaker_texts[speaker].append(text)

        # Save utterance to database
        self._save_utterance(speaker, text, vak, need)

        # Track current speaker
        self.current_speaker = speaker

        # Update overlay
        if self.overlay:
            self.overlay.update_speaker(
                speaker=speaker,
                confidence=result.get('confidence', 0),
                word_count=profile['word_count'],
                vak=profile.get('vak', vak),
                need=profile.get('need', need)
            )
            # Update Claude insights in overlay if available
            if speaker in self.claude_insights:
                self.overlay.update_claude_insights(self.claude_insights[speaker])

        # Update dashboard if open
        if self.dashboard:
            self.dashboard.add_utterance(
                speaker=speaker,
                text=text,
                vak=profile.get('vak', vak),
                need=profile.get('need', need)
            )
            self.dashboard.update_current_speaker(
                speaker=speaker,
                vak=profile.get('vak', vak),
                need=profile.get('need', need)
            )

            # Update speaker in list
            self.dashboard.add_speaker(
                speaker_id=self.speaker_db_ids.get(speaker, 0),
                name=speaker,
                word_count=profile['word_count'],
                sessions_count=1,
                last_seen=datetime.now()
            )

        # Check if we should trigger Claude analysis
        self._maybe_analyze_with_claude(speaker)

    def _create_speaker_in_db(self, speaker_name: str):
        """Create a speaker record in database."""
        try:
            with self.db.get_session() as session:
                # Check if speaker exists
                existing = session.query(Speaker).filter_by(display_name=speaker_name).first()
                if existing:
                    self.speaker_db_ids[speaker_name] = existing.id
                    return

                # Create new speaker
                speaker = Speaker(
                    speaker_id=f"speaker_{speaker_name.lower().replace(' ', '_')}_{uuid.uuid4().hex[:8]}",
                    display_name=speaker_name,
                    created_at=datetime.utcnow()
                )
                session.add(speaker)
                session.flush()
                self.speaker_db_ids[speaker_name] = speaker.id
                logger.info(f"Created speaker: {speaker_name} (ID: {speaker.id})")
        except Exception as e:
            logger.error(f"Failed to create speaker: {e}")

    def _save_utterance(self, speaker_name: str, text: str, vak: Optional[str], need: Optional[str]):
        """Save an utterance to database."""
        if not self.current_session_db_id:
            return

        try:
            speaker_id = self.speaker_db_ids.get(speaker_name)
            if not speaker_id:
                return

            with self.db.get_session() as session:
                utterance = Utterance(
                    session_id=self.current_session_db_id,
                    speaker_db_id=speaker_id,
                    text=text,
                    word_count=len(text.split()),
                    vak_detected=vak,
                    dominant_need=need,
                    timestamp=datetime.utcnow()
                )
                session.add(utterance)
        except Exception as e:
            logger.error(f"Failed to save utterance: {e}")

    def _maybe_analyze_with_claude(self, speaker_name: str):
        """Check if we should trigger Claude analysis."""
        # Skip if no API key configured
        if not config.ANTHROPIC_API_KEY:
            return

        profile = self.speaker_profiles.get(speaker_name, {})
        word_count = profile.get('word_count', 0)
        last_analyzed = self.last_claude_word_count.get(speaker_name, 0)

        if self.claude.should_analyze(word_count, last_analyzed):
            logger.info(f"Triggering Claude analysis for {speaker_name} at {word_count} words")

            all_text = " ".join(self.speaker_texts.get(speaker_name, []))
            if not all_text:
                return

            # Build deception context
            deception_context = ""
            pol = profile.get('politician_score', 0)
            dec = profile.get('deception_score', 0)
            if pol > 0.2 or dec > 0.2:
                deception_context = f"\n\nNOTE: Linguistic analysis detected politician_score={pol:.0%}, deception_score={dec:.0%}"

            # Run analysis in background
            def do_analysis():
                insights = self.claude.analyze(
                    speaker_name=speaker_name,
                    text=all_text,
                    deception_context=deception_context,
                    save_to_db=True,
                    speaker_db_id=self.speaker_db_ids.get(speaker_name)
                )

                if insights:
                    self.claude_insights[speaker_name] = insights
                    self.last_claude_word_count[speaker_name] = word_count

                    # Update overlay
                    if self.overlay and speaker_name == self.current_speaker:
                        self.overlay.update_claude_insights(insights)

                    if self.dashboard:
                        self.dashboard.update_claude_insights(insights)

            threading.Thread(target=do_analysis, daemon=True).start()

    def _create_session(self):
        """Create a new session in database."""
        try:
            with self.db.get_session() as session:
                db_session = Session(
                    session_id=str(uuid.uuid4()),
                    name=f"Session {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                    start_time=datetime.utcnow(),
                    status='active'
                )
                session.add(db_session)
                session.flush()
                self.current_session_db_id = db_session.id
                self.session_start_time = datetime.now()
                logger.info(f"Created session: {db_session.id}")
        except Exception as e:
            logger.error(f"Failed to create session: {e}")

    def _end_session(self):
        """End the current session."""
        if not self.current_session_db_id:
            return

        try:
            with self.db.get_session() as session:
                db_session = session.query(Session).get(self.current_session_db_id)
                if db_session:
                    db_session.end_time = datetime.utcnow()
                    db_session.status = 'completed'
                    if self.session_start_time:
                        duration = (datetime.now() - self.session_start_time).total_seconds()
                        db_session.duration_seconds = int(duration)
                    logger.info(f"Ended session: {db_session.id}")
        except Exception as e:
            logger.error(f"Failed to end session: {e}")

        self.current_session_db_id = None
        self.session_start_time = None

    def start_capture(self):
        """Start audio capture and processing."""
        if self.running:
            logger.warning("Already running")
            return

        if not PYAUDIO_AVAILABLE:
            logger.error("PyAudioWPatch not available - cannot capture audio")
            return

        # Create new session
        self._create_session()

        # Reset session state
        self.session_voices.clear()
        self.unknown_counter = 0

        # Start audio capture
        self.capture = WASAPICapture(
            callback=self._audio_callback,
            chunk_duration=5.0,
            target_sample_rate=16000
        )

        if not self.capture.start():
            logger.error("Failed to start audio capture")
            return

        # Start processing thread
        self.running = True
        self.process_thread = threading.Thread(target=self._process_audio, daemon=True)
        self.process_thread.start()

        # Update tray icon
        if self.tray:
            self.tray.update_recording_state(True)

        logger.info("Capture started")

    def stop_capture(self):
        """Stop audio capture and processing."""
        if not self.running:
            return

        self.running = False

        # Stop capture
        if self.capture:
            self.capture.stop()
            self.capture = None

        # Wait for processing thread
        if self.process_thread:
            self.process_thread.join(timeout=2.0)
            self.process_thread = None

        # End session
        self._end_session()

        # Save voice embeddings
        self._save_voice_embeddings()

        # Update tray icon
        if self.tray:
            self.tray.update_recording_state(False)

        logger.info("Capture stopped")

    def rename_speaker(self, speaker_id: int, old_name: str, new_name: str):
        """Rename a speaker."""
        try:
            with self.db.get_session() as session:
                speaker = session.query(Speaker).get(speaker_id)
                if speaker:
                    speaker.display_name = new_name
                    logger.info(f"Renamed speaker {old_name} to {new_name}")

            # Update in-memory caches
            if old_name in self.speaker_profiles:
                self.speaker_profiles[new_name] = self.speaker_profiles.pop(old_name)
            if old_name in self.speaker_texts:
                self.speaker_texts[new_name] = self.speaker_texts.pop(old_name)
            if old_name in self.claude_insights:
                self.claude_insights[new_name] = self.claude_insights.pop(old_name)
            if old_name in self.last_claude_word_count:
                self.last_claude_word_count[new_name] = self.last_claude_word_count.pop(old_name)
            if old_name in self.speaker_db_ids:
                self.speaker_db_ids[new_name] = self.speaker_db_ids.pop(old_name)

            # Update voice embeddings
            if old_name in self.known_voices:
                self.known_voices[new_name] = self.known_voices.pop(old_name)

            # Promote session voice to known_voices for persistence
            if old_name in self.session_voices:
                # Average the embeddings and save to known_voices
                avg_embedding = np.mean(self.session_voices[old_name], axis=0)
                self.known_voices[new_name] = avg_embedding
                # Update session_voices with new name too
                self.session_voices[new_name] = self.session_voices.pop(old_name)

            # Save embeddings (always save after rename)
            self._save_voice_embeddings()

        except Exception as e:
            logger.error(f"Failed to rename speaker: {e}")

    def delete_speaker(self, speaker_id: int, name: str):
        """Delete a speaker and all their data."""
        try:
            with self.db.get_session() as session:
                speaker = session.query(Speaker).get(speaker_id)
                if speaker:
                    session.delete(speaker)
                    logger.info(f"Deleted speaker: {name}")

            # Clear in-memory caches
            self.speaker_profiles.pop(name, None)
            self.speaker_texts.pop(name, None)
            self.claude_insights.pop(name, None)
            self.last_claude_word_count.pop(name, None)
            self.speaker_db_ids.pop(name, None)

            # Remove voice embedding
            if name in self.known_voices:
                del self.known_voices[name]
                self._save_voice_embeddings()

        except Exception as e:
            logger.error(f"Failed to delete speaker: {e}")

    def _show_api_key_popup(self):
        """Show popup to enter API key with instructions."""
        import tkinter as tk

        # Colors matching app theme
        BG = '#1e1e2e'
        FG = '#cdd6f4'
        ACCENT = '#89b4fa'
        ENTRY_BG = '#313244'

        popup = tk.Toplevel()
        popup.title("Claude AI Setup")
        popup.configure(bg=BG)
        popup.geometry("500x400")
        popup.resizable(False, False)

        # Center on screen
        popup.update_idletasks()
        x = (popup.winfo_screenwidth() - 500) // 2
        y = (popup.winfo_screenheight() - 400) // 2
        popup.geometry(f"+{x}+{y}")

        # Title
        tk.Label(
            popup, text="Enable Claude AI Analysis",
            font=('Segoe UI', 16, 'bold'), bg=BG, fg=FG
        ).pack(pady=(20, 10))

        # Instructions
        instructions = """Get your FREE API key in 2 minutes:

1. Go to console.anthropic.com
2. Sign up (free, no credit card)
3. You get $5 FREE credit (hundreds of analyses!)
4. Click "API Keys" → "Create Key"
5. Copy and paste it below:"""

        tk.Label(
            popup, text=instructions,
            font=('Segoe UI', 10), bg=BG, fg=FG,
            justify='left'
        ).pack(pady=10, padx=20, anchor='w')

        # Entry frame
        entry_frame = tk.Frame(popup, bg=BG)
        entry_frame.pack(fill='x', padx=20, pady=10)

        tk.Label(
            entry_frame, text="API Key:",
            font=('Segoe UI', 10), bg=BG, fg=FG
        ).pack(side='left')

        key_var = tk.StringVar()
        key_entry = tk.Entry(
            entry_frame, textvariable=key_var,
            font=('Consolas', 10), bg=ENTRY_BG, fg=FG,
            insertbackground=FG, width=40,
            relief='flat', highlightthickness=1,
            highlightbackground='#45475a', highlightcolor=ACCENT
        )
        key_entry.pack(side='left', padx=(10, 0), ipady=5)

        # Status label
        status_var = tk.StringVar()
        status_label = tk.Label(
            popup, textvariable=status_var,
            font=('Segoe UI', 10), bg=BG, fg='#a6e3a1'
        )
        status_label.pack(pady=5)

        def save_key():
            key = key_var.get().strip()
            if not key:
                status_var.set("Please enter an API key")
                status_label.configure(fg='#f38ba8')
                return

            if not key.startswith('sk-'):
                status_var.set("Invalid key format (should start with sk-)")
                status_label.configure(fg='#f38ba8')
                return

            # Save to .env file
            env_path = DATA_DIR.parent / '.env'
            try:
                # Read existing content
                existing = {}
                if env_path.exists():
                    with open(env_path) as f:
                        for line in f:
                            line = line.strip()
                            if '=' in line and not line.startswith('#'):
                                k, v = line.split('=', 1)
                                existing[k] = v

                # Update key
                existing['ANTHROPIC_API_KEY'] = key

                # Write back
                with open(env_path, 'w') as f:
                    for k, v in existing.items():
                        f.write(f"{k}={v}\n")

                # Update config immediately
                config.ANTHROPIC_API_KEY = key

                # Reinitialize Claude analyzer
                self.claude = ClaudeAnalyzer()

                status_var.set("API key saved! Claude analysis is now enabled.")
                status_label.configure(fg='#a6e3a1')

                # Close after delay
                popup.after(1500, popup.destroy)

            except Exception as e:
                status_var.set(f"Error saving: {e}")
                status_label.configure(fg='#f38ba8')

        # Buttons
        btn_frame = tk.Frame(popup, bg=BG)
        btn_frame.pack(pady=20)

        save_btn = tk.Button(
            btn_frame, text="Save API Key",
            font=('Segoe UI', 11, 'bold'),
            bg=ACCENT, fg='#1e1e2e',
            activebackground='#b4befe', activeforeground='#1e1e2e',
            relief='flat', padx=20, pady=8,
            cursor='hand2', command=save_key
        )
        save_btn.pack(side='left', padx=5)

        cancel_btn = tk.Button(
            btn_frame, text="Maybe Later",
            font=('Segoe UI', 10),
            bg='#45475a', fg=FG,
            activebackground='#585b70', activeforeground=FG,
            relief='flat', padx=15, pady=8,
            cursor='hand2', command=popup.destroy
        )
        cancel_btn.pack(side='left', padx=5)

        # Note at bottom
        tk.Label(
            popup,
            text="Everything else works without the key!\n(transcription, speaker ID, VAK, needs)",
            font=('Segoe UI', 9), bg=BG, fg='#6c7086'
        ).pack(side='bottom', pady=10)

        # Focus entry
        key_entry.focus_set()

        # Make modal
        popup.transient()
        popup.grab_set()
        popup.wait_window()

    def analyze_speaker(self, speaker_id: int, name: str):
        """Manually trigger Claude analysis for a speaker."""
        # Check for API key first
        if not config.ANTHROPIC_API_KEY:
            self._show_api_key_popup()
            return

        all_text = " ".join(self.speaker_texts.get(name, []))
        if not all_text:
            logger.warning(f"No text available for speaker {name}")
            return

        profile = self.speaker_profiles.get(name, {})
        word_count = profile.get('word_count', len(all_text.split()))

        # Build deception context
        deception_context = ""
        pol = profile.get('politician_score', 0)
        dec = profile.get('deception_score', 0)
        if pol > 0.2 or dec > 0.2:
            deception_context = f"\n\nNOTE: Linguistic analysis detected politician_score={pol:.0%}, deception_score={dec:.0%}"

        def do_analysis():
            logger.info(f"Running manual Claude analysis for {name}")
            insights = self.claude.analyze(
                speaker_name=name,
                text=all_text,
                deception_context=deception_context,
                save_to_db=True,
                speaker_db_id=speaker_id
            )

            if insights:
                self.claude_insights[name] = insights
                self.last_claude_word_count[name] = word_count

                # Update overlay
                if self.overlay and name == self.current_speaker:
                    self.overlay.update_claude_insights(insights)

                if self.dashboard:
                    self.dashboard.update_claude_insights(insights)

                    # Update analysis history display
                    analyses = self.claude.get_analysis_history(speaker_id)
                    self.dashboard.update_speaker_analysis(speaker_id, analyses)

        threading.Thread(target=do_analysis, daemon=True).start()

    def select_speaker(self, speaker_id: int, name: str):
        """Load and display a speaker's full data when selected."""
        try:
            # Get all text from in-memory cache or database
            all_text = '\n\n'.join(self.speaker_texts.get(name, []))

            # If no in-memory text, try database
            if not all_text:
                with self.db.get_session() as session:
                    utterances = (
                        session.query(Utterance)
                        .filter_by(speaker_db_id=speaker_id)
                        .order_by(Utterance.timestamp)
                        .all()
                    )
                    all_text = '\n\n'.join(u.text for u in utterances if u.text)

            # Get profile from in-memory cache (this is where the live data is)
            mem_profile = self.speaker_profiles.get(name, {})
            vak_scores = mem_profile.get('vak_scores', {})
            need_scores = mem_profile.get('need_scores', {})

            # Normalize scores to 0-1 range for display
            total_vak = sum(vak_scores.values()) or 1
            total_need = sum(need_scores.values()) or 1

            profile_data = {
                'vak': {k: v / total_vak for k, v in vak_scores.items()},
                'needs': {k: v / total_need for k, v in need_scores.items()},
                'dominant_vak': mem_profile.get('vak'),
                'dominant_need': mem_profile.get('need'),
            }

            # Get analysis history
            analyses = self.claude.get_analysis_history(speaker_id) if self.claude else []

            # Update dashboard
            if self.dashboard:
                self.dashboard.update_speaker_text(speaker_id, all_text)
                self.dashboard.update_speaker_profile(speaker_id, profile_data)
                self.dashboard.update_speaker_analysis(speaker_id, analyses)

        except Exception as e:
            logger.error(f"Failed to load speaker data: {e}")

    def load_session(self, session_id: int):
        """Load a session's transcript for viewing."""
        try:
            with self.db.get_session() as session:
                db_session = session.query(Session).get(session_id)
                if not db_session:
                    return

                utterances = (
                    session.query(Utterance)
                    .filter_by(session_id=session_id)
                    .order_by(Utterance.timestamp)
                    .all()
                )

                utterance_list = []
                speaker_stats = {}

                for u in utterances:
                    speaker_name = u.speaker.name if u.speaker else 'Unknown'
                    utterance_list.append({
                        'speaker': speaker_name,
                        'text': u.text,
                        'timestamp': u.timestamp,
                        'vak': u.vak_detected,
                        'need': u.dominant_need
                    })
                    speaker_stats[speaker_name] = speaker_stats.get(speaker_name, 0) + u.word_count

                if self.dashboard:
                    self.dashboard.load_session_transcript(
                        session_name=db_session.name or 'Session',
                        start_time=db_session.start_time,
                        utterances=utterance_list,
                        speaker_stats=speaker_stats
                    )

        except Exception as e:
            logger.error(f"Failed to load session: {e}")

    def _load_existing_data(self):
        """Load existing speakers and sessions from database."""
        try:
            with self.db.get_session() as session:
                # Load speakers
                speakers = session.query(Speaker).order_by(Speaker.last_seen.desc()).all()
                for speaker in speakers:
                    self.speaker_db_ids[speaker.name] = speaker.id

                    # Count words and sessions
                    word_count = session.query(
                        Utterance
                    ).filter_by(speaker_db_id=speaker.id).count()

                    sessions_count = session.query(
                        Utterance.session_id
                    ).filter_by(speaker_db_id=speaker.id).distinct().count()

                    if self.dashboard:
                        self.dashboard.add_speaker(
                            speaker_id=speaker.id,
                            name=speaker.name,
                            word_count=word_count,
                            sessions_count=sessions_count,
                            last_seen=speaker.last_seen
                        )

                # Load sessions
                sessions = session.query(Session).order_by(Session.start_time.desc()).limit(50).all()
                for s in sessions:
                    utterance_count = session.query(Utterance).filter_by(session_id=s.id).count()

                    if self.dashboard:
                        self.dashboard.add_session(
                            session_id=s.id,
                            name=s.name or 'Session',
                            start_time=s.start_time,
                            duration_seconds=s.duration_seconds or 0,
                            speaker_count=s.speaker_count,
                            utterance_count=utterance_count
                        )

        except Exception as e:
            logger.error(f"Failed to load existing data: {e}")

    def run(self):
        """Run the application."""
        # Create overlay (main view)
        self.overlay = Overlay(
            on_open_dashboard=self._open_dashboard,
            on_toggle_capture=self._toggle_capture,
            on_close=self._quit,
            on_settings=self._show_api_key_popup
        )

        # Show API key setup on first run if not configured
        if not config.ANTHROPIC_API_KEY:
            self.overlay.after(500, self._show_api_key_popup)

        # Create system tray
        if PYSTRAY_AVAILABLE:
            self.tray = SystemTray(
                on_show_dashboard=self._open_dashboard,
                on_toggle_capture=self._toggle_capture,
                on_quit=self._quit
            )
            self.tray.start(blocking=False)

        # Run main loop
        logger.info("Starting Speech Profiler...")
        self.overlay.mainloop()

    def _open_dashboard(self):
        """Open the dashboard window."""
        if not self.dashboard:
            self.dashboard = Dashboard(
                on_start_capture=self.start_capture,
                on_stop_capture=self.stop_capture,
                on_rename_speaker=self.rename_speaker,
                on_delete_speaker=self.delete_speaker,
                on_analyze_speaker=self.analyze_speaker,
                on_select_speaker=self.select_speaker,
                on_load_session=self.load_session,
                on_close=self._on_dashboard_close
            )
            # Load existing data
            self.dashboard.after(100, self._load_existing_data)
            # Sync recording state
            if self.running:
                self.dashboard.start_capture()
        else:
            self.dashboard.deiconify()
            self.dashboard.lift()

    def _toggle_capture(self):
        """Toggle capture from overlay/tray."""
        if self.running:
            self.stop_capture()
            if self.overlay:
                self.overlay.set_recording(False)
            if self.dashboard:
                self.dashboard.stop_capture()
        else:
            self.start_capture()
            if self.overlay:
                self.overlay.set_recording(True)
            if self.dashboard:
                self.dashboard.start_capture()

    def _on_dashboard_close(self):
        """Handle dashboard close - just hide it."""
        if self.dashboard:
            self.dashboard.withdraw()

    def _quit(self):
        """Quit the application."""
        self.stop_capture()

        if self.tray:
            self.tray.stop()

        if self.dashboard:
            self.dashboard.destroy()

        if self.overlay:
            self.overlay.destroy()

        logger.info("Speech Profiler stopped")


def main():
    """Main entry point."""
    print("=" * 50)
    print("Windows Speech Profiler")
    print("=" * 50)

    # Check requirements
    if not PYAUDIO_AVAILABLE:
        print("\nWARNING: PyAudioWPatch not installed!")
        print("Audio capture will not work.")
        print("Install with: pip install PyAudioWPatch")

    if not RESEMBLYZER_AVAILABLE:
        print("\nWARNING: Resemblyzer not installed!")
        print("Speaker identification will not work.")
        print("Install with: pip install resemblyzer")

    if not PYSTRAY_AVAILABLE:
        print("\nWARNING: pystray not installed!")
        print("System tray will not be available.")
        print("Install with: pip install pystray Pillow")

    if not config.ANTHROPIC_API_KEY:
        print("\nWARNING: ANTHROPIC_API_KEY not set!")
        print("Claude analysis will not work.")
        print("Set it in .env file or environment.")

    print()

    # Run application
    app = SpeechProfiler()
    app.run()


if __name__ == '__main__':
    main()
