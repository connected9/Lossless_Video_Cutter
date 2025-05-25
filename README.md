# Lossless Video Cutter

Lossless Video Cutter is a desktop application for cutting video segments without re-encoding (for lossless operations) or with re-encoding to various formats. It aims to replicate the core functionality of tools like "Free Video Editor" with a focus on user-friendliness and responsiveness.

## Prerequisites

*   **Python:** Python 3.8 or newer.
*   **ffmpeg & ffprobe:** `ffmpeg` and `ffprobe` must be installed on your system and accessible via the system's PATH environment variable. You can download them from [ffmpeg.org](https://ffmpeg.org/download.html).

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

## Basic Usage

1.  Ensure `ffmpeg` and `ffprobe` are in your system's PATH.
2.  Activate your virtual environment (if you created one).
3.  Run the application:
    ```bash
    python main.py
    ```

## Features

*   **Load Videos:** Add video files via a dialog or drag-and-drop.
    *   Supported input formats: .avi, .mpg, .mp4, .mkv, .flv, .3gp, .webm, .wmv.
*   **Keyframe Detection:** Automatically detects and displays keyframes on a timeline.
*   **Timeline:** Visual representation of video duration, keyframes, and current playback position.
*   **Segment Selection:**
    *   Define multiple segments using "Begin Selection" and "End Selection" buttons.
    *   Visually see selected segments on the timeline.
    *   Undo selections.
*   **Keyframe Tagging:** Select individual keyframes for splitting operations.
*   **Output Options:**
    *   **Original Format (Lossless):** Stream copy, no re-encoding.
    *   **AVI, MP4, MKV:** Re-encode to these formats.
    *   **MP3 (Audio Only):** Extract audio.
    *   **GIF:** Generate animated GIF from selections.
*   **Saving Modes:**
    *   **Save Video (Keep Selections):** Concatenate all selected segments into one file.
    *   **Split by Selections + Save:** Save each selected segment as a separate file.
    *   **Split by Tags + Save:** Split video at selected keyframes and save each part.
*   **Responsive UI:** All video processing happens in background threads, keeping the UI responsive.
*   **Progress Indication:** Progress bar and status messages for operations.
*   **Settings Persistence:** Remembers last used directories and output format.
