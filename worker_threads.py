# lossless_video_cutter/worker_threads.py
from PyQt6.QtCore import QThread, pyqtSignal, QObject
from typing import List, Dict, Any, Tuple, Optional # Ensure these are here from previous versions
import os # Ensure os is imported
import shutil # Ensure shutil is imported
import tempfile # Ensure tempfile is imported


from ffmpeg_utils import (
    get_video_info,
    get_keyframes,
    get_video_duration,
    get_video_fps, # Ensure this is correctly imported
    FfmpegProcess
)
from app_config import OUTPUT_FORMATS, TEMP_DIR_NAME # Ensure these are here


class VideoProberWorker(QThread):
    """Worker thread for ffprobe operations (duration, keyframes, fps)."""
    info_ready = pyqtSignal(dict)
    duration_ready = pyqtSignal(float)
    fps_ready = pyqtSignal(float) # <--- THIS IS THE CRUCIAL LINE
    keyframes_ready = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, filepath: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.filepath = filepath

    def run(self):
        try:
            video_info = get_video_info(self.filepath)
            if not video_info:
                self.error.emit(f"Could not probe video information for: {os.path.basename(self.filepath)}")
                return

            self.info_ready.emit(video_info)

            duration = get_video_duration(video_info)
            if duration <= 0:
                # Attempt to get duration from streams if format.duration is invalid
                stream_duration_found = False
                if video_info and "streams" in video_info:
                    max_stream_duration = 0.0
                    for stream in video_info["streams"]:
                        if "duration" in stream:
                            try:
                                stream_dur = float(stream["duration"])
                                if stream_dur > max_stream_duration:
                                    max_stream_duration = stream_dur
                                    stream_duration_found = True
                            except ValueError:
                                continue
                    if stream_duration_found and max_stream_duration > 0:
                        duration = max_stream_duration
                    else:
                        self.error.emit(f"Could not determine video duration or duration is zero for: {os.path.basename(self.filepath)}")
                        return
                else: # No streams info to fallback on
                    self.error.emit(f"Could not determine video duration (no format or stream duration) for: {os.path.basename(self.filepath)}")
                    return
            self.duration_ready.emit(duration)

            fps = get_video_fps(video_info)
            if fps <= 0:
                print(f"Warning: Could not determine valid FPS for {os.path.basename(self.filepath)}. Frame stepping disabled.")
                self.fps_ready.emit(0.0) 
            else:
                self.fps_ready.emit(fps)

            keyframes = get_keyframes(self.filepath)
            self.keyframes_ready.emit(keyframes)

        except Exception as e:
            import traceback # For more detailed error
            print(f"Exception in VideoProberWorker for {self.filepath}:")
            traceback.print_exc()
            self.error.emit(f"Error during video probing: {str(e)}")


