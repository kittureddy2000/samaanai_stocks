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

const api = axios.create({
    baseURL: API_BASE,
    timeout: 10000,
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
    (error) => {
        if (error.response?.status === 401) {
            // Don't clear tokens on auth/me endpoint - that's expected when not logged in
            if (!error.config?.url?.includes('/auth/me')) {
                clearTokens();
            }
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
    return response.data;
};

export const login = async (email, password) => {
    const response = await api.post('/auth/login', { email, password });
    return response.data;
};

export const getLoginUrl = () => `${API_BASE}/auth/google`;
export const getLogoutUrl = () => `${API_BASE}/auth/logout`;

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

export const getConfig = async () => {
    const response = await api.get('/api/config');
    return response.data;
};

export const getIndicators = async () => {
    const response = await api.get('/api/indicators');
    return response.data;
};

export const getOptionChain = async (symbol, strike, type, withRecommendation = true) => {
    const response = await api.get('/api/option-chain', {
        params: { symbol, strike, type, with_recommendation: withRecommendation }
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
