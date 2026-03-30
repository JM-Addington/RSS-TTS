// AIDEV-NOTE: Unified provider filter logic. Replaces inline JS in feed_form.html, article_form.html,
// and article_voice_settings.html. Configured via a div with data-provider-select, data-voice-select,
// and data-preset-select attributes. (issue #228)
// AIDEV-NOTE: Provider detection uses startsWith('en-US-') heuristic — fragile if new providers added.
(function() {
'use strict';

function initProviderFilter(configEl) {
    var providerSelector = configEl.getAttribute('data-provider-select');
    var voiceSelector = configEl.getAttribute('data-voice-select');
    var presetSelector = configEl.getAttribute('data-preset-select');

    var providerSelect = providerSelector ? document.querySelector(providerSelector) : null;
    var voiceSelect = voiceSelector ? document.querySelector(voiceSelector) : null;
    var presetSelect = presetSelector ? document.querySelector(presetSelector) : null;

    if (!providerSelect) return;

    // Tag voice options with provider
    if (voiceSelect) {
        Array.from(voiceSelect.options).forEach(function(option) {
            if (option.value) {
                option.dataset.provider = option.value.startsWith('en-US-') ? 'google' : 'openai';
            }
        });
    }

    // Tag preset options with provider (based on voice in label)
    if (presetSelect) {
        Array.from(presetSelect.options).forEach(function(option) {
            if (option.value && option.text) {
                var voiceMatch = option.text.match(/\(([^,]+),/);
                if (voiceMatch) {
                    var voiceId = voiceMatch[1].trim();
                    option.dataset.provider = voiceId.startsWith('en-US-') ? 'google' : 'openai';
                }
            }
        });
    }

    function filterOptions() {
        var selectedProvider = providerSelect.value;

        if (voiceSelect) {
            Array.from(voiceSelect.options).forEach(function(option) {
                if (!option.value) {
                    option.style.display = '';
                } else if (!selectedProvider) {
                    option.style.display = '';
                } else {
                    option.style.display = option.dataset.provider === selectedProvider ? '' : 'none';
                }
            });

            // Reset voice if hidden
            var currentVoice = voiceSelect.options[voiceSelect.selectedIndex];
            if (currentVoice && currentVoice.style.display === 'none') {
                voiceSelect.value = '';
            }
        }

        if (presetSelect) {
            Array.from(presetSelect.options).forEach(function(option) {
                if (!option.value) {
                    option.style.display = '';
                } else if (!selectedProvider) {
                    option.style.display = '';
                } else {
                    option.style.display = option.dataset.provider === selectedProvider ? '' : 'none';
                }
            });

            // Reset preset if hidden
            var currentPreset = presetSelect.options[presetSelect.selectedIndex];
            if (currentPreset && currentPreset.style.display === 'none') {
                presetSelect.value = '';
            }
        }
    }

    providerSelect.addEventListener('change', filterOptions);
    filterOptions();
}

function init() {
    var configs = document.querySelectorAll('[data-provider-filter]');
    configs.forEach(function(configEl) {
        initProviderFilter(configEl);
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

})();