class VideoProcessorWorker(QThread):
    """Worker thread for ffmpeg cutting/encoding operations."""
    progress_update = pyqtSignal(int, str)
    segment_processed = pyqtSignal(int, int, str)
    finished = pyqtSignal(str)
    error = pyqtSignal(str)

    def __init__(self, input_filepath: str, output_tasks: List[Dict[str, Any]], parent: Optional[QObject] = None):
        super().__init__(parent)
        self.input_filepath = input_filepath
        self.output_tasks = output_tasks
        self._is_cancelled = False

    def run(self):
        total_tasks = len(self.output_tasks)
        temp_concat_dir = None

        try:
            for i, task_info in enumerate(self.output_tasks):
                if self._is_cancelled:
                    # self.error.emit("Operation cancelled by user.") # Emitting error can be disruptive if it's a normal cancel
                    self.finished.emit("Operation cancelled.") # Or a specific cancelled signal
                    return

                task_type = task_info.get("type", "single_cut")
                output_path = task_info["output_path"]
                output_format_key = task_info["output_format_key"]
                start_time = task_info.get("start_time")
                end_time = task_info.get("end_time")

                format_details = OUTPUT_FORMATS[output_format_key]
                base_ffmpeg_args = format_details["ffmpeg_args"][:] # Use a copy

                current_status_msg = f"Processing segment {i+1} of {total_tasks}: {os.path.basename(output_path)}"
                self.progress_update.emit(0, current_status_msg)

                if task_type == "concat":
                    segments_to_concat = task_info["segments"]
                    final_output_path = output_path 

                    # Ensure temp_concat_dir path is robust
                    # Using a subfolder within the system's temp directory
                    base_temp_dir = tempfile.gettempdir()
                    temp_concat_dir_name = f"{TEMP_DIR_NAME}_{os.getpid()}" # Add PID for uniqueness
                    temp_concat_dir = os.path.join(base_temp_dir, temp_concat_dir_name)
                    
                    os.makedirs(temp_concat_dir, exist_ok=True)
                    
                    temp_files_list_path = os.path.join(temp_concat_dir, "concat_list.txt")
                    temp_segment_files = []

                    for seg_idx, (seg_start, seg_end) in enumerate(segments_to_concat):
                        if self._is_cancelled: raise OperationCancelledError("Cancelled during segment cutting for concat.")
                        
                        seg_duration = seg_end - seg_start
                        temp_ext = os.path.splitext(self.input_filepath)[1] if not format_details["needs_reencode"] else format_details["ext"]
                        # Ensure temp_ext has a leading dot if it's from format_details
                        if temp_ext and not temp_ext.startswith('.'):
                            temp_ext = '.' + temp_ext
                        
                        temp_segment_path = os.path.join(temp_concat_dir, f"segment_{seg_idx}{temp_ext or '.tmp'}") # Fallback extension
                        temp_segment_files.append(temp_segment_path)

                        cmd = ["ffmpeg", "-y", "-i", self.input_filepath]
                        if seg_start is not None: cmd.extend(["-ss", str(seg_start)])
                        if seg_end is not None: cmd.extend(["-to", str(seg_end)])
                        
                        # Make a copy of base_ffmpeg_args to avoid modifying it if it's complex for GIF
                        current_task_ffmpeg_args = base_ffmpeg_args[:]
                        cmd.extend(current_task_ffmpeg_args)
                        cmd.append(temp_segment_path)
                        
                        segment_msg = f"Cutting segment {seg_idx+1}/{len(segments_to_concat)} for concatenation..."
                        
                        # Calculate progress for this sub-task more accurately
                        overall_progress_start_for_cutting = int((i / total_tasks) * 100)
                        progress_span_for_cutting_one_segment = (1.0 / total_tasks) * (1.0 / len(segments_to_concat)) * 50 # 50% for cutting part
                        
                        ffmpeg_process = FfmpegProcess(cmd, total_duration=seg_duration if format_details["needs_reencode"] else None)
                        
                        def seg_progress_callback(percentage, msg):
                            task_progress = int(overall_progress_start_for_cutting + \
                                                (seg_idx * progress_span_for_cutting_one_segment) + \
                                                (percentage/100.0 * progress_span_for_cutting_one_segment))
                            self.progress_update.emit(task_progress, f"Task {i+1}, Segment {seg_idx+1}: {msg}")

                        if not ffmpeg_process.run(progress_callback=seg_progress_callback if format_details["needs_reencode"] else None):
                            raise FfmpegProcessingError(f"Failed to cut segment {seg_idx+1}: {ffmpeg_process.get_error_message()}")
                    
                    with open(temp_files_list_path, "w", encoding='utf-8') as f: # Specify encoding
                        for p in temp_segment_files:
                             # ffmpeg concat demuxer expects 'file' directives with relative paths if running from that dir
                             # or absolute paths. Using absolute paths is safer here.
                             # Need to escape special characters in paths for the concat file list if any.
                             # For simplicity, assume paths are okay, but this is a known ffmpeg pitfall.
                             # Let's use absolute paths and ensure they are quoted if they contain spaces.
                             # However, -safe 0 allows any path. Using relative to a CWD is also an option.
                             # For now, sticking to simple relative name for simplicity if CWD is set for Popen.
                             # Let's use absolute path to be safer for the concat list, ffmpeg -f concat should handle it with -safe 0
                             f.write(f"file '{p.replace(os.sep, '/')}'\n") # Use forward slashes and quote
                    
                    overall_progress_start_for_concat_step = int((i / total_tasks) * 100) + 50 # 50% for concat step

                    concat_cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", temp_files_list_path]
                    
                    current_task_ffmpeg_args_concat = base_ffmpeg_args[:] # Fresh copy for concat step
                    if format_details["is_gif"] and not format_details["needs_reencode"]:
                        gif_args = OUTPUT_FORMATS["GIF (Animated)"]["ffmpeg_args"][:]
                        concat_cmd.extend(gif_args)
                    elif not format_details["needs_reencode"]:
                         concat_cmd.extend(["-c", "copy"])
                    else: 
                        concat_cmd.extend(current_task_ffmpeg_args_concat)

                    concat_cmd.append(final_output_path)

                    # Rough duration for concat re-encode: sum of segment durations.
                    concat_reencode_duration = sum(s[1]-s[0] for s in segments_to_concat) if format_details["needs_reencode"] else None

                    ffmpeg_process_concat = FfmpegProcess(concat_cmd, total_duration=concat_reencode_duration)

                    def concat_progress_callback(percentage, msg):
                         task_progress = int(overall_progress_start_for_concat_step + (percentage/100.0) * (50.0 / total_tasks))
                         self.progress_update.emit(task_progress, f"Task {i+1}, Finalizing: {msg}")

                    if not ffmpeg_process_concat.run(progress_callback=concat_progress_callback if format_details["needs_reencode"] or (format_details["is_gif"] and not format_details["needs_reencode"]) else None):
                        raise FfmpegProcessingError(f"Concatenation failed: {ffmpeg_process_concat.get_error_message()}")

                    self.segment_processed.emit(i + 1, total_tasks, final_output_path)

                else: # single_cut
                    cmd = ["ffmpeg", "-y", "-i", self.input_filepath]
                    if start_time is not None: cmd.extend(["-ss", str(start_time)])
                    if end_time is not None: cmd.extend(["-to", str(end_time)])
                    
                    current_task_ffmpeg_args = base_ffmpeg_args[:]
                    cmd.extend(current_task_ffmpeg_args)
                    cmd.append(output_path)

                    segment_duration = None
                    if start_time is not None and end_time is not None:
                        segment_duration = end_time - start_time
                    elif end_time is not None:
                        segment_duration = end_time
                    
                    overall_progress_start_for_segment = int((i / total_tasks) * 100)
                    progress_span_for_segment = (1.0 / total_tasks) * 100


                    ffmpeg_process = FfmpegProcess(cmd, total_duration=segment_duration if format_details["needs_reencode"] else None)
                    
                    def single_cut_progress_callback(percentage, msg):
                        task_progress = int(overall_progress_start_for_segment + (percentage/100.0 * progress_span_for_segment))
                        self.progress_update.emit(task_progress, f"Task {i+1}/{total_tasks}: {msg}")

                    if not ffmpeg_process.run(progress_callback=single_cut_progress_callback if format_details["needs_reencode"] else None):
                        raise FfmpegProcessingError(f"Processing failed for {os.path.basename(output_path)}: {ffmpeg_process.get_error_message()}")

                    self.segment_processed.emit(i + 1, total_tasks, output_path)


            if total_tasks == 1 and self.output_tasks[0].get("type", "single_cut") != "concat":
                self.finished.emit(self.output_tasks[0]["output_path"])
            elif total_tasks > 0 and self.output_tasks[0].get("type") == "concat":
                 self.finished.emit(self.output_tasks[0]["output_path"])
            else:
                self.finished.emit(f"Successfully processed {total_tasks} segment(s).")

        except OperationCancelledError as oce: # Catch specific cancel error
            self.error.emit(str(oce) if str(oce) else "Operation cancelled.")
        except FfmpegProcessingError as e:
            self.error.emit(str(e))
        except Exception as e:
            import traceback
            print(f"Exception in VideoProcessorWorker for {self.input_filepath}, task {i if 'i' in locals() else -1}:")
            traceback.print_exc()
            self.error.emit(f"An unexpected error occurred in processing: {str(e)}")
        finally:
            if temp_concat_dir and os.path.exists(temp_concat_dir):
                try:
                    shutil.rmtree(temp_concat_dir) # Ensure shutil is imported
                except Exception as e_rm:
                    print(f"Warning: Could not remove temp directory {temp_concat_dir}: {e_rm}")
            # Do not reset _is_cancelled here, the thread instance is finishing.
            # It should be reset if the worker instance is reused, but here it's one-shot.

    def cancel(self):
        self._is_cancelled = True
        # More advanced: if self.ffmpeg_process_handle: self.ffmpeg_process_handle.terminate()
        # For now, relies on checks between ffmpeg calls and within FfmpegProcess if it were to support it.


class FfmpegProcessingError(Exception):
    pass

class OperationCancelledError(Exception):
    pass