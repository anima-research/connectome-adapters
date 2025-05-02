import logging
import os

from enum import Enum
from core.utils.config import Config

class SecurityMode(str, Enum):
    """Security modes supported by the FileValidator"""
    STRICT = "strict"
    PERMISSIVE = "permissive"
    UNRESTRICTED = "unrestricted"

class FileValidator:
    """Validator for file operations, handling size limits, token limits, and file type restrictions"""

    def __init__(self, file_path: str, config: Config):
        """Initialize the file validator

        Args:
            file_path: Path to the file
            config: Configuration object
        """
        self.config = config
        self.max_file_size = self.config.get_setting("adapter", "max_file_size") * 1024 * 1024
        self.max_token_count = self.config.get_setting("adapter", "max_token_count")
        self.security_mode = self.config.get_setting("adapter", "security_mode")
        self.allowed_extensions = self.config.get_setting("adapter", "allowed_extensions")
        self.blocked_extensions = self.config.get_setting("adapter", "blocked_extensions")
        self.file_path = file_path
        self.extension = os.path.splitext(self.file_path)[-1].lower().strip(".")
        self.file_size = None
        self.errors = []

    def validate(self) -> bool:
        """Validate a file for reading operations

        Returns:
            True if the file is valid, False otherwise
        """
        try:
            if not self._validate_file_existence():
                return False
            if not self._validate_file_type_against_policy():
                return False
            if not self._validate_file_is_textual():
                return False

            self.file_size = os.stat(self.file_path).st_size
            if self.file_size > self.max_file_size:
                self.errors.append(f"File size {self.file_size}B exceeds limit for files.")
                return False

            return self._validate_context_length()
        except Exception as e:
            self.errors.append(f"Error validating file: {e}")
            return False

    def _validate_file_existence(self) -> bool:
        """Validate the existence of a file

        Returns:
            True if the file exists and is a file, False otherwise
        """
        if not os.path.exists(self.file_path):
            self.errors.append(f"File does not exist: {self.file_path}")
            return False

        if not os.path.isfile(self.file_path):
            self.errors.append(f"Path is not a file: {self.file_path}")
            return False

        return True

    def _validate_file_type_against_policy(self) -> bool:
        """Validate the type of a file

        Returns:
            True if the file is among the allowed file types, False otherwise
        """
        if self.security_mode == SecurityMode.UNRESTRICTED:
            return True
        if self.security_mode == SecurityMode.PERMISSIVE:
            return self.extension not in self.blocked_extensions
        return self.extension in self.allowed_extensions

    def _validate_file_is_textual(self) -> bool:
        """Check if a file is textual

        Returns:
            True if the file appears to be textual, False otherwise
        """
        try:
            with open(self.file_path, "r", encoding="utf-8") as file:
                file.read(1024)  # Try reading as text
            return True
        except UnicodeDecodeError:
            self.errors.append(f"File is not textual: {self.file_path}")
            return False

    def _validate_context_length(self) -> bool:
        """Check if the context length is within the limit

        Returns:
            True if the context length is within the limit, False otherwise
        """
        chars_per_token = 4
        estimated_tokens = 0

        with open(self.file_path, "r", encoding="utf-8") as f:
            sample = f.read(10000)

            if sample:
                sample_ratio = min(1, self.file_size / len(sample.encode("utf-8")))
                estimated_tokens = int(len(sample) / chars_per_token * sample_ratio)
            else:
                estimated_tokens = int(self.file_size / chars_per_token)

        if not estimated_tokens <= self.max_token_count:
            self.errors.append(
                f"Estimated token count ({estimated_tokens}) exceeds limit."
            )
            return False

        return True
