// QuantEdge AI - Real-Time Dashboard Logic & Chart Engine

let equityChartInstance = null;
let assetChartInstance = null;
let currentTab = 'overview';

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  initClocks();
  initCharts();
  if (window.InstitutionalChart) {
    window.InstitutionalChart.init();
  }
  const hash = (window.location.hash || '').replace('#', '');
  if (['overview', 'assets', 'positions', 'macro', 'reports', 'observability'].includes(hash)) {
    switchTab(hash);
  }
  fetchDashboardData();
  setInterval(fetchDashboardData, 5000); // 5-second live polling
});

// Clocks
function initClocks() {
  function updateTime() {
    const now = new Date();
    // UTC
    const utcHours = String(now.getUTCHours()).padStart(2, '0');
    const utcMins = String(now.getUTCMinutes()).padStart(2, '0');
    const utcSecs = String(now.getUTCSeconds()).padStart(2, '0');
    document.getElementById('utc-clock').textContent = `${utcHours}:${utcMins}:${utcSecs}`;

    // Local
    const locHours = String(now.getHours()).padStart(2, '0');
    const locMins = String(now.getMinutes()).padStart(2, '0');
    const locSecs = String(now.getSeconds()).padStart(2, '0');
    document.getElementById('local-clock').textContent = `${locHours}:${locMins}:${locSecs}`;

    // Date
    const options = { weekday: 'long', year: 'numeric', month: 'short', day: 'numeric' };
    document.getElementById('current-date-display').textContent = now.toLocaleDateString('en-US', options);
  }
  updateTime();
  setInterval(updateTime, 1000);
}

// Tab Switching
function switchTab(tabId) {
  currentTab = tabId;
  // Update Nav
  document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active'));
  const activeNav = document.getElementById(`nav-${tabId}`);
  if (activeNav) activeNav.classList.add('active');

  // Update Panes
  document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.remove('active'));
  const activePane = document.getElementById(`pane-${tabId}`);
  if (activePane) activePane.classList.add('active');

  // Update Page Title
  const titles = {
    overview: 'Executive Overview',
    assets: 'Asset Strategies Matrix',
    positions: 'Live Open Positions',
    macro: 'Macro Climate & News Catalyst Schedule',
    reports: 'Daily Performance Reports',
    observability: 'Model Observability & Cost Tracking',
  };
  document.getElementById('page-title').textContent = titles[tabId] || 'Dashboard';
  if (tabId === 'observability') {
    fetchObservabilityLogs();
  }
  if (tabId === 'positions') {
    setTimeout(() => {
      if (window.InstitutionalChart) {
        window.InstitutionalChart.init();
        const container = document.getElementById('liveChartContainer');
        if (container && window.InstitutionalChart.chart && container.clientWidth > 0) {
          window.InstitutionalChart.chart.resize(container.clientWidth, container.clientHeight || 520);
          window.InstitutionalChart.fitContent();
        }
        window.InstitutionalChart.fetchChartData();
      }
    }, 60);
  }
}

// Chart Initializations
function initCharts() {
  // 1. Equity Curve Chart
  const ctxEquity = document.getElementById('equityChart');
  if (ctxEquity) {
    equityChartInstance = new Chart(ctxEquity, {
      type: 'line',
      data: {
        labels: ['Day -14', 'Day -12', 'Day -10', 'Day -8', 'Day -6', 'Day -4', 'Day -2', 'Today'],
        datasets: [{
          label: 'Portfolio Equity ($)',
          data: [10000, 10080, 10140, 10210, 10320, 10390, 10480, 10544],
          borderColor: '#10b981',
          borderWidth: 2.5,
          backgroundColor: 'rgba(16, 185, 129, 0.08)',
          fill: true,
          tension: 0.35,
          pointRadius: 3,
          pointBackgroundColor: '#10b981',
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#111827',
            titleColor: '#94a3b8',
            bodyColor: '#10b981',
            borderColor: 'rgba(255,255,255,0.1)',
            borderWidth: 1,
          }
        },
        scales: {
          x: {
            grid: { color: 'rgba(255, 255, 255, 0.03)' },
            ticks: { color: '#64748b', font: { size: 11 } }
          },
          y: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: {
              color: '#64748b',
              font: { size: 11 },
              callback: (val) => '$' + val.toLocaleString()
            }
          }
        }
      }
    });
  }

  // 2. Asset Performance Chart
  const ctxAsset = document.getElementById('assetChart');
  if (ctxAsset) {
    assetChartInstance = new Chart(ctxAsset, {
      type: 'bar',
      data: {
        labels: ['Gold (XAU)', 'Crude (OIL)', 'Euro (EUR)'],
        datasets: [{
          label: 'Benchmark Net PnL ($)',
          data: [461.14, 188.79, -105.86],
          backgroundColor: [
            'rgba(245, 158, 11, 0.85)',
            'rgba(6, 182, 212, 0.85)',
            'rgba(99, 102, 241, 0.85)',
          ],
          borderRadius: 6,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            backgroundColor: '#111827',
            titleColor: '#94a3b8',
            bodyColor: '#fff',
          }
        },
        scales: {
          x: {
            grid: { display: false },
            ticks: { color: '#94a3b8', font: { size: 11 } }
          },
          y: {
            grid: { color: 'rgba(255, 255, 255, 0.05)' },
            ticks: {
              color: '#64748b',
              font: { size: 11 },
              callback: (val) => (val >= 0 ? '+$' : '-$') + Math.abs(val)
            }
          }
        }
      }
    });
  }
}

// Fetch Data from QuantEdge API
async function fetchDashboardData() {
  try {
    const [dailyRes, reportRes, schedRes, missedRes] = await Promise.all([
      fetch('/api/v1/analytics/daily').then(r => r.ok ? r.json() : null),
      fetch('/api/v1/analytics/reports').then(r => r.ok ? r.json() : null),
      fetch('/api/v1/analytics/schedule').then(r => r.ok ? r.json() : null),
      fetch('/api/v1/analytics/missed-opportunities').then(r => r.ok ? r.json() : null),
    ]);

    if (dailyRes) updateDailyView(dailyRes);
    if (reportRes) updateReportsView(reportRes);
    if (schedRes) updateScheduleView(schedRes);
    if (missedRes) renderMissedOpportunities(missedRes);
  } catch (err) {
    console.warn('Dashboard live fetch error:', err);
  }
}

