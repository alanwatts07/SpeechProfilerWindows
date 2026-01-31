# Building Speech Profiler for Windows

## Quick Build

1. Open PowerShell in the project folder
2. Make sure you're in the venv: `.\venv\Scripts\Activate`
3. Run: `python build.py`
4. Find the output in `dist/SpeechProfiler/`

## What You Get

The `dist/SpeechProfiler/` folder contains:
- `SpeechProfiler.exe` - The main application
- `data/` - Where profiles are stored

## Distributing to Friends

1. Zip the entire `dist/SpeechProfiler/` folder
2. Share the zip file
3. Tell them to:
   - Extract the zip
   - Run `SpeechProfiler.exe`
   - That's it!

## First Run Experience

When users first open the app:
1. A setup popup appears automatically
2. Shows how to get a FREE API key (takes 2 min)
3. They paste the key right in the app
4. Done! No file editing needed.

They can also click **Settings** anytime to add/change the key.

## What Works Without API Key

Everything except Claude AI insights:
- Live transcription
- Speaker identification
- VAK modality detection
- Social needs analysis
- All profile meters

## Getting a Free API Key

1. Go to https://console.anthropic.com
2. Sign up (free, no credit card)
3. You get $5 free credit (that's hundreds of analyses!)
4. Create an API key
5. Paste it in the app's Settings

## Troubleshooting

**"Whisper model not found"**
- First run downloads the model (~140MB)
- Needs internet connection

**"No audio devices"**
- Make sure speakers/headphones are connected
- The app captures what you hear (loopback audio)

**App won't start**
- Make sure Windows Defender isn't blocking it
- Try running as Administrator

## File Size

The app is large (~500MB) because it includes:
- PyTorch (AI framework)
- Whisper (speech recognition)
- Resemblyzer (voice identification)

This is normal for ML-based applications.

## Hosting on Your Website

Just upload the zip file! Users download, extract, and run.
No installer needed.
