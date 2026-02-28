const Auth = (() => {
    const API_BASE = "/auth";
    const MOCK_MODE = true;

    // ── Token Storage ──
    function getAccessToken() {
        return localStorage.getItem("access_token");
    }

    function setTokens(access, refresh) {
        localStorage.setItem("access_token", access);
        if (refresh) localStorage.setItem("refresh_token", refresh);
    }

    function clearTokens() {
        localStorage.removeItem("access_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("user");
    }

    // ── User Data ──
    function getUser() {
        const raw = localStorage.getItem("user");
        if (!raw) return null;
        try {
            return JSON.parse(raw);
        } catch {
            return null;
        }
    }

    function setUser(user) {
        localStorage.setItem("user", JSON.stringify(user));
    }

    function isAuthenticated() {
        return !!getAccessToken();
    }

    // ── Mock Backend ──
    function getMockUsers() {
        try {
            return JSON.parse(localStorage.getItem("mock_users") || "[]");
        } catch {
            return [];
        }
    }

    function saveMockUsers(users) {
        localStorage.setItem("mock_users", JSON.stringify(users));
    }

    function mockRegister(name, email, password) {
        return new Promise((resolve, reject) => {
            setTimeout(() => {
                const users = getMockUsers();
                const exists = users.find(
                    (u) => u.email === email.toLowerCase(),
                );
                if (exists) {
                    reject(
                        new Error("An account with this email already exists."),
                    );
                    return;
                }
                const user = {
                    name,
                    email: email.toLowerCase(),
                    id: Date.now().toString(),
                };
                users.push({ ...user, password });
                saveMockUsers(users);
                resolve({ access_token: "mock_token_" + user.id, user });
            }, 500);
        });
    }

    function mockLogin(email, password) {
        return new Promise((resolve, reject) => {
            setTimeout(() => {
                const users = getMockUsers();
                const found = users.find(
                    (u) =>
                        u.email === email.toLowerCase() &&
                        u.password === password,
                );
                if (!found) {
                    reject(new Error("Invalid email or password."));
                    return;
                }
                const { password: _, ...user } = found;
                resolve({ access_token: "mock_token_" + user.id, user });
            }, 500);
        });
    }

    // ── API Calls ──
    async function register(name, email, password) {
        if (MOCK_MODE) {
            const result = await mockRegister(name, email, password);
            setTokens(result.access_token, null);
            setUser(result.user);
            return result.user;
        }

        const res = await fetch(`${API_BASE}/register`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name, email, password }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || "Registration failed.");
        }
        const data = await res.json();
        setTokens(data.access_token, data.refresh_token);
        setUser(data.user);
        return data.user;
    }

    async function login(email, password) {
        if (MOCK_MODE) {
            const result = await mockLogin(email, password);
            setTokens(result.access_token, null);
            setUser(result.user);
            return result.user;
        }

        const res = await fetch(`${API_BASE}/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, password }),
        });
        if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            throw new Error(err.detail || "Login failed.");
        }
        const data = await res.json();
        setTokens(data.access_token, data.refresh_token);
        setUser(data.user);
        return data.user;
    }

    function logout() {
        if (!MOCK_MODE && getAccessToken()) {
            fetch(`${API_BASE}/logout`, {
                method: "POST",
                headers: { Authorization: "Bearer " + getAccessToken() },
            }).catch(() => {});
        }
        clearTokens();
        window.location.href = "/auth/login.html";
    }

    // ── Guards ──
    function requireAuth() {
        if (!isAuthenticated()) {
            window.location.href = "/auth/login.html";
            return false;
        }
        return true;
    }

    function redirectIfAuth() {
        if (isAuthenticated()) {
            window.location.href = "/index.html";
        }
    }

    function updateProfileButton() {
        const user = getUser();
        const btn = document.querySelector(".profile-btn");
        if (btn && user && user.name) {
            btn.textContent = user.name.charAt(0).toUpperCase();
        }
    }

    return {
        register,
        login,
        logout,
        isAuthenticated,
        getUser,
        getAccessToken,
        requireAuth,
        redirectIfAuth,
        updateProfileButton,
    };
})();
