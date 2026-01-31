"""Build script to create Windows executable."""

import subprocess
import sys
import shutil
from pathlib import Path

def main():
    print("=" * 60)
    print("Building Windows Speech Profiler")
    print("=" * 60)

    # Install PyInstaller if needed
    print("\n[1/4] Checking PyInstaller...")
    try:
        import PyInstaller
        print("  PyInstaller is installed")
    except ImportError:
        print("  Installing PyInstaller...")
        subprocess.run([sys.executable, "-m", "pip", "install", "pyinstaller"], check=True)

    # Clean previous builds
    print("\n[2/4] Cleaning previous builds...")
    for folder in ["build", "dist"]:
        if Path(folder).exists():
            try:
                shutil.rmtree(folder)
                print(f"  Removed {folder}/")
            except PermissionError:
                print(f"  WARNING: Could not remove {folder}/ (files in use)")
                print(f"  Close SpeechProfiler.exe and try again, or delete {folder}/ manually")
                sys.exit(1)

    # Create data directory in dist
    print("\n[3/4] Building executable...")

    # Run PyInstaller
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=SpeechProfiler",
        "--onedir",  # Use onedir for faster startup (onefile is slower)
        "--console",  # Keep console to see errors
        "--icon=NONE",  # Add your own .ico file if you have one
        "--add-data=src;src",  # Include source files
        "--additional-hooks-dir=hooks",  # Custom hooks
        # Core dependencies
        "--hidden-import=numpy",
        "--hidden-import=numpy.core._methods",
        "--hidden-import=numpy.lib.format",
        # Audio
        "--hidden-import=pyaudiowpatch",
        "--hidden-import=pyaudio",
        # ML/AI
        "--hidden-import=whisper",
        "--hidden-import=whisper.tokenizer",
        "--hidden-import=torch",
        "--hidden-import=torchaudio",
        "--hidden-import=resemblyzer",
        "--hidden-import=resemblyzer.audio",
        "--hidden-import=resemblyzer.voice_encoder",
        "--hidden-import=librosa",
        "--hidden-import=librosa.core",
        "--hidden-import=librosa.util",
        "--hidden-import=librosa.feature",
        "--hidden-import=soundfile",
        "--hidden-import=audioread",
        "--hidden-import=resampy",
        "--hidden-import=numba",
        "--hidden-import=llvmlite",
        # Scientific
        "--hidden-import=scipy",
        "--hidden-import=scipy.spatial",
        "--hidden-import=scipy.spatial.distance",
        "--hidden-import=scipy.signal",
        "--hidden-import=scipy.io",
        "--hidden-import=scipy.io.wavfile",
        "--hidden-import=sklearn",
        "--hidden-import=sklearn.cluster",
        "--hidden-import=sklearn.metrics",
        # NLP
        "--hidden-import=nltk",
        "--hidden-import=textstat",
        # Database
        "--hidden-import=sqlalchemy",
        "--hidden-import=sqlalchemy.orm",
        # UI
        "--hidden-import=tkinter",
        "--hidden-import=PIL",
        "--hidden-import=PIL.Image",
        "--hidden-import=pystray",
        # API
        "--hidden-import=anthropic",
        # Utils
        "--hidden-import=dotenv",
        # Exclude problematic packages we don't need
        "--exclude-module=tensorboard",
        "--exclude-module=pytest",
        "--exclude-module=IPython",
        "--exclude-module=jupyter",
        # webrtcvad IS needed by resemblyzer
        "--hidden-import=webrtcvad",
        # Collect all files from these packages
        "--collect-all=numpy",
        "--collect-all=resemblyzer",
        "--collect-all=whisper",
        "--collect-all=torch",
        "--collect-all=torchaudio",
        "--collect-all=librosa",
        "--collect-all=soundfile",
        "--collect-all=audioread",
        "--collect-data=resemblyzer",
        "--collect-binaries=resemblyzer",
        "--noconfirm",
        "main.py"
    ]

    subprocess.run(cmd, check=True)

    # Create data directory
    print("\n[4/4] Setting up distribution...")

    # Copy resemblyzer package manually (PyInstaller often misses it)
    import site
    site_packages = Path(site.getsitepackages()[0])
    resemblyzer_src = site_packages / "resemblyzer"
    if resemblyzer_src.exists():
        resemblyzer_dst = Path("dist/SpeechProfiler/_internal/resemblyzer")
        if resemblyzer_dst.exists():
            shutil.rmtree(resemblyzer_dst)
        shutil.copytree(resemblyzer_src, resemblyzer_dst)
        print(f"  Copied resemblyzer package")
    else:
        print(f"  WARNING: resemblyzer not found at {resemblyzer_src}")
    dist_dir = Path("dist/SpeechProfiler")
    data_dir = dist_dir / "data"
    data_dir.mkdir(exist_ok=True)

    # Create .env template (optional - users can also enter key in app)
    env_template = dist_dir / ".env.example"
    env_template.write_text("""# Speech Profiler Configuration
# NOTE: You can also enter your API key directly in the app (Settings button)!

# Optional: Add API key here instead of using the Settings dialog
# ANTHROPIC_API_KEY=your_api_key_here
""")

    print("\n" + "=" * 60)
    print("BUILD COMPLETE!")
    print("=" * 60)
    print(f"\nOutput: dist/SpeechProfiler/")
    print("\nTo distribute:")
    print("  1. Zip the 'dist/SpeechProfiler' folder")
    print("  2. Upload to your website")
    print("  3. Users download, extract, and run SpeechProfiler.exe")
    print("  4. App will guide them to get a free API key on first run")
    print("\nNote: First run downloads Whisper model (~140MB)")

if __name__ == "__main__":
    main()
