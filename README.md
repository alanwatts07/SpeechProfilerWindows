# Speech Profiler for Windows

Real-time speech analysis tool that profiles speakers using AI. Captures system audio (what you hear), identifies speakers, transcribes speech, and analyzes communication patterns.

![Speech Profiler](https://img.shields.io/badge/Platform-Windows-blue) ![Python](https://img.shields.io/badge/Python-3.10+-green) ![License](https://img.shields.io/badge/License-MIT-yellow)

## Features

- **Live Transcription** - Real-time speech-to-text using OpenAI Whisper
- **Speaker Identification** - Recognizes and tracks different speakers by voice
- **VAK Analysis** - Detects Visual/Auditory/Kinesthetic communication styles
- **Social Needs Detection** - Identifies underlying psychological needs
- **Claude AI Insights** - Deep analysis of speaker patterns and persuasion tips
- **Session History** - Browse past conversations and speaker profiles

## Download

**[Download Latest Release](../../releases/latest)**

1. Download the zip file
2. Extract anywhere
3. Run `SpeechProfiler.exe`
4. That's it!

## First Run

On first launch:
1. A setup popup appears for the optional Claude AI API key
2. Get a FREE key at [console.anthropic.com](https://console.anthropic.com) ($5 free credit!)
3. Paste it in the app - or skip and use without AI insights

**Note:** First run downloads the Whisper speech model (~140MB). This may take a minute.

## What Works Without API Key

Everything except Claude AI analysis:
- Live transcription
- Speaker identification
- VAK modality detection
- Social needs analysis
- All profile meters

## Requirements

- Windows 10/11
- Audio output device (speakers/headphones)
- Internet connection (first run only, for model download)

## How It Works

The app captures "loopback" audio - whatever is playing through your speakers. This means it can transcribe:
- Video calls (Zoom, Teams, Discord, etc.)
- YouTube videos
- Podcasts
- Any audio playing on your PC

## Building From Source

If you want to build it yourself:

```powershell
# Clone the repo
git clone https://github.com/YOURUSERNAME/SpeechProfiler.git
cd SpeechProfiler

# Create virtual environment
python -m venv venv
.\venv\Scripts\Activate

# Install dependencies
pip install -r requirements.txt

# Build exe
python build.py
```

Output will be in `dist/SpeechProfiler/`

## Tech Stack

- **Whisper** - OpenAI's speech recognition
- **Resemblyzer** - Speaker identification via voice embeddings
- **PyAudioWPatch** - Windows WASAPI loopback audio capture
- **Claude API** - Anthropic's AI for deep analysis
- **Tkinter** - Native Windows GUI

## License

MIT License - do whatever you want with it!

## Credits

Built with Claude AI assistance.
