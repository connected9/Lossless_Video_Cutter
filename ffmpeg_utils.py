# lossless_video_cutter/ffmpeg_utils.py
import subprocess
import json
import os
import re
from typing import List, Optional, Tuple, Dict, Any
from app_config import FFMPEG_TIME_REGEX # Make sure app_config.py is accessible

def check_ffmpeg_tools() -> bool:
    """Checks if ffmpeg and ffprobe are accessible."""
    try:
        # Use startupinfo to hide console window on Windows
        si = get_startup_info()
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, startupinfo=si, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
        subprocess.run(["ffprobe", "-version"], capture_output=True, check=True, startupinfo=si, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def get_startup_info():
    """Returns startupinfo for subprocess to prevent console window on Windows."""
    if os.name == 'nt':
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        return startupinfo
    return None

def get_video_info(filepath: str) -> Optional[Dict[str, Any]]:
    """Gets video duration and other stream info using ffprobe."""
    command = [
        "ffprobe",
        "-v", "quiet",
        "-print_format", "json",
        "-show_format",
        "-show_streams",
        filepath
    ]
    try:
        si = get_startup_info()
        process = subprocess.run(command, capture_output=True, text=True, check=True, startupinfo=si, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
        return json.loads(process.stdout)
    except (subprocess.CalledProcessError, FileNotFoundError, json.JSONDecodeError) as e:
        print(f"Error probing video info for '{filepath}': {e}")
        return None

def get_video_duration(video_info: Dict[str, Any]) -> float:
    """Extracts duration from ffprobe output. More robust parsing."""
    duration = 0.0
    if video_info and "format" in video_info and "duration" in video_info["format"]:
        try:
            duration_str = video_info["format"]["duration"]
            if duration_str and duration_str != "N/A":
                duration = float(duration_str)
        except (ValueError, TypeError):
            print(f"Warning: Could not parse format duration: {video_info['format'].get('duration')}")
            duration = 0.0 # Reset if parsing failed

    # Fallback or primary if format duration is 0 or invalid
    if duration <= 0 and video_info and "streams" in video_info:
        max_stream_duration = 0.0
        for stream in video_info["streams"]:
            if "duration" in stream:
                try:
                    stream_dur_str = stream["duration"]
                    if stream_dur_str and stream_dur_str != "N/A":
                        stream_dur = float(stream_dur_str)
                        if stream_dur > max_stream_duration:
                            max_stream_duration = stream_dur
                except (ValueError, TypeError):
                    continue
        if max_stream_duration > 0:
            return max_stream_duration
            
    return duration if duration > 0 else 0.0


def get_video_fps(video_info: Dict[str, Any]) -> float:
    """
    Extracts FPS (Frames Per Second) from ffprobe output for the first video stream.
    Tries 'avg_frame_rate' first, then 'r_frame_rate'.
    """
    if video_info and "streams" in video_info:
        for stream in video_info["streams"]:
            if stream.get("codec_type") == "video":
                # Try avg_frame_rate
                avg_frame_rate_str = stream.get("avg_frame_rate")
                if avg_frame_rate_str and avg_frame_rate_str != "0/0":
                    try:
                        num, den = map(int, avg_frame_rate_str.split('/'))
                        if den != 0:
                            return float(num) / den
                    except ValueError:
                        print(f"Warning: Could not parse avg_frame_rate: {avg_frame_rate_str}")
                        pass # Invalid format, try next

                # Fallback to r_frame_rate
                r_frame_rate_str = stream.get("r_frame_rate")
                if r_frame_rate_str and r_frame_rate_str != "0/0":
                    try:
                        num, den = map(int, r_frame_rate_str.split('/'))
                        if den != 0:
                            return float(num) / den
                    except ValueError:
                        print(f"Warning: Could not parse r_frame_rate: {r_frame_rate_str}")
                        pass # Invalid format
                
                # If neither worked but we are in a video stream, break (or log warning)
                print(f"Warning: FPS not found for video stream in {stream.get('index', 'N/A')}")
                return 0.0 # Indicate FPS not found for this stream
    print("Warning: No video stream found or FPS could not be determined.")
    return 0.0 # Default or if not found


def get_video_dimensions(video_info: Dict[str, Any]) -> Tuple[int, int]:
    """Extracts width and height from ffprobe output for the first video stream."""
    if video_info and "streams" in video_info:
        for stream in video_info["streams"]:
            if stream.get("codec_type") == "video":
                width = int(stream.get("width", 0))
                height = int(stream.get("height", 0))
                if width > 0 and height > 0:
                    return width, height
    return 0, 0


def get_keyframes(filepath: str) -> List[float]:
    """Gets keyframe timestamps using ffprobe."""
    command = [
        "ffprobe",
        "-v", "error",
        "-skip_frame", "nokey", # This selects only keyframes
        "-select_streams", "v:0", # Only from the first video stream
        "-show_entries", "frame=pkt_pts_time", # Get presentation timestamp
        "-of", "csv=p=0", # Output as CSV, no header
        filepath
    ]
    keyframes = []
    try:
        si = get_startup_info()
        process = subprocess.run(command, capture_output=True, text=True, check=True, startupinfo=si, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
        raw_output = process.stdout.strip()
        if raw_output: # Ensure there's output before splitting
            for line in raw_output.split('\n'):
                if line: # Ensure line is not empty
                    try:
                        keyframes.append(float(line))
                    except ValueError:
                        print(f"Warning: Could not parse keyframe time: {line}")
        return sorted(list(set(keyframes))) # Ensure sorted and unique
    except subprocess.CalledProcessError as e:
        # If ffprobe fails (e.g., corrupted file, or no keyframes if skip_frame is too strict for some formats)
        print(f"Error getting keyframes (ffprobe failed for '{filepath}'): {e}")
        print(f"ffprobe stderr: {e.stderr.decode() if e.stderr else 'N/A'}")
        return []
    except FileNotFoundError:
        print(f"Error getting keyframes: ffprobe not found.")
        return []
    except Exception as e:
        print(f"Unexpected error getting keyframes for '{filepath}': {e}")
        return []


def time_str_to_seconds(time_str: str) -> float:
    """Converts HH:MM:SS.ms, MM:SS.ms, or SS.ms string to seconds."""
    if not isinstance(time_str, str): return 0.0
    parts = time_str.split(':')
    try:
        if len(parts) == 3: # HH:MM:SS.ms
            h = int(parts[0])
            m = int(parts[1])
            s_ms = float(parts[2])
            return float(h * 3600 + m * 60 + s_ms)
        elif len(parts) == 2: # MM:SS.ms
            m = int(parts[0])
            s_ms = float(parts[1])
            return float(m * 60 + s_ms)
        elif len(parts) == 1: # SS.ms
            return float(parts[0])
    except ValueError:
        print(f"Warning: Could not parse time string to seconds: {time_str}")
    return 0.0


class FfmpegProcess:
    """
    Manages an ffmpeg subprocess, allowing for progress monitoring and basic error capture.
    """
    def __init__(self, command: List[str], total_duration: Optional[float] = None):
        self.command = command
        self.total_duration = total_duration
        self.process: Optional[subprocess.Popen] = None
        self.error_output: str = ""
        self.stdout_buffer: List[str] = [] # To capture more output if needed

    def run(self, progress_callback: Optional[callable] = None) -> bool:
        try:
            si = get_startup_info()
            # For CREATE_NO_WINDOW with Popen, it's slightly different
            creation_flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

            self.process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, # Redirect stderr to stdout
                universal_newlines=True,  # text mode
                startupinfo=si,
                creationflags=creation_flags,
                bufsize=1 # Line buffered
            )

            self.error_output = "" # Reset error output
            self.stdout_buffer = []

            if self.process.stdout:
                for line in iter(self.process.stdout.readline, ''):
                    if not line: # Should not happen with iter(readline, '') but good practice
                        break
                    line_strip = line.strip()
                    # print(f"FFMPEG_RAW: {line_strip}") # Verbose Debugging
                    self.stdout_buffer.append(line_strip) # Store all output for later inspection

                    if progress_callback and self.total_duration and self.total_duration > 0:
                        match = re.search(FFMPEG_TIME_REGEX, line_strip)
                        if match:
                            current_time_str = match.group(1)
                            current_time_sec = time_str_to_seconds(current_time_str)
                            percentage = min(100, int((current_time_sec / self.total_duration) * 100))
                            progress_callback(percentage, f"Encoding... {current_time_str}")
                self.process.stdout.close()

            return_code = self.process.wait() # Wait for the process to complete

            # Combine buffer into error_output string for final message
            self.error_output = "\n".join(self.stdout_buffer)


            if return_code == 0:
                return True
            else:
                # Extract a more relevant snippet for the error message
                error_lines = self.error_output.strip().split('\n')
                relevant_errors = [l for l in error_lines if "error" in l.lower() or "failed" in l.lower() or "invalid" in l.lower()]
                if not relevant_errors: # If no specific error lines, take last few
                    specific_error_snippet = "\n".join(error_lines[-5:])
                else:
                    specific_error_snippet = "\n".join(relevant_errors[-3:]) # Last 3 relevant error lines

                print(f"FFmpeg command failed with exit code {return_code}")
                print(f"Command: {' '.join(self.command)}")
                # print(f"Full FFmpeg Output:\n{self.error_output}") # Optional: print full output for debug
                self.error_output = f"FFmpeg failed (code {return_code}):\n{specific_error_snippet if specific_error_snippet else 'Unknown error, check console for full ffmpeg output.'}"
                return False

        except FileNotFoundError:
            self.error_output = "ffmpeg executable not found. Please ensure it's in your PATH."
            print(self.error_output)
            return False
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.error_output = f"An unexpected error occurred while running ffmpeg: {e}"
            print(self.error_output)
            return False
        finally:
            # Ensure process is cleaned up if it exists
            if self.process and self.process.poll() is None: # Check if still running
                print("Warning: FFmpeg process did not terminate, attempting to kill.")
                self.process.kill()
                self.process.wait() # Wait for kill to complete


    def get_error_message(self) -> str:
        return self.error_output