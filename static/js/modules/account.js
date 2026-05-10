import { confirmModal, alertModal, showModal } from './modal.js';

const RECENT_PICK_LIMIT = 10;

const _esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
));

function _formatDate(iso) {
    if (!iso) return 'Unknown date';
    const d = new Date(iso);
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function _sessionListHtml(recent, totalCount) {
    const rows = recent.map(s => {
        const preview = s.summary
            ? (s.summary.length > 110 ? s.summary.slice(0, 110).trim() + '…' : s.summary)
            : (s.takeaway || 'In progress — no summary yet');
        return `
            <label class="session-pick-row">
                <input type="checkbox" class="session-pick" value="${s.id}">
                <div class="session-pick-meta">
                    <div class="session-pick-date">${_esc(_formatDate(s.startedAt))}</div>
                    <div class="session-pick-preview">${_esc(preview)}</div>
                </div>
            </label>
        `;
    }).join('');

    const moreNote = totalCount > recent.length
        ? `<p class="session-pick-note">Showing your ${recent.length} most recent sessions (you have ${totalCount} total). Use "Delete all" to wipe everything.</p>`
        : '';

    return `
        <button type="button" id="modal-delete-all" class="modal-inline-danger">Delete all sessions</button>

        <div class="modal-divider"><span>or pick from recent</span></div>

        ${moreNote}
        <div class="session-pick-toolbar">
            <button type="button" class="session-pick-toggle" onclick="document.querySelectorAll('.session-pick').forEach(c=>c.checked=true)">Select all</button>
            <button type="button" class="session-pick-toggle" onclick="document.querySelectorAll('.session-pick').forEach(c=>c.checked=false)">Select none</button>
        </div>
        <div class="session-pick-list scrollbar-custom">${rows}</div>
    `;
}

function _readCheckedIds() {
    return Array.from(document.querySelectorAll('.session-pick:checked'))
        .map(cb => parseInt(cb.value, 10))
        .filter(n => !Number.isNaN(n));
}

export async function confirmDeleteSessions(onDeleted) {
    let sessions;
    try {
        const res = await fetch('/api/sessions');
        if (!res.ok) throw new Error('fetch failed');
        sessions = await res.json();
    } catch {
        await alertModal({ title: 'Connection error', bodyHtml: '<p>Could not load your sessions.</p>' });
        return;
    }

    if (!Array.isArray(sessions) || sessions.length === 0) {
        await alertModal({
            title: 'No sessions yet',
            bodyHtml: '<p>You don\'t have any therapy sessions to delete.</p>',
        });
        return;
    }

    const recent = sessions.slice(0, RECENT_PICK_LIMIT);

    const result = await showModal({
        title: 'Delete sessions',
        bodyHtml: _sessionListHtml(recent, sessions.length),
        buttons: [
            { label: 'Cancel',                 value: null, variant: 'cancel' },
            { label: 'Delete selected',        variant: 'primary', onClick: _readCheckedIds },
        ],
        onMount: (close) => {
            const allBtn = document.getElementById('modal-delete-all');
            if (allBtn) allBtn.onclick = () => close('ALL');
        },
    });

    if (result === null) return;

    let toDelete; // 'ALL' or array of ids
    let countLabel;
    if (result === 'ALL') {
        toDelete   = 'ALL';
        countLabel = `all ${sessions.length} session${sessions.length > 1 ? 's' : ''}`;
    } else if (Array.isArray(result) && result.length > 0) {
        toDelete   = result;
        countLabel = `${result.length} session${result.length > 1 ? 's' : ''}`;
    } else {
        // user clicked "Delete selected" with nothing checked
        await alertModal({ title: 'Nothing selected', bodyHtml: '<p>Please pick at least one session, or use "Delete all sessions".</p>' });
        return;
    }

    const confirmed = await confirmModal({
        title: 'Final confirmation',
        bodyHtml: `<p>Permanently delete <strong>${countLabel}</strong>? This cannot be undone.</p>`,
        confirmLabel: 'Delete',
        cancelLabel: 'Cancel',
        danger: true,
    });
    if (!confirmed) return;

    try {
        const opts = { method: 'DELETE' };
        if (toDelete !== 'ALL') {
            opts.headers = { 'Content-Type': 'application/json' };
            opts.body    = JSON.stringify({ sessionIds: toDelete });
        }
        const res = await fetch('/api/sessions', opts);
        if (!res.ok) {
            await alertModal({ title: 'Could not delete', bodyHtml: '<p>Something went wrong. Please try again.</p>' });
            return;
        }
    } catch {
        await alertModal({ title: 'Connection error', bodyHtml: '<p>Sessions were not deleted.</p>' });
        return;
    }

    await alertModal({
        title: 'Sessions deleted',
        bodyHtml: `<p>Removed ${countLabel}. Your intake form and account remain intact.</p>`,
    });
    onDeleted();
}

export async function confirmDeleteAccount(onDeleted) {
    const step1 = await confirmModal({
        title: 'Wipe your account?',
        bodyHtml: `
            <p>This will permanently delete:</p>
            <ul>
                <li>All therapy sessions and chats</li>
                <li>Your intake form data</li>
                <li>Your entire account</li>
            </ul>
            <p>You will need to create a new account to use ZenShell again.</p>
        `,
        confirmLabel: 'Continue',
        cancelLabel: 'Cancel',
    });
    if (!step1) return;

    const step2 = await confirmModal({
        title: 'Final confirmation',
        bodyHtml: `
            <p>Wipe your entire account?</p>
            <ul>
                <li>All data will be permanently deleted</li>
                <li>You will be logged out</li>
                <li>This cannot be undone</li>
            </ul>
        `,
        confirmLabel: 'Wipe account',
        cancelLabel: 'Cancel',
        danger: true,
    });
    if (!step2) return;

    try {
        const res = await fetch('/api/account', { method: 'DELETE' });
        if (!res.ok) {
            await alertModal({ title: 'Could not delete', bodyHtml: '<p>Something went wrong. Please try again.</p>' });
            return;
        }
    } catch {
        await alertModal({ title: 'Connection error', bodyHtml: '<p>Account was not deleted.</p>' });
        return;
    }

    await alertModal({
        title: 'Account wiped',
        bodyHtml: '<p>Your account has been permanently deleted. You can create a new account if you want.</p>',
    });
    onDeleted();
}
