# lossless_video_cutter/main.py
import sys
import os
from typing import List, Tuple, Optional, Dict, Any

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QFileDialog, QProgressBar, QComboBox,
    QRadioButton, QButtonGroup, QMessageBox, QStatusBar, QSlider,
    QStyle, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QDir, QTimer, QStandardPaths, QUrl
# --- Ensure QCloseEvent and other QtGui elements are imported ---
from PyQt6.QtGui import (
    QIcon, QPalette, QColor, QDragEnterEvent, QDropEvent, 
    QShortcut, QKeySequence, QKeyEvent, QCloseEvent # <--- ADDED QCloseEvent HERE
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtMultimediaWidgets import QVideoWidget


from app_config import (
    SUPPORTED_INPUT_FORMATS_FILTER, SUPPORTED_INPUT_EXTENSIONS,
    OUTPUT_FORMATS, TIMELINE_HEIGHT
)
from app_settings import AppSettings
from ffmpeg_utils import check_ffmpeg_tools, get_video_dimensions
from worker_threads import VideoProberWorker, VideoProcessorWorker
from ui_timeline import TimelineWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Lossless Video Cutter")
        self.setGeometry(100, 100, 900, 750)
        self.setAcceptDrops(True)

        self.settings = AppSettings()

        self.current_video_path: Optional[str] = None
        self.video_info: Optional[Dict[str, Any]] = None
        self.video_duration: float = 0.0
        self.video_fps: float = 0.0 
        self.keyframes: List[float] = []
        self.selections: List[Tuple[float, float]] = []
        self.current_selection_start: Optional[float] = None

        self.prober_worker: Optional[VideoProberWorker] = None
        self.processor_worker: Optional[VideoProcessorWorker] = None

        self.media_player: Optional[QMediaPlayer] = None
        self.audio_output: Optional[QAudioOutput] = None
        self.video_widget: Optional[QVideoWidget] = None
        self._player_is_seeking: bool = False
        self._frame_step_buttons_enabled: bool = False

        self._init_ui()
        self._init_media_player()
        self._connect_signals()
        self.update_ui_state()

        if not check_ffmpeg_tools():
            QMessageBox.critical(
                self, "Error",
                "ffmpeg and ffprobe not found in PATH. Please install them and ensure they are accessible."
            )
            QTimer.singleShot(0, self.close)


    def _init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)

        file_layout = QHBoxLayout()
        self.add_file_button = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton), " Add File...")
        file_layout.addWidget(self.add_file_button)
        self.loaded_file_label = QLabel("No video loaded.")
        self.loaded_file_label.setWordWrap(True)
        file_layout.addWidget(self.loaded_file_label, 1)
        main_layout.addLayout(file_layout)

        self.video_widget = QVideoWidget()
        self.video_widget.setMinimumHeight(300)
        self.video_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        
        pal = self.video_widget.palette()
        pal.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.black)
        self.video_widget.setPalette(pal)
        self.video_widget.setAutoFillBackground(True)
        main_layout.addWidget(self.video_widget)

        playback_controls_layout = QHBoxLayout()
        self.play_pause_button = QPushButton()
        self.play_pause_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))
        self.play_pause_button.setToolTip("Play/Pause (Spacebar)")
        playback_controls_layout.addWidget(self.play_pause_button)
        playback_controls_layout.addStretch()
        main_layout.addLayout(playback_controls_layout)

        self.playhead_slider = QSlider(Qt.Orientation.Horizontal)
        self.playhead_slider.setRange(0, 1000)
        self.playhead_slider.setEnabled(False)
        main_layout.addWidget(self.playhead_slider)

        self.current_time_label = QLabel("00:00.000 / 00:00.000")
        main_layout.addWidget(self.current_time_label, alignment=Qt.AlignmentFlag.AlignRight)
        
        self.timeline_widget = TimelineWidget()
        main_layout.addWidget(self.timeline_widget)

        selection_layout = QHBoxLayout()
        self.begin_selection_button = QPushButton("Begin Selection (B)")
        self.end_selection_button = QPushButton("End Selection (E)")
        self.undo_selection_button = QPushButton("Undo/Clear Selection (U)")
        
        selection_layout.addWidget(self.begin_selection_button)
        selection_layout.addWidget(self.end_selection_button)
        selection_layout.addWidget(self.undo_selection_button)
        main_layout.addLayout(selection_layout)

        output_options_layout = QHBoxLayout()
        output_options_layout.addWidget(QLabel("Output Format:"))
        self.output_format_combo = QComboBox()
        self.output_format_combo.addItems(OUTPUT_FORMATS.keys())
        last_format = self.settings.get_last_output_format()
        if last_format in OUTPUT_FORMATS:
            self.output_format_combo.setCurrentText(last_format)
        output_options_layout.addWidget(self.output_format_combo)
        main_layout.addLayout(output_options_layout)

        save_actions_layout = QHBoxLayout()
        self.save_action_group = QButtonGroup(self)
        self.save_keep_selections_radio = QRadioButton("Save (Keep Selections)")
        self.save_remove_selections_radio = QRadioButton("Save (Remove Selections)")
        self.split_by_selections_radio = QRadioButton("Split by Selections + Save")
        self.split_by_tags_radio = QRadioButton("Split by Tags + Save")

        self.save_action_group.addButton(self.save_keep_selections_radio, 0)
        self.save_action_group.addButton(self.save_remove_selections_radio, 1)
        self.save_action_group.addButton(self.split_by_selections_radio, 2)
        self.save_action_group.addButton(self.split_by_tags_radio, 3)
        
        self.save_keep_selections_radio.setChecked(True)

        save_actions_layout.addWidget(self.save_keep_selections_radio)
        save_actions_layout.addWidget(self.save_remove_selections_radio)
        save_actions_layout.addWidget(self.split_by_selections_radio)
        save_actions_layout.addWidget(self.split_by_tags_radio)
        main_layout.addLayout(save_actions_layout)

        self.save_video_button = QPushButton(self.style().standardIcon(QStyle.StandardPixmap.SP_DialogSaveButton)," Save Video (Ctrl+S)")
        main_layout.addWidget(self.save_video_button)

        self.progress_bar = QProgressBar()
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setValue(0)
        main_layout.addWidget(self.progress_bar)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready.")


    def _init_media_player(self):
        self.media_player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.media_player.setAudioOutput(self.audio_output)
        if self.video_widget:
             self.media_player.setVideoOutput(self.video_widget)

        self.media_player.positionChanged.connect(self.on_media_player_position_changed)
        self.media_player.playbackStateChanged.connect(self.on_media_player_playback_state_changed)
        self.media_player.errorOccurred.connect(self.on_media_player_error)


    def _connect_signals(self):
        self.add_file_button.clicked.connect(self.open_file_dialog)
        
        self.playhead_slider.sliderMoved.connect(self.on_playhead_slider_scrubbed) 
        self.playhead_slider.sliderReleased.connect(self.on_playhead_slider_released) 
        self.playhead_slider.actionTriggered.connect(self.on_playhead_slider_action_triggered)

        self.timeline_widget.playhead_pos_changed_by_click.connect(self.on_timeline_clicked_playhead_change)
        self.timeline_widget.keyframe_tag_clicked.connect(self.on_keyframe_tag_clicked)

        self.begin_selection_button.clicked.connect(self.on_begin_selection)
        self.end_selection_button.clicked.connect(self.on_end_selection)
        self.undo_selection_button.clicked.connect(self.on_undo_selection)

        self.output_format_combo.currentTextChanged.connect(self.on_output_format_changed)
        self.save_video_button.clicked.connect(self.on_save_video)

        if self.play_pause_button:
            self.play_pause_button.clicked.connect(self.toggle_play_pause)

        for radio_button in self.save_action_group.buttons():
            radio_button.toggled.connect(self.update_ui_state)

        QShortcut(QKeySequence("Ctrl+O"), self, self.open_file_dialog)
        QShortcut(QKeySequence("Ctrl+S"), self, self.on_save_video)
        QShortcut(QKeySequence("B"), self, self.on_begin_selection)
        QShortcut(QKeySequence("E"), self, self.on_end_selection)
        QShortcut(QKeySequence("U"), self, self.on_undo_selection)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self, self.on_undo_current_selection_if_playhead_inside)
        QShortcut(QKeySequence(Qt.Key.Key_Space), self, self.toggle_play_pause)

    def format_time(self, time_sec: float, show_ms: bool = True) -> str:
        ms = int((time_sec * 1000) % 1000)
        seconds_total = int(time_sec)
        s = seconds_total % 60
        m = (seconds_total // 60) % 60
        h = seconds_total // 3600
        if show_ms:
            if h > 0: return f"{h:02}:{m:02}:{s:02}.{ms:03d}"
            return f"{m:02}:{s:02}.{ms:03d}"
        else:
            if h > 0: return f"{h:02}:{m:02}:{s:02}"
            return f"{m:02}:{s:02}"

    def update_current_time_display(self, current_t_sec: Optional[float] = None):
        if current_t_sec is None:
            if self.media_player and self.media_player.source().isValid() and self.video_duration > 0:
                 current_t_sec = self.media_player.position() / 1000.0
            else:
                 current_t_sec = self.playhead_slider.value() / 1000.0
        
        current_t_sec = max(0.0, min(current_t_sec, self.video_duration if self.video_duration > 0 else 0.0))

        total_t_str = self.format_time(self.video_duration) 
        current_t_str = self.format_time(current_t_sec)
        self.current_time_label.setText(f"{current_t_str} / {total_t_str}")
        
        self.timeline_widget.set_current_playhead_time(current_t_sec)

    def update_ui_state(self):
        has_video = bool(self.current_video_path and self.video_duration > 0)
        has_valid_fps = has_video and self.video_fps > 0
        is_processing = (self.prober_worker is not None and self.prober_worker.isRunning()) or \
                         (self.processor_worker is not None and self.processor_worker.isRunning())
        
        self._frame_step_buttons_enabled = has_valid_fps and not is_processing

        self.add_file_button.setEnabled(not is_processing)
        self.playhead_slider.setEnabled(has_video and not is_processing)
        self.timeline_widget.setEnabled(has_video and not is_processing)
        if self.play_pause_button:
            self.play_pause_button.setEnabled(has_video and not is_processing)

        self.begin_selection_button.setEnabled(has_video and not is_processing)
        self.end_selection_button.setEnabled(has_video and not is_processing and self.current_selection_start is not None)
        self.undo_selection_button.setEnabled(has_video and not is_processing and (bool(self.selections) or self.current_selection_start is not None))

        self.output_format_combo.setEnabled(has_video and not is_processing)
        
        has_selections = bool(self.selections)
        has_selected_tags = bool(self.timeline_widget.get_selected_keyframes())

        self.save_keep_selections_radio.setEnabled(has_video and not is_processing and has_selections)
        self.save_remove_selections_radio.setEnabled(has_video and not is_processing and has_selections) 
        self.split_by_selections_radio.setEnabled(has_video and not is_processing and has_selections)
        self.split_by_tags_radio.setEnabled(has_video and not is_processing and has_selected_tags)
        
        can_save = False
        if has_video and not is_processing:
            save_action_id = self.save_action_group.checkedId()
            if save_action_id == 0 and has_selections: 
                can_save = True
            elif save_action_id == 1 and has_selections: 
                can_save = True
            elif save_action_id == 2 and has_selections: 
                can_save = True
            elif save_action_id == 3 and has_selected_tags: 
                can_save = True
        self.save_video_button.setEnabled(can_save)

        if self.current_selection_start is not None:
            self.begin_selection_button.setText("Cancel Current Selection")
            self.begin_selection_button.setStyleSheet("background-color: #FFA07A;") 
        else:
            self.begin_selection_button.setText("Begin Selection (B)")
            self.begin_selection_button.setStyleSheet("")
        
        if self.media_player and self.play_pause_button:
            if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
                self.play_pause_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPause))
            else:
                self.play_pause_button.setIcon(self.style().standardIcon(QStyle.StandardPixmap.SP_MediaPlay))


    def open_file_dialog(self):
        last_dir = self.settings.get_last_input_dir()
        filepath, _ = QFileDialog.getOpenFileName(
            self, "Open Video File", last_dir, SUPPORTED_INPUT_FORMATS_FILTER
        )
        if filepath:
            self.settings.set_last_input_dir(QDir(filepath).absolutePath())
            self.load_video(filepath)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if urls and urls[0].isLocalFile():
                filepath = urls[0].toLocalFile()
                ext = os.path.splitext(filepath)[1].lower()
                if ext in SUPPORTED_INPUT_EXTENSIONS:
                    event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            filepath = urls[0].toLocalFile()
            self.load_video(filepath)

    def load_video(self, filepath: str):
        if self.processor_worker and self.processor_worker.isRunning():
            QMessageBox.warning(self, "Busy", "Cannot load a new video while another is processing.")
            return
        if self.prober_worker and self.prober_worker.isRunning():
            QMessageBox.information(self, "Busy", "Video is currently being loaded.")
            return

        self.reset_video_state() 
        self.current_video_path = filepath
        
        if self.media_player:
            self.media_player.setSource(QUrl.fromLocalFile(filepath))

        self.loaded_file_label.setText(f"Loading: {os.path.basename(filepath)}...")
        self.status_bar.showMessage(f"Probing video: {os.path.basename(filepath)}...")
        self.progress_bar.setRange(0,0)

        self.prober_worker = VideoProberWorker(filepath)
        self.prober_worker.info_ready.connect(self.on_video_info_ready)
        self.prober_worker.duration_ready.connect(self.on_duration_ready)
        self.prober_worker.fps_ready.connect(self.on_fps_ready)
        self.prober_worker.keyframes_ready.connect(self.on_keyframes_ready)
        self.prober_worker.error.connect(self.on_probing_error)
        self.prober_worker.finished.connect(self.on_probing_finished)
        self.prober_worker.start()
        self.update_ui_state()

    def reset_video_state(self):
        self.current_video_path = None
        self.video_info = None
        self.video_duration = 0.0 
        self.video_fps = 0.0
        self.keyframes = []
        self.selections = []
        self.current_selection_start = None
        
        if self.media_player:
            self.media_player.stop() 
            self.media_player.setSource(QUrl())

        self.loaded_file_label.setText("No video loaded.")
        self.playhead_slider.setValue(0)
        self.playhead_slider.setRange(0, 1000) 
        self.timeline_widget.set_duration(0)
        self.timeline_widget.set_keyframes([])
        self.timeline_widget.set_selections([])
        self.timeline_widget.clear_selected_keyframes()
        self.update_current_time_display(0.0) 
        self.progress_bar.setValue(0)
        self.progress_bar.setRange(0,100)
        self.update_ui_state()

    def on_video_info_ready(self, video_info: Dict[str, Any]):
        self.video_info = video_info

    def on_duration_ready(self, duration: float):
        self.video_duration = duration 
        slider_max_ms = int(duration * 1000)
        self.playhead_slider.setRange(0, slider_max_ms if slider_max_ms > 0 else 1000)
        
        self.timeline_widget.set_duration(duration)
        self.update_current_time_display(0.0) 
        self.loaded_file_label.setText(f"Loaded: {os.path.basename(self.current_video_path or '')} ({self.format_time(duration, False)})")
        self.status_bar.showMessage("Video duration loaded. Detecting keyframes...")
        
        if self.media_player and (not self.media_player.source().isValid() or self.media_player.source().toLocalFile() != self.current_video_path) and self.current_video_path:
             self.media_player.setSource(QUrl.fromLocalFile(self.current_video_path))
             self.media_player.pause() 

    def on_fps_ready(self, fps: float):
        self.video_fps = fps
        if fps > 0:
            self.status_bar.showMessage(f"Video FPS: {fps:.2f}. Frame stepping enabled.", 3000)
        else:
            self.status_bar.showMessage("Could not determine FPS. Frame stepping disabled.", 3000)
        self.update_ui_state()

    def on_keyframes_ready(self, keyframes: List[float]):
        self.keyframes = keyframes
        self.timeline_widget.set_keyframes(keyframes)
        self.status_bar.showMessage(f"Video loaded: {os.path.basename(self.current_video_path or '')}. Found {len(keyframes)} keyframes.", 5000)

    def on_probing_error(self, error_msg: str):
        QMessageBox.critical(self, "Video Load Error", error_msg)
        self.reset_video_state()
        self.prober_worker = None

    def on_probing_finished(self):
        self.progress_bar.setRange(0,100) 
        self.progress_bar.setValue(0)
        if self.prober_worker: 
            self.prober_worker = None 
        self.update_ui_state()
    
    def on_keyframe_tag_clicked(self, kf_time: float):
        if not self.timeline_widget: return

        if self.timeline_widget.toggle_keyframe_selection(kf_time):
            if kf_time in self.timeline_widget.get_selected_keyframes():
                self.status_bar.showMessage(f"Keyframe at {self.format_time(kf_time)} selected for splitting.", 3000)
            else:
                self.status_bar.showMessage(f"Keyframe at {self.format_time(kf_time)} deselected.", 3000)
        self.update_ui_state()

    def on_media_player_position_changed(self, position_ms: int):
        if not self._player_is_seeking and not self.playhead_slider.isSliderDown():
            self.playhead_slider.blockSignals(True)
            self.playhead_slider.setValue(position_ms)
            self.playhead_slider.blockSignals(False)
            self.update_current_time_display(position_ms / 1000.0)

    def on_media_player_playback_state_changed(self, state: QMediaPlayer.PlaybackState):
        self.update_ui_state()

    def on_media_player_error(self, error: QMediaPlayer.Error, error_string: str):
        if error != QMediaPlayer.Error.NoError:
            if self.media_player and self.media_player.source().isValid():
                print(f"Media Player Error: {error} ({error.name}) - {error_string}")
                self.status_bar.showMessage(f"Media player error: {error_string}", 5000)

    def _seek_media_player(self, position_ms: int):
        if self.media_player and self.media_player.isSeekable() and self.video_duration > 0:
            clamped_pos_ms = max(0, min(position_ms, int(self.video_duration * 1000)))
            self._player_is_seeking = True
            self.media_player.setPosition(clamped_pos_ms)
            self.update_current_time_display(clamped_pos_ms / 1000.0)
        else:
            clamped_pos_ms = max(0, min(position_ms, int(self.video_duration * 1000 if self.video_duration > 0 else 0)))
            self.update_current_time_display(clamped_pos_ms / 1000.0)


    def on_playhead_slider_scrubbed(self, value_ms: int):
        self._seek_media_player(value_ms)

    def on_playhead_slider_released(self):
        self._player_is_seeking = False 

    def on_playhead_slider_action_triggered(self, action):
        if not self.playhead_slider.isSliderDown():
            value_ms = self.playhead_slider.value()
            self._seek_media_player(value_ms)
            QTimer.singleShot(100, lambda: setattr(self, '_player_is_seeking', False))


    def on_timeline_clicked_playhead_change(self, time_sec: float):
        value_ms = int(time_sec * 1000)
        self.playhead_slider.blockSignals(True) 
        self.playhead_slider.setValue(value_ms)
        self.playhead_slider.blockSignals(False)
        self._seek_media_player(value_ms)
        QTimer.singleShot(100, lambda: setattr(self, '_player_is_seeking', False))

    def step_frame(self, direction: int):
        if not self.media_player or not self.media_player.source().isValid() or self.video_fps <= 0:
            return

        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()

        time_per_frame_ms = (1.0 / self.video_fps) * 1000.0
        current_pos_ms = self.media_player.position() 
        
        new_pos_ms = current_pos_ms + (direction * time_per_frame_ms)
        
        duration_ms = 0
        if self.media_player.duration() > 0 :
            duration_ms = self.media_player.duration()
        elif self.video_duration > 0 : 
            duration_ms = int(self.video_duration * 1000)
        
        if duration_ms > 0:
            new_pos_ms = max(0, min(new_pos_ms, duration_ms))
        else:
            new_pos_ms = max(0, new_pos_ms)
        
        self._seek_media_player(int(round(new_pos_ms)))


    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        
        if self._frame_step_buttons_enabled:
            if key == Qt.Key.Key_Right:
                self.step_frame(1)
                event.accept()
                return
            elif key == Qt.Key.Key_Left:
                self.step_frame(-1)
                event.accept()
                return
        
        super().keyPressEvent(event)


    def toggle_play_pause(self):
        if not self.media_player or not self.current_video_path or not self.media_player.source().isValid():
            return
        if self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        else:
            current_pos_ms = self.media_player.position()
            duration_ms = self.media_player.duration()
            if duration_ms > 0 and current_pos_ms >= duration_ms - 100 : 
                self.media_player.setPosition(0)
            self.media_player.play()
        self.update_ui_state() 

    def _get_current_playhead_time_sec(self) -> float:
        if self.media_player and self.media_player.source().isValid() and self.video_duration > 0:
            if self.playhead_slider.isSliderDown():
                return self.playhead_slider.value() / 1000.0
            return self.media_player.position() / 1000.0
        return self.playhead_slider.value() / 1000.0

    def on_begin_selection(self):
        if self.current_selection_start is not None: 
            self.current_selection_start = None
            self.status_bar.showMessage("Selection start cancelled.", 3000)
        else:
            self.current_selection_start = self._get_current_playhead_time_sec()
            self.status_bar.showMessage(f"Selection started at: {self.format_time(self.current_selection_start)}", 3000)
        self.update_ui_state()

    def on_end_selection(self):
        if self.current_selection_start is None:
            return 
        
        end_time = self._get_current_playhead_time_sec()
        start_time = self.current_selection_start

        if end_time <= start_time + 0.01:
            QMessageBox.warning(self, "Invalid Selection", "End time must be after start time.")
            return
        
        new_selection = (start_time, end_time)
        self.selections.append(new_selection)
        self.selections.sort()

        self.timeline_widget.set_selections(self.selections)
        self.status_bar.showMessage(f"Segment selected: {self.format_time(start_time)} - {self.format_time(end_time)}", 3000)
        
        self.current_selection_start = None 
        self.update_ui_state()

    def on_undo_selection(self):
        current_time = self._get_current_playhead_time_sec()
        removed_specific = False

        for i, (start, end) in enumerate(self.selections):
            if start <= current_time <= end:
                del self.selections[i]
                removed_specific = True
                self.status_bar.showMessage(f"Selection {self.format_time(start)}-{self.format_time(end)} removed.", 3000)
                break
        
        if not removed_specific:
            if self.selections:
                self.selections.clear()
                self.status_bar.showMessage("All selections cleared.", 3000)
            elif self.current_selection_start is not None:
                 self.current_selection_start = None
                 self.status_bar.showMessage("Current selection start cancelled.", 3000)
            else:
                self.status_bar.showMessage("No selections to clear.", 3000)
        
        self.timeline_widget.set_selections(self.selections)
        self.update_ui_state()

    def on_undo_current_selection_if_playhead_inside(self):
        current_time = self._get_current_playhead_time_sec()
        for i, (start, end) in enumerate(self.selections):
            if start <= current_time <= end:
                del self.selections[i]
                self.status_bar.showMessage(f"Selection {self.format_time(start)}-{self.format_time(end)} removed.", 3000)
                self.timeline_widget.set_selections(self.selections)
                self.update_ui_state()
                return

    def on_output_format_changed(self, format_name: str):
        self.settings.set_last_output_format(format_name)

    def _get_segments_to_keep_for_removal(self) -> List[Tuple[float, float]]:
        if not self.selections or self.video_duration <= 0:
            return [] if not self.selections else [(0, self.video_duration)] 
        
        sorted_removed_selections = sorted(self.selections, key=lambda x: x[0])
        
        segments_to_keep: List[Tuple[float, float]] = []
        current_pos = 0.0
        min_segment_duration = 0.05

        for remove_start, remove_end in sorted_removed_selections:
            remove_start = max(0.0, min(remove_start, self.video_duration))
            remove_end = max(0.0, min(remove_end, self.video_duration))

            if remove_start > current_pos:
                segment_duration = remove_start - current_pos
                if segment_duration >= min_segment_duration:
                    segments_to_keep.append((current_pos, remove_start))
            current_pos = max(current_pos, remove_end)

        if current_pos < self.video_duration:
            segment_duration = self.video_duration - current_pos
            if segment_duration >= min_segment_duration:
                segments_to_keep.append((current_pos, self.video_duration))
        
        return segments_to_keep


    def on_save_video(self):
        if self.media_player and self.media_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.media_player.pause()
        
        if not self.current_video_path: return

        output_format_key = self.output_format_combo.currentText()
        output_format_details = OUTPUT_FORMATS[output_format_key]
        
        default_ext = output_format_details["ext"]
        if default_ext is None: 
            _, default_ext = os.path.splitext(self.current_video_path)

        output_tasks: List[Dict[str, Any]] = []
        save_action_id = self.save_action_group.checkedId()

        base_output_filename = os.path.splitext(os.path.basename(self.current_video_path))[0]
        last_output_dir = self.settings.get_last_output_dir()

        segments_for_concat: List[Tuple[float, float]] = []
        if save_action_id == 0: 
            if not self.selections:
                QMessageBox.information(self, "No Selections", "Please make at least one selection to save.")
                return
            segments_for_concat = sorted(self.selections)
        elif save_action_id == 1: 
            if not self.selections:
                segments_for_concat = [(0, self.video_duration)]
                if self.video_duration <=0:
                    QMessageBox.warning(self, "Warning", "No video duration. Cannot process.")
                    return
            else:
                segments_for_concat = self._get_segments_to_keep_for_removal()
                if not segments_for_concat:
                    QMessageBox.information(self, "Nothing to Save", "After removing selections, no video content remains.")
                    return

        if save_action_id == 0 or save_action_id == 1:
            filename_suffix = "_edited" if save_action_id == 0 else "_cleaned"
            default_save_path = os.path.join(last_output_dir, f"{base_output_filename}{filename_suffix}{default_ext}")
            output_filepath, _ = QFileDialog.getSaveFileName(
                self, "Save Processed Video As", default_save_path, f"Video Files (*{default_ext});;All Files (*)"
            )
            if not output_filepath: return
            self.settings.set_last_output_dir(QDir(output_filepath).absolutePath())

            task = {
                "type": "concat",
                "output_path": output_filepath,
                "output_format_key": output_format_key,
                "segments": segments_for_concat
            }
            if output_format_details["is_gif"] and self.video_info:
                w, _ = get_video_dimensions(self.video_info)
                task["gif_scale_w"] = min(w if w > 0 else 480, 480)
            output_tasks.append(task)

        elif save_action_id == 2: 
            if not self.selections:
                QMessageBox.information(self, "No Selections", "Please make at least one selection to split.")
                return
            
            output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory", last_output_dir)
            if not output_dir: return
            self.settings.set_last_output_dir(output_dir)

            for i, (start_t, end_t) in enumerate(self.selections):
                part_filename = f"{base_output_filename}_part_{i+1}{default_ext}"
                task = {
                    "type": "single_cut",
                    "output_path": os.path.join(output_dir, part_filename),
                    "output_format_key": output_format_key,
                    "start_time": start_t,
                    "end_time": end_t
                }
                if output_format_details["is_gif"] and self.video_info:
                    w, _ = get_video_dimensions(self.video_info)
                    task["gif_scale_w"] = min(w if w > 0 else 480, 480)
                output_tasks.append(task)
        
        elif save_action_id == 3: 
            selected_tags = sorted(self.timeline_widget.get_selected_keyframes())
            if not selected_tags:
                QMessageBox.information(self, "No Tags Selected", "Please select keyframe tags to split by.")
                return

            output_dir = QFileDialog.getExistingDirectory(self, "Select Output Directory", last_output_dir)
            if not output_dir: return
            self.settings.set_last_output_dir(output_dir)

            split_points = [0.0] + selected_tags + [self.video_duration]
            split_points = sorted(list(set(p for p in split_points if p <= self.video_duration + 0.001)))

            processed_segments_count = 0
            for i in range(len(split_points) - 1):
                start_t = split_points[i]
                end_t = split_points[i+1]
                
                start_t = max(0.0, min(start_t, self.video_duration))
                end_t = max(0.0, min(end_t, self.video_duration))

                if end_t - start_t < 0.05: continue
                
                processed_segments_count += 1
                part_filename = f"{base_output_filename}_tag_split_{processed_segments_count}{default_ext}"
                task = {
                    "type": "single_cut",
                    "output_path": os.path.join(output_dir, part_filename),
                    "output_format_key": output_format_key,
                    "start_time": start_t,
                    "end_time": end_t
                }
                if output_format_details["is_gif"] and self.video_info:
                    w, _ = get_video_dimensions(self.video_info)
                    task["gif_scale_w"] = min(w if w > 0 else 480, 480)
                output_tasks.append(task)

        if not output_tasks:
            self.status_bar.showMessage("No tasks to perform based on current settings.", 3000)
            return

        self.progress_bar.setValue(0)
        self.status_bar.showMessage("Starting video processing...")
        if not self.current_video_path:
            QMessageBox.critical(self, "Error", "Internal error: No input video path for processing.")
            return
            
        self.processor_worker = VideoProcessorWorker(self.current_video_path, output_tasks)
        self.processor_worker.progress_update.connect(self.on_processing_progress)
        self.processor_worker.segment_processed.connect(self.on_processing_segment_done)
        self.processor_worker.finished.connect(self.on_processing_finished)
        self.processor_worker.error.connect(self.on_processing_error)
        self.processor_worker.start()
        self.update_ui_state()


    def on_processing_progress(self, percentage: int, message: str):
        self.progress_bar.setValue(percentage)
        self.status_bar.showMessage(message)

    def on_processing_segment_done(self, current_segment: int, total_segments: int, output_path: str):
        progress = int((current_segment / total_segments) * 100)
        self.progress_bar.setValue(progress)
        self.status_bar.showMessage(f"Segment {current_segment}/{total_segments} finished: {os.path.basename(output_path)}")

    def on_processing_finished(self, success_message: str):
        self.progress_bar.setValue(100)
        QMessageBox.information(self, "Processing Complete", success_message)
        self.status_bar.showMessage(f"Operation complete: {success_message}", 5000)
        self.processor_worker = None 
        self.update_ui_state() 

    def on_processing_error(self, error_msg: str):
        QMessageBox.critical(self, "Processing Error", error_msg)
        self.status_bar.showMessage(f"Error during processing: {error_msg}", 10000)
        self.processor_worker = None 
        self.update_ui_state() 

    def closeEvent(self, event: QCloseEvent): # QCloseEvent for type hint
        if self.media_player: 
            self.media_player.stop()

        if self.processor_worker and self.processor_worker.isRunning():
            reply = QMessageBox.question(self, 'Confirm Exit',
                                         "A video processing task is currently running. Are you sure you want to exit? The current task will be cancelled.",
                                         QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                self.processor_worker.cancel()
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


if __name__ == '__main__':
    app = QApplication(sys.argv)
    main_win = MainWindow()
    main_win.show()
    sys.exit(app.exec())