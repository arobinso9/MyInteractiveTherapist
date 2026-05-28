import { state } from '../main.js';
import { showCrisisHelp } from './crisis.js';

export function updateSliderValue(elementId, value) {
    document.getElementById(elementId).textContent = value;
}

export async function startNewSession(render) {
    sessionStorage.removeItem('activeSessionId');
    state.sessionData = { initialStress: 5, chatHistory: [] };
    document.getElementById('stressSlider').value = 5;
    updateSliderValue('stressValue', 5);

    // Reset prior-goal section
    const section = document.getElementById('prior-goal-section');
    const noteEl  = document.getElementById('prior-goal-note');
    if (section) section.style.display = 'none';
    if (noteEl)  noteEl.value = '';
    document.querySelectorAll('input[name="followthrough"]').forEach(r => { r.checked = false; });

    // Find the most recent completed session with a goal
    state.sessionData.priorGoal = null;
    try {
        const res = await fetch('/api/sessions');
        if (res.ok) {
            const sessions = await res.json();   // descending by started_at
            const mostRecentCompleted = sessions.find(s => s.completedAt);
            const priorWithGoal = mostRecentCompleted?.nextSessionGoal ? mostRecentCompleted : null;
            if (priorWithGoal) {
                document.getElementById('prior-goal-text').textContent = priorWithGoal.nextSessionGoal;
                state.sessionData.priorGoal = priorWithGoal.nextSessionGoal;
                section.style.display = '';
            }
        }
    } catch { /* non-fatal — just skip the check-in */ }

    render('pre-check');
}

export async function enterTherapySession(render) {
    state.sessionData.initialStress = parseInt(document.getElementById('stressSlider').value);

    // Read prior-goal check-in if visible
    const section = document.getElementById('prior-goal-section');
    const sectionVisible = section && section.style.display !== 'none';
    const followthroughEl = sectionVisible
        ? document.querySelector('input[name="followthrough"]:checked')
        : null;
    const followthrough = followthroughEl?.value || null;
    const note = sectionVisible
        ? (document.getElementById('prior-goal-note').value.trim() || null)
        : null;

    // Validation: when the check-in is showing, both a radio choice AND an explanation are required
    if (sectionVisible) {
        if (!followthrough) {
            alert('Please answer how the last goal went before continuing.');
            return;
        }
        if (!note) {
            alert('Please add a short explanation about how the goal went.');
            document.getElementById('prior-goal-note').focus();
            return;
        }
    }

    try {
        const res = await fetch('/api/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                initialMood: state.sessionData.initialStress,
                priorGoalFollowthrough: followthrough,
                priorGoalNote: note,
            })
        });
        if (res.ok) {
            const data = await res.json();
            state.sessionData.sessionId = data.sessionId;
            sessionStorage.setItem('activeSessionId', data.sessionId);
        }
    } catch { /* session works; messages just won't persist */ }

    let name = state.currentUser?.username || 'there';
    try {
        const ires = await fetch('/api/intake');
        if (ires.ok) {
            const idata = await ires.json();
            const preferred = idata?.data?.preferredName?.trim();
            const full      = idata?.data?.fullName?.trim();
            // Use first name from fullName if no preferred name
            const firstFromFull = full ? full.split(/\s+/)[0] : '';
            name = preferred || firstFromFull || name;
        }
    } catch { /* fall back to username */ }

    // Always fetch the greeting from the backend — it decides whether to use AI
    // (prior goal or pattern alert) or return a fast hardcoded hello.
    const fallback = `Hello ${name}, I'm here to listen. What would you like to talk about today?`;

    state.sessionData.chatHistory = [{ type: 'thinking', text: 'Thinking...' }];
    renderChatMessages();
    render('session');

    try {
        const gres = await fetch(`/api/sessions/${state.sessionData.sessionId}/greeting`, { method: 'POST' });
        const text = gres.ok ? (await gres.json()).greeting : fallback;
        state.sessionData.chatHistory = [{ type: 'therapist', text }];
    } catch {
        state.sessionData.chatHistory = [{ type: 'therapist', text: fallback }];
    }
    renderChatMessages();
}

export async function endSession(render) {
    if (!state.sessionData.sessionId) {
        // No persisted session — skip wrap-up, go straight to post-check
        continueToPostCheck(render);
        return;
    }

    // Skip wrap-up + goal-setting for trivial sessions (≤5 user messages)
    const userMsgCount = (state.sessionData.chatHistory || []).filter(m => m.type === 'user').length;
    if (userMsgCount <= 5) {
        state.sessionData.proposedGoal = null;
        continueToPostCheck(render);
        return;
    }

    // Disable End Session button + lock state so we don't fire it twice
    const endBtn      = document.getElementById('end-session-btn');
    const continueBtn = document.getElementById('continue-wrapup-btn');
    if (endBtn) endBtn.disabled = true;

    state.sessionData.wrapUpMode = true;
    state.sessionData.proposedGoal = null;

    // Add a thinking indicator
    state.sessionData.chatHistory.push({ type: 'thinking', text: 'Wrapping up…' });
    renderChatMessages();

    try {
        const res = await fetch(`/api/sessions/${state.sessionData.sessionId}/wrap-up`, { method: 'POST' });
        if (res.ok) {
            const data = await res.json();
            state.sessionData.chatHistory.pop();   // remove thinking
            state.sessionData.chatHistory.push({ type: 'therapist', text: data.reply });
            state.sessionData.proposedGoal = data.proposedGoal || null;
        } else {
            state.sessionData.chatHistory.pop();
            state.sessionData.chatHistory.push({
                type: 'therapist',
                text: "Before we wrap, is there one small thing you want to try working on before next session?"
            });
        }
    } catch {
        state.sessionData.chatHistory.pop();
        state.sessionData.chatHistory.push({
            type: 'therapist',
            text: "Before we wrap, is there one small thing you want to try working on before next session?"
        });
    } finally {
        if (endBtn) endBtn.style.display = 'none';
        if (continueBtn) continueBtn.style.display = '';
        const skipBtn = document.getElementById('skip-goal-btn');
        if (skipBtn) skipBtn.style.display = '';
        renderChatMessages();
    }
}

