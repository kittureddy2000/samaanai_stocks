import { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { getPortfolio, getRisk, getMarket, getWatchlist, getTrades, getConfig, getIndicators, getCurrentUser, getLoginUrl, register, login, logout, getOptionChain, getCollarStrategy, addToWatchlist, removeFromWatchlist, setTokens } from './api';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import './App.css';

// ============================================================
// Sortable Table Hook & Helper
// ============================================================
function useSortableTable(data, defaultKey = null, defaultDir = 'asc') {
  const [sortKey, setSortKey] = useState(defaultKey);
  const [sortDir, setSortDir] = useState(defaultDir);

  const handleSort = (key) => {
    if (sortKey === key) {
      setSortDir(prev => prev === 'asc' ? 'desc' : 'asc');
    } else {
      setSortKey(key);
      setSortDir('asc');
    }
  };

  const sorted = useMemo(() => {
    if (!sortKey || !data?.length) return data || [];
    return [...data].sort((a, b) => {
      let aVal = a[sortKey], bVal = b[sortKey];
      if (aVal == null) return 1;
      if (bVal == null) return -1;
      if (typeof aVal === 'string') {
        return sortDir === 'asc'
          ? aVal.localeCompare(bVal)
          : bVal.localeCompare(aVal);
      }
      return sortDir === 'asc' ? aVal - bVal : bVal - aVal;
    });
  }, [data, sortKey, sortDir]);

  return { sorted, sortKey, sortDir, handleSort };
}

function SortTh({ label, sortKey, currentKey, currentDir, onSort }) {
  const active = currentKey === sortKey;
  return (
    <th onClick={() => onSort(sortKey)} className="sortable-th">
      {label}
      <span className={`sort-arrow ${active ? (currentDir === 'asc' ? 'asc' : 'desc') : ''}`} />
    </th>
  );
}

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

// Format market cap
const formatMarketCap = (value) => {
  if (!value) return '--';
  if (value >= 1e12) return `$${(value / 1e12).toFixed(2)}T`;
  if (value >= 1e9) return `$${(value / 1e9).toFixed(2)}B`;
  if (value >= 1e6) return `$${(value / 1e6).toFixed(1)}M`;
  return `$${value.toLocaleString()}`;
};

// Get signal color class
const getSignalClass = (signal) => {
  if (!signal) return '';
  const s = signal.toUpperCase();
  if (s.includes('BUY') || s.includes('OVERSOLD') || s.includes('BULLISH')) return 'positive';
  if (s.includes('SELL') || s.includes('OVERBOUGHT') || s.includes('BEARISH')) return 'negative';
  return '';
};

// ============================================================
// Option Chain Page Component
// ============================================================
function OptionChainPage() {
  const [formData, setFormData] = useState({ symbol: 'AAPL', strike: '230', type: 'call' });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const { sorted: sortedOptions, sortKey: ocSortKey, sortDir: ocSortDir, handleSort: ocHandleSort } = useSortableTable(data?.options);

  const fetchChain = async () => {
    if (!formData.symbol || !formData.strike) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getOptionChain(formData.symbol, formData.strike, formData.type);
      setData(result);
    } catch (err) {
      // Fallback: show chain data even if LLM recommendation times out.
      try {
        const fallback = await getOptionChain(
          formData.symbol,
          formData.strike,
          formData.type,
          false
        );
        fallback.recommendation_error = 'LLM recommendation timed out. Showing live chain data only.';
        setData(fallback);
      } catch (fallbackErr) {
        setError(
          fallbackErr.response?.data?.error ||
          err.response?.data?.error ||
          'Failed to fetch option chain data'
        );
        setData(null);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') fetchChain();
  };

  // Chart data
  const chartData = data?.options?.map(opt => ({
    expiration: opt.expiration.slice(5), // MM-DD format for readability
    fullDate: opt.expiration,
    iv: opt.implied_volatility,
    price: opt.last_price,
    days: opt.days_to_expiry,
  })) || [];
  const recommendation = data?.sell_recommendation;

  // Custom tooltip for chart
  const ChartTooltip = ({ active, payload }) => {
    if (!active || !payload?.length) return null;
    const d = payload[0]?.payload;
    return (
      <div className="chart-tooltip">
        <div className="chart-tooltip-title">{d?.fullDate}</div>
        <div className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: '#ffd93d' }}></span>
          IV: {d?.iv?.toFixed(2)}%
        </div>
        <div className="chart-tooltip-row">
          <span className="chart-tooltip-dot" style={{ background: '#4da6ff' }}></span>
          Price: ${d?.price?.toFixed(2)}
        </div>
        <div className="chart-tooltip-row dim">{d?.days} days to expiry</div>
      </div>
    );
  };

  return (
    <div className="option-chain-page">
      {/* Header Row */}
      <div className="oc-header-row">
        <div>
          <div className="oc-label">OPTION CHAIN DASHBOARD</div>
          <h1 className="oc-title">Track option prices and IV across expirations.</h1>
          <p className="oc-subtitle">
            Enter a ticker and strike to see live pricing, greeks, and the IV trend for every expiration.
          </p>
        </div>
        <div className="oc-source-card">
          <div className="oc-source-label">DATA SOURCE</div>
          {data ? (
            <>
              <div className="oc-source-value">
                <span className="oc-source-dot active"></span>
                {data.symbol} &mdash; ${data.current_price?.toFixed(2)}
              </div>
              <div className="oc-source-detail">{data.count} expirations loaded via yfinance</div>
            </>
          ) : (
            <>
              <div className="oc-source-value">Not loaded</div>
              <div className="oc-source-detail">Fetch a chain to pull live data.</div>
            </>
          )}
        </div>
      </div>

      {/* Input Form */}
      <div className="oc-form-card">
        <div className="oc-form-row">
          <div className="oc-field">
            <label>Symbol</label>
            <input
              type="text"
              value={formData.symbol}
              onChange={(e) => setFormData({ ...formData, symbol: e.target.value.toUpperCase() })}
              onKeyDown={handleKeyDown}
              placeholder="AAPL"
            />
          </div>
          <div className="oc-field">
            <label>Strike</label>
            <input
              type="number"
              step="0.5"
              value={formData.strike}
              onChange={(e) => setFormData({ ...formData, strike: e.target.value })}
              onKeyDown={handleKeyDown}
              placeholder="230"
            />
          </div>
          <div className="oc-field">
            <label>Type</label>
            <select
              value={formData.type}
              onChange={(e) => setFormData({ ...formData, type: e.target.value })}
            >
              <option value="call">Call</option>
              <option value="put">Put</option>
            </select>
          </div>
          <button className="oc-btn-fetch" onClick={fetchChain} disabled={loading}>
            {loading ? 'Loading\u2026' : 'Fetch Chain'}
          </button>
        </div>
        {error && <div className="oc-form-error">{error}</div>}
      </div>

      {/* Loading */}
      {loading && (
        <div className="oc-loading">
          <div className="oc-spinner"></div>
          Fetching option chain for {formData.symbol}\u2026
        </div>
      )}

      {/* Results */}
      {data && !loading && (
        <>
          <div className="oc-ai-card">
            <div className="oc-ai-header">
              <div className="oc-ai-label">LLM SELL RECOMMENDATION</div>
              <div className="oc-ai-source">Gemini + option-chain liquidity</div>
            </div>
            {recommendation ? (
              <div className="oc-ai-grid">
                <div className="oc-ai-metric">
                  <span>Action</span>
                  <strong>SELL {recommendation.option_type}</strong>
                </div>
                <div className="oc-ai-metric">
                  <span>Expiration</span>
                  <strong>{recommendation.expiration || '--'}</strong>
                </div>
                <div className="oc-ai-metric">
                  <span>Strike</span>
                  <strong>${Number(recommendation.strike || 0).toFixed(2)}</strong>
                </div>
                <div className="oc-ai-metric">
                  <span>Premium</span>
                  <strong>${Number(recommendation.premium || 0).toFixed(2)}</strong>
                </div>
                <div className="oc-ai-metric">
                  <span>Confidence</span>
                  <strong>{Math.round(Number(recommendation.confidence || 0) * 100)}%</strong>
                </div>
                <div className="oc-ai-metric">
                  <span>Liquidity</span>
                  <strong>
                    OI {Number(recommendation.open_interest || 0).toLocaleString()} · Vol {Number(recommendation.volume || 0).toLocaleString()}
                  </strong>
                </div>
              </div>
            ) : (
              <div className="oc-ai-empty">
                {data?.recommendation_error
                  ? `Recommendation unavailable: ${data.recommendation_error}`
                  : 'No recommendation returned for this query.'}
              </div>
            )}
            {recommendation?.reasoning && (
              <p className="oc-ai-reasoning">{recommendation.reasoning}</p>
            )}
          </div>

          <div className="oc-grid">
            {/* IV + Price Trend Chart */}
            <div className="oc-card">
              <h3>IV + Price Trend</h3>
              {chartData.length > 0 ? (
                <ResponsiveContainer width="100%" height={320}>
                  <LineChart data={chartData} margin={{ top: 5, right: 20, left: 0, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                    <XAxis
                      dataKey="expiration"
                      stroke="#555"
                      tick={{ fill: '#8b8b9e', fontSize: 11 }}
                      angle={-35}
                      textAnchor="end"
                      height={50}
                    />
                    <YAxis
                      yAxisId="left"
                      stroke="#ffd93d"
                      tick={{ fill: '#8b8b9e', fontSize: 11 }}
                      tickFormatter={(v) => `${v}%`}
                      width={55}
                    />
                    <YAxis
                      yAxisId="right"
                      orientation="right"
                      stroke="#4da6ff"
                      tick={{ fill: '#8b8b9e', fontSize: 11 }}
                      tickFormatter={(v) => `$${v}`}
                      width={65}
                    />
                    <Tooltip content={<ChartTooltip />} />
                    <Legend
                      verticalAlign="top"
                      height={36}
                      wrapperStyle={{ fontSize: 12, color: '#8b8b9e' }}
                    />
                    <Line
                      yAxisId="left"
                      type="monotone"
                      dataKey="iv"
                      stroke="#ffd93d"
                      strokeWidth={2}
                      name="Implied Volatility (%)"
                      dot={{ fill: '#ffd93d', r: 3, strokeWidth: 0 }}
                      activeDot={{ r: 5, stroke: '#ffd93d', strokeWidth: 2, fill: '#1a1a24' }}
                    />
                    <Line
                      yAxisId="right"
                      type="monotone"
                      dataKey="price"
                      stroke="#4da6ff"
                      strokeWidth={2}
                      name="Last Price ($)"
                      dot={{ fill: '#4da6ff', r: 3, strokeWidth: 0 }}
                      activeDot={{ r: 5, stroke: '#4da6ff', strokeWidth: 2, fill: '#1a1a24' }}
                    />
                  </LineChart>
                </ResponsiveContainer>
              ) : (
                <div className="oc-empty">No data yet. Fetch a chain to see the trend.</div>
              )}
            </div>

            {/* Expiration Table */}
            <div className="oc-card oc-table-card">
              <h3>Expiration Table</h3>
              {data.current_price && (
                <div className="oc-stock-price">
                  Underlying: <span className="oc-price-value">${data.current_price.toFixed(2)}</span>
                  <span className="oc-strike-info">
                    &nbsp;&middot;&nbsp;Strike ${data.strike} {data.type.toUpperCase()}
                  </span>
                </div>
              )}
              <div className="oc-table-scroll">
                <table className="oc-table">
                  <thead>
                    <tr>
                      <SortTh label="Expiration" sortKey="expiration" currentKey={ocSortKey} currentDir={ocSortDir} onSort={ocHandleSort} />
                      <SortTh label="Days" sortKey="days_to_expiry" currentKey={ocSortKey} currentDir={ocSortDir} onSort={ocHandleSort} />
                      <SortTh label="Last" sortKey="last_price" currentKey={ocSortKey} currentDir={ocSortDir} onSort={ocHandleSort} />
                      <SortTh label="Bid" sortKey="bid" currentKey={ocSortKey} currentDir={ocSortDir} onSort={ocHandleSort} />
                      <SortTh label="Ask" sortKey="ask" currentKey={ocSortKey} currentDir={ocSortDir} onSort={ocHandleSort} />
                      <SortTh label="Vol" sortKey="volume" currentKey={ocSortKey} currentDir={ocSortDir} onSort={ocHandleSort} />
                      <SortTh label="OI" sortKey="open_interest" currentKey={ocSortKey} currentDir={ocSortDir} onSort={ocHandleSort} />
                      <SortTh label="IV %" sortKey="implied_volatility" currentKey={ocSortKey} currentDir={ocSortDir} onSort={ocHandleSort} />
                      <SortTh label={'\u0394'} sortKey="delta" currentKey={ocSortKey} currentDir={ocSortDir} onSort={ocHandleSort} />
                      <SortTh label={'\u0393'} sortKey="gamma" currentKey={ocSortKey} currentDir={ocSortDir} onSort={ocHandleSort} />
                      <SortTh label={'\u0398'} sortKey="theta" currentKey={ocSortKey} currentDir={ocSortDir} onSort={ocHandleSort} />
                      <SortTh label="Vega" sortKey="vega" currentKey={ocSortKey} currentDir={ocSortDir} onSort={ocHandleSort} />
                    </tr>
                  </thead>
                  <tbody>
                    {sortedOptions.length === 0 ? (
                      <tr>
                        <td colSpan="12" className="oc-empty">No options found for this strike</td>
                      </tr>
                    ) : (
                      sortedOptions.map((opt, i) => (
                        <tr key={i} className={opt.days_to_expiry <= 7 ? 'near-expiry' : ''}>
                          <td className="oc-exp-cell">{opt.expiration}</td>
                          <td className={opt.days_to_expiry <= 7 ? 'warn' : ''}>{opt.days_to_expiry}</td>
                          <td>${opt.last_price.toFixed(2)}</td>
                          <td>${opt.bid.toFixed(2)}</td>
                          <td>${opt.ask.toFixed(2)}</td>
                          <td>{opt.volume.toLocaleString()}</td>
                          <td>{opt.open_interest.toLocaleString()}</td>
                          <td className="iv-cell">{opt.implied_volatility.toFixed(1)}%</td>
                          <td className={`greek ${(opt.delta ?? 0) >= 0 ? 'pos' : 'neg'}`}>
                            {opt.delta != null ? opt.delta.toFixed(3) : '--'}
                          </td>
                          <td className="greek">
                            {opt.gamma != null ? opt.gamma.toFixed(4) : '--'}
                          </td>
                          <td className={`greek ${(opt.theta ?? 0) >= 0 ? 'pos' : 'neg'}`}>
                            {opt.theta != null ? opt.theta.toFixed(3) : '--'}
                          </td>
                          <td className="greek">
                            {opt.vega != null ? opt.vega.toFixed(3) : '--'}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}

      {/* Initial empty state */}
      {!data && !loading && !error && (
        <div className="oc-empty-state">
          <div className="oc-empty-icon">&#x1F4C8;</div>
          <p>Enter a symbol and strike price above, then click <strong>Fetch Chain</strong> to load option data across all expirations.</p>
        </div>
      )}
    </div>
  );
}


// ============================================================
// Collar Strategy Page Component
// ============================================================
function CollarStrategyPage() {
  const [formData, setFormData] = useState({ symbol: 'AAPL', upsidePct: '5' });
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const { sorted: sortedCollars, sortKey: colSortKey, sortDir: colSortDir, handleSort: colHandleSort } = useSortableTable(data?.collars);

  const fetchCollar = async () => {
    if (!formData.symbol || !formData.upsidePct) return;
    setLoading(true);
    setError(null);
    try {
      const result = await getCollarStrategy(formData.symbol, formData.upsidePct);
      setData(result);
    } catch (err) {
      setError(err.response?.data?.error || 'Failed to fetch collar strategy data');
      setData(null);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === 'Enter') fetchCollar();
  };

  return (
    <div className="option-chain-page collar-strategy-page">
      {/* Header Row */}
      <div className="oc-header-row">
        <div>
          <div className="oc-label">COLLAR STRATEGY</div>
          <h1 className="oc-title">Zero-Cost Collar Calculator</h1>
          <p className="oc-subtitle">
            Sell an OTM call at your target upside, then find the best matching protective put to create a zero-cost collar across all expirations.
          </p>
        </div>
        <div className="oc-source-card">
          <div className="oc-source-label">STRATEGY INFO</div>
          {data ? (
            <>
              <div className="oc-source-value">
                <span className="oc-source-dot active"></span>
                {data.symbol} &mdash; ${data.current_price?.toFixed(2)}
              </div>
              <div className="oc-source-detail">
                Target call @ ${data.call_strike_target?.toFixed(2)} &middot; {data.count} expirations
              </div>
            </>
          ) : (
            <>
              <div className="oc-source-value">Not loaded</div>
              <div className="oc-source-detail">Enter a ticker and upside % to calculate.</div>
            </>
          )}
        </div>
      </div>

      {/* Input Form */}
      <div className="oc-form-card">
        <div className="oc-form-row collar-form-row">
          <div className="oc-field">
            <label>Symbol</label>
            <input
              type="text"
              value={formData.symbol}
              onChange={(e) => setFormData({ ...formData, symbol: e.target.value.toUpperCase() })}
              onKeyDown={handleKeyDown}
              placeholder="AAPL"
            />
          </div>
          <div className="oc-field">
            <label>Upside %</label>
            <input
              type="number"
              step="0.5"
              min="0.5"
              max="50"
              value={formData.upsidePct}
              onChange={(e) => setFormData({ ...formData, upsidePct: e.target.value })}
              onKeyDown={handleKeyDown}
              placeholder="5"
            />
          </div>
          <button className="oc-btn-fetch" onClick={fetchCollar} disabled={loading}>
            {loading ? 'Calculating\u2026' : 'Calculate Collars'}
          </button>
        </div>
        {error && <div className="oc-form-error">{error}</div>}
      </div>

      {/* Loading */}
      {loading && (
        <div className="oc-loading">
          <div className="oc-spinner"></div>
          Calculating collar strategies for {formData.symbol}\u2026
        </div>
      )}

      {/* Results */}
      {data && !loading && (
        <div className="oc-card oc-table-card">
          <h3>Collar Results &mdash; {data.symbol}</h3>
          <div className="oc-stock-price">
            Current: <span className="oc-price-value">${data.current_price?.toFixed(2)}</span>
            <span className="oc-strike-info">
              &nbsp;&middot;&nbsp;Target Call Strike: ${data.call_strike_target?.toFixed(2)} ({data.upside_pct}% upside)
            </span>
          </div>
          <div className="oc-table-scroll collar-table-scroll">
            <table className="oc-table">
              <thead>
                <tr>
                  <SortTh label="Expiration" sortKey="expiration" currentKey={colSortKey} currentDir={colSortDir} onSort={colHandleSort} />
                  <SortTh label="Days" sortKey="days_to_expiry" currentKey={colSortKey} currentDir={colSortDir} onSort={colHandleSort} />
                  <SortTh label="Call Strike" sortKey="call_strike" currentKey={colSortKey} currentDir={colSortDir} onSort={colHandleSort} />
                  <SortTh label="Call Prem" sortKey="call_premium" currentKey={colSortKey} currentDir={colSortDir} onSort={colHandleSort} />
                  <SortTh label="Put Strike" sortKey="put_strike" currentKey={colSortKey} currentDir={colSortDir} onSort={colHandleSort} />
                  <SortTh label="Put Prem" sortKey="put_premium" currentKey={colSortKey} currentDir={colSortDir} onSort={colHandleSort} />
                  <SortTh label="Net Cost" sortKey="net_cost" currentKey={colSortKey} currentDir={colSortDir} onSort={colHandleSort} />
                  <SortTh label="Max Profit" sortKey="max_profit" currentKey={colSortKey} currentDir={colSortDir} onSort={colHandleSort} />
                  <SortTh label="Max Loss" sortKey="max_loss" currentKey={colSortKey} currentDir={colSortDir} onSort={colHandleSort} />
                  <SortTh label="Protection %" sortKey="protection_pct" currentKey={colSortKey} currentDir={colSortDir} onSort={colHandleSort} />
                  <SortTh label="Upside Cap %" sortKey="upside_cap_pct" currentKey={colSortKey} currentDir={colSortDir} onSort={colHandleSort} />
                </tr>
              </thead>
              <tbody>
                {sortedCollars.length === 0 ? (
                  <tr>
                    <td colSpan="11" className="oc-empty">No collar combinations found for this configuration</td>
                  </tr>
                ) : (
                  sortedCollars.map((c, i) => (
                    <tr key={i} className={c.days_to_expiry <= 7 ? 'near-expiry' : ''}>
                      <td className="oc-exp-cell">{c.expiration}</td>
                      <td className={c.days_to_expiry <= 7 ? 'warn' : ''}>{c.days_to_expiry}</td>
                      <td>${c.call_strike.toFixed(2)}</td>
                      <td className="positive">${c.call_premium.toFixed(2)}</td>
                      <td>${c.put_strike.toFixed(2)}</td>
                      <td className="negative">${c.put_premium.toFixed(2)}</td>
                      <td className={c.net_cost <= 0 ? 'positive' : 'negative'}>
                        ${Math.abs(c.net_cost).toFixed(2)} {c.net_cost <= 0 ? 'CR' : 'DR'}
                      </td>
                      <td className="positive">${c.max_profit.toFixed(2)}</td>
                      <td className="negative">${Math.abs(c.max_loss).toFixed(2)}</td>
                      <td className="negative">{c.protection_pct.toFixed(2)}%</td>
                      <td className="positive">{c.upside_cap_pct.toFixed(2)}%</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Initial empty state */}
      {!data && !loading && !error && (
        <div className="oc-empty-state">
          <div className="oc-empty-icon">&#x1F6E1;</div>
          <p>Enter a symbol and target upside %, then click <strong>Calculate Collars</strong> to find zero-cost collar strategies across all expirations.</p>
        </div>
      )}
    </div>
  );
}


// ============================================================
// Auth Page Component
// ============================================================
function AuthPage({ onAuthSuccess }) {
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [name, setName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const validatePassword = (pwd) => {
    if (pwd.length < 8) return 'Password must be at least 8 characters';
    if (!/[A-Z]/.test(pwd)) return 'Password must contain an uppercase letter';
    if (!/[a-z]/.test(pwd)) return 'Password must contain a lowercase letter';
    if (!/[0-9]/.test(pwd)) return 'Password must contain a number';
    return null;
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      if (mode === 'register') {
        const pwdError = validatePassword(password);
        if (pwdError) {
          setError(pwdError);
          setLoading(false);
          return;
        }
        if (password !== confirmPassword) {
          setError('Passwords do not match');
          setLoading(false);
          return;
        }

        const result = await register(email, password, name);
        if (result.success) {
          onAuthSuccess({
            authenticated: true,
            email: result.user.email,
            name: result.user.name
          });
        }
      } else {
        const result = await login(email, password);
        if (result.authenticated) {
          onAuthSuccess(result);
        }
      }
    } catch (err) {
      setError(err.response?.data?.error || 'An error occurred. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="dashboard">
      <div className="login-container">
        <div className="login-card">
          <div className="login-logo">&#x1F916;</div>
          <h1>LLM Trading Agent</h1>
          <p>AI-powered stock trading with Google Gemini</p>

          <div className="auth-tabs">
            <button className={`auth-tab ${mode === 'login' ? 'active' : ''}`} onClick={() => { setMode('login'); setError(''); }}>
              Sign In
            </button>
            <button className={`auth-tab ${mode === 'register' ? 'active' : ''}`} onClick={() => { setMode('register'); setError(''); }}>
              Create Account
            </button>
          </div>

          {error && <div className="auth-error">{error}</div>}

          <form onSubmit={handleSubmit} className="auth-form">
            {mode === 'register' && (
              <div className="form-group">
                <label>Name</label>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" />
              </div>
            )}
            <div className="form-group">
              <label>Email</label>
              <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@example.com" required />
            </div>
            <div className="form-group">
              <label>Password</label>
              <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" required />
            </div>
            {mode === 'register' && (
              <div className="form-group">
                <label>Confirm Password</label>
                <input type="password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} placeholder="••••••••" required />
              </div>
            )}
            <button type="submit" className="btn-auth-submit" disabled={loading}>
              {loading ? 'Please wait...' : (mode === 'login' ? 'Sign In' : 'Create Account')}
            </button>
          </form>

          <div className="auth-divider"><span>or continue with</span></div>

          <a href={getLoginUrl()} className="btn-google-login">
            <svg viewBox="0 0 24 24" width="20" height="20">
              <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z" />
              <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z" />
              <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z" />
              <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z" />
            </svg>
            Sign in with Google
          </a>
        </div>
      </div>
    </div>
  );
}


// ============================================================
// Main App
// ============================================================
function App() {
  const [user, setUser] = useState(null);
  const [authChecked, setAuthChecked] = useState(false);
  const [currentPage, setCurrentPage] = useState('dashboard');
  const [portfolio, setPortfolio] = useState(null);
  const [risk, setRisk] = useState(null);
  const [market, setMarket] = useState(null);
  const [watchlist, setWatchlist] = useState([]);
  const [trades, setTrades] = useState([]);
  const [config, setConfig] = useState(null);
  const [indicators, setIndicators] = useState([]);
  const [lastUpdated, setLastUpdated] = useState(null);
  const [loading, setLoading] = useState(true);
  const [profileOpen, setProfileOpen] = useState(false);
  const [newWatchlistSymbol, setNewWatchlistSymbol] = useState('');
  const [watchlistError, setWatchlistError] = useState('');
  const [watchlistLoading, setWatchlistLoading] = useState(false);
  const profileRef = useRef(null);

  // Handle OAuth callback - extract tokens from URL on app load
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const accessToken = params.get('access');
    const refreshToken = params.get('refresh');

    if (accessToken) {
      // Store tokens in localStorage
      setTokens(accessToken, refreshToken);
      // Clean URL (remove query params) so it looks normal
      window.history.replaceState({}, '', window.location.pathname);
    }
  }, []);

  // Watchlist add/remove handlers
  const handleAddToWatchlist = async () => {
    if (!newWatchlistSymbol.trim()) return;
    setWatchlistError('');
    setWatchlistLoading(true);
    try {
      const result = await addToWatchlist(newWatchlistSymbol);
      setNewWatchlistSymbol('');
      // Refresh watchlist data
      const watchlistData = await getWatchlist();
      setWatchlist(watchlistData.watchlist || []);
      if (result.message) {
        // Show success briefly then clear
        setWatchlistError('');
      }
    } catch (e) {
      console.error('Failed to add to watchlist:', e);
      const errorMsg = e.response?.data?.error || e.response?.data?.detail || 'Failed to add symbol. Please try again.';
      setWatchlistError(errorMsg);
    } finally {
      setWatchlistLoading(false);
    }
  };

  const handleRemoveFromWatchlist = async (symbol) => {
    setWatchlistError('');
    try {
      await removeFromWatchlist(symbol);
      // Refresh watchlist data
      const watchlistData = await getWatchlist();
      setWatchlist(watchlistData.watchlist || []);
    } catch (e) {
      console.error('Failed to remove from watchlist:', e);
      const errorMsg = e.response?.data?.error || e.response?.data?.detail || 'Failed to remove symbol.';
      setWatchlistError(errorMsg);
    }
  };

  // Sortable table hooks for dashboard tables
  const { sorted: sortedPositions, sortKey: posSortKey, sortDir: posSortDir, handleSort: posHandleSort } = useSortableTable(portfolio?.positions);
  const { sorted: sortedWatchlist, sortKey: wlSortKey, sortDir: wlSortDir, handleSort: wlHandleSort } = useSortableTable(watchlist);
  const { sorted: sortedTrades, sortKey: trSortKey, sortDir: trSortDir, handleSort: trHandleSort } = useSortableTable(trades);

  // Close profile dropdown on outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (profileRef.current && !profileRef.current.contains(e.target)) {
        setProfileOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const checkAuth = useCallback(async () => {
    try {
      const userData = await getCurrentUser();
      if (userData.authenticated) {
        setUser(userData);
      } else {
        setUser(null);
      }
    } catch (error) {
      console.error('Auth check failed:', error);
      setUser(null);
    } finally {
      setAuthChecked(true);
    }
  }, []);

  useEffect(() => {
    checkAuth();
  }, [checkAuth]);

  const handleLogout = useCallback(async () => {
    await logout();
    setUser(null);
    setAuthChecked(true);
    setCurrentPage('dashboard');
  }, []);

  const fetchData = useCallback(async () => {
    try {
      const results = await Promise.allSettled([
        getPortfolio(),
        getRisk(),
        getMarket(),
        getWatchlist(),
        getTrades(),
        getConfig(),
      ]);

      const [portfolioRes, riskRes, marketRes, watchlistRes, tradesRes, configRes] = results;

      if (portfolioRes.status === 'fulfilled') {
        setPortfolio(portfolioRes.value);
      } else {
        console.error('Portfolio fetch failed:', portfolioRes.reason);
      }

      if (riskRes.status === 'fulfilled') {
        setRisk(riskRes.value);
      } else {
        console.error('Risk fetch failed:', riskRes.reason);
      }

      if (marketRes.status === 'fulfilled') {
        setMarket(marketRes.value);
      } else {
        console.error('Market fetch failed:', marketRes.reason);
      }

      if (watchlistRes.status === 'fulfilled') {
        setWatchlist(watchlistRes.value.watchlist || []);
      } else {
        console.error('Watchlist fetch failed:', watchlistRes.reason);
      }

      if (tradesRes.status === 'fulfilled') {
        setTrades(tradesRes.value.trades || []);
      } else {
        console.error('Trades fetch failed:', tradesRes.reason);
      }

      if (configRes.status === 'fulfilled') {
        setConfig(configRes.value);
      } else {
        console.error('Config fetch failed:', configRes.reason);
      }

      setLastUpdated(new Date().toLocaleTimeString());
      setLoading(false);

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

  // Auth loading
  if (!authChecked) {
    return (
      <div className="dashboard">
        <div className="loading">Checking authentication...</div>
      </div>
    );
  }

  // Not logged in
  if (!user) {
    return <AuthPage onAuthSuccess={(userData) => setUser(userData)} />;
  }

  if (loading && currentPage === 'dashboard') {
    return (
      <div className="dashboard">
        <div className="loading">Loading dashboard...</div>
      </div>
    );
  }

  const dailyChange = portfolio?.performance?.daily_change || 0;
  const dailyChangePct = portfolio?.performance?.daily_change_pct || 0;
  const totalUnrealizedPL = (portfolio?.positions || []).reduce(
    (sum, pos) => sum + (pos.unrealized_pl || 0), 0
  );
  const totalCostBasis = (portfolio?.positions || []).reduce(
    (sum, pos) => sum + ((pos.avg_entry_price || 0) * (pos.qty || 0)), 0
  );
  const totalPLPercent = totalCostBasis > 0 ? (totalUnrealizedPL / totalCostBasis) * 100 : 0;
  const visibleIndicators = indicators.filter((ind) => ind?.overall_signal !== 'ERROR');
  const indicatorFeedDown = indicators.length > 0 && visibleIndicators.length === 0;

  return (
    <div className="dashboard">
      {/* Header */}
      <header className="header">
        <div className="header-left">
          <h1>&#x1F916; LLM Trading Agent</h1>
          <div className="market-status">
            <span className={`status-dot ${market?.is_open ? 'open' : ''}`}></span>
            <span className="status-text">
              {market?.is_open ? 'Market Open' : 'Market Closed'}
            </span>
          </div>
        </div>
        <div className="header-right">
          <span className="last-updated">Last updated: {lastUpdated || '--:--'}</span>
          <button className="btn-refresh" onClick={fetchData}>&#x1F504; Refresh</button>
          <div className="user-profile" ref={profileRef}>
            <div className="profile-trigger" onClick={() => setProfileOpen(!profileOpen)}>
              {user.picture && <img src={user.picture} alt="profile" className="user-avatar" />}
              <span className="user-name">{user.name || user.email}</span>
              <span className={`profile-chevron ${profileOpen ? 'open' : ''}`}>&#x25BE;</span>
            </div>
            {profileOpen && (
              <div className="profile-dropdown">
                {/* Agent Configuration */}
                <div className="profile-section">
                  <div className="profile-section-title">Agent Configuration</div>
                  <div className="config-grid">
                    <div className="config-item"><span className="label">Analysis Interval</span><span className="value">{config?.analysis_interval || 30} min</span></div>
                    <div className="config-item"><span className="label">Max Position %</span><span className="value">{config?.max_position_pct || 10}%</span></div>
                    <div className="config-item"><span className="label">Max Daily Loss</span><span className="value">{config?.max_daily_loss_pct || 3}%</span></div>
                    <div className="config-item"><span className="label">Min Confidence</span><span className="value">{config?.min_confidence || 70}%</span></div>
                    <div className="config-item"><span className="label">Stop Loss</span><span className="value">{config?.stop_loss_pct || 5}%</span></div>
                    <div className="config-item"><span className="label">Take Profit</span><span className="value">{config?.take_profit_pct || 10}%</span></div>
                  </div>
                </div>
                <div className="profile-divider"></div>
                {/* Technical Indicators */}
                <div className="profile-section">
                  <div className="profile-section-title">Technical Indicators</div>
                  <div className="profile-indicators-scroll">
                    <table className="profile-indicators-table">
                      <thead>
                        <tr><th>Symbol</th><th>Price</th><th>RSI</th><th>MACD</th><th>Signal</th></tr>
                      </thead>
                      <tbody>
                        {indicators.length === 0 ? (
                          <tr><td colSpan="5" className="empty-state">Loading indicators...</td></tr>
                        ) : indicatorFeedDown ? (
                          <tr><td colSpan="5" className="empty-state">Indicator data temporarily unavailable</td></tr>
                        ) : (
                          visibleIndicators.map((ind) => (
                            <tr key={ind.symbol}>
                              <td className="symbol-highlight">{ind.symbol}</td>
                              <td>{ind.price ? formatCurrency(ind.price) : '--'}</td>
                              <td>
                                <span className={getSignalClass(ind.rsi_signal)}>{ind.rsi ? ind.rsi.toFixed(1) : '--'}</span>
                                <span className="signal-badge">{ind.rsi_signal || ''}</span>
                              </td>
                              <td>
                                <span className={getSignalClass(ind.macd_trend)}>{ind.macd ? ind.macd.toFixed(2) : '--'}</span>
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
                <div className="profile-divider"></div>
                {/* Logout */}
                <button onClick={handleLogout} className="profile-logout">
                  Sign Out
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Navigation Tabs */}
      <nav className="nav-tabs">
        <button
          className={`nav-tab ${currentPage === 'dashboard' ? 'active' : ''}`}
          onClick={() => setCurrentPage('dashboard')}
        >
          Dashboard
        </button>
        <button
          className={`nav-tab ${currentPage === 'options' ? 'active' : ''}`}
          onClick={() => setCurrentPage('options')}
        >
          Options Chain
        </button>
        <button
          className={`nav-tab ${currentPage === 'collar' ? 'active' : ''}`}
          onClick={() => setCurrentPage('collar')}
        >
          Collar Strategy
        </button>
      </nav>

      {/* Page Content */}
      {currentPage === 'dashboard' && (
        <>
          {/* Dashboard Hero Header */}
          <div className="dash-header-row">
            <div>
              <div className="dash-label">TRADING DASHBOARD</div>
              <h2 className="dash-title">Your Portfolio at a Glance</h2>
              <p className="dash-subtitle">
                Real-time portfolio tracking, risk management, and trade execution powered by AI.
              </p>
            </div>
            <div className="dash-status-card">
              <div className="dash-status-label">BROKER STATUS</div>
              <div className="dash-status-value">
                <span className={`dash-status-dot ${market?.is_open ? 'active' : ''}`}></span>
                {market?.is_open ? 'Market Open' : 'Market Closed'}
              </div>
              <div className="dash-status-detail">
                {portfolio?.positions?.length || 0} positions &middot; {formatCurrency(portfolio?.account?.portfolio_value || 0)}
              </div>
            </div>
          </div>

          <div className="main-grid">
            {/* Portfolio Card */}
            <div className="card portfolio-card">
              <div className="card-label">OVERVIEW</div>
              <h2>Portfolio</h2>
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
                  <span className="label">Overall P&L</span>
                  <span className={`value ${totalUnrealizedPL >= 0 ? 'positive' : 'negative'}`}>
                    {formatCurrency(totalUnrealizedPL)} ({formatPercent(totalPLPercent)})
                  </span>
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
              <div className="card-label">RISK</div>
              <h2>Risk Status</h2>
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
                  <span className="value">{risk?.kill_switch_active ? 'Active' : 'Inactive'}</span>
                </div>
              </div>
            </div>

            {/* Positions Card */}
            <div className="card positions-card">
              <div className="card-label">HOLDINGS</div>
              <h2>Current Positions ({portfolio?.positions?.length || 0})</h2>
              <div className="positions">
                <table className="positions-table">
                  <thead>
                    <tr>
                      <SortTh label="Symbol" sortKey="symbol" currentKey={posSortKey} currentDir={posSortDir} onSort={posHandleSort} />
                      <SortTh label="Qty" sortKey="qty" currentKey={posSortKey} currentDir={posSortDir} onSort={posHandleSort} />
                      <SortTh label="Avg Cost" sortKey="avg_entry_price" currentKey={posSortKey} currentDir={posSortDir} onSort={posHandleSort} />
                      <SortTh label="Current" sortKey="current_price" currentKey={posSortKey} currentDir={posSortDir} onSort={posHandleSort} />
                      <SortTh label="Mkt Value" sortKey="market_value" currentKey={posSortKey} currentDir={posSortDir} onSort={posHandleSort} />
                      <SortTh label="P&L" sortKey="unrealized_pl" currentKey={posSortKey} currentDir={posSortDir} onSort={posHandleSort} />
                      <SortTh label="P&L %" sortKey="unrealized_plpc" currentKey={posSortKey} currentDir={posSortDir} onSort={posHandleSort} />
                    </tr>
                  </thead>
                  <tbody>
                    {sortedPositions.length === 0 ? (
                      <tr><td colSpan="7" className="empty-state">No positions (100% cash)</td></tr>
                    ) : (
                      sortedPositions.map((pos) => (
                        <tr key={pos.symbol}>
                          <td className="symbol-highlight">{pos.symbol}</td>
                          <td>{pos.qty}</td>
                          <td>{formatCurrency(pos.avg_entry_price)}</td>
                          <td>{formatCurrency(pos.current_price)}</td>
                          <td>{formatCurrency(pos.market_value)}</td>
                          <td className={pos.unrealized_pl >= 0 ? 'positive' : 'negative'}>
                            {formatCurrency(pos.unrealized_pl)}
                          </td>
                          <td className={pos.unrealized_plpc >= 0 ? 'positive' : 'negative'}>
                            {formatPercent(pos.unrealized_plpc * 100)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Watchlist Card */}
            <div className="card watchlist-card">
              <div className="card-label">WATCHLIST</div>
              <h2>Tracked Symbols ({watchlist.length})</h2>
              <div className="watchlist-add-form">
                <input
                  type="text"
                  placeholder="Add symbol..."
                  value={newWatchlistSymbol}
                  onChange={(e) => setNewWatchlistSymbol(e.target.value.toUpperCase())}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddToWatchlist()}
                  disabled={watchlistLoading}
                />
                <button onClick={handleAddToWatchlist} disabled={watchlistLoading}>
                  {watchlistLoading ? '...' : 'Add'}
                </button>
              </div>
              {watchlistError && (
                <div className="watchlist-error" style={{color: '#ff6b6b', fontSize: '12px', marginBottom: '8px'}}>
                  {watchlistError}
                </div>
              )}
              <div className="positions">
                <table className="watchlist-table">
                  <thead>
                    <tr>
                      <SortTh label="Symbol" sortKey="symbol" currentKey={wlSortKey} currentDir={wlSortDir} onSort={wlHandleSort} />
                      <SortTh label="Price" sortKey="price" currentKey={wlSortKey} currentDir={wlSortDir} onSort={wlHandleSort} />
                      <SortTh label="Change" sortKey="change" currentKey={wlSortKey} currentDir={wlSortDir} onSort={wlHandleSort} />
                      <SortTh label="Change %" sortKey="change_pct" currentKey={wlSortKey} currentDir={wlSortDir} onSort={wlHandleSort} />
                      <SortTh label="Prev Close" sortKey="prev_close" currentKey={wlSortKey} currentDir={wlSortDir} onSort={wlHandleSort} />
                      <SortTh label="Volume" sortKey="volume" currentKey={wlSortKey} currentDir={wlSortDir} onSort={wlHandleSort} />
                      <SortTh label="Mkt Cap" sortKey="market_cap" currentKey={wlSortKey} currentDir={wlSortDir} onSort={wlHandleSort} />
                      <th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {sortedWatchlist.length === 0 ? (
                      <tr><td colSpan="8" className="empty-state">Loading watchlist...</td></tr>
                    ) : (
                      sortedWatchlist.map((item) => (
                        <tr key={item.symbol}>
                          <td className="symbol-highlight">{item.symbol}</td>
                          <td>{item.price > 0 ? formatCurrency(item.price) : '--'}</td>
                          <td className={(item.change || 0) >= 0 ? 'positive' : 'negative'}>
                            {item.change != null ? `${item.change >= 0 ? '+' : ''}${item.change.toFixed(2)}` : '--'}
                          </td>
                          <td className={(item.change_pct || 0) >= 0 ? 'positive' : 'negative'}>
                            {item.change_pct != null ? `${item.change_pct >= 0 ? '+' : ''}${item.change_pct.toFixed(2)}%` : '--'}
                          </td>
                          <td>{item.prev_close > 0 ? formatCurrency(item.prev_close) : '--'}</td>
                          <td>{item.volume ? item.volume.toLocaleString() : '--'}</td>
                          <td>{formatMarketCap(item.market_cap)}</td>
                          <td>
                            <button
                              className="btn-remove-watchlist"
                              onClick={() => handleRemoveFromWatchlist(item.symbol)}
                              title={`Remove ${item.symbol}`}
                            >
                              &times;
                            </button>
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Trade History Card */}
            <div className="card trades-card">
              <div className="card-label">EXECUTION</div>
              <h2>Trade History</h2>
              <div className="trades-table">
                <table>
                  <thead>
                    <tr>
                      <SortTh label="Time" sortKey="created_at" currentKey={trSortKey} currentDir={trSortDir} onSort={trHandleSort} />
                      <SortTh label="Action" sortKey="action" currentKey={trSortKey} currentDir={trSortDir} onSort={trHandleSort} />
                      <SortTh label="Symbol" sortKey="symbol" currentKey={trSortKey} currentDir={trSortDir} onSort={trHandleSort} />
                      <SortTh label="Qty" sortKey="quantity" currentKey={trSortKey} currentDir={trSortDir} onSort={trHandleSort} />
                      <SortTh label="Price" sortKey="filled_price" currentKey={trSortKey} currentDir={trSortDir} onSort={trHandleSort} />
                      <SortTh label="Status" sortKey="status" currentKey={trSortKey} currentDir={trSortDir} onSort={trHandleSort} />
                    </tr>
                  </thead>
                  <tbody>
                    {sortedTrades.length === 0 ? (
                      <tr><td colSpan="6" className="empty-state">No trades yet - Agent will execute during market hours</td></tr>
                    ) : (
                      sortedTrades.map((trade, idx) => (
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
          </div>
        </>
      )}
      {currentPage === 'options' && <OptionChainPage />}
      {currentPage === 'collar' && <CollarStrategyPage />}
    </div>
  );
}

export default App;
