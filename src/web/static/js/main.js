/* SMM Agent — shared JS helpers */

function showLoading(show) {
    document.getElementById('loading').classList.toggle('hidden', !show);
}

function copyResult() {
    const text = document.getElementById('resultText')?.textContent;
    if (text) {
        navigator.clipboard.writeText(text).then(() => {
            // brief feedback
        });
    }
}
