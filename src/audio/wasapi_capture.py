"""WASAPI Loopback audio capture for Windows.

Uses PyAudioWPatch to capture system audio output (loopback) without
requiring Voicemeeter or other virtual audio devices.
"""

import logging
import threading
import queue
import time
from typing import Callable, Optional, List, Dict
from dataclasses import dataclass

import numpy as np

try:
    import pyaudiowpatch as pyaudio
    PYAUDIO_AVAILABLE = True
except ImportError:
    try:
        import pyaudio
        PYAUDIO_AVAILABLE = True
    except ImportError:
        PYAUDIO_AVAILABLE = False

try:
    from scipy import signal
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False

from ..config import config
from .audio_processor import AudioChunk

logger = logging.getLogger(__name__)


@dataclass
class AudioDevice:
    """Represents an audio device."""
    index: int
    name: str
    channels: int
    sample_rate: int
    is_loopback: bool = False


class WASAPICapture:
    """WASAPI Loopback audio capture for Windows.

    Captures system audio output (what you hear through speakers/headphones)
    using WASAPI loopback mode via PyAudioWPatch.
    """

    def __init__(
        self,
        device_index: Optional[int] = None,
        callback: Optional[Callable[[AudioChunk], None]] = None,
        chunk_duration: float = None,
        target_sample_rate: int = 16000
    ):
        """Initialize WASAPI capture.

        Args:
            device_index: Audio device index (None for auto-detect loopback)
            callback: Function to call with each audio chunk
            chunk_duration: Duration of each chunk in seconds
            target_sample_rate: Target sample rate for output (resampled from device)
        """
        if not PYAUDIO_AVAILABLE:
            raise ImportError(
                "PyAudioWPatch is required for WASAPI capture. "
                "Install with: pip install PyAudioWPatch"
            )

        self.device_index = device_index
        self.callback = callback
        self.chunk_duration = chunk_duration or config.AUDIO_CHUNK_DURATION
        self.target_sample_rate = target_sample_rate

        self._pa = pyaudio.PyAudio()
        self._stream = None
        self._running = False
        self._thread = None
        self._audio_queue = queue.Queue()

        # Device info (populated when stream is opened)
        self.device_sample_rate: int = 48000
        self.device_channels: int = 2
        self.sample_rate: int = target_sample_rate  # Output sample rate

        # Buffer for collecting audio chunks
        self._buffer = []
        self._buffer_samples = 0

    def list_devices(self) -> List[AudioDevice]:
        """List all available audio devices.

        Returns:
            List of AudioDevice objects
        """
        devices = []
        for i in range(self._pa.get_device_count()):
            try:
                info = self._pa.get_device_info_by_index(i)
                device = AudioDevice(
                    index=i,
                    name=info.get('name', f'Device {i}'),
                    channels=int(info.get('maxInputChannels', 0)),
                    sample_rate=int(info.get('defaultSampleRate', 44100)),
                    is_loopback=info.get('isLoopbackDevice', False)
                )
                devices.append(device)
            except Exception as e:
                logger.debug(f"Failed to get device {i} info: {e}")
        return devices

    def list_loopback_devices(self) -> List[AudioDevice]:
        """List available loopback devices (speakers that can be captured).

        Returns:
            List of loopback AudioDevice objects
        """
        devices = []
        try:
            # PyAudioWPatch has a special method to get WASAPI loopback devices
            wasapi_info = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)

            for i in range(self._pa.get_device_count()):
                try:
                    info = self._pa.get_device_info_by_index(i)

                    # Check if it's a WASAPI device with loopback support
                    if info.get('hostApi') == wasapi_info['index']:
                        # Check for loopback device marker
                        is_loopback = info.get('isLoopbackDevice', False)

                        # Also check name patterns for loopback devices
                        name = info.get('name', '')
                        if is_loopback or '[Loopback]' in name:
                            device = AudioDevice(
                                index=i,
                                name=name,
                                channels=max(int(info.get('maxInputChannels', 2)), 2),
                                sample_rate=int(info.get('defaultSampleRate', 48000)),
                                is_loopback=True
                            )
                            devices.append(device)
                except Exception as e:
                    logger.debug(f"Failed to check device {i}: {e}")

        except Exception as e:
            logger.warning(f"Failed to enumerate WASAPI devices: {e}")

        return devices

    def find_default_loopback(self) -> Optional[AudioDevice]:
        """Find the default speakers' loopback device.

        Returns:
            AudioDevice for default speakers' loopback, or None
        """
        try:
            # Get WASAPI host API info
            wasapi_info = self._pa.get_host_api_info_by_type(pyaudio.paWASAPI)

            # Get default output device
            default_output_idx = wasapi_info.get('defaultOutputDevice', -1)
            if default_output_idx < 0:
                # Fallback to system default
                default_output_idx = self._pa.get_default_output_device_info()['index']

            default_output_info = self._pa.get_device_info_by_index(default_output_idx)
            default_output_name = default_output_info.get('name', '')

            logger.info(f"Default output device: {default_output_name}")

            # Find loopback version of this device
            loopback_devices = self.list_loopback_devices()

            for device in loopback_devices:
                # Match by name (loopback devices often have [Loopback] suffix)
                base_name = device.name.replace('[Loopback]', '').strip()
                if base_name in default_output_name or default_output_name in base_name:
                    logger.info(f"Found loopback device: {device.name}")
                    return device

            # If no exact match, return first loopback device
            if loopback_devices:
                logger.info(f"Using first loopback device: {loopback_devices[0].name}")
                return loopback_devices[0]

            logger.warning("No loopback devices found")
            return None

        except Exception as e:
            logger.error(f"Failed to find default loopback: {e}")
            return None

    def _audio_callback(self, in_data, frame_count, time_info, status):
        """PyAudio stream callback."""
        if status:
            logger.debug(f"Stream status: {status}")

        # Convert bytes to numpy array
        audio_data = np.frombuffer(in_data, dtype=np.float32)

        # Handle stereo -> mono conversion
        if self.device_channels == 2:
            audio_data = audio_data.reshape(-1, 2).mean(axis=1)
        elif self.device_channels > 2:
            audio_data = audio_data.reshape(-1, self.device_channels).mean(axis=1)

        # Resample if needed
        if self.device_sample_rate != self.target_sample_rate:
            audio_data = self._resample(audio_data, self.device_sample_rate, self.target_sample_rate)

        # Add to buffer
        self._buffer.append(audio_data)
        self._buffer_samples += len(audio_data)

        # Check if we have enough for a chunk
        chunk_samples = int(self.chunk_duration * self.target_sample_rate)
        if self._buffer_samples >= chunk_samples:
            # Combine buffer
            combined = np.concatenate(self._buffer)

            # Create chunk
            chunk_data = combined[:chunk_samples]

            # Keep remainder
            remainder = combined[chunk_samples:]
            self._buffer = [remainder] if len(remainder) > 0 else []
            self._buffer_samples = len(remainder)

            # Create AudioChunk and queue it
            chunk = AudioChunk(
                data=chunk_data,
                sample_rate=self.target_sample_rate,
                timestamp=time.time()
            )

            self._audio_queue.put(chunk)

        return (None, pyaudio.paContinue)

    def _resample(self, audio: np.ndarray, from_rate: int, to_rate: int) -> np.ndarray:
        """Resample audio to target sample rate.

        Args:
            audio: Audio samples
            from_rate: Source sample rate
            to_rate: Target sample rate

        Returns:
            Resampled audio
        """
        if from_rate == to_rate:
            return audio

        if SCIPY_AVAILABLE:
            # Use scipy for high-quality resampling
            num_samples = int(len(audio) * to_rate / from_rate)
            resampled = signal.resample(audio, num_samples)
            return resampled.astype(np.float32)
        else:
            # Simple linear interpolation fallback
            ratio = to_rate / from_rate
            new_length = int(len(audio) * ratio)
            indices = np.linspace(0, len(audio) - 1, new_length)
            resampled = np.interp(indices, np.arange(len(audio)), audio)
            return resampled.astype(np.float32)

    def _callback_thread(self):
        """Thread that processes audio queue and calls callback."""
        while self._running:
            try:
                chunk = self._audio_queue.get(timeout=0.1)
                if self.callback:
                    try:
                        self.callback(chunk)
                    except Exception as e:
                        logger.error(f"Callback error: {e}")
            except queue.Empty:
                continue

    def start(self) -> bool:
        """Start capturing audio.

        Returns:
            True if started successfully
        """
        if self._running:
            logger.warning("Capture already running")
            return True

        try:
            # Find device if not specified
            if self.device_index is None:
                device = self.find_default_loopback()
                if device is None:
                    logger.error("No loopback device found")
                    return False
                self.device_index = device.index
                self.device_sample_rate = device.sample_rate
                self.device_channels = device.channels
            else:
                # Get device info
                info = self._pa.get_device_info_by_index(self.device_index)
                self.device_sample_rate = int(info.get('defaultSampleRate', 48000))
                self.device_channels = max(int(info.get('maxInputChannels', 2)), 2)

            logger.info(f"Opening device {self.device_index}: "
                       f"{self.device_sample_rate}Hz, {self.device_channels}ch")

            # Calculate frames per buffer
            frames_per_buffer = int(self.device_sample_rate * 0.1)  # 100ms chunks

            # Open stream
            self._stream = self._pa.open(
                format=pyaudio.paFloat32,
                channels=self.device_channels,
                rate=self.device_sample_rate,
                input=True,
                input_device_index=self.device_index,
                frames_per_buffer=frames_per_buffer,
                stream_callback=self._audio_callback
            )

            self._running = True
            self._stream.start_stream()

            # Start callback thread
            if self.callback:
                self._thread = threading.Thread(target=self._callback_thread, daemon=True)
                self._thread.start()

            logger.info("WASAPI capture started")
            return True

        except Exception as e:
            logger.error(f"Failed to start capture: {e}")
            self._running = False
            return False

    def stop(self):
        """Stop capturing audio."""
        self._running = False

        if self._stream:
            try:
                self._stream.stop_stream()
                self._stream.close()
            except Exception as e:
                logger.debug(f"Error closing stream: {e}")
            self._stream = None

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
            self._thread = None

        # Clear buffer
        self._buffer = []
        self._buffer_samples = 0

        logger.info("WASAPI capture stopped")

    def get_chunk(self, timeout: float = 1.0) -> Optional[AudioChunk]:
        """Get the next audio chunk (blocking).

        Args:
            timeout: Maximum time to wait in seconds

        Returns:
            AudioChunk or None if timeout
        """
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def is_running(self) -> bool:
        """Check if capture is running."""
        return self._running

    def __del__(self):
        """Cleanup on destruction."""
        self.stop()
        if self._pa:
            try:
                self._pa.terminate()
            except Exception:
                pass


def test_wasapi_capture():
    """Test WASAPI capture functionality."""
    print("Testing WASAPI Capture...")

    capture = WASAPICapture()

    print("\nAvailable loopback devices:")
    devices = capture.list_loopback_devices()
    if not devices:
        print("  No loopback devices found!")
        print("\nAll devices:")
        for d in capture.list_devices():
            print(f"  [{d.index}] {d.name} - {d.channels}ch @ {d.sample_rate}Hz")
        return

    for d in devices:
        print(f"  [{d.index}] {d.name} - {d.channels}ch @ {d.sample_rate}Hz")

    print("\nFinding default loopback...")
    default = capture.find_default_loopback()
    if default:
        print(f"  Default: [{default.index}] {default.name}")
    else:
        print("  No default loopback found")


if __name__ == "__main__":
    test_wasapi_capture()
