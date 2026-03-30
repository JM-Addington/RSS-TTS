// AIDEV-NOTE: Unified clipboard copy utility. Replaces inline JS in feed_list.html and copy functions in article_list.js.
// Uses data-clipboard-target attribute on buttons to find the input element to copy from.
(function() {
'use strict';

/**
 * Copy text from an input element to clipboard with visual feedback on the button.
 * Uses navigator.clipboard.writeText() with document.execCommand('copy') fallback.
 */
function copyToClipboard(inputEl, buttonEl) {
    var text = inputEl.value;

    function onSuccess() {
        var originalHTML = buttonEl.innerHTML;
        buttonEl.innerHTML = '<i class="bi bi-check"></i> Copied!';
        buttonEl.classList.remove('btn-outline-secondary');
        buttonEl.classList.add('btn-success');

        setTimeout(function() {
            buttonEl.innerHTML = originalHTML;
            buttonEl.classList.remove('btn-success');
            buttonEl.classList.add('btn-outline-secondary');
        }, 2000);
    }

    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(onSuccess).catch(function() {
            fallbackCopy(inputEl, onSuccess);
        });
    } else {
        fallbackCopy(inputEl, onSuccess);
    }
}

function fallbackCopy(inputEl, onSuccess) {
    inputEl.select();
    inputEl.setSelectionRange(0, 99999);
    try {
        document.execCommand('copy');
        onSuccess();
    } catch (err) {
        console.error('Failed to copy text: ', err);
    }
}

function handleClick(event) {
    var button = event.currentTarget;
    var targetId = button.getAttribute('data-clipboard-target');
    if (!targetId) return;
    var inputEl = document.getElementById(targetId);
    if (!inputEl) return;
    copyToClipboard(inputEl, button);
}

function init() {
    var buttons = document.querySelectorAll('[data-clipboard-target]');
    buttons.forEach(function(btn) {
        btn.addEventListener('click', handleClick);
    });
}

// Initialize on DOMContentLoaded or immediately if DOM is already ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

})();
