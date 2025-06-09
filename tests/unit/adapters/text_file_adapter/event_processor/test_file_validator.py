import os
import pytest
import shutil
import tempfile

from typing import List
from unittest.mock import MagicMock
from src.adapters.text_file_adapter.event_processor.file_validator import FileValidator, SecurityMode

class TestFileValidator:
    """Tests for the FileValidator class"""

    @pytest.fixture
    def setup_test_files(self):
        """Create test files for validation"""
        test_dir = tempfile.mkdtemp()

        small_text_path = os.path.join(test_dir, "small.txt")
        with open(small_text_path, "w", encoding="utf-8") as f:
            f.write("This is a small text file.")

        large_text_path = os.path.join(test_dir, "large.txt")
        with open(large_text_path, "w", encoding="utf-8") as f:
            f.write("This is a line of text.\n" * 50000)  # Large enough to exceed token limits

        binary_path = os.path.join(test_dir, "binary.bin")
        with open(binary_path, "wb") as f:
            f.write(bytes(range(256)))

        py_file_path = os.path.join(test_dir, "script.py")
        with open(py_file_path, "w", encoding="utf-8") as f:
            f.write("print('Hello, world!')")

        exe_file_path = os.path.join(test_dir, "program.exe")
        with open(exe_file_path, "w", encoding="utf-8") as f:
            f.write("Not actually an executable")

        yield {
            "test_dir": test_dir,
            "small_text_path": small_text_path,
            "large_text_path": large_text_path,
            "binary_path": binary_path,
            "py_file_path": py_file_path,
            "exe_file_path": exe_file_path
        }

        shutil.rmtree(test_dir)

    @pytest.fixture
    def mock_config(self):
        """Create a mock config for testing"""
        def _create(max_file_size: int = 1,
                    max_token_count: int = 100,
                    security_mode: SecurityMode = SecurityMode.STRICT,
                    allowed_extensions: List[str] = ["txt", "py", "json"],
                    blocked_extensions: List[str] = ["exe", "bin", "dll"]):
            config = MagicMock()
            config.get_setting.side_effect = lambda section, key: {
                ("adapter", "max_file_size"): max_file_size,
                ("adapter", "max_token_count"): max_token_count,
                ("adapter", "security_mode"): security_mode.value,
                ("adapter", "allowed_extensions"): allowed_extensions,
                ("adapter", "blocked_extensions"): blocked_extensions
            }.get((section, key))
            return config
        return _create

    def test_file_existence_validation(self, setup_test_files, mock_config):
        """Test validation of file existence"""
        config = mock_config()

        # Test with non-existent file
        validator = FileValidator("/path/to/nonexistent/file.txt", config)
        assert validator.validate() is False
        assert any("does not exist" in error for error in validator.errors)

        # Test with directory instead of file
        validator = FileValidator(setup_test_files["test_dir"], config)
        assert validator.validate() is False
        assert any("not a file" in error for error in validator.errors)

        # Test with existing file
        validator = FileValidator(setup_test_files["small_text_path"], config)
        assert validator.validate() is True

    def test_file_type_validation_strict_mode(self, setup_test_files, mock_config):
        """Test validation of file types based on security mode STRICT"""
        config = mock_config()

        # Test with allowed extension in strict mode
        validator = FileValidator(setup_test_files["py_file_path"], config)
        assert validator._validate_file_type_against_policy() is True

        # Test with blocked extension in strict mode
        validator = FileValidator(setup_test_files["exe_file_path"], config)
        assert validator._validate_file_type_against_policy() is False

    def test_file_type_validation_permissive_mode(self, setup_test_files, mock_config):
        """Test validation of file types based on security mode PERMISSIVE"""
        config = mock_config(security_mode=SecurityMode.PERMISSIVE)

        # Allowed extension in permissive mode
        validator = FileValidator(setup_test_files["py_file_path"], config)
        assert validator._validate_file_type_against_policy() is True

        # Non-allowed but not blocked extension in permissive mode
        custom_file_path = os.path.join(setup_test_files["test_dir"], "custom.xyz")
        with open(custom_file_path, "w", encoding="utf-8") as f:
            f.write("Custom file format")

        validator = FileValidator(custom_file_path, config)
        assert validator._validate_file_type_against_policy() is True

        # Blocked extension in permissive mode
        validator = FileValidator(setup_test_files["exe_file_path"], config)
        assert validator._validate_file_type_against_policy() is False

    def test_file_type_validation_unrestricted_mode(self, setup_test_files, mock_config):
        """Test validation of file types based on security mode UNRESTRICTED"""
        config = mock_config(security_mode=SecurityMode.UNRESTRICTED)

        # Even blocked extension should pass in unrestricted mode
        validator = FileValidator(setup_test_files["exe_file_path"], config)
        assert validator._validate_file_type_against_policy() is True

    def test_textual_file_detection(self, setup_test_files, mock_config):
        """Test detection of textual files"""
        config = mock_config()

        # Test with text file
        validator = FileValidator(setup_test_files["small_text_path"], config)
        assert validator._validate_file_is_textual() is True

        # Test with binary file
        validator = FileValidator(setup_test_files["binary_path"], config)
        assert validator._validate_file_is_textual() is False
        assert any("textual" in error for error in validator.errors)

    def test_context_length_validation(self, setup_test_files, mock_config):
        """Test validation of context length for text files"""
        config = mock_config()

        # Test with small text file (under token limit)
        validator = FileValidator(setup_test_files["small_text_path"], config)
        validator.file_size = os.path.getsize(setup_test_files["small_text_path"])
        assert validator._validate_context_length() is True

        # Test with large text file (over token limit)
        validator = FileValidator(setup_test_files["large_text_path"], config)
        validator.file_size = os.path.getsize(setup_test_files["large_text_path"])
        assert validator._validate_context_length() is False
        assert any("token count" in error for error in validator.errors)

    def test_full_validation_flow(self, setup_test_files, mock_config):
        """Test the complete validation flow"""
        config = mock_config()

        # Valid small text file
        validator = FileValidator(setup_test_files["small_text_path"], config)
        assert validator.validate() is True
        assert not validator.errors

        # Binary file (should fail)
        validator = FileValidator(setup_test_files["binary_path"], config)
        assert validator.validate() is False

        # Blocked extension (should fail)
        validator = FileValidator(setup_test_files["exe_file_path"], config)
        assert validator.validate() is False

        # Large text file (should fail token limit)
        validator = FileValidator(setup_test_files["large_text_path"], config)
        assert validator.validate() is False

        # Non-existent file (should fail)
        validator = FileValidator("/path/to/nonexistent/file.txt", config)
        assert validator.validate() is False
