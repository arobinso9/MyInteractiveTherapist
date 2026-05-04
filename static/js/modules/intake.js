// ============================================
// FORM HELPERS
// ============================================
export function updateIntakeSlider(displayId, value) {
    document.getElementById(displayId).textContent = value;
}

function getRadioValue(name) {
    const radio = document.querySelector(`input[name="${name}"]:checked`);
    return radio ? radio.value : '';
}

function getCheckboxValues(name) {
    return Array.from(document.querySelectorAll(`input[name="${name}"]:checked`)).map(cb => cb.value);
}

function setRadioValue(name, value) {
    const radio = document.querySelector(`input[name="${name}"][value="${value}"]`);
    if (radio) radio.checked = true;
}

function setCheckboxValues(name, values) {
    if (!Array.isArray(values)) return;
    values.forEach(value => {
        const cb = document.querySelector(`input[name="${name}"][value="${value}"]`);
        if (cb) cb.checked = true;
    });
}

// ============================================
// VALIDATION HELPERS
// ============================================
function validateEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function validatePhone(phone) {
    const digits = phone.replace(/\D/g, '');
    return digits.length >= 10 && digits.length <= 11;
}

function validateMinWords(text, min) {
    return text && text.trim().split(/\s+/).filter(w => w.length > 0).length >= min;
}

function validateMinLength(text, min) {
    return text && text.trim().length >= min;
}

// ============================================
// LOAD / COLLECT
// ============================================
export async function loadIntakeForm() {
    const banner = document.getElementById('intakeLoadingBanner');
    if (banner) banner.style.display = 'flex';

    let intake;
    try {
        const res = await fetch('/api/intake');
        if (res.ok) intake = (await res.json()).data;
    } catch { /* no draft yet */ }

    if (banner) banner.style.display = 'none';
    if (!intake) return;

    const set = (id, val) => { const el = document.getElementById(id); if (el) el.value = val || ''; };

    set('fullName', intake.fullName);         set('preferredName', intake.preferredName);
    set('pronouns', intake.pronouns);         set('dob', intake.dob);
    set('genderIdentity', intake.genderIdentity); set('sexAssigned', intake.sexAssigned);
    set('phone', intake.phone);               set('email', intake.email);
    set('address', intake.address);           set('emergencyContact', intake.emergencyContact);
    set('presenting', intake.presenting);
    set('distressLevel', intake.distressLevel || 5);
    updateIntakeSlider('distressValue', intake.distressLevel || 5);
    set('therapyDetails', intake.therapyDetails); set('whatWorked', intake.whatWorked);
    set('whatDidntWork', intake.whatDidntWork);   set('prevDiagnoses', intake.prevDiagnoses);
    set('hospitalizationDetails', intake.hospitalizationDetails);
    set('medications', intake.medications);   set('medicalConditions', intake.medicalConditions);
    set('substanceConcerns', intake.substanceConcerns);
    set('childrenAges', intake.childrenAges);
    set('socialSupport', intake.socialSupport || 5);
    updateIntakeSlider('socialValue', intake.socialSupport || 5);
    set('relationalStress', intake.relationalStress);
    set('ethnicity', intake.ethnicity);       set('religion', intake.religion);
    set('culturalConsiderations', intake.culturalConsiderations);
    set('primaryLanguage', intake.primaryLanguage);
    set('therapySuccess', intake.therapySuccess);
    set('goal1', intake.goal1);               set('goal2', intake.goal2); set('goal3', intake.goal3);
    set('attemptsWhen', intake.attemptsWhen);

    ['duration','selfharm','attempts','harmOthers','selfharmHistory','currentlySafe',
     'prevTherapy','hospitalizations','psychiatrist','sleep','alcohol','marijuana',
     'cocaine','opioids','otherSubstance','traumaSymptoms','relStatus','children',
     'workStatus','performance','functioning'].forEach(name => setRadioValue(name, intake[name]));

    setCheckboxValues('issues', intake.issues);
    setCheckboxValues('trauma', intake.trauma);
    setCheckboxValues('therapistType', intake.therapistType);
    setCheckboxValues('therapyStyle', intake.therapyStyle);
}