// Update DOM with Daily Analytics
function updateDailyView(data) {
  const acc = data.account || {};
  const perf = data.daily_performance || {};
  const macro = data.macro || {};

  // Account
  const eq = acc.equity || 501.94;
  const bal = acc.balance || 501.94;
  document.getElementById('val-equity').textContent = `$${eq.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
  document.getElementById('val-balance').textContent = `$${bal.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
  document.getElementById('account-meta-text').textContent = `Account: ${acc.account_id || '73116061'} (${acc.trade_mode || 'Demo'})`;

  // Bridge status
  const pulse = document.getElementById('bridge-pulse');
  const bridgeText = document.getElementById('bridge-status-text');
  if (acc.connected) {
    pulse.className = 'status-indicator online';
    bridgeText.textContent = 'Exness MT4 Active';
  } else {
    pulse.className = 'status-indicator';
    bridgeText.textContent = 'MT4 Disconnected';
  }

  // Net PnL (True MT4 Realized)
  const netPnl = perf.net_pnl || 0.0;
  const pnlEl = document.getElementById('val-net-pnl');
  const trendEl = document.getElementById('badge-pnl-trend');
  const sign = netPnl >= 0 ? '+' : '-';
  pnlEl.textContent = `${sign}$${Math.abs(netPnl).toFixed(2)}`;
  pnlEl.style.color = netPnl > 0 ? 'var(--accent-green)' : (netPnl < 0 ? 'var(--accent-red)' : 'var(--text-main)');
  trendEl.textContent = `${sign}${((Math.abs(netPnl) / Math.max(bal, 1)) * 100).toFixed(1)}%`;
  trendEl.className = netPnl >= 0 ? 'trend-badge positive' : 'trend-badge negative';

  document.getElementById('val-gross-profit').textContent = `$${(perf.gross_profit || 0).toFixed(2)}`;
  document.getElementById('val-gross-loss').textContent = `$${(perf.gross_loss || 0).toFixed(2)}`;

  // Win Rate & Real MT4 Metrics (Zero Fallbacks to Backtest)
  const totalTrades = perf.total_trades || 0;
  const wr = totalTrades > 0 && perf.win_rate_pct !== undefined ? perf.win_rate_pct : 0.0;
  document.getElementById('val-win-rate').textContent = `${wr.toFixed(1)}%`;
  document.getElementById('val-ratio-fill').style.width = `${Math.min(100, Math.max(0, wr))}%`;
  document.getElementById('val-win-loss-count').textContent = `${perf.wins || 0}W / ${perf.losses || 0}L`;

  // Profit factor & Averages
  const pf = totalTrades > 0 && perf.profit_factor !== undefined ? perf.profit_factor : 0.0;
  const avgWin = totalTrades > 0 && perf.avg_win !== undefined ? perf.avg_win : 0.0;
  const avgLoss = totalTrades > 0 && perf.avg_loss !== undefined ? perf.avg_loss : 0.0;
  document.getElementById('val-profit-factor').textContent = pf.toFixed(2);
  document.getElementById('val-avg-win').textContent = `$${avgWin.toFixed(2)}`;
  document.getElementById('val-avg-loss').textContent = `$${avgLoss.toFixed(2)}`;

  // Macro Regime Header
  const regime = (macro.regime || 'risk-on').toUpperCase();
  document.getElementById('header-regime-name').textContent = regime;
  document.getElementById('macro-regime-tag').textContent = regime;
  document.getElementById('macro-summary-text').textContent = macro.summary || 'Consensus aligned with institutional M15 execution.';
  document.getElementById('macro-confidence-val').textContent = `${Math.round((macro.confidence || 0.85) * 100)}%`;

  // Spread guard status
  const guardPill = document.getElementById('spread-guard-pill');
  const guardStatus = document.getElementById('macro-guard-status');
  if (macro.is_pre_news_blackout) {
    guardPill.style.display = 'flex';
    guardStatus.textContent = 'Active (Blackout)';
    guardStatus.style.color = 'var(--accent-gold)';
  } else {
    guardPill.style.display = 'flex';
    guardStatus.textContent = 'Standby (Normal)';
    guardStatus.style.color = 'var(--accent-green)';
  }

  // Open Positions
  const positions = data.open_positions || [];
  document.getElementById('open-positions-badge').textContent = positions.length;
  renderPositionsTable(positions);
  if (window.InstitutionalChart && typeof window.InstitutionalChart.syncOpenPositionDots === 'function') {
    window.InstitutionalChart.syncOpenPositionDots(positions);
  }

  // Strategy Intelligence & Scores
  if (data.strategy_status) {
    renderStrategyStatus(data.strategy_status, data.asset_breakdown);
  }

  // Asset-Specific Macro & Hourly News
  if (data.asset_macro) {
    renderAssetMacro(data.asset_macro);
  }

  // Daily Report Tab elements (Real MT4 Ground Truth)
  document.getElementById('rep-date').textContent = data.date || '-';
  document.getElementById('rep-net-pnl').textContent = `${sign}$${Math.abs(netPnl).toFixed(2)}`;
  document.getElementById('rep-win-rate').textContent = `${wr.toFixed(1)}%`;
  document.getElementById('rep-pf').textContent = pf.toFixed(2);
  document.getElementById('rep-trades').textContent = totalTrades;
  document.getElementById('rep-regime').textContent = regime;

  // Real MT4 Account Bar in Report Tab
  if (data.account) {
    const acc = data.account;
    const sEl = document.getElementById('rep-acc-server');
    const nEl = document.getElementById('rep-acc-num');
    const bEl = document.getElementById('rep-acc-bal');
    const eEl = document.getElementById('rep-acc-eq');
    if (sEl) sEl.textContent = acc.server || 'Exness-Trial12';
    if (nEl) nEl.textContent = acc.account_id || '73116061';
    if (bEl) bEl.textContent = `$${(acc.balance || 0).toFixed(2)}`;
    if (eEl) eEl.textContent = `$${(acc.equity || 0).toFixed(2)}`;
  }

  // Render Real MT4 Asset Performance Breakdown
  renderDailyReportBreakdown(data.asset_breakdown);
}

// Render Real MT4 Asset Performance Breakdown Table
function renderDailyReportBreakdown(breakdown) {
  const tbody = document.getElementById('rep-breakdown-tbody');
  if (!tbody) return;

  if (!breakdown || Object.keys(breakdown).length === 0) {
    tbody.innerHTML = '<tr><td colspan="8" class="text-center empty-state">Awaiting live MT4 asset stream...</td></tr>';
    return;
  }

  const assetNames = {
    XAUUSD: 'Gold (XAUUSD)',
    USOIL: 'Crude Oil (USOIL)',
    EURUSD: 'Euro FX (EURUSD)',
    BTCUSD: 'Bitcoin (BTCUSD)',
  };

  tbody.innerHTML = Object.entries(breakdown).map(([sym, item]) => {
    const title = assetNames[sym] || sym;
    const strategy = item.strategy || 'Adaptive Strategy';
    const isFx = sym.includes('EUR');
    const price = item.live_price ? (isFx ? item.live_price.toFixed(5) : `$${item.live_price.toFixed(2)}`) : '--';
    const openPos = item.open_positions > 0 ? `${item.open_positions} (${item.open_volume} lots)` : '0';
    const trades = item.trades || 0;
    const wr = item.win_rate !== undefined ? `${item.win_rate.toFixed(1)}%` : '0.0%';
    const pnl = item.net_pnl !== undefined ? item.net_pnl : 0.0;
    const pnlSign = pnl >= 0 ? '+' : '-';
    const pnlColor = pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)';
    const statusDesc = item.status_description || 'Active M15 Monitoring';
    const tagClass = item.status === 'TRIGGERED' ? 'active' : (item.status === 'HOLDING' ? 'active' : (item.status === 'DEBATING' ? 'controlled' : ''));

    return `
      <tr>
        <td><strong>${title}</strong></td>
        <td style="font-size: 12px; color: #cbd5e1;">${strategy}</td>
        <td class="positive" style="font-weight: 700;">${price}</td>
        <td>${openPos}</td>
        <td>${trades}</td>
        <td style="color: ${trades > 0 && item.win_rate >= 50 ? 'var(--accent-green)' : '#94a3b8'}; font-weight: 600;">${wr}</td>
        <td style="color: ${pnlColor}; font-weight: 700;">${pnlSign}$${Math.abs(pnl).toFixed(2)}</td>
        <td><span class="status-tag ${tagClass}">${statusDesc}</span></td>
      </tr>
    `;
  }).join('');
}

// Render Open Positions Table
function renderPositionsTable(positions) {
  const tbody = document.getElementById('positions-tbody');
  if (!positions || positions.length === 0) {
    tbody.innerHTML = `<tr><td colspan="11" class="text-center empty-state">No open positions currently active. Bot is monitoring M15 setups.</td></tr>`;
    return;
  }

  let html = '';
  positions.forEach(pos => {
    const isProfitable = (pos.unrealized_pnl || 0) >= 0;
    const pnlSign = isProfitable ? '+' : '-';
    const pnlColor = isProfitable ? 'var(--accent-green)' : 'var(--accent-red)';
    const sideBadge = pos.side === 'long' 
      ? '<span class="trend-badge positive">LONG</span>' 
      : '<span class="trend-badge negative">SHORT</span>';

    const rMult = pos.r_multiple !== undefined ? pos.r_multiple : 0.0;
    const rSign = rMult >= 0 ? '+' : '';
    const rColor = rMult >= 1.0 ? 'var(--accent-green)' : (rMult < 0 ? 'var(--accent-red)' : 'var(--accent-gold)');

    // Action badge styling
    let actionBadge = `<span class="card-chip">${pos.lifecycle_action || 'HOLD'}</span>`;
    if (pos.lifecycle_action === 'CLOSE_DEFENSIVE' || pos.lifecycle_action === 'CLOSE_PRE_NEWS') {
      actionBadge = `<span class="trend-badge negative" title="${pos.lifecycle_reason || ''}">⚡ ${pos.lifecycle_action}</span>`;
    } else if (pos.lifecycle_action === 'CLOSE_TAKE_PROFIT') {
      actionBadge = `<span class="trend-badge positive" title="${pos.lifecycle_reason || ''}">💰 BANK +2R</span>`;
    } else if (pos.lifecycle_action === 'CLOSE_ALPHA_DECAY') {
      actionBadge = `<span class="trend-badge negative" style="background: rgba(245, 158, 11, 0.2); border: 1px solid #f59e0b; color: #fbbf24;" title="${pos.lifecycle_reason || ''}">⏳ ALPHA DECAY</span>`;
    } else if (pos.lifecycle_action === 'CLOSE_TRAIL_EXIT') {
      actionBadge = `<span class="trend-badge positive" style="background: rgba(59, 130, 246, 0.2); border: 1px solid #3b82f6; color: #60a5fa;" title="${pos.lifecycle_reason || ''}">📉 TRAIL EXIT</span>`;
    } else if (pos.lifecycle_action === 'MOVE_BREAKEVEN') {
      actionBadge = `<span class="trend-badge positive" title="${pos.lifecycle_reason || ''}">🔒 LOCK BE</span>`;
    } else if (pos.lifecycle_action === 'SCALE_IN') {
      actionBadge = `<span class="trend-badge positive" style="background: rgba(16, 185, 129, 0.2); border: 1px solid #10b981;" title="${pos.lifecycle_reason || ''}">🚀 SCALE-IN</span>`;
    }

    const controlButtons = `
      <div style="display: flex; gap: 6px; align-items: center;">
        <button class="btn btn-sm" onclick="InstitutionalChart.selectAsset('${pos.symbol}'); window.scrollTo({top: 0, behavior: 'smooth'});" style="background: rgba(99, 102, 241, 0.15); color: #818cf8; border: 1px solid rgba(99, 102, 241, 0.4); padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px;" title="Focus Chart on this Symbol">
          📈 Chart
        </button>
        <button id="btn-close-${pos.ticket}" class="btn btn-sm" onclick="closeOrderTicket('${pos.ticket}')" style="background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.4); padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px;">
          ✕ Close
        </button>
        ${pos.can_scale_in ? `
          <button id="btn-scale-${pos.symbol}" class="btn btn-sm" onclick="scaleInPosition('${pos.symbol}')" style="background: rgba(16, 185, 129, 0.18); color: #34d399; border: 1px solid #10b981; padding: 4px 8px; border-radius: 4px; cursor: pointer; font-size: 11px;">
            + Scale In
          </button>
        ` : ''}
      </div>
    `;

    const mfeStr = pos.mfe !== undefined ? `+${pos.mfe.toFixed(2)}R` : '-';
    const maeStr = pos.mae !== undefined ? `${pos.mae.toFixed(2)}R` : '-';
    const excursionSub = `<div style="font-size: 10px; opacity: 0.7; font-weight: normal; margin-top: 2px;">MFE: ${mfeStr} | MAE: ${maeStr}</div>`;

    html += `
      <tr>
        <td><strong>#${pos.ticket || '0'}</strong></td>
        <td><strong>${pos.symbol}</strong> <span style="font-size: 10px; opacity: 0.6;">(${pos.session || 'M15'})</span></td>
        <td>${sideBadge}</td>
        <td>${(pos.volume || 0.01).toFixed(2)}</td>
        <td>${pos.entry_price ? pos.entry_price.toFixed(pos.symbol.includes('EUR') ? 4 : 2) : '-'}</td>
        <td>${pos.stop_loss ? pos.stop_loss.toFixed(pos.symbol.includes('EUR') ? 4 : 2) : '-'}</td>
        <td>${pos.take_profit ? pos.take_profit.toFixed(pos.symbol.includes('EUR') ? 4 : 2) : '-'}</td>
        <td style="color: ${pnlColor}; font-weight: 700;">${pnlSign}$${Math.abs(pos.unrealized_pnl || 0).toFixed(2)}</td>
        <td style="color: ${rColor}; font-weight: 700;">
          ${rSign}${rMult.toFixed(2)}R
          ${excursionSub}
        </td>
        <td title="${pos.lifecycle_reason || ''}">${actionBadge}</td>
        <td>${controlButtons}</td>
      </tr>
    `;
  });
  tbody.innerHTML = html;
}

