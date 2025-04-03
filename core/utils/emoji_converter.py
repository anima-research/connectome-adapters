import csv
import emoji
import os
import logging

from typing import Optional
from core.utils.config import Config

class EmojiConverter:
    """Singleton class for handling emoji name conversions.

    This class provides methods to convert emoji names between platform-specific
    and python emoji library formats. It uses a CSV file to map emoji names from one
    format to another. The file should contain only those emoji names that differ from
    the python emoji library names.
    """

    _instance = None

    @classmethod
    def get_instance(cls, config: Optional[Config] = None):
        """Get or create the singleton instance

        Args:
            config: Configuration object (only used during first initialization)

        Returns:
            The singleton EmojiConverter instance
        """
        if cls._instance is None:
            cls._instance = cls(config)
        return cls._instance

    def __init__(self, config: Config):
        """Initialize the emoji converter

        Args:
            config: Configuration object
        """
        self.config = config
        self._emoji_to_standard = {}
        self._standard_to_emoji = {}
        self._platform_specific_to_standard = {}
        self._standard_to_platform_specific = {}

        self._add_emoji_to_standardized_mappings()
        self._add_standardized_to_platform_specific_mappings()

    def _add_emoji_to_standardized_mappings(self) -> None:
        """Add standardized mappings for emoji library names"""
        for _, v in emoji.EMOJI_DATA.items():
            emoji_name = v["en"].strip(":")
            standardized_name = emoji_name.lower().replace("-", "_")
            self._emoji_to_standard[emoji_name] = standardized_name
            self._standard_to_emoji[standardized_name] = emoji_name

    def _add_standardized_to_platform_specific_mappings(self) -> None:
        """Add platform specific mappings for standardized emoji names"""
        try:
            file_path = self.config.get_setting("adapter", "emoji_mappings")

            if os.path.exists(file_path):
                with open(file_path, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)

                    for row in reader:
                        platform_specific_name = row["platform_specific_name"]
                        standard_name = row["standard_name"]

                        self._platform_specific_to_standard[platform_specific_name] = standard_name
                        self._standard_to_platform_specific[standard_name] = platform_specific_name
        except Exception as e:
            logging.error(f"Error loading emoji mappings: {e}")

    def platform_specific_to_standard(self, emoji_name: str) -> str:
        """Convert platform specific emoji name to emoji library name

        Args:
            emoji_name: Platform specific emoji name

        Returns:
            emoji library name
        """
        standard_name = self._platform_specific_to_standard.get(emoji_name, emoji_name)

        return self._standard_to_emoji.get(standard_name, standard_name)

    def standard_to_platform_specific(self, emoji_name: str) -> str:
        """Convert emoji library name to platform specific name

        Args:
            emoji_name: emoji library name

        Returns:
            Platform specific emoji name
        """
        standard_name =self._emoji_to_standard.get(emoji_name, emoji_name)

        return self._standard_to_platform_specific.get(standard_name, standard_name)
