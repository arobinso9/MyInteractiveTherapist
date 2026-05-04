import { state } from '../main.js';

export function updateSliderValue(elementId, value) {
    document.getElementById(elementId).textContent = value;
}

export function startNewSession(render) {
    sessionStorage.removeItem('activeSessionId');
    state.sessionData = { initialStress: 5, chatHistory: [] };
    document.getElementById('stressSlider').value = 5;
    updateSliderValue('stressValue', 5);
    render('pre-check');
}

export async function enterTherapySession(render) {
    state.sessionData.initialStress = parseInt(document.getElementById('stressSlider').value);

    try {
        const res = await fetch('/api/sessions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ initialMood: state.sessionData.initialStress })
        });
        if (res.ok) {
            const data = await res.json();
            state.sessionData.sessionId = data.sessionId;
            sessionStorage.setItem('activeSessionId', data.sessionId);
        }
    } catch { /* session works; messages just won't persist */ }

    const name = state.currentUser?.username || 'there';
    state.sessionData.chatHistory = [{
        type: 'therapist',
        text: `Hello ${name}, I'm here to listen. What would you like to talk about today?`
    }];
    renderChatMessages();
    render('session');
}

export function endSession(render) {
    document.getElementById('resolutionSlider').value = 5;
    updateSliderValue('resolutionValue', 5);
    document.getElementById('takeaway').value = '';
    render('post-check');
}

export async function completeSession(render) {
    const finalStress = parseInt(document.getElementById('resolutionSlider').value);
    const takeaway    = document.getElementById('takeaway').value.trim();

    if (!takeaway) { alert('Please share your key takeaway before completing the session'); return; }

    if (state.sessionData.sessionId) {
        try {
            await fetch(`/api/sessions/${state.sessionData.sessionId}/complete`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ finalMood: finalStress, whatWorked: takeaway })
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
        body: JSON.stringify({ message: userText, history, sessionId: state.sessionData.sessionId || null })
    });
    const data = await res.json();
    if (data.error) throw new Error(data.error);
    return data.reply;
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
        const reply = await callChatAPI(text);
        state.sessionData.chatHistory.pop();
        state.sessionData.chatHistory.push({ type: 'therapist', text: reply });
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
