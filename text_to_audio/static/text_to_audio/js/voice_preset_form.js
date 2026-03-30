// AIDEV-NOTE: Extracted from voice_preset_form.html. Config passed via #js-config data-* attrs.
(function() {
'use strict';

document.addEventListener('DOMContentLoaded', function() {
    const configEl = document.getElementById('js-config');
    if (!configEl) return;

    const testUrl = configEl.dataset.testUrl;
    const voiceIdFieldId = configEl.dataset.voiceIdField;
    const speedFieldId = configEl.dataset.speedField;
    const promptFieldId = configEl.dataset.promptField;

    const testVoiceBtn = document.getElementById('testVoiceBtn');
    const testBtnText = document.getElementById('testBtnText');
    const testBtnSpinner = document.getElementById('testBtnSpinner');
    const audioPlayer = document.getElementById('audioPlayer');
    const audioElement = document.getElementById('audioElement');
    const testErrorMessage = document.getElementById('testErrorMessage');
    const testText = document.getElementById('testText');

    console.log('Elements found:', {
        testVoiceBtn: !!testVoiceBtn,
        audioPlayer: !!audioPlayer,
        audioElement: !!audioElement,
        testText: !!testText
    });

    const voiceIdField = document.getElementById(voiceIdFieldId);
    const speedField = document.getElementById(speedFieldId);
    const promptField = promptFieldId ? document.getElementById(promptFieldId) : null;

    console.log('Form elements found:', {
        voiceIdField: !!voiceIdField,
        speedField: !!speedField,
        promptField: !!promptField
    });

    if (!testVoiceBtn || !voiceIdField || !speedField || !testText || !audioPlayer) {
        console.error('Required elements not found');
        return;
    }

    testVoiceBtn.addEventListener('click', function(e) {
        e.preventDefault();
        e.stopPropagation();
        console.log('Test voice button clicked');
        const voiceId = voiceIdField.value;
        const speed = speedField.value;
        const text = testText.value.trim();
        const prompt = promptField ? promptField.value.trim() : '';

        console.log('Form values:', { voiceId, speed, textLength: text.length, promptLength: prompt.length });

        if (!voiceId || !speed || !text) {
            console.log('Validation failed');
            testErrorMessage.textContent = 'Please fill in voice, speed, and sample text fields.';
            testErrorMessage.classList.remove('d-none');
            return;
        }

        // Show loading state
        testVoiceBtn.disabled = true;
        testBtnText.innerHTML = '<i class="bi bi-clock"></i> Generating...';
        testBtnSpinner.classList.remove('d-none');
        audioPlayer.classList.add('d-none');
        testErrorMessage.classList.add('d-none');

        // Prepare form data
        const formData = new FormData();
        formData.append('voice_id', voiceId);
        formData.append('speed', speed);
        formData.append('text', text);
        formData.append('prompt', prompt);
        formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);

        fetch(testUrl, {
            method: 'POST',
            body: formData,
            headers: {
                'X-Requested-With': 'XMLHttpRequest'
            }
        })
        .then(response => {
            console.log('Response status:', response.status);
            console.log('Response content-type:', response.headers.get('content-type'));

            if (response.ok && response.headers.get('content-type') === 'audio/mpeg') {
                return response.blob();
            } else if (response.status === 400) {
                return response.text().then(text => {
                    throw new Error(text);
                });
            } else {
                console.error('Unexpected response:', response.status, response.headers.get('content-type'));
                throw new Error('Failed to generate voice sample');
            }
        })
        .then(blob => {
            console.log('Audio blob received:', blob.size, 'bytes');
            console.log('Blob type:', blob.type);

            if (audioElement.src && audioElement.src.startsWith('blob:')) {
                URL.revokeObjectURL(audioElement.src);
                audioElement.src = '';
            }

            const audioUrl = URL.createObjectURL(blob);
            console.log('Audio URL created:', audioUrl);

            audioElement.addEventListener('error', function(e) {
                console.error('Audio loading error:', e);
                console.error('Audio element error details:', audioElement.error);
                testErrorMessage.textContent = 'Error loading audio. Please try again.';
                testErrorMessage.classList.remove('d-none');
                URL.revokeObjectURL(audioUrl);
            }, { once: true });

            audioElement.addEventListener('loadeddata', function() {
                console.log('Audio loaded successfully');
            }, { once: true });

            audioElement.addEventListener('canplay', function() {
                console.log('Audio can play - starting playback');
                audioElement.play().catch(error => {
                    console.log('Auto-play failed (browser policy):', error);
                });
            }, { once: true });

            audioElement.src = audioUrl;
            audioPlayer.classList.remove('d-none');
            console.log('Audio player shown');

            audioElement.addEventListener('ended', function() {
                URL.revokeObjectURL(audioUrl);
            }, { once: true });
        })
        .catch(error => {
            console.error('Error:', error);
            testErrorMessage.textContent = error.message || 'Error generating voice sample. Please try again.';
            testErrorMessage.classList.remove('d-none');
        })
        .finally(() => {
            testVoiceBtn.disabled = false;
            testBtnText.innerHTML = '<i class="bi bi-play-circle"></i> Test Voice';
            testBtnSpinner.classList.add('d-none');
        });
    });

    // Auto-test when voice or speed changes (with debouncing)
    let autoTestTimeout;
    function scheduleAutoTest() {
        clearTimeout(autoTestTimeout);
        autoTestTimeout = setTimeout(() => {
            if (voiceIdField.value && speedField.value && testText.value.trim()) {
                testVoiceBtn.click();
            }
        }, 1000);
    }

    voiceIdField.addEventListener('change', scheduleAutoTest);
    speedField.addEventListener('input', scheduleAutoTest);
    if (promptField) {
        promptField.addEventListener('input', scheduleAutoTest);
    }
});

})();
