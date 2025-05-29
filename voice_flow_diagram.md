# Voice Processing Flow in RSS-TTS

## Voice Selection and Processing Flow Diagram

```mermaid
graph TD
    A[User Interface] --> |Select voice in forms| B[Form Handlers]
    B --> |Save to model| C[Article Model]
    C --> |Process article task| D[Celery Worker]

    %% Voice Configuration Decision Path
    D --> E[VoiceConfigurationService]
    E --> |configure_article_voice| F{Voice Mode?}
    F --> |single_custom| G[Apply Feed's Default Voice Preset]
    F --> |auto| H[Generate AI Voice Parameters]
    F --> |single_default| I[Use Default Tone-Based Voice]

    %% User Preset Path
    J[User Creates Voice Preset] --> K[UserVoicePreset Model]
    K --> G

    %% User Preferences Path
    L[User Sets Preferences] --> M[UserVoiceProfile Model]
    M --> N[UserPreferencesService]

    %% Applying Voices
    G --> O[Voice & Voice ID Fields]
    H --> O
    I --> O

    %% TTS Processing
    O --> P[Article Processing Task]
    P --> Q{Multi-Voice Available?}
    Q --> |Yes| R[Generate Multi-Voice Audio]
    Q --> |No| S[Fallback to Single Voice]

    %% Voice Priority Selection
    S --> T{Select Voice Priority}
    T --> |Highest| U[article.voice]
    U --> |Fallback| V[article.voice_parameters.voice_id]
    V --> |Fallback| W[article.voice_id]
    W --> |Fallback| X[Default "alloy"]

    %% Final Audio Generation
    R --> Y[OpenAI TTS API]
    X --> Y
    Y --> Z[Final MP3]

    %% Feed Configuration
    AA[Feed Settings] --> AB{Set Voice Mode}
    AB --> F

    %% Article-specific Configuration
    AC[Article Voice Settings] --> AD[UserPreferencesService]
    AD --> |save_article_preferences| O
```

## Voice Flow Description

1. **User Interface Layer**
   - Users select voices via forms: ArticleSubmissionForm, ArticleVoiceForm, UserVoicePreferenceForm, VoicePresetForm
   - Voice can be selected directly or via a preset
   - Forms include validation to prevent selecting both preset and individual settings

2. **Data Storage Layer**
   - Article model stores voice settings: `voice` (original), `voice_id` (newer explicit field)
   - UserVoicePreset model stores reusable voice configurations
   - UserVoiceProfile stores user's default voice preferences
   - Feed model defines voice mode and optional default voice preset

3. **Voice Configuration Process**
   - VoiceConfigurationService.configure_article_voice determines settings based on feed preferences
   - Three voice modes:
     - single_default: Use tone-based voice mapping
     - single_custom: Use feed's default voice preset
     - auto: Generate AI-driven voice parameters

4. **Voice Selection Priority**
   1. Article-specific settings (highest priority):
      - article.voice field (direct choice)
      - article.voice_preset (if set, overrides individual settings)
   2. Feed's default voice preset (if in single_custom mode)
   3. User's voice preferences (from UserVoiceProfile)
   4. AI-recommended voice parameters (if in auto mode)
   5. Default mappings based on tone (lowest priority)

5. **TTS Processing Flow**
   - Celery worker processes article text
   - First attempts multi-voice processing with different voices per segment
   - Falls back to single voice if multi-voice fails
   - When using single voice, checks fields in this order:
     1. article.voice
     2. article.voice_parameters.voice_id
     3. article.voice_id
     4. Default "alloy"

6. **Audio Generation and Storage**
   - Uses OpenAI TTS API for audio generation
   - Applies voice parameters as instructions for richer voice styling
   - Generated audio files are stored in the media/articles directory
   - Files are served through Caddy for compatibility with Apple Podcasts
