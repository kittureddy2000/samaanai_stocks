import axios from 'axios';

// Use environment variable for production, fallback to localhost for development
const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:5000';

// Token management for JWT authentication
export const getAccessToken = () => localStorage.getItem('access_token');
export const getRefreshToken = () => localStorage.getItem('refresh_token');
export const setTokens = (access, refresh) => {
    if (access) localStorage.setItem('access_token', access);
    if (refresh) localStorage.setItem('refresh_token', refresh);
};
export const clearTokens = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
};

const emitAuthLogout = () => {
    if (typeof window !== 'undefined') {
        window.dispatchEvent(new CustomEvent('auth:logout'));
    }
};

const api = axios.create({
    baseURL: API_BASE,
    timeout: 30000,
    withCredentials: true, // Important for cookies/sessions
});

// Add Authorization header to all requests if token exists
api.interceptors.request.use((config) => {
    const token = getAccessToken();
    if (token) {
        config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
});

// Handle 401 responses - clear tokens so user can re-login
api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config || {};
        const status = error.response?.status;
        const requestUrl = originalRequest.url || '';
        const isAuthRoute = (
            requestUrl.includes('/auth/login')
            || requestUrl.includes('/auth/register')
            || requestUrl.includes('/auth/token/refresh')
            || requestUrl.includes('/auth/me')
        );

        if (status === 401 && !originalRequest._retry && !isAuthRoute) {
            const refresh = getRefreshToken();
            if (refresh) {
                originalRequest._retry = true;
                try {
                    const refreshResponse = await axios.post(
                        `${API_BASE}/auth/token/refresh`,
                        { refresh },
                        { withCredentials: true, timeout: 30000 }
                    );
                    const newAccess = refreshResponse.data?.access;
                    const newRefresh = refreshResponse.data?.refresh || refresh;
                    if (newAccess) {
                        setTokens(newAccess, newRefresh);
                        originalRequest.headers = originalRequest.headers || {};
                        originalRequest.headers.Authorization = `Bearer ${newAccess}`;
                        return api(originalRequest);
                    }
                } catch (refreshError) {
                    console.warn('Token refresh failed, clearing session.', refreshError);
                }
            }

            clearTokens();
            emitAuthLogout();
        } else if (status === 401 && requestUrl.includes('/auth/me')) {
            clearTokens();
        }

        return Promise.reject(error);
    }
);

// Auth functions
export const getCurrentUser = async () => {
    try {
        const response = await api.get('/auth/me');
        return response.data;
    } catch (error) {
        if (error.response?.status === 401) {
            return { authenticated: false };
        }
        throw error;
    }
};

export const register = async (email, password, name) => {
    const response = await api.post('/auth/register', { email, password, name });
    const tokens = response.data?.tokens;
    if (tokens?.access) {
        setTokens(tokens.access, tokens.refresh);
    }
    return response.data;
};

export const login = async (email, password) => {
    const response = await api.post('/auth/login', { email, password });
    const tokens = response.data?.tokens;
    if (tokens?.access) {
        setTokens(tokens.access, tokens.refresh);
    }
    return response.data;
};

// Use allauth endpoint directly (works even if /auth/google redirect route is unavailable).
export const getLoginUrl = () => `${API_BASE}/accounts/google/login/`;
export const getLogoutUrl = () => `${API_BASE}/auth/logout`;
export const logout = async () => {
    try {
        const refresh = getRefreshToken();
        await api.post('/auth/logout', { refresh });
    } catch (error) {
        // Clear local tokens even if server logout fails.
        console.warn('Logout request failed, clearing local session anyway.', error);
    } finally {
        clearTokens();
    }
};

// Data functions
export const getPortfolio = async () => {
    const response = await api.get('/api/portfolio');
    return response.data;
};

export const getRisk = async () => {
    const response = await api.get('/api/risk');
    return response.data;
};

export const getMarket = async () => {
    const response = await api.get('/api/market');
    return response.data;
};

export const getWatchlist = async () => {
    const response = await api.get('/api/watchlist');
    return response.data;
};

export const getTrades = async () => {
    const response = await api.get('/api/trades');
    return response.data;
};

export const getAgentStatus = async () => {
    const response = await api.get('/api/agent-status');
    return response.data;
};

export const getOperationsSummary = async (days = 14) => {
    const response = await api.get('/api/operations-summary', { params: { days } });
    return response.data;
};

export const runAnalyzeNow = async () => {
    const response = await api.post('/api/analyze', {});
    return response.data;
};

export const getConfig = async () => {
    const response = await api.get('/api/config');
    return response.data;
};

export const updateConfig = async (payload) => {
    const response = await api.post('/api/config', payload);
    return response.data;
};

export const getIndicators = async () => {
    const response = await api.get('/api/indicators');
    return response.data;
};

export const getOptionChain = async (symbol, strike, type, withRecommendation = true) => {
    const response = await api.get('/api/option-chain', {
        params: { symbol, strike, type, with_recommendation: withRecommendation },
        timeout: 60000,
    });
    return response.data;
};

export const getCollarStrategy = async (symbol, upsidePct) => {
    const response = await api.get('/api/collar-strategy', {
        params: { symbol, upside_pct: upsidePct }
    });
    return response.data;
};

export const addToWatchlist = async (symbol) => {
    const response = await api.post('/api/watchlist', { symbol });
    return response.data;
};

export const removeFromWatchlist = async (symbol) => {
    const response = await api.delete('/api/watchlist', { data: { symbol } });
    return response.data;
};

export default api;
