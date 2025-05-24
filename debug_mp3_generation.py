"""Debug script to check MP3 generation."""

import os
import tempfile
import uuid
from pathlib import Path

from pydub import AudioSegment

# Create a simple MP3 file
silent_audio = AudioSegment.silent(duration=1000)  # 1 second of silence

# Set up a temp folder
temp_dir = Path(tempfile.mkdtemp())
print(f"Created temp directory: {temp_dir}")

# Create a simple MP3 file with the old style (no ID3 tags)
output_file_old = temp_dir / f"old_style_{uuid.uuid4()}.mp3"
silent_audio.export(output_file_old, format="mp3")
print(f"Created old-style MP3: {output_file_old}")
print(f"File exists: {output_file_old.exists()}")
print(f"File size: {os.path.getsize(output_file_old)} bytes")

# Create a new-style MP3 with ID3 tags and 44.1kHz sample rate
output_file_new = temp_dir / f"new_style_{uuid.uuid4()}.mp3"
silent_audio_44k = silent_audio.set_frame_rate(44100)

tags_dict = {
    "title": "Test Article",
    "artist": "Test Feed",
    "album": "Test Feed",
}
export_parameters = ["-id3v2_version", "3", "-write_id3v1", "1"]

silent_audio_44k.export(
    output_file_new,
    format="mp3",
    bitrate="128k",
    tags=tags_dict,
    parameters=export_parameters,
)

print(f"Created new-style MP3: {output_file_new}")
print(f"File exists: {output_file_new.exists()}")
print(f"File size: {os.path.getsize(output_file_new)} bytes")
