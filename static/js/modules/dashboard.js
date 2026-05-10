export async function renderProfileSummary(currentUser) {
    const container = document.getElementById('profileSummary');
    if (!currentUser) return;

    let intake;
    try {
        const res = await fetch('/api/intake');
        if (res.ok) intake = (await res.json()).data;
    } catch { /* ignore */ }

    if (!intake) {
        container.innerHTML = '<p style="text-align:center;opacity:0.7;">Complete your intake form to see your profile summary.</p>';
        return;
    }

    let age = '';
    if (intake.dob) {
        const dob = new Date(intake.dob);
        age = Math.max(0, Math.floor((Date.now() - dob) / (365.25 * 24 * 60 * 60 * 1000)));
    }

    container.innerHTML = `
        <h3>${intake.preferredName || intake.fullName}</h3>
        <p><strong>Age:</strong> ${age} | <strong>Pronouns:</strong> ${intake.pronouns || 'Not specified'}</p>
        <p><strong>Contact:</strong> ${intake.email} | ${intake.phone}</p>
        <hr style="margin:15px 0;border:none;border-top:1px solid rgba(135,169,107,0.3);">
        <p style="margin-top:10px;"><strong>Presenting Concern:</strong></p>
        <p style="font-style:italic;margin-top:5px;">"${intake.presenting}"</p>
        ${intake.issues?.length ? `<p style="margin-top:10px;"><strong>Primary Issues:</strong> ${intake.issues.join(', ')}</p>` : ''}
        ${intake.distressLevel ? `<p style="margin-top:10px;"><strong>Current Distress Level:</strong> <span style="color:var(--sage);font-weight:bold;">${intake.distressLevel}/10</span></p>` : ''}
        ${intake.therapySuccess ? `<p style="margin-top:10px;"><strong>Therapy Goals:</strong></p><p style="font-style:italic;margin-top:5px;">"${intake.therapySuccess}"</p>` : ''}
    `;
}

export async function renderSessionHistory() {
    const container = document.getElementById('sessionHistory');

    let sessions = [];
    try {
        const res = await fetch('/api/sessions');
        if (res.ok) sessions = await res.json();
    } catch { /* ignore */ }

    if (!sessions.length) {
        container.innerHTML = '<div class="empty-state">No sessions yet. Start your first session to begin tracking your progress.</div>';
        return;
    }

    container.innerHTML = sessions.map(session => {
        const date          = new Date(session.startedAt);
        const formattedDate = date.toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        const initial       = session.initialMood ?? '—';
        const final         = session.finalMood   ?? '—';
        let improvementText = '→ In progress';
        if (session.initialMood != null && session.finalMood != null) {
            const diff = session.initialMood - session.finalMood;
            if (diff > 0)      improvementText = `↓ Felt better (stress -${diff})`;
            else if (diff < 0) improvementText = `↑ Felt worse (stress +${Math.abs(diff)})`;
            else               improvementText = `→ No change`;
        }

        return `
            <div class="session-card">
                <div class="session-header">
                    <span class="session-date">${formattedDate}</span>
                    <span>${improvementText}</span>
                </div>
                <div class="stress-indicator">
                    <span>Initial: <span class="stress-value">${initial}/10</span></span>
                    <span>Final: <span class="stress-value">${final}/10</span></span>
                </div>
                ${session.takeaway ? `<div class="takeaway">"${session.takeaway}"</div>` : ''}
                ${session.summary  ? `<div class="session-summary">${session.summary}</div>` : ''}
            </div>
        `;
    }).join('');
}
