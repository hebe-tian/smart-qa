// Modal component: show, close, confirm dialogs
const Modal = {
    show(options) {
        const { title = '', body = '', footer = '', size = 'normal' } = options;
        const overlay = document.createElement('div');
        overlay.className = 'modal-overlay';
        overlay.id = 'modalOverlay';
        overlay.onclick = (e) => {
            if (e.target === overlay) this.close();
        };

        const modal = document.createElement('div');
        modal.className = `modal ${size === 'large' ? 'modal-large' : ''}`;
        modal.innerHTML = `
            <div class="modal-header">
                <span class="modal-title">${title}</span>
                <button class="modal-close" onclick="Modal.close()">x</button>
            </div>
            <div class="modal-body">${body}</div>
            ${footer ? `<div class="modal-footer">${footer}</div>` : ''}
        `;

        overlay.appendChild(modal);
        document.body.appendChild(overlay);
        return overlay;
    },

    close() {
        const overlay = document.getElementById('modalOverlay');
        if (overlay) overlay.remove();
    },

    confirm(message, onConfirm, title = '确认') {
        const overlay = this.show({
            title,
            body: `<p>${message}</p>`,
            footer: `
                <button class="btn btn-secondary" onclick="Modal.close()">取消</button>
                <button class="btn btn-primary" id="modalConfirmBtn">确认</button>
            `,
        });
        document.getElementById('modalConfirmBtn').onclick = () => {
            Modal.close();
            onConfirm();
        };
    },
};
