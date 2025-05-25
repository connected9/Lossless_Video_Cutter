# Lossless Video Cutter

Lossless Video Cutter is a desktop application for cutting video segments without re-encoding (for lossless operations) or with re-encoding to various formats. It aims to replicate the core functionality of tools like "Free Video Editor" with a focus on user-friendliness, responsiveness, and precise selection.

## Prerequisites

*   **Python:** Python 3.8 or newer.
*   **ffmpeg & ffprobe:** `ffmpeg` and `ffprobe` must be installed on your system and accessible via the system's PATH environment variable. You can download them from [ffmpeg.org](https://ffmpeg.org/download.html).
*   **Qt Multimedia Backends:** For the video preview feature, your system needs appropriate Qt multimedia backends installed (e.g., GStreamer good/ugly/bad plugins on Linux, or system-provided Media Foundation on Windows / AVFoundation on macOS).

## Installation

1.  **Clone or Download:**
    Get the application files. If you cloned a repository:
    ```bash
    git clone <repository_url>
    cd lossless_video_cutter
    ```

2.  **Set up a Virtual Environment (Recommended):**
    ```bash
    python -m venv venv
    # On Windows
    venv\Scripts\activate
    # On macOS/Linux
    source venv/bin/activate
    ```

3.  **Install Dependencies:**
    Install the required Python packages using pip:
    ```bash
    pip install -r requirements.txt
    ```
    (Note: `requirements.txt` should list `PyQt6` primarily. `ffmpeg` is an external dependency.)

## Basic Usage

1.  Ensure `ffmpeg` and `ffprobe` are in your system's PATH.
2.  Ensure your system has necessary multimedia codecs for Qt's `QMediaPlayer` if you want video preview (highly recommended).
3.  Activate your virtual environment (if you created one).
4.  Run the application:
    ```bash
    python main.py
    ```

## Features

*   **Load Videos:** Add video files via a dialog or drag-and-drop.
    *   Supported input formats: .avi, .mpg, .mp4, .mkv, .flv, .3gp, .webm, .wmv.
*   **Video Preview:**
    *   Displays the loaded video.
    *   Synchronized with the timeline playhead.
    *   Allows Play/Pause functionality.
*   **Frame Stepping:**
    *   Use **Left Arrow** and **Right Arrow** keys to move backward or forward one frame at a time for precise selection. The video preview will update accordingly.
*   **Keyframe Detection:** Automatically detects and displays keyframes on a timeline.
*   **Timeline:** Visual representation of video duration, playhead position, keyframes, and selected segments.
    *   Click or drag on the timeline to change the current position.
*   **Segment Selection:**
    *   Define multiple segments using "Begin Selection" and "End Selection" buttons.
    *   Visually see selected segments on the timeline.
    *   Undo selections individually or clear all.
*   **Keyframe Tagging:** Select individual keyframes for splitting operations by clicking on their markers in the timeline.
*   **Output Options:**
    *   **Original Format (Lossless):** Stream copy, no re-encoding. (Default)
    *   **AVI, MP4, MKV:** Re-encode to these common formats.
    *   **MP3 (Audio Only):** Extract audio.
    *   **GIF:** Generate animated GIF from selections.
*   **Saving Modes:**
    *   **Save (Keep Selections):** Concatenate all user-defined selected segments into one file.
    *   **Save (Remove Selections):** Concatenate parts of the video *not* in any user-defined selection (i.e., removes selected parts).
    *   **Split by Selections + Save:** Save each selected segment as a separate file.
    *   **Split by Tags + Save:** Split video at selected keyframes and save each resulting part.
*   **Responsive UI:** All video processing (probing, cutting, encoding) happens in background threads, keeping the UI responsive.
*   **Progress Indication:** Progress bar and status messages for operations.
*   **Settings Persistence:** Remembers last used input/output directories and last selected output format.
*   **Keyboard Shortcuts:**
    *   `Ctrl+O`: Add File
    *   `Ctrl+S`: Save Video
    *   `B`: Begin Selection
    *   `E`: End Selection
    *   `U`: Undo/Clear Selection(s)
    *   `Delete`: Undo selection if playhead is inside it
    *   `Spacebar`: Play/Pause video preview
    *   `Left Arrow`: Step back one frame
    *   `Right Arrow`: Step forward one frame

## Known Limitations

*   **Video Preview Accuracy:** The video preview relies on Qt's `QMediaPlayer`, whose frame-seeking accuracy can vary based on system codecs and video formats. For frame stepping, it will attempt to show the correct frame but might occasionally jump to the nearest keyframe depending on the video.
*   **Complex Concatenation for Re-encoding:** When concatenating multiple segments that also require re-encoding (e.g., making a single MP4 from several disparate parts), the current method cuts segments losslessly (if possible) or to a temporary common format, then concatenates them, and finally re-encodes the whole concatenated stream. More advanced `ffmpeg` filter_complex usage could optimize this but adds significant complexity.
