# lossless_video_cutter/ui_timeline.py
from PyQt6.QtWidgets import QWidget, QSizePolicy
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from typing import List, Tuple, Set, Optional

from app_config import (
    TIMELINE_HEIGHT, TIMELINE_MARKER_COLOR, TIMELINE_KEYFRAME_COLOR,
    TIMELINE_SELECTED_KEYFRAME_COLOR, TIMELINE_SELECTION_COLOR,
    TIMELINE_PLAYHEAD_COLOR
)

class TimelineWidget(QWidget):
    playhead_pos_changed_by_click = pyqtSignal(float)  # Emits time in seconds
    keyframe_tag_clicked = pyqtSignal(float) # Emits keyframe time

    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.setMinimumHeight(TIMELINE_HEIGHT)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        self._duration: float = 0.0  # Total duration in seconds
        self._keyframes: List[float] = []
        self._selected_keyframes: Set[float] = set()
        self._selections: List[Tuple[float, float]] = [] # List of (start_time, end_time)
        self._current_playhead_time: float = 0.0

        self._font = QFont("Arial", 8)
        self._keyframe_marker_height = 15
        self._tag_clickable_radius = 5 # pixels

    def set_duration(self, duration: float):
        self._duration = max(0.0, duration)
        self.update()

    def set_keyframes(self, keyframes: List[float]):
        self._keyframes = sorted(keyframes)
        self.update()

    def set_selections(self, selections: List[Tuple[float, float]]):
        self._selections = selections
        self.update()
    
    def toggle_keyframe_selection(self, time_sec: float):
        # Find the closest keyframe to time_sec within a small tolerance
        closest_kf = None
        min_diff = float('inf')
        for kf_time in self._keyframes:
            diff = abs(kf_time - time_sec)
            if diff < 0.1: # Tolerance for clicking near a keyframe
                if diff < min_diff:
                    min_diff = diff
                    closest_kf = kf_time
        
        if closest_kf is not None:
            if closest_kf in self._selected_keyframes:
                self._selected_keyframes.remove(closest_kf)
            else:
                self._selected_keyframes.add(closest_kf)
            self.update()
            return True
        return False

    def get_selected_keyframes(self) -> List[float]:
        return sorted(list(self._selected_keyframes))

    def clear_selected_keyframes(self):
        self._selected_keyframes.clear()
        self.update()

    def set_current_playhead_time(self, time_sec: float):
        self._current_playhead_time = max(0.0, min(time_sec, self._duration))
        self.update()

    def _time_to_x(self, time_sec: float) -> float:
        if self._duration == 0:
            return 0
        return (time_sec / self._duration) * self.width()

    def _x_to_time(self, x_pos: float) -> float:
        if self.width() == 0:
            return 0
        return (x_pos / self.width()) * self._duration

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Background
        painter.fillRect(self.rect(), QColor("#303030"))

        if self._duration == 0:
            painter.setPen(QColor(TIMELINE_MARKER_COLOR))
            painter.setFont(self._font)
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Load a video file")
            return

        # Draw time ruler and ticks
        self._draw_ruler(painter)

        # Draw selections
        for start_time, end_time in self._selections:
            x_start = self._time_to_x(start_time)
            x_end = self._time_to_x(end_time)
            selection_rect = QRectF(x_start, 0, x_end - x_start, self.height() * 0.7) # Upper part for selections
            painter.fillRect(selection_rect, QColor(TIMELINE_SELECTION_COLOR))

        # Draw keyframes
        keyframe_pen = QPen(QColor(TIMELINE_KEYFRAME_COLOR))
        keyframe_pen.setWidth(1)
        selected_keyframe_pen = QPen(QColor(TIMELINE_SELECTED_KEYFRAME_COLOR))
        selected_keyframe_pen.setWidth(2) # Thicker for selected

        for kf_time in self._keyframes:
            x_kf = self._time_to_x(kf_time)
            if kf_time in self._selected_keyframes:
                painter.setPen(selected_keyframe_pen)
                painter.setBrush(QColor(TIMELINE_SELECTED_KEYFRAME_COLOR))
                # Draw a small circle or different marker for selected keyframes
                painter.drawEllipse(QPointF(x_kf, self.height() - self._keyframe_marker_height - 5), 3, 3)

            else:
                painter.setPen(keyframe_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)

            painter.drawLine(QPointF(x_kf, self.height() - self._keyframe_marker_height),
                             QPointF(x_kf, self.height()))


        # Draw playhead
        x_playhead = self._time_to_x(self._current_playhead_time)
        playhead_pen = QPen(QColor(TIMELINE_PLAYHEAD_COLOR))
        playhead_pen.setWidth(2)
        painter.setPen(playhead_pen)
        painter.drawLine(QPointF(x_playhead, 0), QPointF(x_playhead, self.height()))
        
        # Draw playhead time label near playhead
        fm = QFontMetrics(self._font)
        time_str = self.format_time(self._current_playhead_time)
        text_width = fm.horizontalAdvance(time_str)
        text_x = x_playhead + 5
        if text_x + text_width > self.width():
            text_x = x_playhead - text_width - 5
        text_y = fm.ascent() + 2 # Top of timeline
        painter.setPen(QColor(TIMELINE_MARKER_COLOR))
        painter.setFont(self._font)
        painter.drawText(QPointF(text_x, text_y), time_str)


    def _draw_ruler(self, painter: QPainter):
        painter.setFont(self._font)
        fm = QFontMetrics(self._font)
        
        # Determine tick interval based on duration and width
        # Aim for a reasonable number of labels
        num_major_ticks_ideal = self.width() / 80 # approx one label every 80px
        
        if self._duration <= 0: return

        if self._duration <= 10: # seconds
            major_tick_interval = 1.0
            minor_tick_interval = 0.2
        elif self._duration <= 60: # 1 minute
            major_tick_interval = 5.0
            minor_tick_interval = 1.0
        elif self._duration <= 300: # 5 minutes
            major_tick_interval = 30.0
            minor_tick_interval = 5.0
        elif self._duration <= 1800: # 30 minutes
            major_tick_interval = 60.0 * 2 # 2 minutes
            minor_tick_interval = 30.0
        elif self._duration <= 3600 * 2: # 2 hours
            major_tick_interval = 60.0 * 10 # 10 minutes
            minor_tick_interval = 60.0 * 2 # 2 minutes
        else: # Very long
            major_tick_interval = 60.0 * 30 # 30 minutes
            minor_tick_interval = 60.0 * 5  # 5 minutes
        
        # Minor ticks
        painter.setPen(QColor(TIMELINE_MARKER_COLOR).darker(120))
        num_minor_ticks = int(self._duration / minor_tick_interval)
        for i in range(num_minor_ticks + 1):
            time_sec = i * minor_tick_interval
            x = self._time_to_x(time_sec)
            painter.drawLine(QPointF(x, self.height() * 0.85), QPointF(x, self.height()))

        # Major ticks and labels
        painter.setPen(QColor(TIMELINE_MARKER_COLOR))
        num_major_ticks = int(self._duration / major_tick_interval)
        last_label_end_x = -1

        for i in range(num_major_ticks + 1):
            time_sec = i * major_tick_interval
            x = self._time_to_x(time_sec)
            painter.drawLine(QPointF(x, self.height() * 0.7), QPointF(x, self.height()))

            time_str = self.format_time(time_sec)
            text_width = fm.horizontalAdvance(time_str)
            
            label_x = x - text_width / 2
            # Prevent label overlap
            if label_x > last_label_end_x + 5 and label_x + text_width < self.width() -5 :
                painter.drawText(QPointF(label_x, self.height() * 0.7 - fm.descent()), time_str)
                last_label_end_x = label_x + text_width

    def format_time(self, time_sec: float) -> str:
        ms = int((time_sec * 1000) % 1000)
        seconds_total = int(time_sec)
        s = seconds_total % 60
        m = (seconds_total // 60) % 60
        h = seconds_total // 3600
        if h > 0:
            return f"{h:02}:{m:02}:{s:02}.{ms:03d}"
        else:
            return f"{m:02}:{s:02}.{ms:03d}"

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            clicked_time = self._x_to_time(event.position().x())
            
            # Check if a keyframe tag was clicked
            for kf_time in self._keyframes:
                x_kf = self._time_to_x(kf_time)
                # Check distance from click to keyframe marker visual representation
                # A simple check: if click x is close to keyframe x, and y is in the lower part
                if abs(event.position().x() - x_kf) < self._tag_clickable_radius and \
                   event.position().y() > self.height() - self._keyframe_marker_height - self._tag_clickable_radius * 2: # Check y pos too
                    self.keyframe_tag_clicked.emit(kf_time)
                    return # Handled by keyframe click

            # If not a keyframe click, treat as playhead position change
            self.playhead_pos_changed_by_click.emit(clicked_time)

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton:
            # If dragging, update playhead
            clicked_time = self._x_to_time(event.position().x())
            self.playhead_pos_changed_by_click.emit(clicked_time)