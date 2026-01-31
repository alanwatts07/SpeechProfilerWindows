"""Speaker identification using Resemblyzer.

Uses voice embeddings to identify and track speakers without requiring
HuggingFace authentication.
"""

import logging
from pathlib import Path
from typing import Optional, Union, Dict, List
from dataclasses import dataclass, field

import numpy as np

try:
    from resemblyzer import VoiceEncoder, preprocess_wav
    RESEMBLYZER_AVAILABLE = True
except ImportError as e:
    print(f"RESEMBLYZER IMPORT ERROR: {e}")
    import traceback
    traceback.print_exc()
    RESEMBLYZER_AVAILABLE = False

try:
    from scipy.spatial.distance import cosine
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

from ..config import config
from .audio_processor import AudioChunk

logger = logging.getLogger(__name__)


@dataclass
class SpeakerSegment:
    """A segment of speech attributed to a speaker."""
    speaker: str
    start: float
    end: float
    text: str = ""
    confidence: float = 1.0


class SpeakerIdentifier:
    """Identifies and tracks speakers using Resemblyzer voice embeddings."""

    def __init__(self):
        """Initialize speaker identifier."""
        self.similarity_threshold = config.SPEAKER_SIMILARITY_THRESHOLD

        self._encoder = None
        self._known_speakers: Dict[str, np.ndarray] = {}
        self._speaker_counter = 0

    def _load_encoder(self):
        """Lazy load the voice encoder."""
        if self._encoder is None:
            if not RESEMBLYZER_AVAILABLE:
                raise ImportError(
                    "resemblyzer is required for speaker identification. "
                    "Install with: pip install resemblyzer"
                )

            logger.info("Loading Resemblyzer voice encoder...")
            self._encoder = VoiceEncoder()
            logger.info("Voice encoder loaded")

    def extract_embedding(
        self,
        audio: Union[np.ndarray, AudioChunk],
        sample_rate: int = 16000
    ) -> Optional[np.ndarray]:
        """Extract voice embedding from audio.

        Args:
            audio: Audio data as numpy array or AudioChunk
            sample_rate: Sample rate of the audio

        Returns:
            Embedding vector (256-dim) or None on failure
        """
        self._load_encoder()

        try:
            # Get audio data
            if isinstance(audio, AudioChunk):
                audio_data = audio.data
                sample_rate = audio.sample_rate
            else:
                audio_data = audio

            # Ensure float32
            if audio_data.dtype != np.float32:
                audio_data = audio_data.astype(np.float32)

            # Ensure mono
            if len(audio_data.shape) > 1:
                audio_data = audio_data.mean(axis=1)

            # Normalize
            max_val = np.abs(audio_data).max()
            if max_val > 0:
                audio_data = audio_data / max_val

            # Preprocess for Resemblyzer (resamples to 16kHz internally if needed)
            # Resemblyzer expects audio at 16kHz
            if sample_rate != 16000:
                # Simple resampling
                from scipy import signal
                num_samples = int(len(audio_data) * 16000 / sample_rate)
                audio_data = signal.resample(audio_data, num_samples).astype(np.float32)

            # Need at least 1 second of audio for reliable embedding
            if len(audio_data) < 16000:
                logger.debug("Audio too short for embedding")
                return None

            # Extract embedding
            embedding = self._encoder.embed_utterance(audio_data)
            return embedding

        except Exception as e:
            logger.error(f"Failed to extract embedding: {e}")
            return None

    def match_speaker(
        self,
        embedding: np.ndarray,
        threshold: float = None
    ) -> Optional[str]:
        """Match embedding against known speakers.

        Args:
            embedding: Voice embedding to match
            threshold: Similarity threshold (uses config if None)

        Returns:
            Speaker ID if match found, None otherwise
        """
        if not SCIPY_AVAILABLE:
            logger.warning("scipy not available for speaker matching")
            return None

        if not self._known_speakers:
            return None

        threshold = threshold or self.similarity_threshold

        best_match = None
        best_similarity = 0.0

        for speaker_id, known_embedding in self._known_speakers.items():
            # Cosine similarity (1 - cosine distance)
            similarity = 1 - cosine(embedding, known_embedding)

            if similarity > threshold and similarity > best_similarity:
                best_match = speaker_id
                best_similarity = similarity

        if best_match:
            logger.debug(f"Matched speaker {best_match} with similarity {best_similarity:.3f}")

        return best_match

    def register_speaker(
        self,
        embedding: np.ndarray,
        speaker_id: str = None
    ) -> str:
        """Register a new speaker with their embedding.

        Args:
            embedding: Voice embedding
            speaker_id: Optional ID (generated if None)

        Returns:
            Speaker ID
        """
        if speaker_id is None:
            speaker_id = self._generate_speaker_id()

        self._known_speakers[speaker_id] = embedding
        logger.info(f"Registered speaker: {speaker_id}")
        return speaker_id

    def update_speaker_embedding(
        self,
        speaker_id: str,
        new_embedding: np.ndarray,
        alpha: float = 0.3
    ):
        """Update a speaker's embedding with exponential smoothing.

        Args:
            speaker_id: Speaker to update
            new_embedding: New embedding to blend in
            alpha: Weight for new embedding (0-1)
        """
        if speaker_id in self._known_speakers:
            old_embedding = self._known_speakers[speaker_id]
            self._known_speakers[speaker_id] = (
                alpha * new_embedding + (1 - alpha) * old_embedding
            )

    def rename_speaker(self, old_id: str, new_id: str) -> bool:
        """Rename a registered speaker.

        Args:
            old_id: Current speaker ID
            new_id: New speaker ID

        Returns:
            True if successful
        """
        if old_id not in self._known_speakers:
            return False

        self._known_speakers[new_id] = self._known_speakers.pop(old_id)
        logger.info(f"Renamed speaker {old_id} to {new_id}")
        return True

    def remove_speaker(self, speaker_id: str) -> bool:
        """Remove a speaker from known speakers.

        Args:
            speaker_id: Speaker to remove

        Returns:
            True if removed, False if not found
        """
        if speaker_id in self._known_speakers:
            del self._known_speakers[speaker_id]
            logger.info(f"Removed speaker: {speaker_id}")
            return True
        return False

    def identify_or_register(
        self,
        audio: Union[np.ndarray, AudioChunk],
        sample_rate: int = 16000
    ) -> tuple:
        """Identify speaker or register if new.

        Args:
            audio: Audio data
            sample_rate: Sample rate

        Returns:
            Tuple of (speaker_id, confidence)
        """
        embedding = self.extract_embedding(audio, sample_rate)
        if embedding is None:
            return self._generate_speaker_id(), 0.0

        # Try to match existing
        matched = self.match_speaker(embedding)
        if matched:
            # Update their embedding
            self.update_speaker_embedding(matched, embedding)
            # Calculate confidence
            similarity = 1 - cosine(embedding, self._known_speakers[matched])
            return matched, similarity

        # Register as new speaker
        new_id = self.register_speaker(embedding)
        return new_id, 1.0

    def get_known_speakers(self) -> List[str]:
        """Get list of all known speaker IDs."""
        return list(self._known_speakers.keys())

    def load_embeddings(self, embeddings_dict: Dict[str, list]):
        """Load speaker embeddings from dictionary.

        Args:
            embeddings_dict: Dict of speaker_id -> embedding list
        """
        for speaker_id, embedding in embeddings_dict.items():
            self._known_speakers[speaker_id] = np.array(embedding, dtype=np.float32)
        logger.info(f"Loaded {len(embeddings_dict)} speaker embeddings")

    def export_embeddings(self) -> Dict[str, list]:
        """Export speaker embeddings as dictionary.

        Returns:
            Dict of speaker_id -> embedding list
        """
        return {
            speaker_id: embedding.tolist()
            for speaker_id, embedding in self._known_speakers.items()
        }

    def _generate_speaker_id(self) -> str:
        """Generate a new speaker ID."""
        self._speaker_counter += 1
        letter = chr(ord('A') + (self._speaker_counter - 1) % 26)
        suffix = "" if self._speaker_counter <= 26 else str(self._speaker_counter // 26)
        return f"Speaker {letter}{suffix}"

    def is_available(self) -> bool:
        """Check if speaker identification is available."""
        return RESEMBLYZER_AVAILABLE


class SimpleSpeakerTracker:
    """Simple speaker tracking without ML (fallback).

    Uses basic voice characteristics for rough speaker separation.
    Less accurate but works without any dependencies.
    """

    def __init__(self):
        self._speaker_profiles: Dict[str, dict] = {}
        self._speaker_counter = 0

    def estimate_speaker(
        self,
        audio_data: np.ndarray,
        sample_rate: int = 16000
    ) -> tuple:
        """Estimate speaker based on basic audio features.

        Args:
            audio_data: Audio samples
            sample_rate: Sample rate

        Returns:
            Tuple of (speaker_id, confidence)
        """
        features = self._extract_simple_features(audio_data, sample_rate)

        best_match = None
        best_score = 0.0

        for speaker_id, profile in self._speaker_profiles.items():
            score = self._compare_features(features, profile)
            if score > 0.7 and score > best_score:
                best_match = speaker_id
                best_score = score

        if best_match:
            self._update_profile(best_match, features)
            return best_match, best_score

        speaker_id = self._generate_id()
        self._speaker_profiles[speaker_id] = features
        return speaker_id, 1.0

    def _extract_simple_features(
        self,
        audio_data: np.ndarray,
        sample_rate: int
    ) -> dict:
        """Extract simple audio features for speaker comparison."""
        features = {
            'energy_mean': float(np.mean(np.abs(audio_data))),
            'energy_std': float(np.std(np.abs(audio_data))),
            'zero_crossings': int(np.sum(np.diff(np.sign(audio_data)) != 0)),
        }

        try:
            # Simple autocorrelation-based pitch
            corr = np.correlate(audio_data, audio_data, mode='full')
            corr = corr[len(corr)//2:]
            d = np.diff(corr)
            peaks = np.where((d[:-1] > 0) & (d[1:] <= 0))[0] + 1
            if len(peaks) > 1:
                period = peaks[1] - peaks[0]
                features['pitch_estimate'] = sample_rate / period if period > 0 else 0
            else:
                features['pitch_estimate'] = 0
        except Exception:
            features['pitch_estimate'] = 0

        return features

    def _compare_features(self, f1: dict, f2: dict) -> float:
        """Compare two feature sets, return similarity 0-1."""
        if not f1 or not f2:
            return 0.0

        score = 0.0
        count = 0

        for key in ['energy_mean', 'energy_std', 'pitch_estimate']:
            v1 = f1.get(key, 0)
            v2 = f2.get(key, 0)
            if v1 > 0 and v2 > 0:
                diff = abs(v1 - v2) / max(v1, v2)
                score += 1 - min(diff, 1)
                count += 1

        return score / count if count > 0 else 0.0

    def _update_profile(self, speaker_id: str, new_features: dict):
        """Update speaker profile with exponential smoothing."""
        profile = self._speaker_profiles.get(speaker_id, {})
        alpha = 0.3

        for key, new_val in new_features.items():
            old_val = profile.get(key, new_val)
            profile[key] = alpha * new_val + (1 - alpha) * old_val

        self._speaker_profiles[speaker_id] = profile

    def _generate_id(self) -> str:
        """Generate new speaker ID."""
        self._speaker_counter += 1
        letter = chr(ord('A') + (self._speaker_counter - 1) % 26)
        return f"Speaker {letter}"

    def rename_speaker(self, old_id: str, new_id: str) -> bool:
        """Rename a speaker."""
        if old_id in self._speaker_profiles:
            self._speaker_profiles[new_id] = self._speaker_profiles.pop(old_id)
            return True
        return False

    def remove_speaker(self, speaker_id: str) -> bool:
        """Remove a speaker."""
        if speaker_id in self._speaker_profiles:
            del self._speaker_profiles[speaker_id]
            return True
        return False

    def export_profiles(self) -> Dict[str, dict]:
        """Export speaker profiles."""
        return dict(self._speaker_profiles)

    def load_profiles(self, profiles: Dict[str, dict]):
        """Load speaker profiles."""
        self._speaker_profiles = dict(profiles)


def test_speaker_identifier():
    """Test speaker identification."""
    print("Testing Speaker Identifier...")

    if not RESEMBLYZER_AVAILABLE:
        print("Resemblyzer not installed!")
        print("Install with: pip install resemblyzer")
        return

    identifier = SpeakerIdentifier()

    # Generate test audio (sine waves at different frequencies)
    sample_rate = 16000
    duration = 2.0
    t = np.linspace(0, duration, int(sample_rate * duration))

    # Two "speakers" with different pitches
    speaker_a_audio = (np.sin(2 * np.pi * 150 * t) * 0.5).astype(np.float32)
    speaker_b_audio = (np.sin(2 * np.pi * 250 * t) * 0.5).astype(np.float32)

    print("\nRegistering Speaker A...")
    emb_a = identifier.extract_embedding(speaker_a_audio, sample_rate)
    if emb_a is not None:
        identifier.register_speaker(emb_a, "Speaker A")
        print(f"  Embedding shape: {emb_a.shape}")

    print("\nRegistering Speaker B...")
    emb_b = identifier.extract_embedding(speaker_b_audio, sample_rate)
    if emb_b is not None:
        identifier.register_speaker(emb_b, "Speaker B")
        print(f"  Embedding shape: {emb_b.shape}")

    print("\nTesting identification...")
    speaker, conf = identifier.identify_or_register(speaker_a_audio, sample_rate)
    print(f"  Speaker A audio -> {speaker} (confidence: {conf:.2f})")

    speaker, conf = identifier.identify_or_register(speaker_b_audio, sample_rate)
    print(f"  Speaker B audio -> {speaker} (confidence: {conf:.2f})")

    print("\nKnown speakers:", identifier.get_known_speakers())


if __name__ == "__main__":
    test_speaker_identifier()
