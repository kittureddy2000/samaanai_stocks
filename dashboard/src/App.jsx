import { useState, useEffect, useCallback } from 'react';
import { getPortfolio, getRisk, getMarket, getWatchlist, getTrades, getConfig, getIndicators } from './api';
import './App.css';

// Format currency
const formatCurrency = (value) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(value);
};

// Format percentage
const formatPercent = (value) => {
  const sign = value >= 0 ? '+' : '';
  return `${sign}${value.toFixed(2)}%`;
};

// Get signal color class
const getSignalClass = (signal) => {
  if (!signal) return '';
  const s = signal.toUpperCase();
  if (s.includes('BUY') || s.includes('OVERSOLD') || s.includes('BULLISH')) return 'positive';
  if (s.includes('SELL') || s.includes('OVERBOUGHT') || s.includes('BEARISH')) return 'negative';
  return '';
};

function App() {
  const [portfolio, setPortfolio] = useState(null);
  const [risk, setRisk] = useState(null);
  const [market, setMarket] = useState(null);
  const [watchlist, setWatchlist] = useState([]);
  const [trades, setTrades] = useState([]);
  const [config, setConfig] = useState(null);
  const [indicators, setIndicators] = useState([]);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [loading, setLoading] = useState(true);

  const fetchData = useCallback(async () => {
    try {
      const [portfolioData, riskData, marketData, watchlistData, tradesData, configData] = await Promise.all([
        getPortfolio(),
        getRisk(),
        getMarket(),
        getWatchlist(),
        getTrades(),
        getConfig(),
      ]);

      setPortfolio(portfolioData);
      setRisk(riskData);
      setMarket(marketData);
      setWatchlist(watchlistData.watchlist || []);
      setTrades(tradesData.trades || []);
      setConfig(configData);
      setLastUpdated(new Date().toLocaleTimeString());
      setLoading(false);

      // Fetch indicators separately (slower API call)
      try {
        const indicatorsData = await getIndicators();
        setIndicators(indicatorsData.indicators || []);
      } catch (e) {
        console.error('Failed to fetch indicators:', e);
      }
    } catch (error) {
      console.error('Failed to fetch data:', error);
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000);
    return () => clearInterval(interval);
  }, [fetchData]);

  if (loading) {
    return (
      <div className="dashboard">
        <div className="loading">Loading dashboard...</div>
      </div>
    );
  }

  const dailyChange = portfolio?.performance?.daily_change || 0;
  const dailyChangePct = portfolio?.performance?.daily_change_pct || 0;

  return (
    <div className="dashboard">
      {/* Header */}
      <header className="header">
        <div className="header-left">
          <h1>🤖 LLM Trading Agent</h1>
          <div className="market-status">
            <span className={`status-dot ${market?.is_open ? 'open' : ''}`}></span>
            <span className="status-text">
              {market?.is_open ? 'Market Open' : 'Market Closed'}
            </span>
          </div>
        </div>
        <div className="header-right">
          <span className="last-updated">Last updated: {lastUpdated || '--:--'}</span>
          <button className="btn-refresh" onClick={fetchData}>🔄 Refresh</button>
        </div>
      </header>

      {/* Main Grid */}
      <div className="main-grid">
        {/* Portfolio Card */}
        <div className="card portfolio-card">
          <h2>💰 Portfolio</h2>
          <div className="portfolio-value">
            <span className="label">Total Value</span>
            <span className="value">{formatCurrency(portfolio?.account?.portfolio_value || 0)}</span>
          </div>
          <div className="portfolio-stats">
            <div className="stat">
              <span className="label">Cash</span>
              <span className="value">{formatCurrency(portfolio?.account?.cash || 0)}</span>
            </div>
            <div className="stat">
              <span className="label">Buying Power</span>
              <span className="value">{formatCurrency(portfolio?.account?.buying_power || 0)}</span>
            </div>
            <div className="stat">
              <span className="label">Daily Change</span>
              <span className={`value ${dailyChange >= 0 ? 'positive' : 'negative'}`}>
                {formatCurrency(dailyChange)} ({formatPercent(dailyChangePct)})
              </span>
            </div>
          </div>
        </div>

        {/* Risk Card */}
        <div className="card risk-card">
          <h2>🛡️ Risk Status</h2>
          <div className="risk-level">
            <span className={`risk-dot ${(risk?.risk_level || 'low').toLowerCase()}`}></span>
            <span className="risk-text">{risk?.risk_level || 'LOW'}</span>
          </div>
          <div className="risk-stats">
            <div className="stat">
              <span className="label">Daily Trades</span>
              <span className="value">{risk?.daily_trades || 0}</span>
            </div>
            <div className="stat">
              <span className="label">Daily Loss</span>
              <span className="value">{formatCurrency(risk?.daily_loss || 0)}</span>
            </div>
            <div className="stat">
              <span className="label">Max Position</span>
              <span className="value">{formatCurrency(risk?.max_position_value || 0)}</span>
            </div>
            <div className="stat">
              <span className="label">Kill Switch</span>
              <span className="value">{risk?.kill_switch_active ? 'Active ⛔' : 'Inactive ✅'}</span>
            </div>
          </div>
        </div>

        {/* Positions Card - MOVED UP */}
        <div className="card positions-card">
          <h2>📋 Current Positions ({portfolio?.positions?.length || 0})</h2>
          <div className="positions">
            {(portfolio?.positions?.length || 0) === 0 ? (
              <div className="empty-state">No positions (100% cash)</div>
            ) : (
              portfolio.positions.map((pos) => (
                <div key={pos.symbol} className="position-item">
                  <div>
                    <span className="label">Symbol</span>
                    <span className="value symbol-highlight">{pos.symbol}</span>
                  </div>
                  <div>
                    <span className="label">Shares</span>
                    <span className="value">{pos.qty}</span>
                  </div>
                  <div>
                    <span className="label">Avg Cost</span>
                    <span className="value">{formatCurrency(pos.avg_entry_price)}</span>
                  </div>
                  <div>
                    <span className="label">Current</span>
                    <span className="value">{formatCurrency(pos.current_price)}</span>
                  </div>
                  <div>
                    <span className="label">Market Value</span>
                    <span className="value">{formatCurrency(pos.market_value)}</span>
                  </div>
                  <div>
                    <span className="label">Unrealized P&L</span>
                    <span className={`value ${pos.unrealized_pl >= 0 ? 'positive' : 'negative'}`}>
                      {formatCurrency(pos.unrealized_pl)} ({formatPercent(pos.unrealized_plpc * 100)})
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Trade History Card - MOVED UP */}
        <div className="card trades-card">
          <h2>📜 Trade History</h2>
          <div className="trades-table">
            <table>
              <thead>
                <tr>
                  <th>Time</th>
                  <th>Action</th>
                  <th>Symbol</th>
                  <th>Qty</th>
                  <th>Price</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {trades.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="empty-state">No trades yet - Agent will execute during market hours</td>
                  </tr>
                ) : (
                  trades.map((trade, idx) => (
                    <tr key={idx}>
                      <td>{trade.created_at ? new Date(trade.created_at).toLocaleString() : '--'}</td>
                      <td className={`action-${(trade.action || '').toLowerCase()}`}>{trade.action}</td>
                      <td className="symbol-highlight">{trade.symbol}</td>
                      <td>{trade.quantity || trade.filled_quantity || 0}</td>
                      <td>{trade.filled_price ? formatCurrency(trade.filled_price) : '--'}</td>
                      <td><span className={`status-badge ${(trade.status || '').toLowerCase()}`}>{trade.status}</span></td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Watchlist Card */}
        <div className="card watchlist-card">
          <h2>📈 Watchlist ({watchlist.length} symbols)</h2>
          <div className="watchlist">
            {watchlist.slice(0, 12).map((item) => (
              <div key={item.symbol} className="watchlist-item">
                <span className="symbol">{item.symbol}</span>
                <span className="price">{item.price > 0 ? formatCurrency(item.price) : '--'}</span>
              </div>
            ))}
            {watchlist.length > 12 && (
              <div className="watchlist-more">+{watchlist.length - 12} more</div>
            )}
          </div>
        </div>

        {/* Config Card */}
        <div className="card config-card">
          <h2>⚙️ Agent Configuration</h2>
          <div className="config-grid">
            <div className="config-item">
              <span className="label">Analysis Interval</span>
              <span className="value">{config?.analysis_interval || 30} min</span>
            </div>
            <div className="config-item">
              <span className="label">Max Position %</span>
              <span className="value">{config?.max_position_pct || 10}%</span>
            </div>
            <div className="config-item">
              <span className="label">Max Daily Loss</span>
              <span className="value">{config?.max_daily_loss_pct || 3}%</span>
            </div>
            <div className="config-item">
              <span className="label">Min Confidence</span>
              <span className="value">{config?.min_confidence || 70}%</span>
            </div>
            <div className="config-item">
              <span className="label">Stop Loss</span>
              <span className="value">{config?.stop_loss_pct || 5}%</span>
            </div>
            <div className="config-item">
              <span className="label">Take Profit</span>
              <span className="value">{config?.take_profit_pct || 10}%</span>
            </div>
          </div>
        </div>

        {/* Technical Indicators Card - MOVED TO BOTTOM */}
        <div className="card indicators-card">
          <h2>📊 Technical Indicators (Top 10)</h2>
          <div className="indicators-table">
            <table>
              <thead>
                <tr>
                  <th>Symbol</th>
                  <th>Price</th>
                  <th>RSI</th>
                  <th>MACD</th>
                  <th>Signal</th>
                </tr>
              </thead>
              <tbody>
                {indicators.length === 0 ? (
                  <tr>
                    <td colSpan="5" className="empty-state">Loading indicators...</td>
                  </tr>
                ) : (
                  indicators.map((ind) => (
                    <tr key={ind.symbol}>
                      <td className="symbol-highlight">{ind.symbol}</td>
                      <td>{ind.price ? formatCurrency(ind.price) : '--'}</td>
                      <td>
                        <span className={getSignalClass(ind.rsi_signal)}>
                          {ind.rsi ? ind.rsi.toFixed(1) : '--'}
                        </span>
                        <span className="signal-badge">{ind.rsi_signal || ''}</span>
                      </td>
                      <td>
                        <span className={getSignalClass(ind.macd_trend)}>
                          {ind.macd ? ind.macd.toFixed(2) : '--'}
                        </span>
                        <span className="signal-badge">{ind.macd_trend || ''}</span>
                      </td>
                      <td>
                        <span className={`overall-signal ${getSignalClass(ind.overall_signal)}`}>
                          {ind.overall_signal || 'NEUTRAL'}
                        </span>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}

export default App;
