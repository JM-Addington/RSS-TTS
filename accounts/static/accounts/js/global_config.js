// AIDEV-NOTE: Sets hidden forceInput value from forceOverride checkbox on migration form submit (#227)
(function() {
'use strict';

function init() {
    var form = document.getElementById('migrationForm');
    if (!form) return;

    form.addEventListener('submit', function() {
        var forceInput = document.getElementById('forceInput');
        var forceOverride = document.getElementById('forceOverride');
        if (forceInput && forceOverride) {
            forceInput.value = forceOverride.checked ? '1' : '0';
        }
    });
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
} else {
    init();
}

})();
