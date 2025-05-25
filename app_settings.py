# lossless_video_cutter/app_settings.py
from PyQt6.QtCore import QSettings, QStandardPaths
import os

from app_config import (
    SETTING_LAST_INPUT_DIR,
    SETTING_LAST_OUTPUT_DIR,
    SETTING_LAST_OUTPUT_FORMAT
)

class AppSettings:
    def __init__(self, organization_name: str = "MyCompany", application_name: str = "LosslessVideoCutter"):
        self.settings = QSettings(organization_name, application_name)

    def get_last_input_dir(self) -> str:
        default_dir = QStandardPaths.standardLocations(QStandardPaths.StandardLocation.MoviesLocation)[0]
        return self.settings.value(SETTING_LAST_INPUT_DIR, default_dir, type=str)

    def set_last_input_dir(self, directory: str) -> None:
        self.settings.setValue(SETTING_LAST_INPUT_DIR, directory)

    def get_last_output_dir(self) -> str:
        default_dir = QStandardPaths.standardLocations(QStandardPaths.StandardLocation.MoviesLocation)[0]
        return self.settings.value(SETTING_LAST_OUTPUT_DIR, default_dir, type=str)

    def set_last_output_dir(self, directory: str) -> None:
        self.settings.setValue(SETTING_LAST_OUTPUT_DIR, directory)

    def get_last_output_format(self) -> str:
        # Default to the first key in OUTPUT_FORMATS
        from app_config import OUTPUT_FORMATS
        default_format = list(OUTPUT_FORMATS.keys())[0]
        return self.settings.value(SETTING_LAST_OUTPUT_FORMAT, default_format, type=str)

    def set_last_output_format(self, format_name: str) -> None:
        self.settings.setValue(SETTING_LAST_OUTPUT_FORMAT, format_name)