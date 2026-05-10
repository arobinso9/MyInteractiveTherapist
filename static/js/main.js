import { handleLogin, handleSignup, logout, updatePasswordStrength, hideAuthError } from './modules/auth.js';
import { confirmDeleteSessions, confirmDeleteAccount } from './modules/account.js';
import { loadIntakeForm, completeIntake, saveDraft, updateIntakeSlider } from './modules/intake.js';
import { renderProfileSummary, renderSessionHistory } from './modules/dashboard.js';
import { startNewSession, enterTherapySession, endSession, completeSession, renderChatMessages, handleChatKeyPress, sendMessage, updateSliderValue, continueToPostCheck, skipGoalAndContinue } from './modules/session.js';
import { showCrisisHelp, closeCrisisModal } from './modules/crisis.js';

// ============================================
// GLOBAL STATE
// ============================================
export const state = {
    currentUser: null,
    sessionData: { initialStress: 5, chatHistory: [] }
};

// ============================================
// ROUTER
// ============================================
function render(route) {
    if (state.currentUser && !state.currentUser.hasCompletedIntake) {
        if (['progress', 'pre-check', 'session', 'post-check'].includes(route)) route = 'intake';
    }

    document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
    document.getElementById(`${route}-view`)?.classList.add('active');

    const header = document.getElementById('appHeader');
    if (state.currentUser && route !== 'auth') {
        header.classList.add('visible');
        document.getElementById('headerUsername').textContent = state.currentUser.username;
    } else {
        header.classList.remove('visible');
    }

    if (route !== 'auth') {
        document.getElementById('authPassword').value = '';
        document.getElementById('passwordStrength').innerHTML = '';
        document.getElementById('passwordRequirements').style.display = 'none';
        hideAuthError();
    }

    if (route === 'progress') {
        renderProfileSummary(state.currentUser);
        renderSessionHistory();
    } else if (route === 'intake') {
        loadIntakeForm();
    }
}

// ============================================
// INITIALIZATION
// ============================================
window.addEventListener('load', async () => {
    try {
        const res = await fetch('/api/me');
        if (res.ok) {
            const data = await res.json();
            state.currentUser = { username: data.username, isPro: data.isPro, hasCompletedIntake: data.hasCompletedIntake };

            const savedSessionId = sessionStorage.getItem('activeSessionId');
            if (savedSessionId) {
                try {
                    const sRes = await fetch(`/api/sessions/${savedSessionId}`);
                    if (sRes.ok) {
                        const sData = await sRes.json();
                        if (!sData.completedAt) {
                            state.sessionData.sessionId    = sData.id;
                            state.sessionData.initialStress = sData.initialMood ?? 5;
                            state.sessionData.chatHistory   = sData.messages.map(m => ({
                                type: m.role === 'user' ? 'user' : 'therapist',
                                text: m.content
                            }));
                            renderChatMessages();
                            render('session');
                            return;
                        }
                    }
                    sessionStorage.removeItem('activeSessionId');
                } catch {
                    sessionStorage.removeItem('activeSessionId');
                }
            }
            render(state.currentUser.hasCompletedIntake ? 'progress' : 'intake');
        } else {
            render('auth');
        }
    } catch {
        render('auth');
    } finally {
        const overlay = document.getElementById('app-loading-overlay');
        if (overlay) overlay.style.display = 'none';
    }
});

// ============================================
// EXPOSE TO HTML (onclick handlers)
// ============================================
window.handleLogin     = () => handleLogin(user => { state.currentUser = user; render(user.hasCompletedIntake ? 'progress' : 'intake'); });
window.handleSignup    = handleSignup;
window.logout          = () => logout(() => { state.currentUser = null; sessionStorage.removeItem('activeSessionId'); state.sessionData = { initialStress: 5, chatHistory: [] }; render('auth'); });
window.updatePasswordStrength = updatePasswordStrength;

window.confirmDeleteSessions = () => confirmDeleteSessions(() => { sessionStorage.removeItem('activeSessionId'); state.sessionData = { initialStress: 5, chatHistory: [] }; render('progress'); });
window.confirmDeleteAccount  = () => confirmDeleteAccount(() => { state.currentUser = null; sessionStorage.removeItem('activeSessionId'); state.sessionData = { initialStress: 5, chatHistory: [] }; render('auth'); });

window.completeIntake   = () => completeIntake(() => { state.currentUser.hasCompletedIntake = true; render('progress'); });
window.saveDraft        = saveDraft;
window.updateIntakeSlider = updateIntakeSlider;

window.startNewSession  = () => startNewSession(render);
window.enterTherapySession = () => enterTherapySession(render);
window.endSession       = () => endSession(render);
window.continueToPostCheck = () => continueToPostCheck(render);
window.skipGoalAndContinue = () => skipGoalAndContinue(render);
window.completeSession  = () => completeSession(render);
window.updateSliderValue = updateSliderValue;
window.handleChatKeyPress = handleChatKeyPress;
window.sendMessage      = sendMessage;

window.showCrisisHelp    = showCrisisHelp;
window.closeCrisisModal  = closeCrisisModal;
window.render            = render;
