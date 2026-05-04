export function confirmDeleteSessions(onDeleted) {
    if (!confirm(
        "🗑️ DELETE SESSION CHATS - STEP 1 of 2\n\n" +
        "This will PERMANENTLY delete:\n" +
        "• All therapy session history\n• All chat transcripts\n• All stress ratings and takeaways\n\n" +
        "Your intake form and account will remain intact.\n\nContinue to Step 2?"
    )) return;

    if (!confirm(
        "🗑️ FINAL CONFIRMATION - STEP 2 of 2\n\n" +
        "Delete all session chats?\nThis CANNOT be undone.\n\nClick OK to delete sessions."
    )) return;

    deleteSessionsOnly(onDeleted);
}

async function deleteSessionsOnly(onDeleted) {
    try {
        const res = await fetch('/api/sessions', { method: 'DELETE' });
        if (!res.ok) { alert('❌ Could not delete sessions. Please try again.'); return; }
    } catch {
        alert('❌ Connection error. Sessions not deleted.');
        return;
    }
    alert("✓ Sessions Deleted\n\nAll therapy sessions have been deleted.\nYour intake form and account remain intact.");
    onDeleted();
}

export function confirmDeleteAccount(onDeleted) {
    if (!confirm(
        "⚠️ WIPE ACCOUNT - STEP 1 of 2\n\n" +
        "This will PERMANENTLY delete:\n" +
        "• All therapy sessions and chats\n• Your intake form data\n• YOUR ENTIRE ACCOUNT\n\n" +
        "You will need to create a NEW account.\n\nContinue to Step 2?"
    )) return;

    if (!confirm(
        "⚠️ FINAL CONFIRMATION - STEP 2 of 2\n\n" +
        "WIPE YOUR ENTIRE ACCOUNT?\n\n" +
        "• All data will be PERMANENTLY deleted\n• You will be logged out\n• This CANNOT be undone\n\n" +
        "Click OK to wipe account completely."
    )) return;

    wipeAccount(onDeleted);
}

async function wipeAccount(onDeleted) {
    try {
        const res = await fetch('/api/account', { method: 'DELETE' });
        if (!res.ok) { alert('❌ Could not delete account. Please try again.'); return; }
    } catch {
        alert('❌ Connection error. Account not deleted.');
        return;
    }
    alert("✓ Account Wiped\n\nYour account has been permanently deleted.\nAll data has been removed.\n\nYou can create a new account if desired.");
    onDeleted();
}
