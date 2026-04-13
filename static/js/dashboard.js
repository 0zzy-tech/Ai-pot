/**
 * Main dashboard logic.
 *  - WebSocket connection with exponential-backoff reconnect
 *  - Stats polling (every 30s fallback)
 *  - Request feed table management
 *  - Coordinates map + chart updates on new events
 */

(function () {
  'use strict';

  const ADMIN_PREFIX = window.ADMIN_PREFIX || '/__admin';
  const MAX_FEED_ROWS = 200;

  // ── State ───────────────────────────────────────────────────────────────────
  let stats = { total: 0, unique_ips: 0, by_risk: {}, by_category: {}, last_24h: 0 };
  let ws = null;
  let wsReconnectDelay = 1000;
  let feedRowCount = 0;

  // ── Helpers ─────────────────────────────────────────────────────────────────
  function esc(str) {
    return String(str || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function fmtTime(iso) {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString('en-GB', { hour12: false });
    } catch { return iso.slice(11, 19); }
  }

  function riskBadge(risk) {
    return `<span class="badge badge-${esc(risk)}">${esc(risk)}</span>`;
  }

  function catChip(cat) {
    return `<span class="cat">${esc(cat)}</span>`;
  }

  // ── Stats bar ────────────────────────────────────────────────────────────────
  function renderStats() {
    document.getElementById('stat-total').textContent    = (stats.total || 0).toLocaleString();
    document.getElementById('stat-critical').textContent = (stats.by_risk?.CRITICAL || 0).toLocaleString();
    document.getElementById('stat-high').textContent     = (stats.by_risk?.HIGH     || 0).toLocaleString();
    document.getElementById('stat-medium').textContent   = (stats.by_risk?.MEDIUM   || 0).toLocaleString();
    document.getElementById('stat-low').textContent      = (stats.by_risk?.LOW      || 0).toLocaleString();
    document.getElementById('stat-ips').textContent      = (stats.unique_ips || 0).toLocaleString();
    document.getElementById('stat-24h').textContent      = (stats.last_24h   || 0).toLocaleString();
  }

  function incrementStat(riskLevel) {
    stats.total = (stats.total || 0) + 1;
    stats.last_24h = (stats.last_24h || 0) + 1;
    stats.by_risk = stats.by_risk || {};
    stats.by_risk[riskLevel] = (stats.by_risk[riskLevel] || 0) + 1;
    renderStats();
  }

  // ── Feed table ───────────────────────────────────────────────────────────────
  function addFeedRow(d) {
    const tbody = document.getElementById('feed-tbody');
    if (!tbody) return;

    const tr = document.createElement('tr');
    tr.className = 'new-row';
    tr.innerHTML = `
      <td>${fmtTime(d.timestamp)}</td>
      <td title="${esc(d.ip)}">${esc(d.ip)}</td>
      <td title="${esc(d.path)}">${esc(d.path)}</td>
      <td>${riskBadge(d.risk_level)}</td>
      <td>${catChip(d.category)}</td>
      <td title="${esc(d.city || '')} ${esc(d.country || '')}">${esc(d.country || '—')}</td>
    `;
    tbody.insertBefore(tr, tbody.firstChild);
    feedRowCount++;

    // Trim old rows
    while (feedRowCount > MAX_FEED_ROWS) {
      tbody.removeChild(tbody.lastChild);
      feedRowCount--;
    }
  }

  function loadInitialFeed() {
    fetch(`${ADMIN_PREFIX}/api/requests?limit=50`)
      .then(r => r.json())
      .then(rows => {
        // Rows come newest-first; render them
        rows.forEach(addFeedRow);
      })
      .catch(console.warn);
  }

  // ── Full stats refresh ────────────────────────────────────────────────────────
  function refreshStats() {
    fetch(`${ADMIN_PREFIX}/api/stats`)
      .then(r => r.json())
      .then(data => {
        stats = data;
        renderStats();
        HoneypotCharts.updateRisk(data.by_risk || {});
        HoneypotCharts.updateCategory(data.by_category || {});
        HoneypotCharts.updateTimeline(data.hourly_trend || []);
      })
      .catch(console.warn);
  }

  function loadMapData() {
    fetch(`${ADMIN_PREFIX}/api/map-data`)
      .then(r => r.json())
      .then(rows => HoneypotMap.loadInitial(rows))
      .catch(console.warn);
  }

  // ── WebSocket ─────────────────────────────────────────────────────────────────
  function connectWS() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    ws = new WebSocket(`${proto}://${location.host}/ws`);

    ws.onopen = () => {
      wsReconnectDelay = 1000;
      setLiveStatus(true);
    };

    ws.onmessage = (event) => {
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }

      if (msg.type === 'new_request') {
        const d = msg.data;
        addFeedRow(d);
        incrementStat(d.risk_level);
        HoneypotCharts.incrementRisk(d.risk_level);
        HoneypotCharts.incrementCategory(d.category);
        HoneypotMap.addOrUpdatePin(d);

        // Bump unique IPs (rough heuristic — accurate count from stats)
        updateFooterTime();
      }
    };

    ws.onclose = () => {
      setLiveStatus(false);
      setTimeout(connectWS, wsReconnectDelay);
      wsReconnectDelay = Math.min(wsReconnectDelay * 2, 30000);
    };

    ws.onerror = () => {
      ws.close();
    };
  }

  function setLiveStatus(online) {
    const dot   = document.getElementById('live-dot');
    const label = document.getElementById('live-label');
    if (dot)   dot.className   = 'live-dot' + (online ? '' : ' offline');
    if (label) label.textContent = online ? 'LIVE' : 'RECONNECTING…';
  }

  function updateFooterTime() {
    const el = document.getElementById('footer-time');
    if (el) el.textContent = new Date().toLocaleTimeString('en-GB', { hour12: false });
  }

  // ── Init ──────────────────────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', () => {
    // Charts
    HoneypotCharts.initRiskChart('risk-chart');
    HoneypotCharts.initCategoryChart('category-chart');
    HoneypotCharts.initTimelineChart('timeline-chart');

    // Map
    HoneypotMap.init('map');

    // Initial data load
    refreshStats();
    loadInitialFeed();
    loadMapData();

    // Periodic full refresh (fallback if WS misses something)
    setInterval(refreshStats, 30000);

    // WebSocket
    connectWS();

    updateFooterTime();
    setInterval(updateFooterTime, 1000);
  });
})();
