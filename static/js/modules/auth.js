// ============================================
// PASSWORD SECURITY
// ============================================
const COMMON_PATTERNS = [
    /^password/i, /^welcome/i, /^admin/i, /^user/i, /^test/i,
    /^qwerty/i, /^abc123/i, /123456/, /^letmein/i, /^iloveyou/i,
    /^\d{6,}$/,
    /^[a-z]+$/i,
    /(.)\1{2,}/,
    /^(?=.*bank)(?=.*\d{4})/i,
    /^(?=.*password)(?=.*\d+)/i
];

export function validatePasswordStrength(password) {
    const checks = {
        length:    password.length >= 10,
        uppercase: /[A-Z]/.test(password),
        lowercase: /[a-z]/.test(password),
        number:    /\d/.test(password),
        special:   /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password)
    };
    return { checks, allValid: Object.values(checks).every(v => v) };
}

// k-anonymity check via HaveIBeenPwned Passwords API.
// Only the first 5 chars of the SHA-1 hash are sent — the password never leaves the browser.
// Returns: { breached: bool, count: number } on success, { breached: false, offline: true } on network failure.
async function sha1(text) {
    const buf    = await crypto.subtle.digest('SHA-1', new TextEncoder().encode(text));
    return Array.from(new Uint8Array(buf)).map(b => b.toString(16).padStart(2, '0')).join('').toUpperCase();
}

export async function isBreachedPassword(password) {
    // Always run pattern checks synchronously first
    if (COMMON_PATTERNS.some(p => p.test(password))) return { breached: true, count: null };

    try {
        const hash   = await sha1(password);
        const prefix = hash.slice(0, 5);
        const suffix = hash.slice(5);

        const res  = await fetch(`https://api.pwnedpasswords.com/range/${prefix}`, {
            headers: { 'Add-Padding': 'true' }  // prevents traffic-analysis leaks
        });
        if (!res.ok) return { breached: false, offline: true };

        const lines = (await res.text()).split('\n');
        const match = lines.find(line => line.split(':')[0] === suffix);
        if (match) {
            const count = parseInt(match.split(':')[1], 10);
            return { breached: true, count };
        }
        return { breached: false };
    } catch {
        // Network failure — fail open (don't block signup) but flag it
        return { breached: false, offline: true };
    }
}

export function containsUserInfo(password, username) {
    const lp = password.toLowerCase();
    const lu = username.toLowerCase();
    return lp.includes(lu) || (lu.includes(lp) && password.length > 3);
}

export function updatePasswordStrength() {
    const password     = document.getElementById('authPassword').value;
    const strengthBar  = document.getElementById('passwordStrength');
    const requirements = document.getElementById('passwordRequirements');

    if (!password.length) {
        strengthBar.innerHTML = '';
        requirements.style.display = 'none';
        return;
    }

    requirements.style.display = 'block';
    const { checks } = validatePasswordStrength(password);

    const items = [
        ['reqLength',  checks.length,    '10 characters'],
        ['reqUpper',   checks.uppercase, 'One uppercase letter'],
        ['reqLower',   checks.lowercase, 'One lowercase letter'],
        ['reqNumber',  checks.number,    'One number'],
        ['reqSpecial', checks.special,   'One special character'],
    ];
    items.forEach(([id, valid, label]) => {
        const el = document.getElementById(id);
        el.className   = valid ? 'req-item valid' : 'req-item';
        el.textContent = (valid ? '✓ ' : '✗ ') + label;
    });

    const score = Object.values(checks).filter(v => v).length;
    const cls   = score <= 2 ? 'strength-weak' : score <= 4 ? 'strength-medium' : 'strength-strong';
    strengthBar.innerHTML = `<div class="password-strength-bar ${cls}"></div>`;
}

// ============================================
// AUTH ERROR / SUCCESS DISPLAY
// ============================================
export function showAuthError(message) {
    const el = document.getElementById('lockoutMessage');
    el.textContent = message;
    el.className   = 'lockout-message';
    el.style.display = 'block';
}

export function showAuthSuccess(message) {
    const el = document.getElementById('lockoutMessage');
    el.textContent = message;
    el.className   = 'success-message';
    el.style.display = 'block';
}

export function hideAuthError() {
    const el = document.getElementById('lockoutMessage');
    el.style.display = 'none';
    el.textContent   = '';
}

// ============================================
// AUTH HANDLERS
// ============================================
export async function handleLogin(onSuccess) {
    const username = document.getElementById('authUsername').value.trim();
    const password = document.getElementById('authPassword').value.trim();

    hideAuthError();
    if (!username || !password) { showAuthError('Please enter both username and password'); return; }

    try {
        const res  = await fetch('/api/login', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (!res.ok) { showAuthError(data.error || 'Login failed'); return; }

        document.getElementById('authUsername').value = '';
        document.getElementById('authPassword').value = '';
        onSuccess({ username, isPro: data.isPro, hasCompletedIntake: data.hasCompletedIntake });
    } catch {
        showAuthError('Connection error. Please try again.');
    }
}

export async function handleSignup() {
    const username = document.getElementById('authUsername').value.trim();
    const password = document.getElementById('authPassword').value.trim();

    hideAuthError();
    if (!username || !password) { showAuthError('Please enter both username and password'); return; }
    if (username.length < 3 || username.length > 30) { showAuthError('Username must be 3–30 characters'); return; }
    if (!/^[a-zA-Z0-9_]+$/.test(username)) { showAuthError('Username can only contain letters, numbers, and underscores'); return; }

    const { checks } = validatePasswordStrength(password);
    if (!checks.length)    { showAuthError('Password must be at least 10 characters'); return; }
    if (!checks.uppercase) { showAuthError('Password must contain an uppercase letter'); return; }
    if (!checks.lowercase) { showAuthError('Password must contain a lowercase letter'); return; }
    if (!checks.number)    { showAuthError('Password must contain a number'); return; }
    if (!checks.special)   { showAuthError('Password must contain a special character'); return; }
    if (containsUserInfo(password, username)) { showAuthError('Password cannot contain your username'); return; }

    showAuthError('Checking password safety…');
    const { breached, count, offline } = await isBreachedPassword(password);
    if (breached) {
        const detail = count ? ` (found ${count.toLocaleString()} times in data breaches)` : '';
        showAuthError(`This password is too common or has been compromised${detail}. Please choose a stronger one.`);
        return;
    }
    if (offline) {
        // HIBP unreachable — warn but don't block
        console.warn('HIBP check skipped: network unavailable');
    }
    hideAuthError();

    try {
        const res  = await fetch('/api/signup', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password })
        });
        const data = await res.json();
        if (!res.ok) { showAuthError(data.error || 'Signup failed'); return; }

        showAuthSuccess('Account created! Please log in.');
        document.getElementById('authPassword').value = '';
        updatePasswordStrength();
    } catch {
        showAuthError('Connection error. Please try again.');
    }
}

export async function logout(onComplete) {
    try { await fetch('/api/logout', { method: 'POST' }); } catch { /* ignore */ }
    onComplete();
}
