/**
 * API service for the Trading Dashboard.
 * Uses Axios for HTTP requests with JWT authentication.
 */

import axios from 'axios';

// Use environment variable for production, fallback to localhost for development
const API_BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// Token storage keys
const ACCESS_TOKEN_KEY = 'trading_access_token';
const REFRESH_TOKEN_KEY = 'trading_refresh_token';

// Create axios instance
const api = axios.create({
    baseURL: API_BASE,
    timeout: 30000,
    withCredentials: true,
});

// Add auth token to requests
api.interceptors.request.use(
    (config) => {
        const token = localStorage.getItem(ACCESS_TOKEN_KEY);
        if (token) {
            config.headers.Authorization = `Bearer ${token}`;
        }
        return config;
    },
    (error) => Promise.reject(error)
);

// Handle token refresh on 401
api.interceptors.response.use(
    (response) => response,
    async (error) => {
        const originalRequest = error.config;

        if (error.response?.status === 401 && !originalRequest._retry) {
            originalRequest._retry = true;

            try {
                const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
                if (refreshToken) {
                    const response = await axios.post(`${API_BASE}/auth/token/refresh`, {
                        refresh: refreshToken,
                    });

                    const { access } = response.data;
                    localStorage.setItem(ACCESS_TOKEN_KEY, access);

                    originalRequest.headers.Authorization = `Bearer ${access}`;
                    return api(originalRequest);
                }
            } catch (refreshError) {
                // Clear tokens and redirect to login
                clearTokens();
                window.location.href = '/';
            }
        }

        return Promise.reject(error);
    }
);

// Token management
export const setTokens = (tokens) => {
    if (tokens.access) {
        localStorage.setItem(ACCESS_TOKEN_KEY, tokens.access);
    }
    if (tokens.refresh) {
        localStorage.setItem(REFRESH_TOKEN_KEY, tokens.refresh);
    }
};

export const clearTokens = () => {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
};

export const hasToken = () => {
    return !!localStorage.getItem(ACCESS_TOKEN_KEY);
};

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
    if (response.data.tokens) {
        setTokens(response.data.tokens);
    }
    return response.data;
};

export const login = async (email, password) => {
    const response = await api.post('/auth/login', { email, password });
    if (response.data.tokens) {
        setTokens(response.data.tokens);
    }
    return response.data;
};

export const logout = async () => {
    try {
        const refreshToken = localStorage.getItem(REFRESH_TOKEN_KEY);
        if (refreshToken) {
            await api.post('/auth/logout', { refresh: refreshToken });
        }
    } catch (error) {
        console.error('Logout error:', error);
    } finally {
        clearTokens();
    }
};

export const getGoogleLoginUrl = () => `${API_BASE}/accounts/google/login/`;

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

export const getBrokerStatus = async () => {
    const response = await api.get('/api/broker-status');
    return response.data;
};

export default api;
