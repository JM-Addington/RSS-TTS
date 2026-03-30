// AIDEV-NOTE: Extracted from article_list.html inline script. Dynamic data passed via #js-config data-* attrs.
(function() {
'use strict';

// Read config from DOM element populated by Django template
const configEl = document.getElementById('js-config');
if (!configEl) {
    // No config element means we're on the "all articles" page without a feed context
    // Only set up basic clipboard and play button functionality
    setupClipboard();
    document.addEventListener('DOMContentLoaded', function() {
        attachPlayButtonListeners();
        attachRegenerateButtonListeners();
        setupAudioPlayer();
        setupMutationObserver();
    });
    return;
}

const csrfToken = configEl.dataset.csrfToken;
// Strip placeholder UUID/IDs from URL templates so we can append real values
const mediaUrlTemplate = configEl.dataset.mediaUrl
    .replace('00000000-0000-0000-0000-000000000000/', '');
const voiceSettingsUrlTemplate = configEl.dataset.voiceSettingsUrl
    .replace('/0/', '/');
const regenerateUrlTemplate = configEl.dataset.regenerateUrl
    .replace('/0/', '/');
const deleteUrlTemplate = configEl.dataset.deleteUrl || '';
const articleStatusUrl = configEl.dataset.statusUrl || '';
const feedId = configEl.dataset.feedId;

// Helper function to safely escape HTML for use in attributes
function escapeHtml(unsafe) {
    if (unsafe === undefined || unsafe === null) return '';
    return unsafe
        .toString()
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

// Create reusable SVG templates
const playIconSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-play-circle" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/><path d="M6.271 5.055a.5.5 0 0 1 .52.038l3.5 2.5a.5.5 0 0 1 0 .814l-3.5 2.5A.5.5 0 0 1 6 10.5v-5a.5.5 0 0 1 .271-.445z"/></svg> Play';
const pauseIconSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-pause-circle" viewBox="0 0 16 16" aria-hidden="true"><path d="M8 15A7 7 0 1 1 8 1a7 7 0 0 1 0 14zm0 1A8 8 0 1 0 8 0a8 8 0 0 0 0 16z"/><path d="M5 6.25a1.25 1.25 0 1 1 2.5 0v3.5a1.25 1.25 0 1 1-2.5 0v-3.5zm3.5 0a1.25 1.25 0 1 1 2.5 0v3.5a1.25 1.25 0 1 1-2.5 0v-3.5z"/></svg> Pause';
const regenerateIconSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-arrow-clockwise" viewBox="0 0 16 16" aria-hidden="true"><path fill-rule="evenodd" d="M8 3a5 5 0 1 0 4.546 2.914.5.5 0 0 1 .908-.417A6 6 0 1 1 8 2v1z"/><path d="M8 4.466V.534a.25.25 0 0 1 .41-.192l2.36 1.966c.12.1.12.284 0 .384L8.41 4.658A.25.25 0 0 1 8 4.466z"/></svg>';
const spinnerIconSvg = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span>';

// URL construction functions
function getMediaUrl(audioUuid) {
    return mediaUrlTemplate + audioUuid + '/';
}

function getVoiceSettingsUrl(articleId) {
    return voiceSettingsUrlTemplate + articleId + '/';
}

function getRegenerateUrl(articleId) {
    return regenerateUrlTemplate + articleId + '/';
}

function getDeleteUrl(articleId) {
    return deleteUrlTemplate.replace('/articles/0/', '/articles/' + articleId + '/');
}

// Function to generate complete article actions HTML
function generateArticleActionsHTML(article) {
    return `
        <a href="${getMediaUrl(article.audio_uuid)}" class="btn btn-primary btn-sm">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-download" viewBox="0 0 16 16" aria-hidden="true">
                <path d="M.5 9.9a.5.5 0 0 1 .5.5v2.5a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-2.5a.5.5 0 0 1 1 0v2.5a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2v-2.5a.5.5 0 0 1 .5-.5z"/>
                <path d="M7.646 11.854a.5.5 0 0 0 .708 0l3-3a.5.5 0 0 0-.708-.708L8.5 10.293V1.5a.5.5 0 0 0-1 0v8.793L5.354 8.146a.5.5 0 1 0-.708.708l3 3z"/>
            </svg>
            Download MP3
        </a>
        <button type="button" class="btn btn-success btn-sm play-audio-btn" data-audio-url="${getMediaUrl(article.audio_uuid)}" data-article-id="${article.id}" data-article-title="${escapeHtml(article.title)}">
            ${playIconSvg}
        </button>
        <a href="${getVoiceSettingsUrl(article.id)}" class="btn btn-info btn-sm">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-mic" viewBox="0 0 16 16" aria-hidden="true">
                <path d="M3.5 6.5A.5.5 0 0 1 4 7v1a4 4 0 0 0 8 0V7a.5.5 0 0 1 1 0v1a5 5 0 0 1-4.5 4.975V15h3a.5.5 0 0 1 0 1h-7a.5.5 0 0 1 0-1h3v-2.025A5 5 0 0 1 3 8V7a.5.5 0 0 1 .5-.5z"/>
                <path d="M10 8a2 2 0 1 1-4 0V3a2 2 0 1 1 4 0v5zM8 0a3 3 0 0 0-3 3v5a3 3 0 0 0 6 0V3a3 3 0 0 0-3-3z"/>
            </svg>
            Voice Settings
        </a>
        <button type="button" class="btn btn-outline-secondary btn-sm regenerate-btn" data-article-id="${article.id}" data-regenerate-url="${getRegenerateUrl(article.id)}">
            ${regenerateIconSvg}
            Regenerate
        </button>
        <a href="${getDeleteUrl(article.id)}" class="btn btn-danger btn-sm">
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-trash" viewBox="0 0 16 16" aria-hidden="true">
                <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
            </svg>
            Delete
        </a>`;
}

// Function to reset playback UI
function resetPlaybackUI() {
    document.querySelectorAll('tr.now-playing').forEach(row => {
        row.classList.remove('now-playing');
    });
    document.querySelectorAll('.play-audio-btn').forEach(btn => {
        btn.innerHTML = playIconSvg;
    });
    const playerContainer = document.getElementById('audioPlayerContainer');
    if (playerContainer) {
        playerContainer.style.display = 'none';
    }
}

// Handle play button click events
function handlePlayButtonClick(event) {
    event.preventDefault();
    const button = event.currentTarget;
    const audioUrl = button.dataset.audioUrl;
    const articleId = button.dataset.articleId;
    let articleTitle = button.dataset.articleTitle || 'Unknown Title';

    const audioPlayer = document.getElementById('audioPlayer');
    if (!audioPlayer) {
        console.error('Audio player element not found');
        return;
    }

    if (!audioUrl) {
        console.error('Invalid audio URL');
        alert('Cannot play this audio: missing URL');
        resetPlaybackUI();
        return;
    }

    const row = button.closest('tr');
    const currentSrc = audioPlayer.getAttribute('src') || '';

    // Toggle play/pause if clicking the same audio
    if (currentSrc === audioUrl) {
        if (audioPlayer.paused) {
            document.querySelectorAll('tr.now-playing').forEach(r => r.classList.remove('now-playing'));
            document.querySelectorAll('.play-audio-btn').forEach(btn => { btn.innerHTML = playIconSvg; });
            if (row) {
                row.classList.add('now-playing');
                button.innerHTML = pauseIconSvg;
            }
            const playPromise = audioPlayer.play();
            if (playPromise !== undefined) {
                playPromise.catch(error => {
                    console.error('Audio playback failed:', error);
                    alert('Failed to play audio. The file may be missing or corrupted.');
                    resetPlaybackUI();
                });
            }
        } else {
            audioPlayer.pause();
            if (row) {
                row.classList.remove('now-playing');
                button.innerHTML = playIconSvg;
            }
        }
        return;
    }

    // Remove playing status from all rows
    document.querySelectorAll('tr.now-playing').forEach(r => {
        r.classList.remove('now-playing');
    });
    document.querySelectorAll('.play-audio-btn').forEach(btn => {
        btn.innerHTML = playIconSvg;
    });

    // Add playing status to current row
    if (row) {
        row.classList.add('now-playing');
        button.innerHTML = pauseIconSvg;
    }

    if (currentSrc !== audioUrl) {
        audioPlayer.setAttribute('src', audioUrl);
        const playPromise = audioPlayer.play();
        if (playPromise !== undefined) {
            playPromise.catch(error => {
                console.error('Audio playback failed:', error);
                alert('Failed to play audio. The file may be missing or corrupted.');
                resetPlaybackUI();
            });
        }
    }

    const nowPlayingTitle = document.getElementById('nowPlayingTitle');
    if (nowPlayingTitle) {
        nowPlayingTitle.textContent = articleTitle;
    }

    const playerContainer = document.getElementById('audioPlayerContainer');
    if (playerContainer) {
        playerContainer.style.display = 'block';
    }
}

// Function to attach event listeners to play buttons
function attachPlayButtonListeners() {
    const currentPlayButtons = document.querySelectorAll('.play-audio-btn');
    currentPlayButtons.forEach(button => {
        button.removeEventListener('click', handlePlayButtonClick);
        button.addEventListener('click', handlePlayButtonClick);
    });
}

// AIDEV-NOTE: Async regenerate handler - updates UI without page reload
async function handleRegenerateClick(event) {
    event.preventDefault();
    const button = event.currentTarget;
    const articleId = button.dataset.articleId;
    const regenerateUrl = button.dataset.regenerateUrl;

    if (!regenerateUrl) {
        console.error('Missing regenerate URL');
        alert('Cannot regenerate: missing URL');
        return;
    }

    const originalContent = button.innerHTML;
    button.disabled = true;
    button.innerHTML = spinnerIconSvg + ' Processing...';

    try {
        const response = await fetch(regenerateUrl, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'X-CSRFToken': csrfToken,
                'X-Requested-With': 'XMLHttpRequest',
                'Accept': 'application/json',
            },
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const data = await response.json();

        if (!data.success) {
            throw new Error(data.message || 'Regeneration failed');
        }

        // Update the row to show processing state
        const row = button.closest('tr');
        if (row) {
            row.dataset.articleId = data.new_article.id;
            row.dataset.status = data.new_article.status;

            const statusBadge = row.querySelector('.status-badge');
            if (statusBadge) {
                statusBadge.innerHTML = '<span class="badge bg-warning text-dark">Processing</span>';
            }

            const actionCell = row.querySelector('.action-cell');
            if (actionCell) {
                actionCell.innerHTML = `
                    <span class="text-muted">Processing...</span>
                    <a href="${getDeleteUrl(data.new_article.id)}" class="btn btn-outline-danger btn-sm mt-1 d-block">
                        <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="bi bi-trash" viewBox="0 0 16 16" aria-hidden="true">
                            <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6z"/>
                            <path fill-rule="evenodd" d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1zM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"/>
                        </svg>
                        Delete
                    </a>
                `;
            }
        }
    } catch (error) {
        console.error('Regeneration failed:', error);
        alert('Failed to regenerate article: ' + error.message);
        button.disabled = false;
        button.innerHTML = originalContent;
    }
}

// Function to attach event listeners to regenerate buttons
function attachRegenerateButtonListeners() {
    const regenerateButtons = document.querySelectorAll('.regenerate-btn');
    regenerateButtons.forEach(button => {
        button.removeEventListener('click', handleRegenerateClick);
        button.addEventListener('click', handleRegenerateClick);
    });
}

// Set up audio player event handlers
function setupAudioPlayer() {
    const audioPlayer = document.getElementById('audioPlayer');
    if (audioPlayer) {
        audioPlayer.addEventListener('ended', resetPlaybackUI);
        audioPlayer.addEventListener('error', function() {
            console.error('Audio playback failed:', audioPlayer.error);
            alert('Failed to play audio. The file may be missing or corrupted.');
            resetPlaybackUI();
        });
    }
}

// Status polling for feed articles
function updateArticleStatus() {
    if (!articleStatusUrl) return;
    fetch(articleStatusUrl)
        .then(res => res.json())
        .then(data => {
            data.articles.forEach(a => {
                const row = document.querySelector(`tr[data-article-id='${a.id}']`);
                if (!row) return;
                if (row.dataset.status !== a.status) {
                    row.dataset.status = a.status;
                    const statusCell = row.querySelector('.status-badge');
                    if (statusCell) {
                        let badgeHtml = '';
                        if (a.status === 'COMPLETED') {
                            badgeHtml = '<span class="badge bg-success">Completed</span>';
                        } else if (a.status === 'PROCESSING') {
                            badgeHtml = '<span class="badge bg-warning text-dark">Processing</span>';
                        } else if (a.status === 'FAILED') {
                            badgeHtml = '<span class="badge bg-danger">Failed</span>';
                        }
                        statusCell.innerHTML = badgeHtml;
                    }
                    if (a.status === 'COMPLETED') {
                        const actions = row.querySelector('.action-cell');
                        if (actions) {
                            if (!actions.querySelector('.play-audio-btn')) {
                                actions.innerHTML = generateArticleActionsHTML(a);
                                attachPlayButtonListeners();
                                attachRegenerateButtonListeners();
                            }
                        }
                    }
                }
            });
        })
        .catch(err => console.error('Status polling error', err));
}

// Set up MutationObserver for dynamically added rows
function setupMutationObserver() {
    const articleTableBody = document.querySelector('.table-responsive tbody');
    if (articleTableBody) {
        const observer = new MutationObserver(mutations => {
            mutations.forEach(mutation => {
                if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                    let needsReAttach = false;
                    mutation.addedNodes.forEach(node => {
                        if (node.nodeType === Node.ELEMENT_NODE && node.tagName === 'TR') {
                            if (node.querySelector('.play-audio-btn') || node.querySelector('.regenerate-btn')) {
                                needsReAttach = true;
                            }
                        }
                    });
                    if (!needsReAttach && mutation.target && mutation.target.classList && mutation.target.classList.contains('action-cell')) {
                         if (mutation.target.querySelector('.play-audio-btn') || mutation.target.querySelector('.regenerate-btn')) {
                            needsReAttach = true;
                         }
                    }
                    if (needsReAttach) {
                        attachPlayButtonListeners();
                        attachRegenerateButtonListeners();
                    }
                }
            });
        });
        observer.observe(articleTableBody, { childList: true, subtree: true });
    }
}

// Clipboard functions
function setupClipboard() {
    // These are called via onclick attributes in the template, so expose them globally
    window.copyFeedUrl = function() {
        var copyText = document.getElementById("feed-url");
        copyText.select();
        copyText.setSelectionRange(0, 99999);
        navigator.clipboard.writeText(copyText.value);

        var copyButton = document.getElementById("copy-button");
        copyButton.innerHTML = "<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='currentColor' class='bi bi-check-lg' viewBox='0 0 16 16' aria-hidden='true'><path d='M12.736 3.97a.733.733 0 0 1 1.047 0c.286.289.29.756.01 1.05L7.88 12.01a.733.733 0 0 1-1.065.02L3.217 8.384a.757.757 0 0 1 0-1.06.733.733 0 0 1 1.047 0l3.052 3.093 5.4-6.425a.247.247 0 0 1 .02-.022Z'/></svg> Copied!";
        copyButton.classList.remove("btn-outline-secondary");
        copyButton.classList.add("btn-success");

        setTimeout(function() {
            copyButton.innerHTML = "<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='currentColor' class='bi bi-clipboard' viewBox='0 0 16 16' aria-hidden='true'><path d='M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1v-1z'/><path d='M9.5 1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-3a.5.5 0 0 1-.5-.5v-1a.5.5 0 0 1 .5-.5h3zm-3-1A1.5 1.5 0 0 0 5 1.5v1A1.5 1.5 0 0 0 6.5 4h3A1.5 1.5 0 0 0 11 2.5v-1A1.5 1.5 0 0 0 9.5 0h-3z'/></svg> Copy";
            copyButton.classList.remove("btn-success");
            copyButton.classList.add("btn-outline-secondary");
        }, 2000);
    };

    window.copyApiUrl = function() {
        var copyText = document.getElementById("api-url");
        copyText.select();
        copyText.setSelectionRange(0, 99999);
        navigator.clipboard.writeText(copyText.value);

        var copyButton = document.getElementById("copy-api-button");
        copyButton.innerHTML = "<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='currentColor' class='bi bi-check-lg' viewBox='0 0 16 16' aria-hidden='true'><path d='M12.736 3.97a.733.733 0 0 1 1.047 0c.286.289.29.756.01 1.05L7.88 12.01a.733.733 0 0 1-1.065.02L3.217 8.384a.757.757 0 0 1 0-1.06.733.733 0 0 1 1.047 0l3.052 3.093 5.4-6.425a.247.247 0 0 1 .02-.022Z'/></svg> Copied!";
        copyButton.classList.remove("btn-outline-secondary");
        copyButton.classList.add("btn-success");

        setTimeout(function() {
            copyButton.innerHTML = "<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='currentColor' class='bi bi-clipboard' viewBox='0 0 16 16' aria-hidden='true'><path d='M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1v-1z'/><path d='M9.5 1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-3a.5.5 0 0 1-.5-.5v-1a.5.5 0 0 1 .5-.5h3zm-3-1A1.5 1.5 0 0 0 5 1.5v1A1.5 1.5 0 0 0 6.5 4h3A1.5 1.5 0 0 0 11 2.5v-1A1.5 1.5 0 0 0 9.5 0h-3z'/></svg> Copy";
            copyButton.classList.remove("btn-success");
            copyButton.classList.add("btn-outline-secondary");
        }, 2000);
    };

    window.copyFeedEmail = function() {
        var copyText = document.getElementById("feed-email");
        copyText.select();
        copyText.setSelectionRange(0, 99999);
        navigator.clipboard.writeText(copyText.value);

        var copyButton = document.getElementById("copy-email-button");
        copyButton.innerHTML = "<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='currentColor' class='bi bi-check-lg' viewBox='0 0 16 16' aria-hidden='true'><path d='M12.736 3.97a.733.733 0 0 1 1.047 0c.286.289.29.756.01 1.05L7.88 12.01a.733.733 0 0 1-1.065.02L3.217 8.384a.757.757 0 0 1 0-1.06.733.733 0 0 1 1.047 0l3.052 3.093 5.4-6.425a.247.247 0 0 1 .02-.022Z'/></svg> Copied!";
        copyButton.classList.remove("btn-outline-secondary");
        copyButton.classList.add("btn-success");

        setTimeout(function() {
            copyButton.innerHTML = "<svg xmlns='http://www.w3.org/2000/svg' width='16' height='16' fill='currentColor' class='bi bi-clipboard' viewBox='0 0 16 16' aria-hidden='true'><path d='M4 1.5H3a2 2 0 0 0-2 2V14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V3.5a2 2 0 0 0-2-2h-1v1h1a1 1 0 0 1 1 1V14a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1V3.5a1 1 0 0 1 1-1h1v-1z'/><path d='M9.5 1a.5.5 0 0 1 .5.5v1a.5.5 0 0 1-.5.5h-3a.5.5 0 0 1-.5-.5v-1a.5.5 0 0 1 .5-.5h3zm-3-1A1.5 1.5 0 0 0 5 1.5v1A1.5 1.5 0 0 0 6.5 4h3A1.5 1.5 0 0 0 11 2.5v-1A1.5 1.5 0 0 0 9.5 0h-3z'/></svg> Copy";
            copyButton.classList.remove("btn-success");
            copyButton.classList.add("btn-outline-secondary");
        }, 2000);
    };
}

// Initialize everything
setupClipboard();

document.addEventListener('DOMContentLoaded', function() {
    setupAudioPlayer();
    attachPlayButtonListeners();
    attachRegenerateButtonListeners();
    setupMutationObserver();

    // Start status polling if we have a status URL
    if (articleStatusUrl) {
        setInterval(updateArticleStatus, 10000);
    }
});

})();
