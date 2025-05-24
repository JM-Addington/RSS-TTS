# Testing RSS-TTS

## Running Tests with Audio Dependency Mocking

The RSS-TTS project uses the `pydub` library for audio processing, which depends on `audioop`/`pyaudioop` modules. These modules might not be available in all environments, which can cause test failures.

We've created a set of test scripts that mock these dependencies to allow running tests without the audio processing libraries installed.

### Available Test Scripts

1. `run_single_test.py` - Run a specific test file
   ```bash
   python run_single_test.py tests/test_models.py
   ```

2. `run_all_tests_with_mock.py` - Run all tests
   ```bash
   python run_all_tests_with_mock.py
   ```

### How It Works

The mocking approach works by:

1. Creating mock versions of `pydub`, `audioop`, and `pyaudioop` modules
2. Adding these mocks to `sys.modules` before any app code is imported
3. Providing mock implementations of the core audio processing functionality

### Mock Implementation Details

The mock implementation is in `tests/conftest_mock.py` and includes:

- A `MockAudioSegment` class that mimics the basic functionality of `pydub.AudioSegment`
- Mock implementations of audio file loading and exporting
- Mock implementations of audio combining operations

### Running Tests in Docker

When running tests in Docker, make sure the necessary audio processing libraries are installed:

```bash
# In your Dockerfile
RUN apt-get update && apt-get install -y ffmpeg
```

### Test Coverage

The test suite includes 78 tests covering:

- Core model functionality
- Article processing and chunking
- Audio file generation and management
- URL content extraction and processing
- Error handling and recovery
- Project structure and configuration

### Notes

- One test is skipped: `test_process_article_server_error_with_retry` because it requires complex mocking of Celery's retry mechanism
- All other tests pass with the mocking approach

## Manual Test Requirements

For full manual testing, ensure:

1. FFmpeg is installed for audio processing
2. Redis is running for Celery task queueing
3. OpenAI API key is configured for TTS functionality
4. Podcast client for testing RSS feed compatibility