// Render Live Strategy Intelligence & Scores
let prevPrices = {};

function renderStrategyStatus(strategyStatus, assetBreakdown) {
  if (!strategyStatus) return;

  // 1. Update Overview Tab Cards
  Object.entries(strategyStatus).forEach(([sym, item]) => {
    const pEl = document.getElementById(`ov-price-${sym}`);
    const sEl = document.getElementById(`ov-score-${sym}`);
    const tagEl = document.getElementById(`ov-status-${sym}`);
    const wrEl = document.getElementById(`ov-winrate-${sym}`);
    const pnlEl = document.getElementById(`ov-pnl-${sym}`);
    const badgeEl = document.getElementById(`ov-badge-${sym}`);

    const px = item.live_price || (item.indicators ? item.indicators.price : null);
    const score = item.score !== undefined ? item.score : 50.0;
    const threshold = item.threshold || 65.0;
    const isTriggered = score >= threshold && item.checklist && item.checklist.score_met;
    const side = (item.side || 'none').toUpperCase();

    if (pEl && px !== null) {
      const prevPx = prevPrices[sym];
      const isUp = prevPx ? px > prevPx : false;
      const isDown = prevPx ? px < prevPx : false;
      const prefix = sym === 'EURUSD' ? '' : '$';
      pEl.textContent = `${prefix}${sym === 'EURUSD' ? px.toFixed(5) : px.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
      pEl.style.color = isUp ? 'var(--accent-green)' : (isDown ? 'var(--accent-red)' : 'var(--text-main)');
    }

    if (sEl) {
      sEl.innerHTML = `<span style="color: ${isTriggered ? '#10b981' : '#eab308'}; font-weight: 700;">${score.toFixed(1)}</span> / ${threshold.toFixed(0)}`;
    }

    if (badgeEl && item.strategy_name) {
      badgeEl.innerHTML = `${item.strategy_name} 🔍`;
    }

    // Bind real MT4 win rate and net PnL from broker ground truth
    if (assetBreakdown && assetBreakdown[sym]) {
      const ab = assetBreakdown[sym];
      if (wrEl) {
        wrEl.textContent = ab.trades > 0 ? `${ab.win_rate.toFixed(1)}%` : '0.0%';
        wrEl.style.color = ab.trades > 0 && ab.win_rate >= 50 ? 'var(--accent-green)' : '#94a3b8';
      }
      if (pnlEl) {
        const pnl = ab.net_pnl || 0.0;
        const sign = pnl >= 0 ? '+' : '-';
        pnlEl.textContent = `${sign}$${Math.abs(pnl).toFixed(2)}`;
        pnlEl.style.color = pnl > 0 ? 'var(--accent-green)' : (pnl < 0 ? 'var(--accent-red)' : 'var(--text-main)');
      }
    }

    if (tagEl) {
      if (isTriggered) {
        tagEl.className = 'status-tag active';
        tagEl.textContent = `⚡ ORDER: ${side}`;
      } else if (score >= 55.0) {
        tagEl.className = 'status-tag active';
        tagEl.textContent = `IMMINENT (${score.toFixed(0)})`;
      } else {
        tagEl.className = 'status-tag controlled';
        tagEl.textContent = 'WAITING SETUP';
      }
    }

    if (px !== null) prevPrices[sym] = px;
  });

  // 2. Update Asset Strategies Tab Cards
  const container = document.getElementById('live-strategy-cards-container');
  if (!container) return;

  const assetMeta = {
    XAUUSD: { title: 'Gold (XAUUSD)', badge: 'Momentum Impulse Runner', icon: 'AU', iconClass: 'gold' },
    USOIL: { title: 'WTI Crude (USOIL)', badge: 'NY Volatility Breakout', icon: 'OIL', iconClass: 'oil' },
    EURUSD: { title: 'Euro FX (EURUSD)', badge: 'Liquidity Sweep Mean Revert', icon: 'EUR', iconClass: 'euro' },
    BTCUSD: { title: 'Bitcoin (BTCUSD)', badge: 'Momentum Impulse Runner', icon: '₿', iconClass: 'gold' },
  };

  const cardsHtml = Object.entries(strategyStatus).map(([sym, item]) => {
    const meta = assetMeta[sym] || { title: sym, badge: 'Adaptive M15', icon: sym.slice(0, 3), iconClass: 'gold' };
    const score = item.score !== undefined ? item.score : 50.0;
    const threshold = item.threshold || 60.0;
    const isTriggered = score >= threshold;
    const isImminent = score >= 55.0 && !isTriggered;
    const side = (item.side || 'none').toUpperCase();
    const progress = Math.min(100, Math.round((score / threshold) * 100));

    const indicators = item.indicators || {};
    const checklist = item.checklist || {};
    const potentialOrder = item.potential_order;

    let indHtml = '';
    if (sym === 'XAUUSD') {
      indHtml = `
        <div class="stat-col"><label>Live Price (5s)</label><div class="stat-val positive">$${indicators.price || '--'}</div></div>
        <div class="stat-col"><label>EMAs (9 / 21 / 50)</label><div class="stat-val" style="font-size: 11px;">${indicators.ema9 || '--'} | ${indicators.ema21 || '--'} | ${indicators.ema50 || '--'}</div></div>
        <div class="stat-col"><label>ADX (14) Trend</label><div class="stat-val">${indicators.adx || '--'} ${indicators.adx >= 18 ? '⚡' : ''}</div></div>
        <div class="stat-col"><label>ATR Volatility</label><div class="stat-val">$${indicators.atr || '--'}</div></div>
      `;
    } else if (sym === 'USOIL') {
      indHtml = `
        <div class="stat-col"><label>Live Price (5s)</label><div class="stat-val positive">$${indicators.price || '--'}</div></div>
        <div class="stat-col"><label>Donchian Range (20)</label><div class="stat-val" style="font-size: 11px;">$${indicators.donchian_low || '--'} - $${indicators.donchian_high || '--'}</div></div>
        <div class="stat-col"><label>EMAs (20 / 50)</label><div class="stat-val" style="font-size: 11px;">${indicators.ema20 || '--'} | ${indicators.ema50 || '--'}</div></div>
        <div class="stat-col"><label>ADX (14) Trend</label><div class="stat-val">${indicators.adx || '--'} ${indicators.adx >= 18 ? '⚡' : ''}</div></div>
      `;
    } else if (sym === 'BTCUSD') {
      indHtml = `
        <div class="stat-col"><label>Live Price (5s)</label><div class="stat-val positive">$${indicators.price ? indicators.price.toLocaleString(undefined, {minimumFractionDigits: 2}) : '--'}</div></div>
        <div class="stat-col"><label>EMAs (9 / 21)</label><div class="stat-val" style="font-size: 11px;">${indicators.ema9 || '--'} | ${indicators.ema21 || '--'}</div></div>
        <div class="stat-col"><label>ADX (14) Trend</label><div class="stat-val">${indicators.adx || '--'} ${indicators.adx >= 20 ? '⚡' : ''}</div></div>
        <div class="stat-col"><label>ATR Volatility</label><div class="stat-val">$${indicators.atr || '--'}</div></div>
      `;
    } else {
      indHtml = `
        <div class="stat-col"><label>Live Price (5s)</label><div class="stat-val positive">${indicators.price || '--'}</div></div>
        <div class="stat-col"><label>Bollinger Bands</label><div class="stat-val" style="font-size: 11px;">${indicators.bb_lower || '--'} - ${indicators.bb_upper || '--'}</div></div>
        <div class="stat-col"><label>RSI (14)</label><div class="stat-val">${indicators.rsi || '--'} ${indicators.rsi <= 35 || indicators.rsi >= 65 ? '🎯' : ''}</div></div>
        <div class="stat-col"><label>ATR Volatility</label><div class="stat-val">${indicators.atr || '--'}</div></div>
      `;
    }

    // Potential Order Jump Banner
    let orderBanner = '';
    if (potentialOrder) {
      if (potentialOrder.triggered) {
        orderBanner = `
          <div style="background: rgba(16, 185, 129, 0.18); border: 2px solid #10b981; border-radius: 8px; padding: 14px; margin-bottom: 14px; box-shadow: 0 0 16px rgba(16, 185, 129, 0.25);">
            <div style="font-weight: 800; color: #34d399; font-size: 13px; display: flex; justify-content: space-between; align-items: center;">
              <span>⚡ ALL AGENTS AGREED — SIGNAL THRESHOLD MET</span>
              <span style="font-size: 11px; background: rgba(0,0,0,0.6); color: #34d399; padding: 2px 8px; border-radius: 4px; border: 1px solid #10b981;">Score: ${score.toFixed(1)} / ${threshold.toFixed(0)}</span>
            </div>
            <div style="font-size: 12px; color: #f1f5f9; margin-top: 6px; display: flex; gap: 14px; flex-wrap: wrap; align-items: center;">
              <span>Action: <strong style="color: #10b981;">${potentialOrder.action}</strong></span>
              <span>Target: <strong>${potentialOrder.price}</strong></span>
              <span>SL: <strong>${potentialOrder.sl_mult}x ATR</strong></span>
              <span>BE: <strong>+${potentialOrder.be_r}R</strong></span>
              <span>TP: <strong>+${potentialOrder.partial_r}R</strong></span>
            </div>
            <div style="margin-top: 12px; display: flex; justify-content: flex-end; gap: 8px; flex-wrap: wrap;">
              <button id="btn-fire-${sym}-buy" class="btn btn-sm" onclick="fireOrderInMT4('${sym}', 'long', false)" style="background: linear-gradient(135deg, #10b981, #059669); color: #fff; font-weight: 700; border: none; padding: 7px 14px; border-radius: 6px; cursor: pointer; display: flex; align-items: center; gap: 5px; box-shadow: 0 4px 12px rgba(16, 185, 129, 0.35); font-size: 11px;">
                <span>🟢</span> FIRE BUY (LONG)
              </button>
              <button id="btn-fire-${sym}-sell" class="btn btn-sm" onclick="fireOrderInMT4('${sym}', 'short', false)" style="background: linear-gradient(135deg, #ef4444, #dc2626); color: #fff; font-weight: 700; border: none; padding: 7px 14px; border-radius: 6px; cursor: pointer; display: flex; align-items: center; gap: 5px; box-shadow: 0 4px 12px rgba(239, 68, 68, 0.35); font-size: 11px;">
                <span>🔴</span> FIRE SELL (SHORT)
              </button>
            </div>
          </div>
        `;
      } else {
        const agreedCount = (potentialOrder.agent_consensus && potentialOrder.agent_consensus.agreed_count) || 0;
        const totalAgents = (potentialOrder.agent_consensus && potentialOrder.agent_consensus.total_agents) || 5;
        orderBanner = `
          <div style="background: rgba(234, 179, 8, 0.12); border: 1px dashed #eab308; border-radius: 8px; padding: 12px; margin-bottom: 14px;">
            <div style="font-weight: 700; color: #eab308; font-size: 13px; display: flex; justify-content: space-between; align-items: center;">
              <span>💬 AGENTS DEBATING ORDER (${agreedCount}/${totalAgents} Agreed)</span>
              <span style="font-size: 11px; background: rgba(0,0,0,0.5); padding: 2px 8px; border-radius: 4px;">Score: ${score.toFixed(1)} / ${threshold.toFixed(0)}</span>
            </div>
            <div style="font-size: 11px; color: #cbd5e1; margin-top: 4px;">
              ${potentialOrder.alert_text || 'Waiting for unanimous multi-agent consensus before order submission.'}
            </div>
            <div style="margin-top: 8px; display: flex; justify-content: flex-end; gap: 8px; flex-wrap: wrap;">
              <button id="btn-fire-${sym}-buy" class="btn btn-sm" onclick="fireOrderInMT4('${sym}', 'long', true)" style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid #10b981; padding: 5px 12px; border-radius: 6px; cursor: pointer; display: flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600;">
                <span>🟢</span> Force BUY
              </button>
              <button id="btn-fire-${sym}-sell" class="btn btn-sm" onclick="fireOrderInMT4('${sym}', 'short', true)" style="background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid #ef4444; padding: 5px 12px; border-radius: 6px; cursor: pointer; display: flex; align-items: center; gap: 5px; font-size: 11px; font-weight: 600;">
                <span>🔴</span> Force SELL
              </button>
            </div>
          </div>
        `;
      }
    }

    // Multi-Agent Deliberation Grid
    let consensusVotesHtml = '';
    if (item.agent_votes && item.agent_votes.length > 0) {
      consensusVotesHtml = `
        <div style="background: rgba(0, 0, 0, 0.35); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 8px; padding: 10px 12px; margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <span style="font-size: 11px; font-weight: 700; color: #93c5fd; text-transform: uppercase; letter-spacing: 0.5px;">
              👥 Multi-Agent Order Deliberation Committee:
            </span>
            <span style="font-size: 11px; font-weight: 600; color: ${checklist.agent_consensus ? '#10b981' : '#eab308'};">
              ${checklist.agent_consensus ? '✓ All Agents Agreed (5/5)' : '💬 Agents Debating'}
            </span>
          </div>
          <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 6px;">
            ${item.agent_votes.map(v => `
              <div style="background: ${v.agreed ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)'}; border: 1px solid ${v.agreed ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}; border-radius: 6px; padding: 6px 8px;" title="${v.argument}">
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 10px; font-weight: 600;">
                  <span style="color: #e2e8f0;">${v.agent}</span>
                  <span style="color: ${v.agreed ? '#10b981' : '#f87171'};">${v.agreed ? '✓ AGREE' : '⏳ DEBATE'}</span>
                </div>
                <div style="font-size: 9px; color: #94a3b8; margin-top: 3px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                  ${v.perspective}
                </div>
              </div>
            `).join('')}
          </div>
        </div>
      `;
    }

    return `
      <div class="asset-status-card highlight-${meta.iconClass}" style="background: rgba(22, 27, 34, 0.7); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 20px;">
        <div class="asset-card-top" style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 14px;">
          <div class="asset-identity" style="display: flex; align-items: center; gap: 12px;">
            <div class="asset-icon ${meta.iconClass}">${meta.icon}</div>
            <div>
              <h4 style="margin: 0; font-size: 16px; font-weight: 600;">${meta.title}</h4>
              <span class="clickable-strategy-badge" onclick="openStrategyModal('${sym}')" title="Click to inspect strategy math, RL state & educational guide" style="margin-top: 4px;">
                ${item.strategy_name || meta.badge} 🔍
              </span>
            </div>
          </div>
          <div style="text-align: right;">
            <span class="status-tag ${isTriggered ? 'active' : (isImminent ? 'active' : 'controlled')}">
              ${isTriggered ? `SIGNAL: ${side}` : (isImminent ? `IMMINENT: ${side}` : 'WAITING SETUP')}
            </span>
            <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">
              Score: <strong style="color: ${isTriggered ? '#10b981' : (isImminent ? '#3b82f6' : '#eab308')}; font-size: 13px;">${score.toFixed(1)}</strong> / ${threshold.toFixed(0)}
            </div>
          </div>
        </div>

        ${orderBanner}

        <!-- Score Progress Bar -->
        <div style="margin-bottom: 16px;">
          <div style="display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 4px; color: var(--text-muted);">
            <span>Signal Threshold Gauge (${progress}%) — ${isTriggered ? 'MET' : 'PENDING'}</span>
            <span>Target: ≥ ${threshold.toFixed(0)}</span>
          </div>
          <div style="width: 100%; height: 6px; background: rgba(255, 255, 255, 0.08); border-radius: 3px; overflow: hidden;">
            <div style="width: ${progress}%; height: 100%; background: ${isTriggered ? '#10b981' : 'linear-gradient(90deg, #3b82f6, #eab308)'}; transition: width 0.4s ease;"></div>
          </div>
        </div>

        <!-- Indicators Grid -->
        <div class="asset-stats-row" style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; background: rgba(0,0,0,0.25); padding: 12px; border-radius: 8px; margin-bottom: 14px;">
          ${indHtml}
        </div>

        <!-- Multi-Agent Consensus Deliberation -->
        ${consensusVotesHtml}

        <!-- Strategy Reasoning / Trigger Condition -->
        <div style="background: rgba(255, 255, 255, 0.03); border-left: 3px solid ${isTriggered ? '#10b981' : (isImminent ? '#3b82f6' : '#eab308')}; border-radius: 4px; padding: 10px 12px; font-size: 12px; line-height: 1.5; margin-bottom: 12px;">
          <div style="font-weight: 600; color: var(--text-main); margin-bottom: 4px;">
            ${isTriggered ? '⚡ Active Order Trigger Condition' : '🔍 Real-Time Analysis & Execution Trigger:'}
          </div>
          <div style="color: #cbd5e1;">${item.analysis || item.reason}</div>
        </div>

        <!-- Hourly Macro Catalyst Summary Box -->
        <div style="background: rgba(0, 0, 0, 0.25); border: 1px dashed rgba(255, 255, 255, 0.12); border-radius: 6px; padding: 10px 12px; font-size: 11px; margin-bottom: 12px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
            <span style="font-weight: 600; color: var(--accent-gold);">🌐 Hourly Macro Catalyst:</span>
            <span class="status-tag ${item.asset_macro && item.asset_macro.stance === 'BULLISH' ? 'active' : (item.asset_macro && item.asset_macro.stance === 'BEARISH' ? 'negative' : 'controlled')}" style="padding: 1px 6px; font-size: 10px;">
              ${(item.asset_macro && item.asset_macro.stance) || 'NEUTRAL'} (${((item.asset_macro && item.asset_macro.bias) || 0.0) >= 0 ? '+' : ''}${((item.asset_macro && item.asset_macro.bias) || 0.0).toFixed(2)})
            </span>
          </div>
          <div style="color: #94a3b8; font-style: italic; line-height: 1.3;">
            &ldquo;${(item.asset_macro && item.asset_macro.headlines && item.asset_macro.headlines[0]) || 'Monitoring international central bank & commodity prints.'}&rdquo;
          </div>
        </div>

        <!-- Checklist -->
        <div style="display: flex; flex-wrap: wrap; gap: 8px; font-size: 11px;">
          <span class="card-chip" style="padding: 2px 8px; font-size: 10px;">${checklist.session ? '✓ Session Active' : '⏱ Off-Hours'}</span>
          <span class="card-chip" style="padding: 2px 8px; font-size: 10px;">${checklist.adx_trend || checklist.rsi_divergence ? '✓ Filter Confirmed' : '⏳ Waiting Trend Filter'}</span>
          <span class="card-chip" style="padding: 2px 8px; font-size: 10px;">${checklist.setup_trigger ? '✓ Trigger Fired' : '⏳ Setup Pending'}</span>
          <span class="card-chip" style="padding: 2px 8px; font-size: 10px; background: ${checklist.agent_consensus ? 'rgba(16, 185, 129, 0.15)' : 'rgba(234, 179, 8, 0.12)'}; border-color: ${checklist.agent_consensus ? '#10b981' : '#eab308'}; color: ${checklist.agent_consensus ? '#34d399' : '#facc15'};">
            ${checklist.agent_consensus ? '✓ All Agents Agreed' : '💬 Agents Debating'}
          </span>
          <span class="card-chip" style="padding: 2px 8px; font-size: 10px; background: ${isTriggered ? 'rgba(16, 185, 129, 0.15)' : 'rgba(255, 255, 255, 0.05)'}; color: ${isTriggered ? '#34d399' : '#94a3b8'};">
            ${isTriggered ? '✓ Gauge Met — Ready MT4' : '⏳ Score < ' + threshold.toFixed(0)}
          </span>
        </div>
      </div>
    `;
  }).join('');

  container.innerHTML = cardsHtml;
}

// Render Asset-Specific Macro & Hourly News Matrix
function renderAssetMacro(assetMacro) {
  if (!assetMacro || !assetMacro.assets) return;
  const container = document.getElementById('asset-macro-cards-container');
  if (!container) return;

  const nextSec = assetMacro.next_pull_in_seconds !== undefined ? assetMacro.next_pull_in_seconds : 3600;
  const nextMin = Math.floor(nextSec / 60);
  const badge = document.getElementById('next-hourly-pull-badge');
  if (badge) badge.textContent = `Next Hourly Pull: in ~${nextMin}m`;

  const assetMeta = {
    XAUUSD: { title: 'Gold (XAUUSD)', icon: 'AU', iconClass: 'gold' },
    USOIL: { title: 'WTI Crude (USOIL)', icon: 'OIL', iconClass: 'oil' },
    EURUSD: { title: 'Euro FX (EURUSD)', icon: 'EUR', iconClass: 'euro' },
  };

  container.innerHTML = Object.entries(assetMacro.assets).map(([sym, item]) => {
    const meta = assetMeta[sym] || { title: sym, icon: sym.slice(0, 3), iconClass: 'gold' };
    const stance = item.stance || 'NEUTRAL';
    const bias = item.bias !== undefined ? item.bias : 0.0;
    const headlines = item.headlines || [];
    const stanceColor = stance === 'BULLISH' ? '#10b981' : (stance === 'BEARISH' ? '#ef4444' : '#eab308');

    return `
      <div class="asset-status-card highlight-${meta.iconClass}" style="background: rgba(22, 27, 34, 0.7); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 12px; padding: 20px;">
        <div class="asset-card-top" style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 12px;">
          <div class="asset-identity" style="display: flex; align-items: center; gap: 12px;">
            <div class="asset-icon ${meta.iconClass}">${meta.icon}</div>
            <div>
              <h4 style="margin: 0; font-size: 15px; font-weight: 600;">${meta.title}</h4>
              <span class="model-badge">Hourly News &amp; Macro</span>
            </div>
          </div>
          <span class="status-tag" style="background: rgba(${stance === 'BULLISH' ? '16, 185, 129' : (stance === 'BEARISH' ? '239, 68, 68' : '234, 179, 8')}, 0.15); color: ${stanceColor}; border-color: ${stanceColor};">
            ${stance} (${bias >= 0 ? '+' : ''}${bias.toFixed(2)})
          </span>
        </div>

        <div style="background: rgba(0,0,0,0.25); border-radius: 6px; padding: 10px 12px; margin-bottom: 10px; font-size: 12px;">
          <div style="font-weight: 600; color: #f1f5f9; margin-bottom: 3px;">Macro Catalyst Synthesis:</div>
          <div style="color: #cbd5e1; line-height: 1.4;">${item.summary || 'Neutral baseline.'}</div>
        </div>

        <div style="background: rgba(59, 130, 246, 0.08); border-left: 3px solid #3b82f6; border-radius: 4px; padding: 8px 12px; margin-bottom: 14px; font-size: 11px;">
          <div style="font-weight: 600; color: #60a5fa; margin-bottom: 2px;">Quant Strategy Impact:</div>
          <div style="color: #e2e8f0; line-height: 1.3;">${item.quant_impact || 'Standard technical rules apply.'}</div>
        </div>

        <div>
          <div style="font-size: 11px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; margin-bottom: 8px;">
            Latest Hourly Headlines:
          </div>
          <div style="display: flex; flex-direction: column; gap: 6px;">
            ${headlines.map(h => `
              <div style="font-size: 11px; color: #94a3b8; background: rgba(255,255,255,0.02); padding: 6px 8px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.05); line-height: 1.3;">
                &bull; ${h}
              </div>
            `).join('')}
          </div>
        </div>
      </div>
    `;
  }).join('');
}

// Force Refresh Asset Macro News
async function refreshAssetMacro() {
  try {
    const btn = document.querySelector('button[onclick="refreshAssetMacro()"]');
    if (btn) btn.textContent = 'Pulling Fresh News...';
    const res = await fetch('/api/v1/analytics/macro/assets/refresh', { method: 'POST' });
    const data = await res.json();
    alert(data.message || 'Hourly Macro News Refreshed');
    fetchDashboardData();
  } catch (err) {
    alert('Failed refreshing macro news: ' + err);
  } finally {
    const btn = document.querySelector('button[onclick="refreshAssetMacro()"]');
    if (btn) btn.textContent = 'Pull Fresh News Now';
  }
}

// Update Reports & Equity Chart
function updateReportsView(data) {
  if (!data || !data.equity_curve || !equityChartInstance) return;

  const labels = data.equity_curve.map(pt => pt.date.slice(5));
  const points = data.equity_curve.map(pt => pt.equity);

  equityChartInstance.data.labels = labels;
  equityChartInstance.data.datasets[0].data = points;
  equityChartInstance.update();
}

// Update Macro Schedule & Countdown
function updateScheduleView(data) {
  if (!data) return;
  const sec = data.seconds_to_next_catalyst || 0;
  const hrs = Math.floor(sec / 3600);
  const mins = Math.floor((sec % 3600) / 60);
  document.getElementById('countdown-badge').textContent = `Next Event in ~${hrs}h ${mins}m`;
}

// Emergency Stop
function confirmEmergencyStop() {
  if (confirm('CRITICAL WARNING: Are you sure you want to trigger EMERGENCY STOP?\nThis will close all open positions and halt the trading bot immediately!')) {
    fetch('/api/v1/config/emergency_stop', { method: 'POST' })
      .then(r => r.json())
      .then(res => {
        alert('EMERGENCY STOP ACTIVATED: ' + JSON.stringify(res));
        fetchDashboardData();
      })
      .catch(err => alert('Failed to execute emergency stop: ' + err));
  }
}

// Fetch & Render Model Observability Logs
async function fetchObservabilityLogs() {
  try {
    const res = await fetch('/api/v1/analytics/llm/logs?limit=30');
    if (!res.ok) return;
    const data = await res.json();

    // Update Status Cards
    const heliconeBadge = document.getElementById('obs-helicone-badge');
    const heliconeStatus = document.getElementById('obs-helicone-status');
    if (data.helicone_active) {
      heliconeBadge.textContent = 'Active Proxy';
      heliconeBadge.className = 'card-chip positive';
      heliconeStatus.textContent = 'Helicone Live';
    } else {
      heliconeBadge.textContent = 'Direct API';
      heliconeBadge.className = 'card-chip';
      heliconeStatus.textContent = 'Standard Provider';
    }

    const cache = data.cache || {};
    const cacheStatus = document.getElementById('obs-cache-status');
    const cacheExpiry = document.getElementById('obs-cache-expiry');
    if (cache.cached) {
      cacheStatus.textContent = `${cache.cached_regime ? cache.cached_regime.toUpperCase() : 'CACHED'}`;
      cacheStatus.className = 'card-value positive';
      cacheExpiry.textContent = `Expires in ${cache.remaining_hours || 0}h (Zero API cost)`;
    } else {
      cacheStatus.textContent = 'Cache Empty';
      cacheStatus.className = 'card-value';
      cacheExpiry.textContent = 'Next run will query LLM and cache for 24h';
    }

    document.getElementById('obs-total-calls').textContent = data.total_recorded_interactions || 0;

    // Render Table
    const tbody = document.getElementById('llm-logs-tbody');
    const logs = data.recent_interactions || [];
    if (logs.length === 0) {
      tbody.innerHTML = `<tr><td colspan="6" class="text-center" style="padding: 24px; color: var(--text-muted);">No LLM interactions recorded yet. Once scheduled catalysts fire or initial setup runs, transparent model traces will display here.</td></tr>`;
      return;
    }

    tbody.innerHTML = logs.map(log => {
      const timeStr = log.timestamp ? log.timestamp.slice(11, 19) : '--:--:--';
      const bias = log.parsed_json && log.parsed_json.bias !== undefined ? log.parsed_json.bias : '--';
      const regime = log.parsed_json && log.parsed_json.regime_hint ? log.parsed_json.regime_hint : '--';
      const rationale = log.parsed_json && log.parsed_json.rationale ? log.parsed_json.rationale : log.response_text.slice(0, 100);

      const promptSnippet = log.user_prompt ? log.user_prompt.replace(/"/g, '&quot;') : '';
      const responseSnippet = log.response_text ? log.response_text.replace(/"/g, '&quot;') : '';

      return `
        <tr>
          <td><code>${timeStr}</code></td>
          <td><strong>${log.agent_name}</strong></td>
          <td><code>${log.model}</code> (${log.provider})</td>
          <td><span class="badge">${log.latency_ms} ms</span></td>
          <td>
            <span class="status-tag ${bias >= 0 ? 'active' : 'controlled'}">
              Bias: ${bias} | ${regime.toUpperCase()}
            </span>
          </td>
          <td style="max-width: 320px;">
            <details style="cursor: pointer;">
              <summary style="color: var(--accent-gold); font-size: 12px;">Inspect Prompt & Response</summary>
              <div style="margin-top: 8px; font-size: 11px; background: rgba(0,0,0,0.4); padding: 8px; border-radius: 4px; max-height: 200px; overflow-y: auto;">
                <p><strong>System:</strong> ${log.system_prompt}</p>
                <p style="margin-top: 4px;"><strong>Prompt:</strong> ${log.user_prompt}</p>
                <p style="margin-top: 4px;"><strong>Response:</strong> ${log.response_text}</p>
              </div>
            </details>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    console.error('Failed to fetch observability logs:', err);
  }
}

// Clear Macro Cache
async function clearMacroCache() {
  if (confirm('Clear the 24-hour macro consensus cache?\nThis will force the engine to call the LLM model again on the next refresh.')) {
    try {
      const res = await fetch('/api/v1/analytics/llm/cache/clear', { method: 'POST' });
      const data = await res.json();
      alert(data.message || 'Cache cleared.');
      fetchObservabilityLogs();
      fetchDashboardData();
    } catch (err) {
      alert('Failed to clear cache: ' + err);
    }
  }
}

// Render 24-Hour Missed Opportunities Table
function renderMissedOpportunities(data) {
  const tbody = document.getElementById('missed-opportunities-tbody');
  const chip = document.getElementById('chip-missed-count');
  if (!tbody || !data) return;

  const diags = data.diagnostics || [];
  if (chip) {
    chip.textContent = `${data.total_missed_detected || diags.length} Market Swings Diagnosed`;
  }

  if (diags.length === 0) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center" style="padding: 16px; color: var(--text-muted);">No major missed swings detected in the last 24 hours. Strategy execution active.</td></tr>`;
    return;
  }

  tbody.innerHTML = diags.map(d => {
    const isGlobal = d.asset === 'GLOBAL';
    const assetColor = isGlobal ? '#f59e0b' : '#38bdf8';
    return `
      <tr>
        <td><strong style="color: ${assetColor};">${d.instrument || d.asset}</strong></td>
        <td><span class="badge" style="background: rgba(239, 68, 68, 0.15); color: #f87171; border-color: rgba(239, 68, 68, 0.3);">${d.move}</span></td>
        <td><code style="color: #fbbf24; font-size: 11px;">${d.bottleneck_title}</code></td>
        <td style="max-width: 260px; font-size: 11px; color: #cbd5e1; line-height: 1.4;">${d.root_cause}</td>
        <td style="max-width: 280px; font-size: 11px; color: #34d399; line-height: 1.4;">
          <strong>Lesson:</strong> ${d.lesson_learned}<br/>
          <span style="color: #94a3b8; font-size: 10px;">Fix: ${d.remedy}</span>
        </td>
        <td>
          <span class="status-tag active" style="font-size: 10px;">✓ LEARNED</span>
        </td>
      </tr>
    `;
  }).join('');
}

// Strategy Intelligence & Learning Modal Handlers
let currentModalAsset = 'XAUUSD';

async function openStrategyModal(asset) {
  currentModalAsset = asset || 'XAUUSD';
  const modal = document.getElementById('modal-strategy-intel');
  if (!modal) return;

  modal.style.display = 'flex';
  modal.classList.add('open');
  document.body.style.overflow = 'hidden';

  // Set initial loading state
  document.getElementById('modal-title').textContent = `${asset} Strategy Intelligence & Specification`;
  document.getElementById('modal-why-rl-text').textContent = 'Loading live strategy specification from QuantEdge API...';

  try {
    const res = await fetch(`/api/v1/analytics/strategy-details/${asset}`);
    if (!res.ok) throw new Error('API request failed: ' + res.status);
    const data = await res.json();

    // Header & Meta
    document.getElementById('modal-title').textContent = `${data.asset} — ${data.strategy_name || 'Adaptive M15 Strategy'}`;
    document.getElementById('modal-subtitle').textContent = `Archetype: ${data.strategy_archetype || 'Adaptive'} | Status: ${data.status || 'WAITING'} | Price: $${data.live_price}`;
    
    const rlIntel = data.rl_intel || {};
    const rlChip = document.getElementById('modal-rl-chip');
    if (rlChip) {
      rlChip.textContent = `RL Q-Score: ${rlIntel.top_q_value !== undefined ? rlIntel.top_q_value : '--'}`;
    }

    // Tab 1: Why Chosen Now
    const whyEl = document.getElementById('modal-why-rl-text');
    const stateKeyEl = document.getElementById('modal-why-state-key');
    const edu = data.educational_guide || {};
    if (whyEl) {
      whyEl.innerHTML = `<strong>Contextual Selection:</strong> ${edu.why_chosen_now || 'Selected dynamically based on ongoing market volatility and ADX trend strength.'}`;
    }
    if (stateKeyEl) {
      stateKeyEl.innerHTML = `Discretized State Signature: <code>${rlIntel.state_key || '--'}</code>`;
    }

    // Agent consensus votes
    const votesContainer = document.getElementById('modal-agent-votes');
    if (votesContainer) {
      const votes = data.agent_votes || [];
      if (votes.length === 0) {
        votesContainer.innerHTML = `<p style="font-size: 12px; color: var(--text-muted);">Awaiting committee deliberation...</p>`;
      } else {
        votesContainer.innerHTML = votes.map(v => `
          <div style="background: ${v.agreed ? 'rgba(16, 185, 129, 0.08)' : 'rgba(239, 68, 68, 0.08)'}; border: 1px solid ${v.agreed ? 'rgba(16, 185, 129, 0.3)' : 'rgba(239, 68, 68, 0.3)'}; border-radius: 6px; padding: 10px 14px;">
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
              <strong style="font-size: 12px; color: #f1f5f9;">${v.agent} <span style="font-weight: 400; color: #94a3b8; font-size: 11px;">(${v.role})</span></strong>
              <span class="status-tag ${v.agreed ? 'active' : 'controlled'}" style="font-size: 10px;">${v.agreed ? '✓ AGREE' : '⏳ DEBATE'}</span>
            </div>
            <p style="font-size: 12px; color: #cbd5e1; margin: 0; line-height: 1.4;">${v.argument}</p>
          </div>
        `).join('');
      }
    }

    // Tab 2: Mathematical Rules & Formulas
    const math = data.math_rules || {};
    document.getElementById('modal-math-entry').textContent = math.entry_rule || 'Price action confirmation with EMA cross';
    document.getElementById('modal-math-trend').textContent = math.trend_filter || 'ADX >= 20.0';
    document.getElementById('modal-math-sl').textContent = math.stop_loss || `Entry - (${data.sl_mult || 1.5} * ATR)`;
    document.getElementById('modal-math-tp').textContent = math.take_profit || `Partial TP: +${data.partial_r || 2.0}R | Breakeven: +${data.be_r || 1.0}R`;

    // Tab 3: Learn the Strategy (Tutorial)
    document.getElementById('modal-edu-concept').textContent = edu.concept || 'Institutional Trend Continuation';
    document.getElementById('modal-edu-edge').textContent = edu.institutional_edge || 'Asymmetric Risk-to-Reward with volatility-adjusted stops.';
    document.getElementById('modal-edu-pitfalls').textContent = edu.pitfalls_to_avoid || 'Avoid entering right before high-impact economic news.';

    // Tab 4: Candidate Archetypes Evaluated
    const candTbody = document.getElementById('modal-candidates-tbody');
    if (candTbody) {
      const candidates = rlIntel.candidates || [];
      candTbody.innerHTML = candidates.map(c => {
        const isCurrent = c.archetype === data.strategy_archetype;
        return `
          <tr style="${isCurrent ? 'background: rgba(99, 102, 241, 0.15);' : ''}">
            <td><strong>${c.archetype.replace('_', ' ').toUpperCase()}</strong> ${isCurrent ? '⭐ <span style="font-size: 10px; color: #818cf8;">(Active Choice)</span>' : ''}</td>
            <td><code style="color: ${c.q_value >= 0.2 ? '#34d399' : (c.q_value < 0 ? '#f87171' : '#f59e0b')}; font-weight: 700;">${c.q_value > 0 ? '+' : ''}${c.q_value}</code></td>
            <td>${c.samples || 0} episodes</td>
            <td><span class="status-tag ${isCurrent ? 'active' : ''}">${isCurrent ? 'SELECTED' : 'RANKED LOWER'}</span></td>
          </tr>
        `;
      }).join('');
    }

  } catch (err) {
    console.error('Failed to load strategy details:', err);
    document.getElementById('modal-why-rl-text').textContent = 'Error loading strategy details: ' + err.message;
  }
}

function closeStrategyModal() {
  const modal = document.getElementById('modal-strategy-intel');
  if (modal) {
    modal.style.display = 'none';
    modal.classList.remove('open');
    document.body.style.overflow = 'auto';
  }
}

function switchModalTab(tabKey) {
  const tabs = ['why', 'math', 'edu', 'candidates'];
  tabs.forEach(t => {
    const btn = document.getElementById(`btn-tab-${t}`);
    const content = document.getElementById(`modal-tab-${t}`);
    if (btn) {
      if (t === tabKey) btn.classList.add('active');
      else btn.classList.remove('active');
    }
    if (content) {
      if (t === tabKey) content.classList.add('active');
      else content.classList.remove('active');
    }
  });
}

function handleBackdropClick(event) {
  if (event.target && event.target.id === 'modal-strategy-intel') {
    closeStrategyModal();
  }
}

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeStrategyModal();
    closeOrderModal();
  }
});

