# lossless_video_cutter/app_config.py
from typing import Dict, List, Tuple

# Supported input file extensions and Qt Dialog filter string
SUPPORTED_INPUT_FORMATS_FILTER: str = \
    "Video Files (*.mp4 *.avi *.mkv *.mpg *.mpeg *.flv *.3gp *.webm *.wmv);;All Files (*)"
SUPPORTED_INPUT_EXTENSIONS: Tuple[str, ...] = (
    '.avi', '.mpg', '.mp4', '.mkv', '.flv', '.3gp', '.webm', '.wmv'
)

# Output format options
# Each key is the display name in the dropdown
# Value is a dict with:
#   'ext': default extension
#   'ffmpeg_args': list of ffmpeg arguments (excluding input/output files, -ss, -to)
#   'is_audio_only': boolean
#   'is_gif': boolean
#   'needs_reencode': boolean (True if not -c copy)
OUTPUT_FORMATS: Dict[str, Dict] = {
    "Original Format (Lossless)": {
        "ext": None,  # Will use original extension
        "ffmpeg_args": ["-c", "copy", "-map", "0"],
        "is_audio_only": False,
        "is_gif": False,
        "needs_reencode": False,
    },
    "MP4 (H.264 + AAC)": {
        "ext": ".mp4",
        "ffmpeg_args": ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart"],
        "is_audio_only": False,
        "is_gif": False,
        "needs_reencode": True,
    },
    "MKV (H.264 + AAC)": {
        "ext": ".mkv",
        "ffmpeg_args": ["-c:v", "libx264", "-preset", "medium", "-crf", "23", "-c:a", "aac", "-b:a", "128k"],
        "is_audio_only": False,
        "is_gif": False,
        "needs_reencode": True,
    },
    "AVI (Xvid + MP3)": {
        "ext": ".avi",
        "ffmpeg_args": ["-c:v", "libxvid", "-qscale:v", "4", "-c:a", "libmp3lame", "-qscale:a", "4"],
        "is_audio_only": False,
        "is_gif": False,
        "needs_reencode": True,
    },
    "MP3 (Audio Only)": {
        "ext": ".mp3",
        "ffmpeg_args": ["-vn", "-c:a", "libmp3lame", "-qscale:a", "2", "-ar", "44100", "-ac", "2"],
        "is_audio_only": True,
        "is_gif": False,
        "needs_reencode": True, # Technically audio re-encode
    },
    "GIF (Animated)": {
        "ext": ".gif",
        # Basic GIF, quality can be improved with palettegen/paletteuse, but complex for multiple segments
        # For simplicity, a direct conversion. Users might want to adjust fps/scale.
        "ffmpeg_args": ["-vf", "fps=10,scale=480:-1:flags=lanczos", "-loop", "0"],
        "is_audio_only": False, # GIF has no audio
        "is_gif": True,
        "needs_reencode": True,
    }
}

# Timeline settings
TIMELINE_SECONDS_PER_TICK_MAJOR: int = 10  # A major tick every 10 seconds
TIMELINE_SECONDS_PER_TICK_MINOR: int = 1   # A minor tick every 1 second
TIMELINE_HEIGHT: int = 80
TIMELINE_MARKER_COLOR: str = "#A0A0A0"
TIMELINE_KEYFRAME_COLOR: str = "#FFD700" # Gold
TIMELINE_SELECTED_KEYFRAME_COLOR: str = "#FF8C00" # DarkOrange
TIMELINE_SELECTION_COLOR: str = "rgba(0, 120, 215, 100)" # Semi-transparent blue
TIMELINE_PLAYHEAD_COLOR: str = "#E74C3C" # Red

# Settings keys for QSettings
SETTING_LAST_INPUT_DIR: str = "last_input_dir"
SETTING_LAST_OUTPUT_DIR: str = "last_output_dir"
SETTING_LAST_OUTPUT_FORMAT: str = "last_output_format"

# FFmpeg progress regex (example, might need refinement)
# time=00:00:01.23
FFMPEG_TIME_REGEX = r"time=(\d{2}:\d{2}:\d{2}\.\d{2,})"

# Temporary directory name for concat operations
TEMP_DIR_NAME = "lossless_cutter_temp"