export function collectIntakeData() {
    const val  = id => (document.getElementById(id)?.value || '').trim();
    const ival = id => parseInt(document.getElementById(id)?.value) || 0;

    return {
        fullName: val('fullName'),                preferredName: val('preferredName'),
        pronouns: val('pronouns'),                dob: val('dob'),
        genderIdentity: val('genderIdentity'),    sexAssigned: val('sexAssigned'),
        phone: val('phone'),                      email: val('email'),
        address: val('address'),                  emergencyContact: val('emergencyContact'),
        presenting: val('presenting'),            duration: getRadioValue('duration'),
        issues: getCheckboxValues('issues'),      distressLevel: ival('distressLevel'),
        selfharm: getRadioValue('selfharm'),      attempts: getRadioValue('attempts'),
        attemptsWhen: val('attemptsWhen'),        harmOthers: getRadioValue('harmOthers'),
        selfharmHistory: getRadioValue('selfharmHistory'), currentlySafe: getRadioValue('currentlySafe'),
        prevTherapy: getRadioValue('prevTherapy'), therapyDetails: val('therapyDetails'),
        whatWorked: val('whatWorked'),            whatDidntWork: val('whatDidntWork'),
        prevDiagnoses: val('prevDiagnoses'),      hospitalizations: getRadioValue('hospitalizations'),
        hospitalizationDetails: val('hospitalizationDetails'),
        medications: val('medications'),          psychiatrist: getRadioValue('psychiatrist'),
        medicalConditions: val('medicalConditions'), sleep: getRadioValue('sleep'),
        alcohol: getRadioValue('alcohol'),        marijuana: getRadioValue('marijuana'),
        cocaine: getRadioValue('cocaine'),        opioids: getRadioValue('opioids'),
        otherSubstance: getRadioValue('otherSubstance'), substanceConcerns: val('substanceConcerns'),
        trauma: getCheckboxValues('trauma'),      traumaSymptoms: getRadioValue('traumaSymptoms'),
        relStatus: getRadioValue('relStatus'),    children: getRadioValue('children'),
        childrenAges: val('childrenAges'),        socialSupport: ival('socialSupport'),
        relationalStress: val('relationalStress'),
        workStatus: getRadioValue('workStatus'),  performance: getRadioValue('performance'),
        functioning: getRadioValue('functioning'),
        therapistType: getCheckboxValues('therapistType'), therapyStyle: getCheckboxValues('therapyStyle'),
        ethnicity: val('ethnicity'),              religion: val('religion'),
        culturalConsiderations: val('culturalConsiderations'), primaryLanguage: val('primaryLanguage'),
        therapySuccess: val('therapySuccess'),
        goal1: val('goal1'),                      goal2: val('goal2'), goal3: val('goal3'),
        completedAt: new Date().toISOString()
    };
}

