// ============================================
        // GLOBAL STATE
        // ============================================
        let currentUser = null;
        let tempSessionData = {
            initialStress: 5,
            chatHistory: []
        };

        // ============================================
        // PASSWORD SECURITY CONSTANTS
        // ============================================
        const COMMON_PASSWORDS = [
            'password', 'password123', '123456', '12345678', 'qwerty', 'abc123',
            'monkey', '1234567', 'letmein', 'trustno1', 'dragon', 'baseball',
            'iloveyou', 'master', 'sunshine', 'ashley', 'bailey', 'shadow',
            'superman', 'qazwsx', 'michael', 'football', 'welcome', 'jesus',
            'ninja', 'mustang', 'password1', 'password!', 'admin', 'root',
            'bank2026', 'therapy', 'zenshell', 'health', 'mental', 'wellness',
            'Password123!', 'Welcome123', 'Admin123!', 'Test1234!', 'User1234!'
        ];

        const COMMON_PATTERNS = [
            /^password/i,
            /^welcome/i,
            /^admin/i,
            /^user/i,
            /^test/i,
            /^qwerty/i,
            /^abc123/i,
            /123456/,
            /^letmein/i,
            /^iloveyou/i,
            /^\d{6,}$/, // All numbers
            /^[a-z]+$/i, // All letters
            /(.)\1{2,}/, // Repeated characters (aaa, 111)
            /^(?=.*bank)(?=.*\d{4})/i, // Bank + year
            /^(?=.*password)(?=.*\d+)/i // Password + numbers
        ];


        // ============================================
        // PASSWORD SECURITY FUNCTIONS
        // ============================================
        function validatePasswordStrength(password) {
            const checks = {
                length: password.length >= 10,
                uppercase: /[A-Z]/.test(password),
                lowercase: /[a-z]/.test(password),
                number: /\d/.test(password),
                special: /[!@#$%^&*()_+\-=\[\]{};':"\\|,.<>\/?]/.test(password)
            };

            const allValid = Object.values(checks).every(v => v);
            return { checks, allValid };
        }

        function isCommonPassword(password) {
            const lowerPassword = password.toLowerCase();

            // Check exact matches
            if (COMMON_PASSWORDS.some(common => lowerPassword === common.toLowerCase())) {
                return true;
            }

            // Check patterns
            if (COMMON_PATTERNS.some(pattern => pattern.test(password))) {
                return true;
            }

            return false;
        }

        function containsUserInfo(password, username) {
            const lowerPassword = password.toLowerCase();
            const lowerUsername = username.toLowerCase();

            // Check if password contains username
            if (lowerPassword.includes(lowerUsername)) {
                return true;
            }

            // Check if username contains password
            if (lowerUsername.includes(lowerPassword) && password.length > 3) {
                return true;
            }

            return false;
        }


        function updatePasswordStrength() {
            const password = document.getElementById('authPassword').value;
            const strengthBar = document.getElementById('passwordStrength');
            const requirements = document.getElementById('passwordRequirements');

            if (password.length === 0) {
                strengthBar.innerHTML = '';
                requirements.style.display = 'none';
                return;
            }

            // Show requirements during signup
            requirements.style.display = 'block';

            const { checks } = validatePasswordStrength(password);

            // Update requirement checkmarks
            document.getElementById('reqLength').className = checks.length ? 'req-item valid' : 'req-item';
            document.getElementById('reqLength').textContent = checks.length ? '✓ At least 10 characters' : '✗ At least 10 characters';

            document.getElementById('reqUpper').className = checks.uppercase ? 'req-item valid' : 'req-item';
            document.getElementById('reqUpper').textContent = checks.uppercase ? '✓ One uppercase letter' : '✗ One uppercase letter';

            document.getElementById('reqLower').className = checks.lowercase ? 'req-item valid' : 'req-item';
            document.getElementById('reqLower').textContent = checks.lowercase ? '✓ One lowercase letter' : '✗ One lowercase letter';

            document.getElementById('reqNumber').className = checks.number ? 'req-item valid' : 'req-item';
            document.getElementById('reqNumber').textContent = checks.number ? '✓ One number' : '✗ One number';

            document.getElementById('reqSpecial').className = checks.special ? 'req-item valid' : 'req-item';
            document.getElementById('reqSpecial').textContent = checks.special ? '✓ One special character' : '✗ One special character';

            // Calculate strength
            const score = Object.values(checks).filter(v => v).length;
            let strengthClass = '';

            if (score <= 2) {
                strengthClass = 'strength-weak';
            } else if (score <= 4) {
                strengthClass = 'strength-medium';
            } else {
                strengthClass = 'strength-strong';
            }

            strengthBar.innerHTML = `<div class="password-strength-bar ${strengthClass}"></div>`;
        }

        // ============================================
        // AUTH ERROR DISPLAY
        // ============================================
        function showAuthError(message) {
            const el = document.getElementById('lockoutMessage');
            el.textContent = message;
            el.className = 'lockout-message';
            el.style.display = 'block';
        }

        function showAuthSuccess(message) {
            const el = document.getElementById('lockoutMessage');
            el.textContent = message;
            el.className = 'success-message';
            el.style.display = 'block';
        }

        function hideAuthError() {
            const el = document.getElementById('lockoutMessage');
            el.style.display = 'none';
            el.textContent = '';
        }

        // ============================================
        // AUTH HANDLERS
        // ============================================
        async function handleLogin() {
            const username = document.getElementById('authUsername').value.trim();
            const password = document.getElementById('authPassword').value.trim();

            hideAuthError();

            if (!username || !password) {
                showAuthError('Please enter both username and password');
                return;
            }

            try {
                const res = await fetch('/api/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                const data = await res.json();

                if (!res.ok) {
                    showAuthError(data.error || 'Login failed');
                    return;
                }

                currentUser = { username, isPro: data.isPro, hasCompletedIntake: data.hasCompletedIntake };

                // Clear form
                document.getElementById('authUsername').value = '';
                document.getElementById('authPassword').value = '';

                render(currentUser.hasCompletedIntake ? 'progress' : 'intake');
            } catch (err) {
                showAuthError('Connection error. Please try again.');
            }
        }

        async function handleSignup() {
            const username = document.getElementById('authUsername').value.trim();
            const password = document.getElementById('authPassword').value.trim();

            hideAuthError();

            if (!username || !password) {
                showAuthError('Please enter both username and password');
                return;
            }

            // Client-side validation before hitting the server
            if (username.length < 3 || username.length > 30) {
                showAuthError('Username must be 3–30 characters');
                return;
            }

            if (!/^[a-zA-Z0-9_]+$/.test(username)) {
                showAuthError('Username can only contain letters, numbers, and underscores');
                return;
            }

            const { checks } = validatePasswordStrength(password);
            if (!checks.length)    { showAuthError('Password must be at least 10 characters'); return; }
            if (!checks.uppercase) { showAuthError('Password must contain an uppercase letter'); return; }
            if (!checks.lowercase) { showAuthError('Password must contain a lowercase letter'); return; }
            if (!checks.number)    { showAuthError('Password must contain a number'); return; }
            if (!checks.special)   { showAuthError('Password must contain a special character'); return; }

            if (isCommonPassword(password)) {
                showAuthError('This password is too common. Please choose a stronger one.');
                return;
            }

            if (containsUserInfo(password, username)) {
                showAuthError('Password cannot contain your username');
                return;
            }

            try {
                const res = await fetch('/api/signup', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password })
                });
                const data = await res.json();

                if (!res.ok) {
                    showAuthError(data.error || 'Signup failed');
                    return;
                }

                showAuthSuccess('Account created! Please log in.');
                document.getElementById('authPassword').value = '';
                updatePasswordStrength();
            } catch (err) {
                showAuthError('Connection error. Please try again.');
            }
        }

        async function logout() {
            try {
                await fetch('/api/logout', { method: 'POST' });
            } catch (_) { /* ignore network errors — log out locally regardless */ }
            currentUser = null;
            sessionStorage.removeItem('activeSessionId');
            tempSessionData = { initialStress: 5, chatHistory: [] };
            render('auth');
        }

        // ============================================
        // "RIGHT TO DISAPPEAR" - TWO DELETE OPTIONS
        // ============================================

        // OPTION 1: Delete Session Chats Only
        function confirmDeleteSessions() {
            const step1 = confirm(
                "🗑️ DELETE SESSION CHATS - STEP 1 of 2\n\n" +
                "This will PERMANENTLY delete:\n" +
                "• All therapy session history\n" +
                "• All chat transcripts\n" +
                "• All stress ratings and takeaways\n\n" +
                "Your intake form and account will remain intact.\n\n" +
                "Continue to Step 2?"
            );

            if (!step1) return;

            const step2 = confirm(
                "🗑️ FINAL CONFIRMATION - STEP 2 of 2\n\n" +
                "Delete all session chats?\n" +
                "This CANNOT be undone.\n\n" +
                "Click OK to delete sessions."
            );

            if (step2) {
                deleteSessionsOnly();
            }
        }

        async function deleteSessionsOnly() {
            if (!currentUser) return;

            try {
                const res = await fetch('/api/sessions', { method: 'DELETE' });
                if (!res.ok) {
                    alert('❌ Could not delete sessions. Please try again.');
                    return;
                }
            } catch (_) {
                alert('❌ Connection error. Sessions not deleted.');
                return;
            }

            alert(
                "✓ Sessions Deleted\n\n" +
                "All therapy sessions have been deleted.\n" +
                "Your intake form and account remain intact."
            );

            sessionStorage.removeItem('activeSessionId');
            tempSessionData = { initialStress: 5, chatHistory: [] };
            render('progress');
        }

        // OPTION 2: Wipe Entire Account
        function confirmDeleteAccount() {
            const step1 = confirm(
                "⚠️ WIPE ACCOUNT - STEP 1 of 2\n\n" +
                "This will PERMANENTLY delete:\n" +
                "• All therapy sessions and chats\n" +
                "• Your intake form data\n" +
                "• YOUR ENTIRE ACCOUNT\n\n" +
                "You will need to create a NEW account.\n\n" +
                "Continue to Step 2?"
            );

            if (!step1) return;

            const step2 = confirm(
                "⚠️ FINAL CONFIRMATION - STEP 2 of 2\n\n" +
                "WIPE YOUR ENTIRE ACCOUNT?\n\n" +
                "• All data will be PERMANENTLY deleted\n" +
                "• You will be logged out\n" +
                "• This CANNOT be undone\n\n" +
                "Click OK to wipe account completely."
            );

            if (step2) {
                wipeAccount();
            }
        }

        async function wipeAccount() {
            if (!currentUser) return;

            try {
                const res = await fetch('/api/account', { method: 'DELETE' });
                if (!res.ok) {
                    alert('❌ Could not delete account. Please try again.');
                    return;
                }
            } catch (_) {
                alert('❌ Connection error. Account not deleted.');
                return;
            }

            alert(
                "✓ Account Wiped\n\n" +
                "Your account has been permanently deleted.\n" +
                "All data has been removed.\n\n" +
                "You can create a new account if desired."
            );

            currentUser = null;
            sessionStorage.removeItem('activeSessionId');
            tempSessionData = { initialStress: 5, chatHistory: [] };
            render('auth');
        }

        // ============================================
        // ROUTING WITH INTAKE GATEKEEPER
        // ============================================
        function render(route) {
            // Intake Gatekeeper Logic
            if (currentUser && !currentUser.hasCompletedIntake) {
                if (route === 'progress' || route === 'pre-check' || route === 'session' || route === 'post-check') {
                    route = 'intake'; // Force redirect to intake
                }
            }

            // Hide all views
            const views = document.querySelectorAll('.view');
            views.forEach(view => view.classList.remove('active'));

            // Show target view
            const targetView = document.getElementById(`${route}-view`);
            if (targetView) {
                targetView.classList.add('active');
            }

            // Update header visibility
            const header = document.getElementById('appHeader');
            if (currentUser && route !== 'auth') {
                header.classList.add('visible');
                document.getElementById('headerUsername').textContent = currentUser.username;
            } else {
                header.classList.remove('visible');
            }

            // Clear auth form when leaving auth view
            if (route !== 'auth') {
                document.getElementById('authPassword').value = '';
                document.getElementById('passwordStrength').innerHTML = '';
                document.getElementById('passwordRequirements').style.display = 'none';
                hideAuthError();
            }

            // View-specific rendering
            if (route === 'progress') {
                renderProfileSummary();
                renderSessionHistory();
            } else if (route === 'intake') {
                loadIntakeForm();
            }
        }

        // ============================================
        // INTAKE FORM HELPERS
        // ============================================
        function updateIntakeSlider(displayId, value) {
            document.getElementById(displayId).textContent = value;
        }

        function getRadioValue(name) {
            const radio = document.querySelector(`input[name="${name}"]:checked`);
            return radio ? radio.value : '';
        }

        function getCheckboxValues(name) {
            const checkboxes = document.querySelectorAll(`input[name="${name}"]:checked`);
            return Array.from(checkboxes).map(cb => cb.value);
        }

        function setRadioValue(name, value) {
            const radio = document.querySelector(`input[name="${name}"][value="${value}"]`);
            if (radio) radio.checked = true;
        }

        function setCheckboxValues(name, values) {
            if (!values || !Array.isArray(values)) return;
            values.forEach(value => {
                const checkbox = document.querySelector(`input[name="${name}"][value="${value}"]`);
                if (checkbox) checkbox.checked = true;
            });
        }

        // ============================================
        // INTAKE FORM
        // ============================================
        async function loadIntakeForm() {
            const banner = document.getElementById('intakeLoadingBanner');
            if (banner) banner.style.display = 'flex';

            let intake;
            try {
                const res = await fetch('/api/intake');
                if (res.ok) {
                    const data = await res.json();
                    intake = data.data;
                }
            } catch (_) { /* no draft saved yet — leave form blank */ }

            if (banner) banner.style.display = 'none';
            if (!intake) return;

            // Section 1: Basic Information
            document.getElementById('fullName').value = intake.fullName || '';
            document.getElementById('preferredName').value = intake.preferredName || '';
            document.getElementById('pronouns').value = intake.pronouns || '';
            document.getElementById('dob').value = intake.dob || '';
            document.getElementById('genderIdentity').value = intake.genderIdentity || '';
            document.getElementById('sexAssigned').value = intake.sexAssigned || '';
            document.getElementById('phone').value = intake.phone || '';
            document.getElementById('email').value = intake.email || '';
            document.getElementById('address').value = intake.address || '';
            document.getElementById('emergencyContact').value = intake.emergencyContact || '';

            // Section 2: Presenting Concerns
            document.getElementById('presenting').value = intake.presenting || '';
            setRadioValue('duration', intake.duration);
            setCheckboxValues('issues', intake.issues);
            document.getElementById('distressLevel').value = intake.distressLevel || 5;
            updateIntakeSlider('distressValue', intake.distressLevel || 5);

            // Section 3: Risk Assessment
            setRadioValue('selfharm', intake.selfharm);
            setRadioValue('attempts', intake.attempts);
            document.getElementById('attemptsWhen').value = intake.attemptsWhen || '';
            setRadioValue('harmOthers', intake.harmOthers);
            setRadioValue('selfharmHistory', intake.selfharmHistory);
            setRadioValue('currentlySafe', intake.currentlySafe);

            // Section 4: Mental Health History
            setRadioValue('prevTherapy', intake.prevTherapy);
            document.getElementById('therapyDetails').value = intake.therapyDetails || '';
            document.getElementById('whatWorked').value = intake.whatWorked || '';
            document.getElementById('whatDidntWork').value = intake.whatDidntWork || '';
            document.getElementById('prevDiagnoses').value = intake.prevDiagnoses || '';
            setRadioValue('hospitalizations', intake.hospitalizations);
            document.getElementById('hospitalizationDetails').value = intake.hospitalizationDetails || '';

            // Section 5: Medical
            document.getElementById('medications').value = intake.medications || '';
            setRadioValue('psychiatrist', intake.psychiatrist);
            document.getElementById('medicalConditions').value = intake.medicalConditions || '';
            setRadioValue('sleep', intake.sleep);

            // Section 6: Substance Use
            setRadioValue('alcohol', intake.alcohol);
            setRadioValue('marijuana', intake.marijuana);
            setRadioValue('cocaine', intake.cocaine);
            setRadioValue('opioids', intake.opioids);
            setRadioValue('otherSubstance', intake.otherSubstance);
            document.getElementById('substanceConcerns').value = intake.substanceConcerns || '';

            // Section 7: Trauma
            setCheckboxValues('trauma', intake.trauma);
            setRadioValue('traumaSymptoms', intake.traumaSymptoms);

            // Section 8: Relationships
            setRadioValue('relStatus', intake.relStatus);
            setRadioValue('children', intake.children);
            document.getElementById('childrenAges').value = intake.childrenAges || '';
            document.getElementById('socialSupport').value = intake.socialSupport || 5;
            updateIntakeSlider('socialValue', intake.socialSupport || 5);
            document.getElementById('relationalStress').value = intake.relationalStress || '';

            // Section 9: Functioning
            setRadioValue('workStatus', intake.workStatus);
            setRadioValue('performance', intake.performance);
            setRadioValue('functioning', intake.functioning);

            // Section 10: Therapy Preference
            setCheckboxValues('therapistType', intake.therapistType);
            setCheckboxValues('therapyStyle', intake.therapyStyle);

            // Section 11: Cultural
            document.getElementById('ethnicity').value = intake.ethnicity || '';
            document.getElementById('religion').value = intake.religion || '';
            document.getElementById('culturalConsiderations').value = intake.culturalConsiderations || '';
            document.getElementById('primaryLanguage').value = intake.primaryLanguage || '';

            // Section 12: Goals
            document.getElementById('therapySuccess').value = intake.therapySuccess || '';
            document.getElementById('goal1').value = intake.goal1 || '';
            document.getElementById('goal2').value = intake.goal2 || '';
            document.getElementById('goal3').value = intake.goal3 || '';
        }

        function collectIntakeData() {
            return {
                // Section 1: Basic Information
                fullName: document.getElementById('fullName').value.trim(),
                preferredName: document.getElementById('preferredName').value.trim(),
                pronouns: document.getElementById('pronouns').value.trim(),
                dob: document.getElementById('dob').value,
                genderIdentity: document.getElementById('genderIdentity').value.trim(),
                sexAssigned: document.getElementById('sexAssigned').value,
                phone: document.getElementById('phone').value.trim(),
                email: document.getElementById('email').value.trim(),
                address: document.getElementById('address').value.trim(),
                emergencyContact: document.getElementById('emergencyContact').value.trim(),

                // Section 2: Presenting Concerns
                presenting: document.getElementById('presenting').value.trim(),
                duration: getRadioValue('duration'),
                issues: getCheckboxValues('issues'),
                distressLevel: parseInt(document.getElementById('distressLevel').value),

                // Section 3: Risk Assessment
                selfharm: getRadioValue('selfharm'),
                attempts: getRadioValue('attempts'),
                attemptsWhen: document.getElementById('attemptsWhen').value.trim(),
                harmOthers: getRadioValue('harmOthers'),
                selfharmHistory: getRadioValue('selfharmHistory'),
                currentlySafe: getRadioValue('currentlySafe'),

                // Section 4: Mental Health History
                prevTherapy: getRadioValue('prevTherapy'),
                therapyDetails: document.getElementById('therapyDetails').value.trim(),
                whatWorked: document.getElementById('whatWorked').value.trim(),
                whatDidntWork: document.getElementById('whatDidntWork').value.trim(),
                prevDiagnoses: document.getElementById('prevDiagnoses').value.trim(),
                hospitalizations: getRadioValue('hospitalizations'),
                hospitalizationDetails: document.getElementById('hospitalizationDetails').value.trim(),

                // Section 5: Medical
                medications: document.getElementById('medications').value.trim(),
                psychiatrist: getRadioValue('psychiatrist'),
                medicalConditions: document.getElementById('medicalConditions').value.trim(),
                sleep: getRadioValue('sleep'),

                // Section 6: Substance Use
                alcohol: getRadioValue('alcohol'),
                marijuana: getRadioValue('marijuana'),
                cocaine: getRadioValue('cocaine'),
                opioids: getRadioValue('opioids'),
                otherSubstance: getRadioValue('otherSubstance'),
                substanceConcerns: document.getElementById('substanceConcerns').value.trim(),

                // Section 7: Trauma
                trauma: getCheckboxValues('trauma'),
                traumaSymptoms: getRadioValue('traumaSymptoms'),

                // Section 8: Relationships
                relStatus: getRadioValue('relStatus'),
                children: getRadioValue('children'),
                childrenAges: document.getElementById('childrenAges').value.trim(),
                socialSupport: parseInt(document.getElementById('socialSupport').value),
                relationalStress: document.getElementById('relationalStress').value.trim(),

                // Section 9: Functioning
                workStatus: getRadioValue('workStatus'),
                performance: getRadioValue('performance'),
                functioning: getRadioValue('functioning'),

                // Section 10: Therapy Preference
                therapistType: getCheckboxValues('therapistType'),
                therapyStyle: getCheckboxValues('therapyStyle'),

                // Section 11: Cultural
                ethnicity: document.getElementById('ethnicity').value.trim(),
                religion: document.getElementById('religion').value.trim(),
                culturalConsiderations: document.getElementById('culturalConsiderations').value.trim(),
                primaryLanguage: document.getElementById('primaryLanguage').value.trim(),

                // Section 12: Goals
                therapySuccess: document.getElementById('therapySuccess').value.trim(),
                goal1: document.getElementById('goal1').value.trim(),
                goal2: document.getElementById('goal2').value.trim(),
                goal3: document.getElementById('goal3').value.trim(),

                completedAt: new Date().toISOString()
            };
        }

        function validateEmail(email) {
            const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
            return emailRegex.test(email);
        }

        function validatePhone(phone) {
            // Remove all non-digits
            const digits = phone.replace(/\D/g, '');
            // Must be 10 or 11 digits (with optional country code)
            return digits.length >= 10 && digits.length <= 11;
        }

        function validateMinWords(text, minWords) {
            if (!text) return false;
            const words = text.trim().split(/\s+/).filter(word => word.length > 0);
            return words.length >= minWords;
        }

        function validateMinLength(text, minLength) {
            return text && text.trim().length >= minLength;
        }

        async function completeIntake() {
            const intakeData = collectIntakeData();
            const errors = [];

            // Section 1: Basic Information - ALL MANDATORY
            if (!intakeData.fullName) {
                errors.push('• Full Name is required');
            }
            if (!intakeData.preferredName) {
                errors.push('• Preferred Name is required');
            }
            if (!intakeData.pronouns) {
                errors.push('• Pronouns are required');
            }
            if (!intakeData.dob) {
                errors.push('• Date of Birth is required');
            }
            if (!intakeData.genderIdentity) {
                errors.push('• Gender Identity is required');
            }
            if (!intakeData.sexAssigned) {
                errors.push('• Sex Assigned at Birth is required');
            }

            // Email validation
            if (!intakeData.email) {
                errors.push('• Email is required');
            } else if (!validateEmail(intakeData.email)) {
                errors.push('• Email must be a valid email address (e.g., name@example.com)');
            }

            // Phone validation
            if (!intakeData.phone) {
                errors.push('• Phone Number is required');
            } else if (!validatePhone(intakeData.phone)) {
                errors.push('• Phone Number must be valid (10-11 digits)');
            }

            // Address validation - must be meaningful
            if (!intakeData.address) {
                errors.push('• Address (City/State) is required');
            } else if (!validateMinLength(intakeData.address, 10)) {
                errors.push('• Address must be at least 10 characters (e.g., "Boston, MA")');
            }

            if (!intakeData.emergencyContact) {
                errors.push('• Emergency Contact is required');
            } else if (!validateMinWords(intakeData.emergencyContact, 3)) {
                errors.push('• Emergency Contact must include Name, Relationship, and Phone (at least 3 words)');
            }

            // Section 2: Presenting Concerns - MANDATORY
            if (!intakeData.presenting) {
                errors.push('• "What brings you to therapy" is required');
            } else if (!validateMinWords(intakeData.presenting, 10)) {
                errors.push('• "What brings you to therapy" must be at least 10 words (not just a one-word answer)');
            }

            if (!intakeData.duration) {
                errors.push('• Duration of concern is required');
            }

            if (!intakeData.issues || intakeData.issues.length === 0) {
                errors.push('• Please select at least one Primary Issue');
            }

            // Section 3: Risk Assessment - ALL MANDATORY
            if (!intakeData.selfharm) {
                errors.push('• "Thoughts of harming yourself" question is required');
            }
            if (!intakeData.attempts) {
                errors.push('• "History of suicide attempts" question is required');
            }
            if (!intakeData.harmOthers) {
                errors.push('• "Thoughts of harming others" question is required');
            }
            if (!intakeData.selfharmHistory) {
                errors.push('• "History of self-harm" question is required');
            }
            if (!intakeData.currentlySafe) {
                errors.push('• "Are you currently safe" question is required');
            }

            // Section 4: Mental Health History - MANDATORY
            if (!intakeData.prevTherapy) {
                errors.push('• "Previous therapy" question is required');
            }

            // Conditional: Only required if they answered "yes" to previous therapy
            if (intakeData.prevTherapy === 'yes') {
                if (!intakeData.whatWorked) {
                    errors.push('• "What worked well in past therapy" is required when you have had previous therapy');
                } else if (!validateMinWords(intakeData.whatWorked, 5)) {
                    errors.push('• "What worked well" must be at least 5 words');
                }

                if (!intakeData.whatDidntWork) {
                    errors.push('• "What did NOT work well" is required when you have had previous therapy');
                } else if (!validateMinWords(intakeData.whatDidntWork, 5)) {
                    errors.push('• "What did NOT work well" must be at least 5 words');
                }
            }

            // Conditional: Only required if they answered "yes" to suicide attempts
            if (intakeData.attempts === 'yes') {
                if (!intakeData.attemptsWhen) {
                    errors.push('• "When" is required when you have history of suicide attempts');
                }
            }

            if (!intakeData.hospitalizations) {
                errors.push('• "Psychiatric hospitalizations" question is required');
            }

            // Conditional: Only required if they answered "yes" to hospitalizations
            if (intakeData.hospitalizations === 'yes') {
                if (!intakeData.hospitalizationDetails) {
                    errors.push('• Hospitalization details are required when you have been hospitalized');
                }
            }

            // Section 5: Medical - MANDATORY
            if (!intakeData.psychiatrist) {
                errors.push('• "Current psychiatrist" question is required');
            }
            if (!intakeData.sleep) {
                errors.push('• "Sleep quality" question is required');
            }

            // Section 6: Substance Use - ALL MANDATORY
            if (!intakeData.alcohol) {
                errors.push('• Alcohol frequency is required');
            }
            if (!intakeData.marijuana) {
                errors.push('• Marijuana frequency is required');
            }
            if (!intakeData.cocaine) {
                errors.push('• Cocaine frequency is required');
            }
            if (!intakeData.opioids) {
                errors.push('• Opioids frequency is required');
            }
            if (!intakeData.otherSubstance) {
                errors.push('• Other substance frequency is required');
            }

            // Section 7: Trauma - MANDATORY
            if (!intakeData.trauma || intakeData.trauma.length === 0) {
                errors.push('• Please select trauma history (select "None" if not applicable)');
            }
            if (!intakeData.traumaSymptoms) {
                errors.push('• "Flashbacks/nightmares" question is required');
            }

            // Section 8: Relationships - MANDATORY
            if (!intakeData.relStatus) {
                errors.push('• Relationship status is required');
            }
            if (!intakeData.children) {
                errors.push('• "Children" question is required');
            }

            // Conditional: Only required if they answered "yes" to children
            if (intakeData.children === 'yes') {
                if (!intakeData.childrenAges) {
                    errors.push('• Children ages are required when you have children');
                }
            }

            // Section 9: Functioning - ALL MANDATORY
            if (!intakeData.workStatus) {
                errors.push('• Work/School status is required');
            }
            if (!intakeData.performance) {
                errors.push('• "Performance impacted by mental health" is required');
            }
            if (!intakeData.functioning) {
                errors.push('• "Daily functioning" is required');
            }

            // Section 10: Therapy Preference - MANDATORY
            if (!intakeData.therapistType || intakeData.therapistType.length === 0) {
                errors.push('• Please select at least one Therapist Type preference (or "No preference")');
            }
            if (!intakeData.therapyStyle || intakeData.therapyStyle.length === 0) {
                errors.push('• Please select at least one Therapy Style preference');
            }

            // Section 11: Cultural - MANDATORY
            if (!intakeData.ethnicity) {
                errors.push('• Ethnicity/Race is required');
            }
            if (!intakeData.religion) {
                errors.push('• Religion/Spirituality is required (can be "None" or "Prefer not to say")');
            }
            if (!intakeData.primaryLanguage) {
                errors.push('• Primary language is required');
            }

            // Section 12: Goals - MANDATORY with word counts
            if (!intakeData.therapySuccess) {
                errors.push('• "What would success look like" is required');
            } else if (!validateMinWords(intakeData.therapySuccess, 10)) {
                errors.push('• "What would success look like" must be at least 10 words (provide a meaningful description)');
            }

            if (!intakeData.goal1) {
                errors.push('• Top Goal #1 is required');
            } else if (!validateMinWords(intakeData.goal1, 3)) {
                errors.push('• Top Goal #1 must be at least 3 words');
            }

            if (!intakeData.goal2) {
                errors.push('• Top Goal #2 is required');
            } else if (!validateMinWords(intakeData.goal2, 3)) {
                errors.push('• Top Goal #2 must be at least 3 words');
            }

            if (!intakeData.goal3) {
                errors.push('• Top Goal #3 is required');
            } else if (!validateMinWords(intakeData.goal3, 3)) {
                errors.push('• Top Goal #3 must be at least 3 words');
            }

            // If there are any errors, show them
            if (errors.length > 0) {
                const errorMessage = '❌ PLEASE COMPLETE ALL REQUIRED FIELDS:\n\n' + errors.join('\n');
                alert(errorMessage);
                return;
            }

            // Crisis check (after all validation passes)
            if (intakeData.currentlySafe === 'no' || intakeData.selfharm === 'plan') {
                alert('⚠️ IMMEDIATE CRISIS DETECTED\n\nPlease call:\n• 988 (Suicide & Crisis Lifeline)\n• 911 (Emergency Services)\n\nYour safety is our top priority.');
                return;
            }

            // All validation passed — save to backend
            try {
                const res = await fetch('/api/intake', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ data: intakeData, completed: true })
                });
                if (!res.ok) {
                    const err = await res.json().catch(() => ({}));
                    alert('❌ Could not save intake: ' + (err.error || 'Server error'));
                    return;
                }
            } catch (_) {
                alert('❌ Connection error. Please check your internet and try again.');
                return;
            }

            if (currentUser) currentUser.hasCompletedIntake = true;
            alert('✅ Intake form submitted successfully!\n\nAll required information has been validated and saved.');
            render('progress');
        }

        async function saveDraft() {
            const intakeData = collectIntakeData();
            try {
                const res = await fetch('/api/intake', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ data: intakeData, completed: false })
                });
                if (!res.ok) {
                    alert('❌ Could not save draft. Please try again.');
                    return;
                }
            } catch (_) {
                alert('❌ Connection error. Draft not saved.');
                return;
            }
            alert('✅ Draft saved! You can continue later from any device.');
        }

        // ============================================
        // PROGRESS/DASHBOARD VIEW
        // ============================================
        async function renderProfileSummary() {
            const container = document.getElementById('profileSummary');
            if (!currentUser) return;

            let intake;
            try {
                const res = await fetch('/api/intake');
                if (res.ok) intake = (await res.json()).data;
            } catch (_) {}

            if (!intake) {
                container.innerHTML = '<p style="text-align: center; opacity: 0.7;">Complete your intake form to see your profile summary.</p>';
                return;
            }

            // Calculate age from DOB
            let age = '';
            if (intake.dob) {
                const dob = new Date(intake.dob);
                const today = new Date();
                age = Math.floor((today - dob) / (365.25 * 24 * 60 * 60 * 1000));
            }

            container.innerHTML = `
                <h3>${intake.preferredName || intake.fullName}</h3>
                <p><strong>Age:</strong> ${age} | <strong>Pronouns:</strong> ${intake.pronouns || 'Not specified'}</p>
                <p><strong>Contact:</strong> ${intake.email} | ${intake.phone}</p>
                <hr style="margin: 15px 0; border: none; border-top: 1px solid rgba(135, 169, 107, 0.3);">
                <p style="margin-top: 10px;"><strong>Presenting Concern:</strong></p>
                <p style="font-style: italic; margin-top: 5px;">"${intake.presenting}"</p>
                ${intake.issues && intake.issues.length > 0 ? `
                    <p style="margin-top: 10px;"><strong>Primary Issues:</strong> ${intake.issues.join(', ')}</p>
                ` : ''}
                ${intake.distressLevel ? `
                    <p style="margin-top: 10px;"><strong>Current Distress Level:</strong> <span style="color: var(--sage); font-weight: bold;">${intake.distressLevel}/10</span></p>
                ` : ''}
                ${intake.therapySuccess ? `
                    <p style="margin-top: 10px;"><strong>Therapy Goals:</strong></p>
                    <p style="font-style: italic; margin-top: 5px;">"${intake.therapySuccess}"</p>
                ` : ''}
            `;
        }

        async function renderSessionHistory() {
            if (!currentUser) return;

            const container = document.getElementById('sessionHistory');

            let sessions = [];
            try {
                const res = await fetch('/api/sessions');
                if (res.ok) sessions = await res.json();
            } catch (_) {}

            if (sessions.length === 0) {
                container.innerHTML = '<div class="empty-state">No sessions yet. Start your first session to begin tracking your progress.</div>';
                return;
            }

            container.innerHTML = sessions.map(session => {
                const date = new Date(session.startedAt);
                const formattedDate = date.toLocaleDateString('en-US', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit'
                });

                const initial = session.initialMood ?? '—';
                const final = session.finalMood ?? '—';
                let improvementText = '→ In progress';
                if (session.initialMood != null && session.finalMood != null) {
                    const diff = session.initialMood - session.finalMood;
                    improvementText = diff > 0 ? `↓ ${diff} (Improved)` : diff < 0 ? `↑ ${Math.abs(diff)} (Increased)` : '→ 0 (Stable)';
                }

                const card = document.createElement('div');
                card.className = 'session-card';

                const header = document.createElement('div');
                header.className = 'session-header';

                const dateSpan = document.createElement('span');
                dateSpan.className = 'session-date';
                dateSpan.textContent = formattedDate;

                const improvementSpan = document.createElement('span');
                improvementSpan.textContent = improvementText;

                header.appendChild(dateSpan);
                header.appendChild(improvementSpan);

                const indicator = document.createElement('div');
                indicator.className = 'stress-indicator';
                indicator.innerHTML = `
                    <span>Initial: <span class="stress-value">${initial}/10</span></span>
                    <span>Final: <span class="stress-value">${final}/10</span></span>
                `;

                card.appendChild(header);
                card.appendChild(indicator);

                if (session.takeaway) {
                    const takeaway = document.createElement('div');
                    takeaway.className = 'takeaway';
                    takeaway.textContent = `"${session.takeaway}"`;
                    card.appendChild(takeaway);
                }

                if (session.summary) {
                    const summary = document.createElement('div');
                    summary.className = 'session-summary';
                    summary.textContent = session.summary;
                    card.appendChild(summary);
                }

                return card.outerHTML;
            }).join('');
        }

        // ============================================
        // SESSION FLOW
        // ============================================
        function startNewSession() {
            sessionStorage.removeItem('activeSessionId');
            tempSessionData = { initialStress: 5, chatHistory: [] };
            document.getElementById('stressSlider').value = 5;
            updateSliderValue('stressValue', 5);
            render('pre-check');
        }

        function updateSliderValue(elementId, value) {
            document.getElementById(elementId).textContent = value;
        }

        async function enterTherapySession() {
            tempSessionData.initialStress = parseInt(document.getElementById('stressSlider').value);

            // Create session in DB and store the returned sessionId
            try {
                const res = await fetch('/api/sessions', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ initialMood: tempSessionData.initialStress })
                });
                if (res.ok) {
                    const data = await res.json();
                    tempSessionData.sessionId = data.sessionId;
                    sessionStorage.setItem('activeSessionId', data.sessionId);
                }
            } catch (_) { /* session will work; messages just won't persist */ }

            const name = currentUser.username || 'there';
            tempSessionData.chatHistory = [{
                type: 'therapist',
                text: `Hello ${name}, I'm here to listen. What would you like to talk about today?`
            }];
            renderChatMessages();
            render('session');
        }

        // ============================================
        // CHAT FUNCTIONS
        // ============================================
        function renderChatMessages() {
            const chatContainer = document.getElementById('chatMessages');
            chatContainer.innerHTML = '';

            tempSessionData.chatHistory.forEach(msg => {
                const messageDiv = document.createElement('div');
                messageDiv.className = `message ${msg.type}`;
                messageDiv.textContent = msg.text; // XSS-safe
                chatContainer.appendChild(messageDiv);
            });

            // Scroll to bottom
            chatContainer.scrollTop = chatContainer.scrollHeight;
        }

        function handleChatKeyPress(event) {
            if (event.key === 'Enter') {
                sendMessage();
            }
        }

        // ============================================
        // CHAT API
        // ============================================
        async function callChatAPI(userText) {
            const history = tempSessionData.chatHistory
                .filter(m => m.type === 'user' || m.type === 'therapist')
                .map(m => ({
                    role: m.type === 'user' ? 'user' : 'assistant',
                    content: m.text
                }));

            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: userText,
                    history,
                    sessionId: tempSessionData.sessionId || null
                })
            });

            const data = await response.json();
            if (data.error) throw new Error(data.error);
            return data.reply;
        }

        async function sendMessage() {
            const input = document.getElementById('chatInput');
            const sendBtn = document.querySelector('#session-view .chat-input-group button');
            const text = input.value.trim();

            if (!text) return;

            // Add user message
            tempSessionData.chatHistory.push({ type: 'user', text });
            renderChatMessages();
            input.value = '';
            input.disabled = true;
            if (sendBtn) sendBtn.disabled = true;

            // Show thinking indicator
            tempSessionData.chatHistory.push({ type: 'thinking', text: 'Thinking...' });
            renderChatMessages();

            try {
                const reply = await callChatAPI(text);
                tempSessionData.chatHistory.pop(); // remove thinking
                tempSessionData.chatHistory.push({ type: 'therapist', text: reply });
            } catch (err) {
                tempSessionData.chatHistory.pop(); // remove thinking
                tempSessionData.chatHistory.push({
                    type: 'therapist',
                    text: "I'm having trouble connecting right now. Please check your connection and try again."
                });
            } finally {
                input.disabled = false;
                if (sendBtn) sendBtn.disabled = false;
                renderChatMessages();
                input.focus();
            }
        }

        function endSession() {
            document.getElementById('resolutionSlider').value = 5;
            updateSliderValue('resolutionValue', 5);
            document.getElementById('takeaway').value = '';
            render('post-check');
        }

        // ============================================
        // COMPLETE SESSION & SAVE
        // ============================================
        async function completeSession() {
            const finalStress = parseInt(document.getElementById('resolutionSlider').value);
            const takeaway = document.getElementById('takeaway').value.trim();

            if (!takeaway) {
                alert('Please share your key takeaway before completing the session');
                return;
            }

            if (tempSessionData.sessionId) {
                try {
                    await fetch(`/api/sessions/${tempSessionData.sessionId}/complete`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ finalMood: finalStress, whatWorked: takeaway })
                    });
                } catch (_) { /* best-effort — still navigate to progress */ }
            }

            sessionStorage.removeItem('activeSessionId');
            tempSessionData = { initialStress: 5, chatHistory: [] };
            render('progress');
        }

        // ============================================
        // CRISIS HELP
        // ============================================
        function showCrisisHelp() {
            alert(`🆘 CRISIS RESOURCES 🆘

If you're in immediate danger, please call emergency services.

US Resources:
• National Suicide Prevention Lifeline: 988
• Crisis Text Line: Text HOME to 741741
• SAMHSA National Helpline: 1-800-662-4357

International:
• Find local resources at findahelpline.com

You are not alone. Help is available 24/7.`);
        }

        // ============================================
        // INITIALIZATION
        // ============================================
        window.addEventListener('load', async () => {
            try {
                const res = await fetch('/api/me');
                if (res.ok) {
                    const data = await res.json();
                    currentUser = { username: data.username, isPro: data.isPro, hasCompletedIntake: data.hasCompletedIntake };
                    // Restore in-progress session across refreshes
                    const savedSessionId = sessionStorage.getItem('activeSessionId');
                    if (savedSessionId) {
                        try {
                            const sRes = await fetch(`/api/sessions/${savedSessionId}`);
                            if (sRes.ok) {
                                const sData = await sRes.json();
                                if (!sData.completedAt) {
                                    // Session is still active — restore it
                                    tempSessionData.sessionId = sData.id;
                                    tempSessionData.initialStress = sData.initialMood ?? 5;
                                    tempSessionData.chatHistory = sData.messages.map(m => ({
                                        type: m.role === 'user' ? 'user' : 'therapist',
                                        text: m.content
                                    }));
                                    renderChatMessages();
                                    render('session');
                                    return;
                                } else {
                                    // Session was already completed — clear stale sessionStorage
                                    sessionStorage.removeItem('activeSessionId');
                                }
                            } else {
                                sessionStorage.removeItem('activeSessionId');
                            }
                        } catch (_) {
                            sessionStorage.removeItem('activeSessionId');
                        }
                    }
                    render(currentUser.hasCompletedIntake ? 'progress' : 'intake');
                } else {
                    render('auth');
                }
            } catch (_) {
                render('auth');
            } finally {
                const overlay = document.getElementById('app-loading-overlay');
                if (overlay) overlay.style.display = 'none';
            }
        });