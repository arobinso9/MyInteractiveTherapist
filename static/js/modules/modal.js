export function showModal({ title, bodyHtml, buttons, onMount }) {
    return new Promise(resolve => {
        const modal      = document.getElementById('app-modal');
        const titleEl    = document.getElementById('app-modal-title');
        const bodyEl     = document.getElementById('app-modal-body');
        const actionsEl  = document.getElementById('app-modal-actions');
        const backdropEl = modal.querySelector('.app-modal-backdrop');

        titleEl.textContent = title;
        bodyEl.innerHTML    = bodyHtml;
        actionsEl.innerHTML = '';

        function close(value) {
            modal.style.display = 'none';
            backdropEl.onclick  = null;
            resolve(value);
        }

        buttons.forEach(b => {
            const btn = document.createElement('button');
            btn.textContent = b.label;
            btn.className   = `modal-btn-${b.variant || 'primary'}`;
            btn.onclick     = () => close(typeof b.onClick === 'function' ? b.onClick() : b.value);
            actionsEl.appendChild(btn);
        });

        // Clicking backdrop = cancel (resolves with first cancel button's value, or null)
        const cancelBtn = buttons.find(b => b.variant === 'cancel');
        backdropEl.onclick = () => close(cancelBtn ? cancelBtn.value : null);

        modal.style.display = 'flex';

        if (typeof onMount === 'function') onMount(close);
    });
}

export function confirmModal({ title, bodyHtml, confirmLabel = 'Confirm', cancelLabel = 'Cancel', danger = false }) {
    return showModal({
        title,
        bodyHtml,
        buttons: [
            { label: cancelLabel,  value: false, variant: 'cancel' },
            { label: confirmLabel, value: true,  variant: danger ? 'danger' : 'primary' },
        ],
    });
}

export function alertModal({ title, bodyHtml, buttonLabel = 'OK' }) {
    return showModal({
        title,
        bodyHtml,
        buttons: [
            { label: buttonLabel, value: true, variant: 'primary' },
        ],
    });
}