// -----------------------------------------------------------------------------
// Order Decision Agent MT4 Execution Modal
// -----------------------------------------------------------------------------
window.fireOrderInMT4 = async function(asset, side = null, force = false) {
  // Support legacy signature fireOrderInMT4(asset, forceBool)
  if (typeof side === 'boolean') {
    force = side;
    side = null;
  }

  const btnBuy = document.getElementById(`btn-fire-${asset}-buy`);
  const btnSell = document.getElementById(`btn-fire-${asset}-sell`);
  const btnGeneric = document.getElementById(`btn-fire-${asset}`);

  const activeBtn = side === 'short' ? btnSell : (side === 'long' ? btnBuy : (btnBuy || btnGeneric));
  const originalHtml = activeBtn ? activeBtn.innerHTML : '';

  if (activeBtn) {
    activeBtn.disabled = true;
    activeBtn.innerHTML = `<span>⏳</span> Firing ${side ? side.toUpperCase() : ''}...`;
  }
  if (btnBuy && btnBuy !== activeBtn) btnBuy.disabled = true;
  if (btnSell && btnSell !== activeBtn) btnSell.disabled = true;

  try {
    const res = await fetch('/api/v1/orders/fire', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset, side, force })
    });
    const result = await res.json();
    openOrderModal(asset, result);
    fetchLiveData();
  } catch (err) {
    console.error('Failed to execute order in MT4:', err);
    alert('Order execution error: ' + err.message);
  } finally {
    if (activeBtn) {
      activeBtn.disabled = false;
      activeBtn.innerHTML = originalHtml;
    }
    if (btnBuy) btnBuy.disabled = false;
    if (btnSell) btnSell.disabled = false;
    if (btnGeneric) btnGeneric.disabled = false;
  }
};

