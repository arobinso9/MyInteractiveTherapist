export function showCrisisHelp() {
    const modal = document.getElementById('crisis-modal');
    if (modal) modal.style.display = 'flex';
}

export function closeCrisisModal() {
    const modal = document.getElementById('crisis-modal');
    if (modal) modal.style.display = 'none';
}
