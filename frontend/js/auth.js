// Authentication: login, logout, token management, route guard
const Auth = {
    getToken() {
        return localStorage.getItem(CONFIG.TOKEN_KEY);
    },

    getUser() {
        const userStr = localStorage.getItem(CONFIG.USER_KEY);
        return userStr ? JSON.parse(userStr) : null;
    },

    setAuth(token, user) {
        localStorage.setItem(CONFIG.TOKEN_KEY, token);
        localStorage.setItem(CONFIG.USER_KEY, JSON.stringify(user));
    },

    isLoggedIn() {
        return !!this.getToken();
    },

    isGuest() {
        const user = this.getUser();
        return !!(user && user.role === 'guest');
    },

    // Apply guest read-only mode: hide all .user-only elements via CSS class
    applyGuestMode() {
        if (this.isGuest()) {
            document.body.classList.add('guest-mode');
            return true;
        }
        return false;
    },

    // Redirect guests away from management/sensitive pages.
    // Returns true when the caller must stop initializing the page.
    denyGuest() {
        if (this.isGuest()) {
            window.location.replace('/dashboard.html');
            return true;
        }
        return false;
    },

    logout() {
        localStorage.removeItem(CONFIG.TOKEN_KEY);
        localStorage.removeItem(CONFIG.USER_KEY);
        window.location.href = '/index.html';
    },

    requireAuth() {
        if (!this.isLoggedIn()) {
            window.location.href = '/index.html';
            return false;
        }
        this.applyGuestMode();
        return true;
    },

    async login(username, password) {
        const result = await Api.post('/api/auth/login', { username, password });
        if (result && !result.error) {
            this.setAuth(result.token, result.user);
            return true;
        }
        return false;
    },
};