export function skipGoalAndContinue(render) {
    state.sessionData.proposedGoal = null;
    continueToPostCheck(render);
}

export function continueToPostCheck(render) {
    // Reset wrap-up state for the next session
    state.sessionData.wrapUpMode = false;
    // Restore the End Session button visibility for future sessions (won't matter for this view instance)
    const endBtn      = document.getElementById('end-session-btn');
    const continueBtn = document.getElementById('continue-wrapup-btn');
    const skipBtn     = document.getElementById('skip-goal-btn');
    if (endBtn) { endBtn.style.display = ''; endBtn.disabled = false; }
    if (continueBtn) continueBtn.style.display = 'none';
    if (skipBtn) skipBtn.style.display = 'none';

    // Reset Complete button — otherwise it stays disabled + "Completing…" from the prior session
    const completeBtn = document.getElementById('complete-session-btn');
    if (completeBtn) { completeBtn.disabled = false; completeBtn.textContent = 'Complete Session'; }

    document.getElementById('resolutionSlider').value = 5;
    updateSliderValue('resolutionValue', 5);
    document.getElementById('takeaway').value = '';

    // Show the goal that was agreed in chat (read-only). Hide the block entirely if there is no goal.
    const goalGroup   = document.getElementById('post-check-goal-group');
    const goalDisplay = document.getElementById('next-session-goal-display');
    const goal        = state.sessionData.proposedGoal || '';
    if (goalDisplay) goalDisplay.textContent = goal;
    if (goalGroup)   goalGroup.style.display = goal ? '' : 'none';

    render('post-check');
}

export async function completeSession(render) {
    const finalStress = parseInt(document.getElementById('resolutionSlider').value);
    const takeaway    = document.getElementById('takeaway').value.trim();
    const goal        = (state.sessionData.proposedGoal || '').trim();

    if (!takeaway) { alert('Please share your key takeaway before completing the session'); return; }

    // Lock the button + show progress so the user sees something happen immediately
    const completeBtn = document.getElementById('complete-session-btn');
    if (completeBtn) {
        completeBtn.disabled = true;
        completeBtn.textContent = 'Completing…';
    }

    if (state.sessionData.sessionId) {
        try {
            await fetch(`/api/sessions/${state.sessionData.sessionId}/complete`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    finalMood: finalStress,
                    whatWorked: takeaway,
                    nextSessionGoal: goal || null,
                })
            });
        } catch { /* best-effort */ }
    }

    sessionStorage.removeItem('activeSessionId');
    state.sessionData = { initialStress: 5, chatHistory: [] };
    render('progress');
}

// ============================================
// CHAT
// ============================================
export function renderChatMessages() {
    const container = document.getElementById('chatMessages');
    container.innerHTML = '';
    state.sessionData.chatHistory.forEach(msg => {
        const div       = document.createElement('div');
        div.className   = `message ${msg.type}`;
        div.textContent = msg.text;
        container.appendChild(div);
    });
    container.scrollTop = container.scrollHeight;
}

export function handleChatKeyPress(event) {
    if (event.key === 'Enter') sendMessage();
}

async function callChatAPI(userText) {
    const history = state.sessionData.chatHistory
        .filter(m => m.type === 'user' || m.type === 'therapist')
        .map(m => ({ role: m.type === 'user' ? 'user' : 'assistant', content: m.text }));

    const res  = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            message: userText,
            history,
            sessionId: state.sessionData.sessionId || null,
            wrapUp: !!state.sessionData.wrapUpMode,
        })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    if (data.proposedGoal !== undefined) state.sessionData.proposedGoal = data.proposedGoal;
    return data;
}

export async function sendMessage() {
    const input   = document.getElementById('chatInput');
    const sendBtn = document.querySelector('#session-view .chat-input-group button');
    const text    = input.value.trim();
    if (!text) return;

    state.sessionData.chatHistory.push({ type: 'user', text });
    renderChatMessages();
    input.value    = '';
    input.disabled = true;
    if (sendBtn) sendBtn.disabled = true;

    state.sessionData.chatHistory.push({ type: 'thinking', text: 'Thinking...' });
    renderChatMessages();

    try {
        const data = await callChatAPI(text);
        state.sessionData.chatHistory.pop();
        state.sessionData.chatHistory.push({ type: 'therapist', text: data.reply });
        if (data.safetyMode === 'CRISIS') showCrisisHelp();
    } catch {
        state.sessionData.chatHistory.pop();
        state.sessionData.chatHistory.push({ type: 'therapist', text: "I'm having trouble connecting right now. Please check your connection and try again." });
    } finally {
        input.disabled = false;
        if (sendBtn) sendBtn.disabled = false;
        renderChatMessages();
        input.focus();
    }
}