function openOrderModal(asset, result) {
  const modal = document.getElementById('modal-order-execution');
  if (!modal) return;

  const decision = result.decision || {};
  const isOk = result.ok === true || result.status === 'executed';
  const banner = document.getElementById('order-modal-status-banner');
  const digits = asset.includes('EUR') ? 4 : 2;

  if (banner) {
    if (isOk) {
      banner.style.background = 'rgba(16, 185, 129, 0.18)';
      banner.style.border = '1px solid #10b981';
      banner.style.color = '#34d399';
      banner.innerHTML = `✓ EXECUTED IN EXNESS MT4 &mdash; TICKET #${result.ticket || 'CONFIRMED'}`;
    } else {
      banner.style.background = 'rgba(239, 68, 68, 0.18)';
      banner.style.border = '1px solid #ef4444';
      banner.style.color = '#f87171';
      banner.innerHTML = `✕ ORDER NOT FIRED &mdash; ${result.reason || 'Risk Gate or Bridge Reject'}`;
    }
  }

  const symEl = document.getElementById('order-m-symbol');
  const sideEl = document.getElementById('order-m-side');
  const volEl = document.getElementById('order-m-volume');
  const pxEl = document.getElementById('order-m-price');
  const slEl = document.getElementById('order-m-sl');
  const tpEl = document.getElementById('order-m-tp');
  const ratEl = document.getElementById('order-m-rationale');
  const bridgeEl = document.getElementById('order-m-bridge-details');

  if (symEl) symEl.textContent = `${asset} (${decision.symbol || asset})`;
  if (sideEl) {
    const side = (decision.side || 'long').toUpperCase();
    sideEl.innerHTML = side === 'LONG' 
      ? '<span class="trend-badge positive">BUY (LONG)</span>' 
      : '<span class="trend-badge negative">SELL (SHORT)</span>';
  }
  if (volEl) volEl.textContent = `${decision.volume || 0.01} lots`;
  if (pxEl) pxEl.textContent = decision.price ? decision.price.toFixed(digits) : '--';
  if (slEl) slEl.textContent = decision.stop_loss ? decision.stop_loss.toFixed(digits) : '--';
  if (tpEl) tpEl.textContent = decision.take_profit ? decision.take_profit.toFixed(digits) : '--';
  if (ratEl) ratEl.textContent = decision.rationale || result.reason || 'Order formulated by QuantEdge Order Decision Agent.';
  
  if (bridgeEl) {
    bridgeEl.textContent = JSON.stringify({
      status: result.status,
      ticket: result.ticket,
      fill_price: result.fill_price,
      bridge_reply: result.bridge,
    }, null, 2);
  }

  modal.style.display = 'flex';
  modal.classList.add('open');
  document.body.style.overflow = 'hidden';
}

