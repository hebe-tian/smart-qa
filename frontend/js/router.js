// Simple hash-based router with auth guard
const Router = {
    navigate(page, params = {}) {
        let url = `/${page}.html`;
        const query = new URLSearchParams(params).toString();
        if (query) url += `?${query}`;
        window.location.href = url;
    },

    getParam(name) {
        const params = new URLSearchParams(window.location.search);
        return params.get(name);
    },

    back() {
        window.history.back();
    },
};
