# Testing RSS-TTS

## Conditional Audio Dependency Mocking

The RSS-TTS project includes a sophisticated conditional mocking system that automatically handles audio dependencies (`pydub`, `audioop`/`pyaudioop`). The system can use either real audio libraries when available or provide mocked versions for environments where they're not installed.

### Benefits

- **Automatic Detection**: Detects available audio libraries and uses them when possible
- **Graceful Fallback**: Automatically uses mocks when real libraries aren't available
- **Explicit Control**: Environment variable override for forcing specific behavior
- **CI/CD Friendly**: Works seamlessly in environments without FFmpeg/audio libraries
- **Development Flexibility**: Choose between real and mocked audio processing

### Available Test Scripts

1. `run_single_test.py` - Run a specific test file
   ```bash
   # Uses mocks by default (backwards compatibility)
   python run_single_test.py tests/test_models.py

   # Force use of real audio libraries
   MOCK_AUDIO_DEPENDENCIES=false python run_single_test.py tests/test_models.py
   ```

2. `run_all_tests_with_mock.py` - Run all tests with mocking explicitly enabled
   ```bash
   python run_all_tests_with_mock.py
   ```

3. Standard pytest - Use conditional mocking with pytest directly
   ```bash
   # Auto-detect dependencies (uses real libraries if available)
   python -m pytest tests/

   # Force mocking
   MOCK_AUDIO_DEPENDENCIES=true python -m pytest tests/

   # Force real libraries (fails if not available)
   MOCK_AUDIO_DEPENDENCIES=false python -m pytest tests/
   ```

### How Conditional Mocking Works

The conditional mocking system:

1. **Environment Check**: Reads `MOCK_AUDIO_DEPENDENCIES` environment variable
2. **Dependency Detection**: Automatically detects if real audio libraries are available
3. **Conditional Application**: Only applies mocks when needed (explicit request or missing dependencies)
4. **Pytest Integration**: Uses `pytest_configure` and `pytest_unconfigure` for clean setup/teardown
5. **Backwards Compatibility**: Existing test scripts continue to work without changes

### Mock Implementation Details

The enhanced mock implementation in `tests/conftest_mock.py` includes:

- **`MockAudioSegment`**: Comprehensive mock of `pydub.AudioSegment` with enhanced functionality
- **`apply_audio_mocks()`**: Conditional function to apply mocks only when needed
- **`remove_audio_mocks()`**: Clean teardown function for proper test isolation
- **`check_audio_dependencies()`**: Automatic detection of available audio libraries
- **Pytest hooks**: `pytest_configure`/`pytest_unconfigure` for automatic management

### Environment Variable Control

- **`MOCK_AUDIO_DEPENDENCIES=true`**: Force audio mocking regardless of available libraries
- **`MOCK_AUDIO_DEPENDENCIES=false`**: Use real audio libraries (test fails if not available)
- **Unset/other values**: Auto-detect and use real libraries when available, fallback to mocks

### Testing the Mocking System

Verify the conditional mocking works correctly:

```bash
# Test the mocking system functionality
python test_audio_mocking.py
```

This verification script tests:
- ✅ Mocking works when explicitly enabled
- ✅ Real libraries work when available and mocking is disabled
- ✅ Automatic fallback functions correctly

### Running Tests in Docker

When running tests in Docker, make sure the necessary audio processing libraries are installed:

```bash
# In your Dockerfile
RUN apt-get update && apt-get install -y ffmpeg
```

### Test Coverage

The test suite includes 78+ tests covering:

- Core model functionality
- Article processing and chunking
- Audio file generation and management
- URL content extraction and processing
- Error handling and recovery
- Project structure and configuration
- **Article deletion safety** - Protection against accidental directory deletion

#### Article Deletion Safety Tests

The `tests/test_article_deletion_safety.py` module contains comprehensive tests for safe audio file deletion:

**Core Safety Features:**
- Directory protection: Prevents deletion of directories (raises AssertionError)
- File extension validation: Only allows deletion of audio files (.mp3, .wav, .m4a, .ogg, .flac, .aac)
- Path validation: Ensures paths are not None, empty, or whitespace-only
- Symlink handling: Safely handles symlinks to files but blocks symlinks to directories

**Edge Case Handling:**
- Non-existent files (returns False gracefully)
- Permission errors (logs warning, returns False)
- Integration with ArticleDeleteView to ensure view-level safety

**Implementation Details:**
The `safe_delete_audio_file()` function in `utils.py` includes multiple assertion checks:
```python
assert not os.path.isdir(file_path), f"Cannot delete directory: {file_path}"
assert file_extension in valid_audio_extensions, "Only audio files can be deleted"
```

These safety measures ensure that even if there's a bug in path resolution logic, the deletion function will never accidentally remove directories or non-audio files.

### Notes

- One test is skipped: `test_process_article_server_error_with_retry` because it requires complex mocking of Celery's retry mechanism
- All other tests pass with the mocking approach

## Manual Test Requirements

For full manual testing, ensure:

1. FFmpeg is installed for audio processing
2. Redis is running for Celery task queueing
3. OpenAI API key is configured for TTS functionality
4. Podcast client for testing RSS feed compatibility
