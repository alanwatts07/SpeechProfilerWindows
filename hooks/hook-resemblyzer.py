"""PyInstaller hook for resemblyzer."""

from PyInstaller.utils.hooks import collect_all, collect_data_files

# Collect everything from resemblyzer
datas, binaries, hiddenimports = collect_all('resemblyzer')

# Also need librosa and its dependencies
datas2, binaries2, hiddenimports2 = collect_all('librosa')
datas += datas2
binaries += binaries2
hiddenimports += hiddenimports2

# Soundfile for audio loading
hiddenimports += [
    'soundfile',
    'audioread',
    'resampy',
    'numba',
    'llvmlite',
]