function closeOrderModal() {
  const modal = document.getElementById('modal-order-execution');
  if (modal) {
    modal.style.display = 'none';
    modal.classList.remove('open');
    document.body.style.overflow = 'auto';
  }
}

// -----------------------------------------------------------------------------
// Multi-Order Management Controls: Close Specific Ticket & Scale In
// -----------------------------------------------------------------------------
window.closeOrderTicket = async function(ticket) {
  if (!confirm(`Are you sure you want to close position #${ticket} in MT4?`)) return;
  const btn = document.getElementById(`btn-close-${ticket}`);
  if (btn) { btn.disabled = true; btn.textContent = 'Closing...'; }
  try {
    const res = await fetch(`/api/v1/orders/close/${ticket}`, { method: 'POST' });
    const data = await res.json();
    if (data.ok) {
      alert(`Ticket #${ticket} closed successfully in MT4.`);
      fetchLiveData();
    } else {
      alert(`Failed to close #${ticket}: ` + (data.error || 'Unknown error'));
    }
  } catch (e) {
    alert('Close error: ' + e.message);
  } finally {
    if (btn) { btn.disabled = false; btn.textContent = '✕ Close'; }
  }
};

window.scaleInPosition = async function(asset) {
  if (!confirm(`Agent will evaluate and formulate a scale-in order on ${asset}. Confirm?`)) return;
  try {
    const res = await fetch('/api/v1/orders/scale-in', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset })
    });
    const data = await res.json();
    if (data.ok) {
      alert(`Scale-in order placed successfully on ${asset}!`);
      fetchLiveData();
    } else {
      alert(`Scale-in failed: ` + (data.error || data.reason || 'Risk limits prevented scale-in'));
    }
  } catch (e) {
    alert('Scale-in error: ' + e.message);
  }
};

