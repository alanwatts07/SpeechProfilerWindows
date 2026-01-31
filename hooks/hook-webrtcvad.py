"""Custom PyInstaller hook for webrtcvad - overrides the broken default one."""

# Don't try to copy metadata (causes issues with webrtcvad-wheels)
# Just make sure the module is included
hiddenimports = ['webrtcvad']
