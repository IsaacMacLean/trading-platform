/**
 * Dashboard WebSocket client and chart updater.
 * Supplemental JS — core logic is embedded in index.html.
 * This file provides additional utilities and can be imported if needed.
 */

'use strict';

const TradingDashboard = (function() {

  // ---- State ----
  let _state = {};
  let _ws = null;
  let _chart = null;
  let _reconnectTimer = null;
  const WS_RECONNECT_MS = 5000;
  const POLL_INTERVAL_MS = 10000;

  // ---- Formatters ----
  function fmtDollar(n) {
    return '$' + Number(n || 0).toLocaleString('en-US', {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2
    });
  }

  function fmtPct(n) {
    const v = Number(n || 0);
    return (v >= 0 ? '+' : '') + v.toFixed(2) + '%';
  }

  function colorClass(n) {
    return n >= 0 ? 'profit' : 'loss';
  }

  // ---- WebSocket ----
  function connect(host) {
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const url = proto + '//' + (host || location.host) + '/ws';

    _ws = new WebSocket(url);

    _ws.onopen = function() {
      console.info('[WS] Connected');
      setConnected(true);
      if (_reconnectTimer) {
        clearTimeout(_reconnectTimer);
        _reconnectTimer = null;
      }
    };

    _ws.onmessage = function(evt) {
      try {
        const msg = JSON.parse(evt.data);
        if (msg.type === 'state_update' && msg.data) {
          handleState(msg.data);
        }
      } catch (e) {
        console.error('[WS] Parse error:', e);
      }
    };

    _ws.onerror = function(e) {
      console.error('[WS] Error:', e);
    };

    _ws.onclose = function() {
      console.warn('[WS] Disconnected — reconnecting in', WS_RECONNECT_MS, 'ms');
      setConnected(false);
      _reconnectTimer = setTimeout(() => connect(host), WS_RECONNECT_MS);
    };
  }

  function setConnected(connected) {
    const dot = document.getElementById('ws-dot');
    if (dot) {
      dot.classList.toggle('connected', connected);
    }
  }

  // ---- HTTP fallback ----
  async function poll() {
    try {
      const endpoints = [
        '/api/account', '/api/positions', '/api/equity-curve',
        '/api/scanner-feed', '/api/trade-log', '/api/risk'
      ];
      const responses = await Promise.all(
        endpoints.map(url => fetch(url).then(r => r.json()).catch(() => null))
      );
      const [account, positions, equity_curve, scanner_feed, trade_log, risk] = responses;
      handleState({ account, positions, equity_curve, scanner_feed, trade_log, risk });
    } catch (e) {
      console.warn('[Poll] Error:', e);
    }
  }

  // ---- State handler ----
  function handleState(state) {
    _state = state;
    if (typeof renderState === 'function') {
      renderState(state);  // delegate to inline code in index.html
    }
  }

  // ---- Chart helpers ----
  function getChartGradient(ctx, chartArea) {
    const gradient = ctx.createLinearGradient(0, chartArea.top, 0, chartArea.bottom);
    gradient.addColorStop(0, 'rgba(0,170,255,0.3)');
    gradient.addColorStop(1, 'rgba(0,170,255,0.0)');
    return gradient;
  }

  // ---- Notification helpers ----
  function showAlert(message, type) {
    // type: 'profit' | 'loss' | 'warn' | 'info'
    console.log(`[ALERT ${type.toUpperCase()}] ${message}`);
    // In a real system, push a toast notification
  }

  // ---- Public API ----
  return {
    connect,
    poll,
    fmtDollar,
    fmtPct,
    colorClass,
    showAlert,
    getState: () => _state,
    startPolling: function() {
      setInterval(() => {
        if (!_ws || _ws.readyState !== WebSocket.OPEN) {
          poll();
        }
      }, POLL_INTERVAL_MS);
    }
  };

})();

// Auto-init if not in index.html context (standalone import)
if (typeof window !== 'undefined' && !window.__tradingDashboardInline) {
  TradingDashboard.connect();
  TradingDashboard.startPolling();
}