/* ==========================================================================
   INSTITUTIONAL LIVE MT4 CHART & POSITION ENGINE
   ========================================================================== */
const InstitutionalChart = {
  currentAsset: 'BTCUSD',
  currentTimeframe: 'M15',
  chart: null,
  candleSeries: null,
  ema9Series: null,
  ema21Series: null,
  ema50Series: null,
  donUpperSeries: null,
  donLowerSeries: null,
  donPocSeries: null,
  entryLine: null,
  slLine: null,
  tpLine: null,
  lastPrice: null,
  activePositionData: null,
  isEmaVisible: true,
  isDonchianVisible: true,
  isPositionLinesVisible: true,
  initialized: false,
  isPolling: false,
  userHasManuallySelected: false,

  init() {
    if (this.initialized) return;
    const container = document.getElementById('liveChartContainer');
    if (!container || typeof LightweightCharts === 'undefined') return;

    try {
      const chartWidth = container.clientWidth || 800;
      const chartHeight = container.clientHeight || 480;

      this.chart = LightweightCharts.createChart(container, {
        width: chartWidth,
        height: chartHeight,
        layout: {
          background: { type: 'solid', color: '#090d14' },
          textColor: '#94a3b8',
          fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, sans-serif",
          fontSize: 11,
        },
        grid: {
          vertLines: { color: 'rgba(255, 255, 255, 0.03)' },
          horzLines: { color: 'rgba(255, 255, 255, 0.03)' },
        },
        crosshair: {
          mode: LightweightCharts.CrosshairMode.Normal,
          vertLine: {
            color: 'rgba(99, 102, 241, 0.5)',
            width: 1,
            style: LightweightCharts.LineStyle.Dashed,
            labelBackgroundColor: '#4f46e5',
          },
          horzLine: {
            color: 'rgba(99, 102, 241, 0.5)',
            width: 1,
            style: LightweightCharts.LineStyle.Dashed,
            labelBackgroundColor: '#4f46e5',
          },
        },
        rightPriceScale: {
          borderColor: 'rgba(255, 255, 255, 0.08)',
          scaleMargins: { top: 0.12, bottom: 0.12 },
          autoScale: true,
        },
        timeScale: {
          borderColor: 'rgba(255, 255, 255, 0.08)',
          timeVisible: true,
          secondsVisible: false,
          barSpacing: 10,
          minBarSpacing: 3,
          rightOffset: 12,
        },
      });

      // Helper to add series supporting both v4 (addCandlestickSeries) and v5 (addSeries)
      const addCandles = (opts) => {
        if (typeof this.chart.addCandlestickSeries === 'function') {
          return this.chart.addCandlestickSeries(opts);
        } else if (typeof this.chart.addSeries === 'function' && typeof LightweightCharts.CandlestickSeries !== 'undefined') {
          return this.chart.addSeries(LightweightCharts.CandlestickSeries, opts);
        }
        return null;
      };

      const addLine = (opts) => {
        if (typeof this.chart.addLineSeries === 'function') {
          return this.chart.addLineSeries(opts);
        } else if (typeof this.chart.addSeries === 'function' && typeof LightweightCharts.LineSeries !== 'undefined') {
          return this.chart.addSeries(LightweightCharts.LineSeries, opts);
        }
        return null;
      };

      // 1. Candlestick Series (Bullish Emerald Green, Bearish Crimson Red)
      this.candleSeries = addCandles({
        upColor: '#10b981',
        downColor: '#ef4444',
        borderUpColor: '#10b981',
        borderDownColor: '#ef4444',
        wickUpColor: '#10b981',
        wickDownColor: '#ef4444',
      });

      // 2. EMA 9 Series (Cyan / Fast)
      this.ema9Series = addLine({
        color: '#00d2ff',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });

      // 3. EMA 21 Series (Amber / Medium)
      this.ema21Series = addLine({
        color: '#f59e0b',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });

      // 4. EMA 50 Series (Purple / Slow Baseline)
      this.ema50Series = addLine({
        color: '#a855f7',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });

      // 5. Donchian / Value Area Channels
      this.donUpperSeries = addLine({
        color: 'rgba(56, 189, 248, 0.45)',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle ? LightweightCharts.LineStyle.Dashed : 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      this.donLowerSeries = addLine({
        color: 'rgba(56, 189, 248, 0.45)',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle ? LightweightCharts.LineStyle.Dashed : 2,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      this.donPocSeries = addLine({
        color: '#ec4899',
        lineWidth: 1,
        lineStyle: LightweightCharts.LineStyle ? LightweightCharts.LineStyle.Dotted : 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });

      // Handle Resize smoothly
      window.addEventListener('resize', () => {
        if (this.chart && container && container.clientWidth > 0) {
          this.chart.resize(container.clientWidth, container.clientHeight || 520);
        }
      });

      this.initialized = true;
      this.fetchChartData();

      // Poll every 3 seconds for live streaming ticks
      if (!this.isPolling) {
        setInterval(() => {
          if (currentTab === 'positions') {
            this.fetchChartData(true);
          }
        }, 3000);
        this.isPolling = true;
      }
    } catch (e) {
      console.error('Failed to initialize LightweightCharts:', e);
    }
  },

  selectAsset(asset) {
    if (!asset) return;
    let clean = asset.toUpperCase();
    if (clean.endsWith('M')) clean = clean.slice(0, -1);
    this.currentAsset = clean;
    this.userHasManuallySelected = true;

    document.querySelectorAll('#chart-asset-selector .asset-pill').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.asset === this.currentAsset);
    });

    this.fetchChartData();
  },

  selectTimeframe(tf) {
    if (!tf) return;
    this.currentTimeframe = tf.toUpperCase();

    document.querySelectorAll('#chart-tf-selector .tf-pill').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tf === this.currentTimeframe);
    });

    this.fetchChartData();
  },

  toggleEMA(visible) {
    this.isEmaVisible = visible;
    if (this.ema9Series) this.ema9Series.applyOptions({ visible });
    if (this.ema21Series) this.ema21Series.applyOptions({ visible });
    if (this.ema50Series) this.ema50Series.applyOptions({ visible });
  },

  toggleDonchian(visible) {
    this.isDonchianVisible = visible;
    if (this.donUpperSeries) this.donUpperSeries.applyOptions({ visible });
    if (this.donLowerSeries) this.donLowerSeries.applyOptions({ visible });
    if (this.donPocSeries) this.donPocSeries.applyOptions({ visible });
  },

  togglePositionLines(visible) {
    this.isPositionLinesVisible = visible;
    this.renderPositionLines();
  },

  fitContent() {
    if (this.chart) {
      this.chart.timeScale().fitContent();
    }
  },

  focusOnPosition() {
    this.fitContent();
  },

  async fetchChartData(silent = false) {
    if (!this.initialized) this.init();
    if (!this.chart) return;

    const overlay = document.getElementById('chart-loading-overlay');
    if (!silent && overlay) overlay.style.display = 'flex';

    try {
      const url = `/api/v1/analytics/chart/${this.currentAsset}?timeframe=${this.currentTimeframe}&limit=220`;
      const res = await fetch(url);
      if (!res.ok) return;
      const data = await res.json();

      // 1. Update Candlestick Data
      if (data.candles && data.candles.length > 0 && this.candleSeries) {
        this.candleSeries.setData(data.candles);
      }

      // 2. Update Technical Indicators
      if (data.indicators) {
        if (data.indicators.ema9 && this.ema9Series) this.ema9Series.setData(data.indicators.ema9);
        if (data.indicators.ema21 && this.ema21Series) this.ema21Series.setData(data.indicators.ema21);
        if (data.indicators.ema50 && this.ema50Series) this.ema50Series.setData(data.indicators.ema50);
        if (data.indicators.donchian_high && this.donUpperSeries) this.donUpperSeries.setData(data.indicators.donchian_high);
        if (data.indicators.donchian_low && this.donLowerSeries) this.donLowerSeries.setData(data.indicators.donchian_low);
        if (data.indicators.donchian_poc && this.donPocSeries) this.donPocSeries.setData(data.indicators.donchian_poc);
      }

      // 3. Update Watermark
      const wm = document.getElementById('chart-watermark');
      if (wm) wm.textContent = `${data.asset} · ${data.timeframe}`;

      // 4. Update HUD
      this.updateHud(data);

      // 5. Update Position Lines & Banner
      this.activePositionData = data.active_position;
      this.renderPositionLines();

      if (!silent) {
        this.chart.timeScale().scrollToRealTime();
      }
    } catch (e) {
      console.error('Error fetching chart data:', e);
    } finally {
      if (overlay) overlay.style.display = 'none';
    }
  },

  updateHud(data) {
    const elAsset = document.getElementById('hud-asset-name');
    const elTf = document.getElementById('hud-tf-badge');
    const elPrice = document.getElementById('hud-live-price');
    const elQuote = document.getElementById('hud-bid-ask');
    const elEma9 = document.getElementById('hud-val-ema9');
    const elEma21 = document.getElementById('hud-val-ema21');
    const elEma50 = document.getElementById('hud-val-ema50');
    const elPoc = document.getElementById('hud-val-poc');
    const elAtr = document.getElementById('hud-val-atr');
    const elRsi = document.getElementById('hud-val-rsi');

    if (elAsset) elAsset.textContent = data.asset;
    if (elTf) elTf.textContent = this.currentTimeframe;

    const dec = data.decimals || (data.asset === 'EURUSD' ? 5 : 2);
    if (elPrice && data.live_price !== undefined) {
      const newPx = Number(data.live_price);
      if (this.lastPrice !== null) {
        elPrice.classList.remove('tick-up', 'tick-down');
        if (newPx > this.lastPrice) elPrice.classList.add('tick-up');
        else if (newPx < this.lastPrice) elPrice.classList.add('tick-down');
      }
      this.lastPrice = newPx;
      elPrice.textContent = newPx.toFixed(dec);
    }

    if (elQuote && data.bid !== undefined && data.ask !== undefined) {
      const bid = Number(data.bid).toFixed(dec);
      const ask = Number(data.ask).toFixed(dec);
      const spread = Number(data.spread).toFixed(dec);
      elQuote.textContent = `Bid: ${bid} | Ask: ${ask} | Spread: ${spread}`;
    }

    const ind = data.indicators_summary || {};
    if (elEma9 && ind.ema9 !== undefined) elEma9.textContent = Number(ind.ema9).toFixed(dec);
    if (elEma21 && ind.ema21 !== undefined) elEma21.textContent = Number(ind.ema21).toFixed(dec);
    if (elEma50 && ind.ema50 !== undefined) elEma50.textContent = Number(ind.ema50).toFixed(dec);
    if (elPoc && ind.donchian_poc !== undefined) elPoc.textContent = Number(ind.donchian_poc).toFixed(dec);
    if (elAtr && ind.atr !== undefined) elAtr.textContent = Number(ind.atr).toFixed(dec);
    if (elRsi && ind.rsi !== undefined) elRsi.textContent = Number(ind.rsi).toFixed(1);
  },

  renderPositionLines() {
    // Clear old lines
    if (this.entryLine && this.candleSeries) {
      try { this.candleSeries.removePriceLine(this.entryLine); } catch (_) {}
      this.entryLine = null;
    }
    if (this.slLine && this.candleSeries) {
      try { this.candleSeries.removePriceLine(this.slLine); } catch (_) {}
      this.slLine = null;
    }
    if (this.tpLine && this.candleSeries) {
      try { this.candleSeries.removePriceLine(this.tpLine); } catch (_) {}
      this.tpLine = null;
    }

    const banner = document.getElementById('chart-position-banner');
    const pos = this.activePositionData;

    // Check if open position exists for this asset
    if (!pos || !pos.has_position) {
      if (banner) banner.style.display = 'none';
      return;
    }

    const entryPx = Number(pos.entry_price);
    const slPx = pos.stop_loss ? Number(pos.stop_loss) : (pos.algo_stop_loss ? Number(pos.algo_stop_loss) : null);
    const tpPx = pos.take_profit ? Number(pos.take_profit) : (pos.algo_take_profit ? Number(pos.algo_take_profit) : null);

    // Populate Position Banner
    if (banner) {
      banner.style.display = 'flex';
      const bSide = document.getElementById('cp-side-badge');
      const bTicket = document.getElementById('cp-ticket');
      const bVol = document.getElementById('cp-volume');
      const bEntry = document.getElementById('cp-entry');
      const bSl = document.getElementById('cp-sl');
      const bTp = document.getElementById('cp-tp');
      const bPnl = document.getElementById('cp-pnl');
      const bR = document.getElementById('cp-r');

      if (bSide) {
        bSide.textContent = pos.side;
        bSide.className = `badge-order-side ${pos.side.toLowerCase()}`;
      }
      if (bTicket) bTicket.textContent = `#${pos.ticket}`;
      if (bVol) bVol.textContent = `${pos.volume} Lots`;
      if (bEntry) bEntry.textContent = pos.entry_price;

      if (bSl) {
        if (pos.stop_loss) {
          bSl.textContent = pos.stop_loss;
        } else if (pos.algo_stop_loss) {
          bSl.innerHTML = `${pos.algo_stop_loss} <span class="badge-algo-stop">ALGO</span>`;
        } else {
          bSl.textContent = 'Dynamic Trailing';
        }
      }

      if (bTp) {
        if (pos.take_profit) {
          bTp.textContent = pos.take_profit;
        } else if (pos.algo_take_profit) {
          bTp.innerHTML = `${pos.algo_take_profit} <span class="badge-algo-stop">TARGET</span>`;
        } else {
          bTp.textContent = 'Trend Runner';
        }
      }

      if (bPnl) {
        const pnl = Number(pos.unrealized_pnl || 0);
        bPnl.textContent = (pnl >= 0 ? '+$' : '-$') + Math.abs(pnl).toFixed(2);
        bPnl.className = `banner-pnl ${pnl >= 0 ? '' : 'negative'}`;
      }
      if (bR) {
        const r = Number(pos.r_multiple || 0);
        bR.textContent = (r >= 0 ? '+' : '') + r.toFixed(2) + 'R';
      }
    }

    // Draw Price Lines if enabled
    if (!this.isPositionLinesVisible || !this.candleSeries) return;

    // 1. Entry Line (Emerald Green)
    if (entryPx && entryPx > 0) {
      this.entryLine = this.candleSeries.createPriceLine({
        price: entryPx,
        color: '#10b981',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Dashed,
        axisLabelVisible: true,
        title: `ENTRY (${pos.side} ${pos.volume}L #${pos.ticket})`,
      });
    }

    // 2. Stop Loss Line (Crimson Red) - Validate reasonable price range
    if (slPx && slPx > 0 && Math.abs(slPx - entryPx) < entryPx * 0.4) {
      const isAlgo = !pos.stop_loss;
      this.slLine = this.candleSeries.createPriceLine({
        price: slPx,
        color: '#ef4444',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Dotted,
        axisLabelVisible: true,
        title: isAlgo ? `ALGO SL (~${slPx})` : `STOP LOSS (${slPx})`,
      });
    }

    // 3. Take Profit Line (Sky Blue) - Validate reasonable price range
    if (tpPx && tpPx > 0 && Math.abs(tpPx - entryPx) < entryPx * 0.5) {
      const isAlgo = !pos.take_profit;
      this.tpLine = this.candleSeries.createPriceLine({
        price: tpPx,
        color: '#38bdf8',
        lineWidth: 2,
        lineStyle: LightweightCharts.LineStyle.Dotted,
        axisLabelVisible: true,
        title: isAlgo ? `ALGO TP (~${tpPx})` : `TAKE PROFIT (${tpPx})`,
      });
    }
  },

  syncOpenPositionDots(openPositions) {
    const symbolsWithPos = new Set();
    if (Array.isArray(openPositions)) {
      openPositions.forEach(p => {
        let sym = p.symbol || '';
        if (sym.endsWith('m') || sym.endsWith('M')) sym = sym.slice(0, -1);
        symbolsWithPos.add(sym.toUpperCase());
      });
    }

    ['BTCUSD', 'XAUUSD', 'EURUSD', 'USOIL'].forEach(sym => {
      const dot = document.getElementById(`pos-dot-${sym}`);
      if (dot) {
        dot.style.display = symbolsWithPos.has(sym) ? 'inline-block' : 'none';
      }
    });

    // If current selected asset has no position but another asset does, auto-focus on initial load
    if (!this.userHasManuallySelected && symbolsWithPos.size > 0 && !symbolsWithPos.has(this.currentAsset)) {
      const firstActive = Array.from(symbolsWithPos)[0];
      this.selectAsset(firstActive);
    }
  }
};

window.InstitutionalChart = InstitutionalChart;


