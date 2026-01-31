"""System tray integration for Windows Speech Profiler."""

import logging
import threading
from typing import Callable, Optional
from io import BytesIO

try:
    import pystray
    from PIL import Image, ImageDraw
    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False

logger = logging.getLogger(__name__)


class SystemTray:
    """System tray icon and menu for the profiler."""

    def __init__(
        self,
        on_show_dashboard: Optional[Callable] = None,
        on_toggle_capture: Optional[Callable] = None,
        on_quit: Optional[Callable] = None
    ):
        """Initialize system tray.

        Args:
            on_show_dashboard: Callback when "Open Dashboard" is clicked
            on_toggle_capture: Callback when "Start/Stop Capture" is clicked
            on_quit: Callback when "Quit" is clicked
        """
        if not PYSTRAY_AVAILABLE:
            raise ImportError(
                "pystray and Pillow are required for system tray. "
                "Install with: pip install pystray Pillow"
            )

        self.on_show_dashboard = on_show_dashboard
        self.on_toggle_capture = on_toggle_capture
        self.on_quit = on_quit

        self._icon = None
        self._is_recording = False
        self._thread = None

    def _create_icon_image(self, recording: bool = False) -> Image.Image:
        """Create icon image based on recording state.

        Args:
            recording: Whether currently recording

        Returns:
            PIL Image for the icon
        """
        # Create a simple icon
        size = 64
        image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # Background circle
        if recording:
            # Green when recording
            bg_color = (46, 204, 113)  # Emerald green
        else:
            # Gray when idle
            bg_color = (149, 165, 166)  # Gray

        # Draw filled circle
        margin = 4
        draw.ellipse(
            [margin, margin, size - margin, size - margin],
            fill=bg_color,
            outline=(255, 255, 255)
        )

        # Draw microphone or waveform symbol
        center = size // 2
        if recording:
            # Draw waveform lines when recording
            for i, height in enumerate([12, 20, 16, 22, 14]):
                x = center - 16 + i * 8
                y1 = center - height // 2
                y2 = center + height // 2
                draw.line([(x, y1), (x, y2)], fill=(255, 255, 255), width=3)
        else:
            # Draw microphone shape when idle
            mic_top = center - 12
            mic_bottom = center + 8
            mic_width = 8
            draw.rounded_rectangle(
                [center - mic_width, mic_top, center + mic_width, mic_bottom],
                radius=mic_width,
                fill=(255, 255, 255)
            )
            # Microphone base
            draw.arc(
                [center - 12, center, center + 12, center + 16],
                start=0, end=180,
                fill=(255, 255, 255),
                width=2
            )
            draw.line(
                [(center, center + 16), (center, center + 22)],
                fill=(255, 255, 255),
                width=2
            )

        return image

    def _create_menu(self):
        """Create the tray icon menu."""
        def show_dashboard(icon, item):
            if self.on_show_dashboard:
                self.on_show_dashboard()

        def toggle_capture(icon, item):
            if self.on_toggle_capture:
                self.on_toggle_capture()

        def quit_app(icon, item):
            icon.stop()
            if self.on_quit:
                self.on_quit()

        capture_text = "Stop Capture" if self._is_recording else "Start Capture"

        return pystray.Menu(
            pystray.MenuItem("Open Dashboard", show_dashboard, default=True),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(capture_text, toggle_capture),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", quit_app)
        )

    def _on_click(self, icon, button):
        """Handle left-click on tray icon."""
        if self.on_show_dashboard:
            self.on_show_dashboard()

    def update_recording_state(self, recording: bool):
        """Update the icon to reflect recording state.

        Args:
            recording: Whether currently recording
        """
        self._is_recording = recording
        if self._icon:
            self._icon.icon = self._create_icon_image(recording)
            self._icon.menu = self._create_menu()

    def start(self, blocking: bool = False):
        """Start the system tray icon.

        Args:
            blocking: If True, run in current thread (blocks). If False, run in background.
        """
        self._icon = pystray.Icon(
            name="Speech Profiler",
            icon=self._create_icon_image(self._is_recording),
            title="Speech Profiler",
            menu=self._create_menu()
        )

        # Set up left-click handler
        # Note: pystray doesn't directly support left-click, but default menu item works

        if blocking:
            self._icon.run()
        else:
            self._thread = threading.Thread(target=self._icon.run, daemon=True)
            self._thread.start()

    def stop(self):
        """Stop the system tray icon."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception as e:
                logger.debug(f"Error stopping tray icon: {e}")
            self._icon = None

    def is_running(self) -> bool:
        """Check if tray icon is running."""
        return self._icon is not None and self._icon.visible


def test_system_tray():
    """Test system tray functionality."""
    import time

    def on_show():
        print("Show dashboard clicked!")

    def on_toggle():
        print("Toggle capture clicked!")
        tray.update_recording_state(not tray._is_recording)

    def on_quit():
        print("Quit clicked!")

    print("Testing System Tray...")
    print("Look for the icon in your system tray.")
    print("Press Ctrl+C to exit.")

    tray = SystemTray(
        on_show_dashboard=on_show,
        on_toggle_capture=on_toggle,
        on_quit=on_quit
    )

    try:
        tray.start(blocking=True)
    except KeyboardInterrupt:
        print("\nStopping...")
        tray.stop()


if __name__ == "__main__":
    test_system_tray()
