import logging
import logging.handlers
import os

from core.utils.config import Config

LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL
}

def setup_logging(config: Config):
    """Set up logging based on configuration

    Args:
        config: Config instance
    """
    log_level = LOG_LEVELS.get(config.get_setting("logging", "logging_level").upper(), logging.INFO)
    log_format = config.get_setting("logging", "log_format")
    log_file_path = config.get_setting("logging", "log_file_path")
    max_log_size = config.get_setting("logging", "max_log_size")
    backup_count = config.get_setting("logging", "backup_count")

    formatter = logging.Formatter(log_format)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    log_dir = os.path.dirname(log_file_path)

    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir)

    file_handler = logging.handlers.RotatingFileHandler(
        log_file_path,
        maxBytes=max_log_size,
        backupCount=backup_count
    )
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    logging.info(f"Log file created at {log_file_path}")

    # Add a minimal console handler for critical errors only (optional)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.CRITICAL)
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    class SensitiveDataFilter(logging.Filter):
        def filter(self, record):
            if hasattr(record, 'msg') and isinstance(record.msg, str):
                token = config.get_token() if hasattr(config, 'get_token') else None
                if token:
                    record.msg = record.msg.replace(token, "[REDACTED_TOKEN]")
            return True

    sensitive_filter = SensitiveDataFilter()
    for handler in root_logger.handlers:
        handler.addFilter(sensitive_filter)

    logging.debug("Logging system initialized")
