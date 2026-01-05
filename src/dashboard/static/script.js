// LLM Trading Agent Dashboard - JavaScript

const API_BASE = '';

// Format currency
function formatCurrency(value) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(value);
}

// Format percentage
function formatPercent(value) {
    const sign = value >= 0 ? '+' : '';
    return `${sign}${value.toFixed(2)}%`;
}

// Update portfolio data
async function updatePortfolio() {
    try {
        const response = await fetch(`${API_BASE}/api/portfolio`);
        const data = await response.json();

        if (data.error) {
            console.error('Portfolio error:', data.error);
            return;
        }

        // Update values
        document.getElementById('portfolioValue').textContent = formatCurrency(data.account.portfolio_value);
        document.getElementById('cashValue').textContent = formatCurrency(data.account.cash);
        document.getElementById('buyingPower').textContent = formatCurrency(data.account.buying_power);

        const dailyChangeEl = document.getElementById('dailyChange');
        dailyChangeEl.textContent = `${formatCurrency(data.performance.daily_change)} (${formatPercent(data.performance.daily_change_pct)})`;
        dailyChangeEl.className = data.performance.daily_change >= 0 ? 'value positive' : 'value negative';

        // Update positions
        const positionsEl = document.getElementById('positions');
        if (data.positions.length === 0) {
            positionsEl.innerHTML = '<div class="empty-state">No positions (100% cash)</div>';
        } else {
            positionsEl.innerHTML = data.positions.map(pos => `
                <div class="position-item">
                    <div>
                        <span class="label">Symbol</span>
                        <span class="value">${pos.symbol}</span>
                    </div>
                    <div>
                        <span class="label">Quantity</span>
                        <span class="value">${pos.qty}</span>
                    </div>
                    <div>
                        <span class="label">Entry</span>
                        <span class="value">${formatCurrency(pos.avg_entry_price)}</span>
                    </div>
                    <div>
                        <span class="label">P&L</span>
                        <span class="value ${pos.unrealized_pl >= 0 ? 'positive' : 'negative'}">
                            ${formatCurrency(pos.unrealized_pl)}
                        </span>
                    </div>
                </div>
            `).join('');
        }
    } catch (error) {
        console.error('Failed to update portfolio:', error);
    }
}

// Update risk status
async function updateRisk() {
    try {
        const response = await fetch(`${API_BASE}/api/risk`);
        const data = await response.json();

        if (data.error) {
            console.error('Risk error:', data.error);
            return;
        }

        const riskLevel = document.getElementById('riskLevel');
        const riskDot = riskLevel.querySelector('.risk-dot');
        const riskText = riskLevel.querySelector('.risk-text');

        riskDot.className = `risk-dot ${data.risk_level.toLowerCase()}`;
        riskText.textContent = data.risk_level;

        document.getElementById('dailyTrades').textContent = data.daily_trades;
        document.getElementById('dailyLoss').textContent = formatCurrency(data.daily_loss);
        document.getElementById('maxPosition').textContent = formatCurrency(data.max_position_value);
        document.getElementById('killSwitch').textContent = data.kill_switch_active ? 'Active ⛔' : 'Inactive ✅';
    } catch (error) {
        console.error('Failed to update risk:', error);
    }
}

// Update market status
async function updateMarket() {
    try {
        const response = await fetch(`${API_BASE}/api/market`);
        const data = await response.json();

        const statusEl = document.getElementById('marketStatus');
        const dot = statusEl.querySelector('.status-dot');
        const text = statusEl.querySelector('.status-text');

        if (data.is_open) {
            dot.classList.add('open');
            text.textContent = 'Market Open';
        } else {
            dot.classList.remove('open');
            const nextOpen = new Date(data.next_open);
            text.textContent = `Market Closed (Opens ${nextOpen.toLocaleString()})`;
        }
    } catch (error) {
        console.error('Failed to update market:', error);
    }
}

// Update watchlist
async function updateWatchlist() {
    try {
        const response = await fetch(`${API_BASE}/api/watchlist`);
        const data = await response.json();

        if (data.error) {
            console.error('Watchlist error:', data.error);
            return;
        }

        const watchlistEl = document.getElementById('watchlist');
        watchlistEl.innerHTML = data.watchlist.map(item => `
            <div class="watchlist-item">
                <span class="symbol">${item.symbol}</span>
                <span class="price">${item.price > 0 ? formatCurrency(item.price) : '--'}</span>
            </div>
        `).join('');
    } catch (error) {
        console.error('Failed to update watchlist:', error);
    }
}

// Update trades
async function updateTrades() {
    try {
        const response = await fetch(`${API_BASE}/api/trades`);
        const data = await response.json();

        const tradesBody = document.getElementById('tradesBody');

        if (!data.trades || data.trades.length === 0) {
            tradesBody.innerHTML = '<tr><td colspan="6" class="empty-state">No trades yet</td></tr>';
            return;
        }

        tradesBody.innerHTML = data.trades.map(trade => `
            <tr>
                <td>${new Date(trade.timestamp).toLocaleString()}</td>
                <td class="action-${trade.action.toLowerCase()}">${trade.action}</td>
                <td>${trade.symbol}</td>
                <td>${trade.quantity}</td>
                <td>${trade.status}</td>
                <td>${(trade.confidence * 100).toFixed(0)}%</td>
            </tr>
        `).join('');
    } catch (error) {
        console.error('Failed to update trades:', error);
    }
}

// Update config
async function updateConfig() {
    try {
        const response = await fetch(`${API_BASE}/api/config`);
        const data = await response.json();

        const configGrid = document.getElementById('configGrid');
        configGrid.innerHTML = `
            <div class="config-item">
                <span class="label">Analysis Interval</span>
                <span class="value">${data.analysis_interval} min</span>
            </div>
            <div class="config-item">
                <span class="label">Max Position %</span>
                <span class="value">${data.max_position_pct}%</span>
            </div>
            <div class="config-item">
                <span class="label">Max Daily Loss</span>
                <span class="value">${data.max_daily_loss_pct}%</span>
            </div>
            <div class="config-item">
                <span class="label">Min Confidence</span>
                <span class="value">${data.min_confidence}%</span>
            </div>
            <div class="config-item">
                <span class="label">Stop Loss</span>
                <span class="value">${data.stop_loss_pct}%</span>
            </div>
            <div class="config-item">
                <span class="label">Take Profit</span>
                <span class="value">${data.take_profit_pct}%</span>
            </div>
        `;
    } catch (error) {
        console.error('Failed to update config:', error);
    }
}

// Refresh all data
async function refreshData() {
    document.getElementById('lastUpdated').textContent = `Last updated: ${new Date().toLocaleTimeString()}`;

    await Promise.all([
        updatePortfolio(),
        updateRisk(),
        updateMarket(),
        updateWatchlist(),
        updateTrades(),
        updateConfig()
    ]);
}

// Initial load
document.addEventListener('DOMContentLoaded', () => {
    refreshData();

    // Auto-refresh every 30 seconds
    setInterval(refreshData, 30000);
});