// ============================================
// VALIDATION
// ============================================
function validateIntake(d) {
    const errors = [];
    const req = (v, msg) => { if (!v) errors.push(msg); };
    const minW = (v, n, msg) => { if (v && !validateMinWords(v, n)) errors.push(msg); else if (!v) errors.push(msg); };

    req(d.fullName,          '• Full Name is required');
    req(d.preferredName,     '• Preferred Name is required');
    req(d.pronouns,          '• Pronouns are required');
    req(d.dob,               '• Date of Birth is required');
    req(d.genderIdentity,    '• Gender Identity is required');
    req(d.sexAssigned,       '• Sex Assigned at Birth is required');

    if (!d.email)                            errors.push('• Email is required');
    else if (!validateEmail(d.email))        errors.push('• Email must be a valid address (e.g., name@example.com)');
    if (!d.phone)                            errors.push('• Phone Number is required');
    else if (!validatePhone(d.phone))        errors.push('• Phone Number must be valid (10–11 digits)');
    if (!d.address)                          errors.push('• Address (City/State) is required');
    else if (!validateMinLength(d.address, 10)) errors.push('• Address must be at least 10 characters');
    if (!d.emergencyContact)                 errors.push('• Emergency Contact is required');
    else if (!validateMinWords(d.emergencyContact, 3)) errors.push('• Emergency Contact must include Name, Relationship, and Phone');

    if (!d.presenting)                        errors.push('• "What brings you to therapy" is required');
    else if (!validateMinWords(d.presenting, 10)) errors.push('• "What brings you to therapy" must be at least 10 words');
    req(d.duration,  '• Duration of concern is required');
    if (!d.issues?.length) errors.push('• Please select at least one Primary Issue');

    req(d.selfharm,         '• "Thoughts of harming yourself" is required');
    req(d.attempts,         '• "History of suicide attempts" is required');
    req(d.harmOthers,       '• "Thoughts of harming others" is required');
    req(d.selfharmHistory,  '• "History of self-harm" is required');
    req(d.currentlySafe,    '• "Are you currently safe" is required');

    req(d.prevTherapy, '• "Previous therapy" question is required');
    if (d.prevTherapy === 'yes') {
        if (!d.whatWorked || !validateMinWords(d.whatWorked, 5))       errors.push('• "What worked well" must be at least 5 words');
        if (!d.whatDidntWork || !validateMinWords(d.whatDidntWork, 5)) errors.push('• "What did NOT work well" must be at least 5 words');
    }
    if (d.attempts === 'yes' && !d.attemptsWhen) errors.push('• "When" is required for history of suicide attempts');
    req(d.hospitalizations, '• "Psychiatric hospitalizations" is required');
    if (d.hospitalizations === 'yes' && !d.hospitalizationDetails) errors.push('• Hospitalization details are required');

    req(d.psychiatrist, '• "Current psychiatrist" is required');
    req(d.sleep,        '• "Sleep quality" is required');
    req(d.alcohol,      '• Alcohol frequency is required');
    req(d.marijuana,    '• Marijuana frequency is required');
    req(d.cocaine,      '• Cocaine frequency is required');
    req(d.opioids,      '• Opioids frequency is required');
    req(d.otherSubstance, '• Other substance frequency is required');

    if (!d.trauma?.length) errors.push('• Please select trauma history (select "None" if not applicable)');
    req(d.traumaSymptoms, '• "Flashbacks/nightmares" is required');
    req(d.relStatus,      '• Relationship status is required');
    req(d.children,       '• "Children" question is required');
    if (d.children === 'yes' && !d.childrenAges) errors.push('• Children ages are required');

    req(d.workStatus,   '• Work/School status is required');
    req(d.performance,  '• "Performance impacted by mental health" is required');
    req(d.functioning,  '• "Daily functioning" is required');

    if (!d.therapistType?.length) errors.push('• Please select at least one Therapist Type preference');
    if (!d.therapyStyle?.length)  errors.push('• Please select at least one Therapy Style preference');

    req(d.ethnicity,       '• Ethnicity/Race is required');
    req(d.religion,        '• Religion/Spirituality is required');
    req(d.primaryLanguage, '• Primary language is required');

    if (!d.therapySuccess || !validateMinWords(d.therapySuccess, 10)) errors.push('• "What would success look like" must be at least 10 words');
    if (!d.goal1 || !validateMinWords(d.goal1, 3)) errors.push('• Top Goal #1 must be at least 3 words');
    if (!d.goal2 || !validateMinWords(d.goal2, 3)) errors.push('• Top Goal #2 must be at least 3 words');
    if (!d.goal3 || !validateMinWords(d.goal3, 3)) errors.push('• Top Goal #3 must be at least 3 words');

    return errors;
}

// ============================================
// COMPLETE / DRAFT
// ============================================
export async function completeIntake(onSuccess) {
    const data   = collectIntakeData();
    const errors = validateIntake(data);

    if (errors.length) {
        alert('❌ PLEASE COMPLETE ALL REQUIRED FIELDS:\n\n' + errors.join('\n'));
        return;
    }

    if (data.currentlySafe === 'no' || data.selfharm === 'plan') {
        alert('⚠️ IMMEDIATE CRISIS DETECTED\n\nPlease call:\n• 988 (Suicide & Crisis Lifeline)\n• 911 (Emergency Services)\n\nYour safety is our top priority.');
        return;
    }

    try {
        const res = await fetch('/api/intake', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ data, completed: true })
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            alert('❌ Could not save intake: ' + (err.error || 'Server error'));
            return;
        }
    } catch {
        alert('❌ Connection error. Please check your internet and try again.');
        return;
    }

    alert('✅ Intake form submitted successfully!\n\nAll required information has been validated and saved.');
    onSuccess();
}

export async function saveDraft() {
    const data = collectIntakeData();
    try {
        const res = await fetch('/api/intake', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ data, completed: false })
        });
        if (!res.ok) { alert('❌ Could not save draft. Please try again.'); return; }
    } catch {
        alert('❌ Connection error. Draft not saved.');
        return;
    }
    alert('✅ Draft saved! You can continue later from any device.');
}
