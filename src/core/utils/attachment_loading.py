import os
import json
import logging
import shutil

from typing import Optional, Dict, Any

# Comprehensive file type mapping
EXTENSION_TYPE_MAPPING = {
    "image": ["jpg", "jpeg", "png", "gif", "webp", "bmp", "tiff", "tif", "svg", "heic", "heif"],
    "video": ["mp4", "mov", "avi", "mkv", "wmv", "flv", "webm", "3gp", "m4v", "mpeg", "mpg", "ts"],
    "audio": ["mp3", "wav", "ogg", "flac", "m4a", "aac", "wma", "opus", "aiff"],
    "document": ["pdf", "doc", "docx", "xls", "xlsx", "ppt", "pptx", "odt", "ods", "odp", "txt", "rtf", "csv"],
    "archive": ["zip", "rar", "7z", "tar", "gz", "bz2", "xz", "iso"],
    "code": ["py", "js", "html", "css", "java", "c", "cpp", "h", "php", "rb", "json", "xml", "sql", "sh", "bat"],
    "ebook": ["epub", "mobi", "azw", "azw3", "fb2"],
    "font": ["ttf", "otf", "woff", "woff2", "eot"],
    "3d_model": ["obj", "stl", "fbx", "3ds", "blend"],
    "executable": ["exe", "dll", "app", "msi", "apk", "deb", "rpm"],
    "sticker": ["tgs"]
}

def create_attachment_dir(attachment_dir: str) -> str:
    """Create a directory for an attachment

    Args:
        attachment_dir: Directory for attachments

    Returns:
        Path to the attachment directory

    Raises:
        IOError: If directory creation fails
    """
    try:
        os.makedirs(attachment_dir, exist_ok=True)
    except Exception as e:
        logging.error(f"Error creating attachment directory: {e}")

def get_attachment_type_by_extension(file_extension: Optional[str]) -> str:
    """Determine the specific attachment type based on file extension

    Args:
        file_extension: File extension (without the dot), can be None

    Returns:
        Specific attachment type category
    """
    if not file_extension:
        return "document"

    for type_name, extensions in EXTENSION_TYPE_MAPPING.items():
        if file_extension.lower() in extensions:
            return type_name

    return "document"

def move_attachment(src_path: str, dest_path: str) -> None:
    """Move an attachment from one location to another

    Args:
        src_path: Source path
        dest_path: Destination path
    """
    try:
        shutil.move(src_path, dest_path)
    except Exception as e:
        logging.error(f"Error moving file {src_path}: {e}")

def save_metadata_file(metadata: Dict[str, Any], attachment_dir: str) -> None:
    """Store metadata in a JSON file

    Args:
        metadata: Metadata dictionary
        attachment_dir: Path to the attachment directory

    Raises:
        IOError: If saving metadata fails
    """
    try:
        required_keys = [
            "attachment_id", "attachment_type",
            "filename", "size", "content_type",
            "url", "created_at", "processable"
        ]

        data_copy = metadata.copy()
        existing_keys = list(data_copy.keys())

        for key in existing_keys:
            if key not in required_keys:
                del data_copy[key]

        with open(os.path.join(attachment_dir, f"{metadata['attachment_id']}.json"), "w") as f:
            json.dump(data_copy, f, indent=2, default=str)
    except Exception as e:
        logging.error(f"Error saving attachment metadata: {e}")
        raise IOError(f"Could not save attachment metadata: {e}")
