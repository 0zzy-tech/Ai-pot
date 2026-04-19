/**
 * Main dashboard logic.
 *  - WebSocket connection with exponential-backoff reconnect
 *  - Stats polling (every 30s fallback)
 *  - Request feed table management
 *  - Service enable/disable panel
 *  - Coordinates map + chart updates on new events
 */

(function () {
  'use strict';

  const ADMIN_PREFIX  = window.ADMIN_PREFIX || '/__admin';
  const WS_TOKEN      = window.WS_TOKEN     || '';
  const MAX_FEED_ROWS = 200;

  // ── State ───────────────────────────────────────────────────────────────────
  let stats = { total: 0, unique_ips: 0, by_risk: {}, by_category: {}, last_24h: 0 };
  let ws    = null;
  let wsReconnectDelay  = 1000;
  let feedRowCount      = 0;
  let searchQuery       = '';
  let searchDebounce    = null;
  let _currentDrawerIp  = null;
  let _currentModalData = null;

  // ── Helpers ─────────────────────────────────────────────────────────────────
  function esc(str) {
    return String(str || '')
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function fmtTime(iso) {
    if (!iso) return '';
    try { return new Date(iso).toLocaleTimeString('en-GB', { hour12: false }); }
    catch { return String(iso).slice(11, 19); }
  }

  function riskBadge(risk) {
    return `<span class="badge badge-${esc(risk)}">${esc(risk)}</span>`;
  }

  function catChip(cat) {
    return `<span class="cat">${esc(cat)}</span>`;
  }

  // ── Stats bar ────────────────────────────────────────────────────────────────
  function renderStats() {
    document.getElementById('stat-total').textContent    = (stats.total       || 0).toLocaleString();
    document.getElementById('stat-critical').textContent = (stats.by_risk?.CRITICAL || 0).toLocaleString();
    document.getElementById('stat-high').textContent     = (stats.by_risk?.HIGH     || 0).toLocaleString();
    document.getElementById('stat-medium').textContent   = (stats.by_risk?.MEDIUM   || 0).toLocaleString();
    document.getElementById('stat-low').textContent      = (stats.by_risk?.LOW      || 0).toLocaleString();
    document.getElementById('stat-ips').textContent      = (stats.unique_ips  || 0).toLocaleString();
    document.getElementById('stat-24h').textContent      = (stats.last_24h    || 0).toLocaleString();
  }

  function incrementStat(riskLevel) {
    stats.total   = (stats.total   || 0) + 1;
    stats.last_24h = (stats.last_24h || 0) + 1;
    stats.by_risk  = stats.by_risk || {};
    stats.by_risk[riskLevel] = (stats.by_risk[riskLevel] || 0) + 1;
    renderStats();
  }

  // ── Feed table ────────────────────────────────────────────────────────────────
  function _feedRowHtml(d) {
    const abuseIndicator = d.abuse_score >= 50
      ? ` <span title="AbuseIPDB score: ${d.abuse_score}" style="color:var(--risk-critical)">&#9679;</span>` : '';
    const torBadge = d.is_tor
      ? ` <span title="Tor exit node" style="font-size:10px;color:var(--risk-high)">TOR</span>` : '';
    const noteIndicator = d.note
      ? ` <span title="${esc(d.note)}" style="font-size:10px;cursor:pointer">📝</span>` : '';
    return `
      <td>${fmtTime(d.timestamp)}</td>
      <td class="ip-cell" title="${esc(d.ip)}" data-ip="${esc(d.ip)}">${esc(d.ip)}${abuseIndicator}${torBadge}${noteIndicator}</td>
      <td title="${esc(d.path)}">${esc(d.path)}</td>
      <td>${riskBadge(d.risk_level)}</td>
      <td>${catChip(d.category)}</td>
      <td title="${esc(d.city||'')} ${esc(d.country||'')}">${esc(d.country || '—')}</td>
    `;
  }

  function addFeedRow(d) {
    // While a search is active, don't inject live rows (they'd be off-filter)
    if (searchQuery) return;
    const tbody = document.getElementById('feed-tbody');
    if (!tbody) return;
    const tr = document.createElement('tr');
    tr.className = 'new-row feed-row';
    tr.dataset.id = d.id;
    tr.innerHTML = _feedRowHtml(d);
    tbody.insertBefore(tr, tbody.firstChild);
    feedRowCount++;
    while (feedRowCount > MAX_FEED_ROWS) {
      tbody.removeChild(tbody.lastChild);
      feedRowCount--;
    }
  }

  function loadFeed(q) {
    const qs = q ? `&q=${encodeURIComponent(q)}` : '';
    fetch(`${ADMIN_PREFIX}/api/requests?limit=50${qs}`)
      .then(r => r.json())
      .then(rows => {
        const tbody = document.getElementById('feed-tbody');
        if (!tbody) return;
        tbody.innerHTML = '';
        feedRowCount = 0;
        // loadFeed bypasses the searchQuery guard — render directly
        rows.forEach(d => {
          const tr = document.createElement('tr');
          tr.className = 'feed-row';
          tr.dataset.id = d.id;
          tr.innerHTML = _feedRowHtml(d);
          tbody.appendChild(tr);
          feedRowCount++;
        });
      })
      .catch(console.warn);
  }

  function loadInitialFeed() {
    loadFeed('');
  }

  // ── Full stats refresh ──────────────────────────────────────────────────────
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
      .then(r => r.json()).then(rows => HoneypotMap.loadInitial(rows))
      .catch(console.warn);
  }

  function loadIntelCharts() {
    fetch(`${ADMIN_PREFIX}/api/stats/weekly`)
      .then(r => r.json())
      .then(rows => HoneypotCharts.updateWeeklyChart(rows))
      .catch(console.warn);
    fetch(`${ADMIN_PREFIX}/api/stats/heatmap`)
      .then(r => r.json())
      .then(rows => HoneypotCharts.updateHeatmapChart(rows))
      .catch(console.warn);
  }

  // ── Services panel ──────────────────────────────────────────────────────────
  function renderServicesGrid(services) {
    const grid = document.getElementById('services-grid');
    if (!grid) return;
    grid.innerHTML = '';
    services.forEach(svc => {
      const card = document.createElement('div');
      card.className = 'service-card' + (svc.enabled ? '' : ' disabled');
      card.dataset.serviceId = svc.id;
      card.innerHTML = `
        <div class="service-icon">${esc(svc.icon)}</div>
        <div class="service-info">
          <div class="service-name">${esc(svc.label)}<span class="service-port">:${esc(String(svc.port))}</span></div>
          <div class="service-desc">${esc(svc.description)}</div>
        </div>
        <div class="toggle-wrap">
          <label class="toggle" title="${svc.enabled ? 'Disable' : 'Enable'} ${esc(svc.label)}">
            <input type="checkbox" id="svc-toggle-${esc(svc.id)}"
                   ${svc.enabled ? 'checked' : ''}
                   data-service-id="${esc(svc.id)}">
            <span class="toggle-slider"></span>
          </label>
          <span class="toggle-label" id="svc-label-${esc(svc.id)}">
            ${svc.enabled ? 'ON' : 'OFF'}
          </span>
          <label class="toggle tarpit-toggle" title="Tarpit ${esc(svc.label)} (delay responses ${esc(String(30))}s)">
            <input type="checkbox" id="svc-tarpit-${esc(svc.id)}"
                   ${svc.tarpitted ? 'checked' : ''}
                   data-service-id="${esc(svc.id)}">
            <span class="toggle-slider"></span>
          </label>
          <span class="tarpit-label" id="svc-tarpit-label-${esc(svc.id)}">
            ${svc.tarpitted ? 'TRAP' : '—'}
          </span>
          <button class="export-link" data-export-id="${esc(svc.id)}" title="Export ${esc(svc.label)} logs as CSV">⬇ CSV</button>
        </div>
      `;
      grid.appendChild(card);

      // Wire up enable toggle
      const input = card.querySelector('#svc-toggle-' + svc.id);
      input.addEventListener('change', () => toggleService(svc.id, input));

      // Wire up tarpit toggle
      const tarpitInput = card.querySelector('#svc-tarpit-' + svc.id);
      tarpitInput.addEventListener('change', () => toggleTarpit(svc.id, tarpitInput));

      // Wire up CSV export
      const exportBtn = card.querySelector('[data-export-id]');
      exportBtn.addEventListener('click', () => exportCsv(svc.id));
    });
  }

  function exportCsv(serviceId) {
    // Use navigation (not fetch) so the browser sends cached Basic Auth credentials.
    // Content-Disposition: attachment on the server side triggers a download without leaving the page.
    window.location.href = `${ADMIN_PREFIX}/api/export/${encodeURIComponent(serviceId)}.csv`;
  }

  function applyServiceUpdate(id, enabled) {
    const card  = document.querySelector(`.service-card[data-service-id="${CSS.escape(id)}"]`);
    const input = document.getElementById(`svc-toggle-${id}`);
    const label = document.getElementById(`svc-label-${id}`);
    if (card)  card.classList.toggle('disabled', !enabled);
    if (input) input.checked = enabled;
    if (label) label.textContent = enabled ? 'ON' : 'OFF';
  }

  function applyTarpitUpdate(id, tarpitted) {
    const input = document.getElementById(`svc-tarpit-${id}`);
    const label = document.getElementById(`svc-tarpit-label-${id}`);
    if (input) input.checked = tarpitted;
    if (label) label.textContent = tarpitted ? 'TRAP' : '—';
  }

  function toggleService(serviceId, inputEl) {
    inputEl.disabled = true;

    fetch(`${ADMIN_PREFIX}/api/services/${encodeURIComponent(serviceId)}/toggle`, {
      method: 'POST',
    })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        applyServiceUpdate(data.id, data.enabled);
      })
      .catch(err => {
        console.error('Toggle failed:', err);
        inputEl.checked = !inputEl.checked;
      })
      .finally(() => {
        inputEl.disabled = false;
      });
  }

  function toggleTarpit(serviceId, inputEl) {
    inputEl.disabled = true;

    fetch(`${ADMIN_PREFIX}/api/services/${encodeURIComponent(serviceId)}/tarpit`, {
      method: 'POST',
    })
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(data => {
        applyTarpitUpdate(data.id, data.tarpitted);
      })
      .catch(err => {
        console.error('Tarpit toggle failed:', err);
        inputEl.checked = !inputEl.checked;
      })
      .finally(() => {
        inputEl.disabled = false;
      });
  }

  function loadServices() {
    fetch(`${ADMIN_PREFIX}/api/services`)
      .then(r => r.json())
      .then(renderServicesGrid)
      .catch(console.warn);
  }

  // ── WebSocket ─────────────────────────────────────────────────────────────────
  function connectWS() {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws';
    const tokenParam = WS_TOKEN ? `?token=${encodeURIComponent(WS_TOKEN)}` : '';
    ws = new WebSocket(`${proto}://${location.host}/ws${tokenParam}`);

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
        updateFooterTime();
      } else if (msg.type === 'service_update') {
        applyServiceUpdate(msg.data.id, msg.data.enabled);
      } else if (msg.type === 'tarpit_update') {
        applyTarpitUpdate(msg.data.id, msg.data.tarpitted);
      } else if (msg.type === 'ip_blocked') {
        showToast(`🚫 Auto-blocked: ${msg.data.ip}`);
        loadBlockedIps();
      } else if (msg.type === 'ip_unblocked') {
        loadBlockedIps();
      }
    };

    ws.onclose = () => {
      setLiveStatus(false);
      setTimeout(connectWS, wsReconnectDelay);
      wsReconnectDelay = Math.min(wsReconnectDelay * 2, 30000);
    };

    ws.onerror = () => ws.close();
  }

  // ── Toast ─────────────────────────────────────────────────────────────────────
  function showToast(msg, duration = 3000) {
    const el = document.getElementById('toast');
    if (!el) return;
    el.textContent = msg;
    el.classList.add('visible');
    setTimeout(() => el.classList.remove('visible'), duration);
  }

  // ── IP Session Drawer ────────────────────────────────────────────────────────
  function openIpDrawer(ip) {
    _currentDrawerIp = ip;
    const drawer  = document.getElementById('ip-drawer');
    const overlay = document.getElementById('ip-drawer-overlay');
    const title   = document.getElementById('ip-drawer-title');
    const body    = document.getElementById('ip-drawer-body');
    if (!drawer) return;

    title.textContent = `Sessions: ${ip}`;
    body.innerHTML = '<div style="color:var(--text-muted);font-size:13px">Loading…</div>';
    drawer.classList.add('open');
    overlay.classList.add('visible');

    // Load current note
    _refreshIpNoteDisplay(ip);

    fetch(`${ADMIN_PREFIX}/api/ip/${encodeURIComponent(ip)}/requests`)
      .then(r => r.json())
      .then(rows => {
        if (!rows.length) {
          body.innerHTML = '<div style="color:var(--text-muted);font-size:13px">No requests found.</div>';
          return;
        }
        const geo = rows.find(r => r.country);
        const meta = `
          <div class="ip-meta">
            <span><strong>IP:</strong> ${esc(ip)}</span>
            ${geo ? `<span><strong>Country:</strong> ${esc(geo.country)}</span>` : ''}
            ${geo ? `<span><strong>City:</strong> ${esc(geo.city || '—')}</span>` : ''}
            <span><strong>Requests:</strong> ${rows.length}</span>
          </div>`;
        const tbRows = rows.map(r => `
          <tr>
            <td>${(r.timestamp || '').slice(0,19)}</td>
            <td>${esc(r.method)}</td>
            <td title="${esc(r.path)}">${esc(r.path)}</td>
            <td>${riskBadge(r.risk_level)}</td>
            <td title="${esc(r.flagged_patterns || '')}">${esc((r.flagged_patterns || '[]').replace(/[\[\]"]/g,'').slice(0,40) || '—')}</td>
          </tr>`).join('');
        body.innerHTML = meta + `
          <table>
            <thead><tr><th>Time</th><th>Method</th><th>Path</th><th>Risk</th><th>Patterns</th></tr></thead>
            <tbody>${tbRows}</tbody>
          </table>`;
      })
      .catch(() => {
        body.innerHTML = '<div style="color:var(--risk-critical);font-size:13px">Failed to load session data.</div>';
      });
  }

  function closeIpDrawer() {
    _currentDrawerIp = null;
    document.getElementById('ip-drawer')?.classList.remove('open');
    document.getElementById('ip-drawer-overlay')?.classList.remove('visible');
  }

  // ── IP blocking ───────────────────────────────────────────────────────────────

  function blockIpFromDrawer() {
    if (!_currentDrawerIp) return;
    blockIp(_currentDrawerIp, 'manual block from IP drawer');
  }

  function blockIpFromModal() {
    if (!_currentModalData) return;
    blockIp(_currentModalData.ip, `manual block from request #${_currentModalData.id}`);
  }

  function blockIp(ip, reason) {
    if (!confirm(`Block ${ip}?\n\nAll future requests from this IP will receive a 429 response.`)) return;
    fetch(`${ADMIN_PREFIX}/api/blocked-ips`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ip, reason}),
    })
      .then(r => r.json())
      .then(() => { showToast(`${ip} blocked`); loadBlockedIps(); })
      .catch(() => showToast('Block failed'));
  }

  function unblockIp(ip) {
    fetch(`${ADMIN_PREFIX}/api/blocked-ips/${encodeURIComponent(ip)}`, {method: 'DELETE'})
      .then(r => r.json())
      .then(() => { showToast(`${ip} unblocked`); loadBlockedIps(); })
      .catch(() => showToast('Unblock failed'));
  }

  function manualBlockIp() {
    const ip     = (document.getElementById('block-ip-input')?.value || '').trim();
    const reason = (document.getElementById('block-reason-input')?.value || '').trim() || 'manual block';
    if (!ip) return;
    blockIp(ip, reason);
    const el = document.getElementById('block-ip-input');
    if (el) el.value = '';
  }

  function loadBlockedIps() {
    fetch(`${ADMIN_PREFIX}/api/blocked-ips`)
      .then(r => r.json())
      .then(rows => {
        const badge = document.getElementById('blocked-count-badge');
        const tbody = document.getElementById('blocked-tbody');
        if (badge) badge.textContent = rows.length;
        if (!tbody) return;
        if (!rows.length) {
          tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-muted);text-align:center;padding:16px">No blocked IPs</td></tr>';
          return;
        }
        tbody.innerHTML = rows.map(r => `
          <tr>
            <td>${esc(r.ip)}</td>
            <td style="color:var(--text-muted);font-family:inherit">${esc(r.reason || '—')}</td>
            <td style="color:var(--text-muted);font-family:inherit">${(r.blocked_at || '').slice(0,19)}</td>
            <td><button class="btn-reset" style="font-size:11px;color:var(--text-muted)" onclick="unblockIp('${esc(r.ip)}')">Unblock</button></td>
          </tr>`).join('');
      })
      .catch(console.warn);
  }

  function toggleBlockedSection() {
    const body = document.getElementById('blocked-body');
    if (!body) return;
    const visible = body.style.display !== 'none';
    body.style.display = visible ? 'none' : '';
  }

  // ── IP Allow-list ─────────────────────────────────────────────────────────────

  function loadAllowedIps() {
    fetch(`${ADMIN_PREFIX}/api/allowed-ips`)
      .then(r => r.json())
      .then(rows => {
        const badge = document.getElementById('allowed-count-badge');
        const tbody = document.getElementById('allowed-tbody');
        if (badge) badge.textContent = rows.length;
        if (!tbody) return;
        if (!rows.length) {
          tbody.innerHTML = '<tr><td colspan="4" style="color:var(--text-muted);text-align:center;padding:16px">No allowed IPs</td></tr>';
          return;
        }
        tbody.innerHTML = rows.map(r => `
          <tr>
            <td>${esc(r.ip)}</td>
            <td style="color:var(--text-muted)">${esc(r.label || '—')}</td>
            <td style="color:var(--text-muted)">${(r.added_at || '').slice(0,19)}</td>
            <td><button class="btn-reset" style="font-size:11px;color:var(--text-muted)" onclick="removeAllowedIp('${esc(r.ip)}')">Remove</button></td>
          </tr>`).join('');
      })
      .catch(console.warn);
  }

  function addAllowedIp() {
    const ip    = (document.getElementById('allow-ip-input')?.value || '').trim();
    const label = (document.getElementById('allow-label-input')?.value || '').trim() || 'manual';
    if (!ip) return;
    fetch(`${ADMIN_PREFIX}/api/allowed-ips`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ip, label}),
    })
      .then(r => r.json())
      .then(() => {
        showToast(`${ip} added to allow-list`);
        document.getElementById('allow-ip-input').value = '';
        document.getElementById('allow-label-input').value = '';
        loadAllowedIps();
      })
      .catch(() => showToast('Failed to add IP'));
  }

  function removeAllowedIp(ip) {
    fetch(`${ADMIN_PREFIX}/api/allowed-ips/${encodeURIComponent(ip)}`, {method: 'DELETE'})
      .then(r => r.json())
      .then(() => { showToast(`${ip} removed from allow-list`); loadAllowedIps(); })
      .catch(() => showToast('Failed to remove IP'));
  }

  function toggleAllowedSection() {
    const body = document.getElementById('allowed-body');
    if (!body) return;
    const visible = body.style.display !== 'none';
    body.style.display = visible ? 'none' : '';
  }

  // ── IP Notes ──────────────────────────────────────────────────────────────────

  function _refreshIpNoteDisplay(ip) {
    const display = document.getElementById('ip-note-display');
    const input   = document.getElementById('ip-note-input');
    if (!display) return;
    fetch(`${ADMIN_PREFIX}/api/ip-notes/${encodeURIComponent(ip)}`)
      .then(r => r.json())
      .then(data => {
        if (data.note) {
          display.textContent = `📝 ${data.note}`;
          display.style.display = '';
        } else {
          display.textContent = '+ Add note…';
          display.style.color = 'var(--text-muted)';
          display.style.display = '';
        }
        if (input) input.style.display = 'none';
      })
      .catch(() => {});
  }

  function editIpNote() {
    if (!_currentDrawerIp) return;
    const display = document.getElementById('ip-note-display');
    const input   = document.getElementById('ip-note-input');
    if (!display || !input) return;
    // Populate input with current note (strip prefix)
    const current = display.textContent.replace(/^📝\s*/, '').replace(/^\+\s*Add note…$/, '');
    input.value = current;
    display.style.display = 'none';
    input.style.display = '';
    input.focus();
  }

  function saveIpNote() {
    if (!_currentDrawerIp) return;
    const input = document.getElementById('ip-note-input');
    if (!input) return;
    const note = input.value.trim();
    if (!note) {
      // Delete the note if empty
      fetch(`${ADMIN_PREFIX}/api/ip-notes/${encodeURIComponent(_currentDrawerIp)}`, {method: 'DELETE'})
        .then(() => _refreshIpNoteDisplay(_currentDrawerIp))
        .catch(() => {});
      return;
    }
    fetch(`${ADMIN_PREFIX}/api/ip-notes/${encodeURIComponent(_currentDrawerIp)}`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({note}),
    })
      .then(() => _refreshIpNoteDisplay(_currentDrawerIp))
      .catch(() => showToast('Failed to save note'));
  }

  function cancelIpNote() {
    if (!_currentDrawerIp) return;
    _refreshIpNoteDisplay(_currentDrawerIp);
  }

  // ── Webhook config ───────────────────────────────────────────────────────────
  function loadWebhookConfig() {
    fetch(`${ADMIN_PREFIX}/api/webhooks/config`)
      .then(r => r.json())
      .then(data => {
        const el = document.getElementById('webhook-status');
        if (!el) return;
        if (data.configured) {
          el.innerHTML = `<span style="color:var(--risk-low)">✓ Active</span> &bull; ${data.url_count} URL${data.url_count !== 1 ? 's' : ''} &bull; Format: <strong>${esc(data.format)}</strong> &bull; Levels: <strong>${esc(data.risk_levels.join(', '))}</strong>`;
        } else {
          el.innerHTML = `<span style="color:var(--text-muted)">Not configured</span> — set <code>WEBHOOK_URLS</code> env var`;
        }
      })
      .catch(() => {});
  }

  function testWebhook() {
    const btn = document.getElementById('test-webhook-btn');
    const result = document.getElementById('webhook-test-result');
    if (btn) btn.disabled = true;
    fetch(`${ADMIN_PREFIX}/api/webhooks/test`, { method: 'POST' })
      .then(r => r.json())
      .then(data => {
        if (result) result.textContent = data.sent > 0 ? `Sent to ${data.sent} URL${data.sent !== 1 ? 's' : ''}` : 'No URLs configured';
        showToast('Test webhook sent');
      })
      .catch(() => {
        if (result) result.textContent = 'Error';
      })
      .finally(() => {
        if (btn) btn.disabled = false;
        setTimeout(() => { if (result) result.textContent = ''; }, 4000);
      });
  }

  // ── Canary token ─────────────────────────────────────────────────────────────
  function loadCanaryToken() {
    fetch(`${ADMIN_PREFIX}/api/canary-token`)
      .then(r => r.json())
      .then(data => {
        const el = document.getElementById('canary-token-display');
        if (el) el.textContent = data.token;
      })
      .catch(() => {});
  }

  function copyCanaryToken() {
    const el = document.getElementById('canary-token-display');
    const result = document.getElementById('canary-copy-result');
    if (!el) return;
    navigator.clipboard.writeText(el.textContent).then(() => {
      if (result) result.textContent = 'Copied!';
      showToast('Canary token copied to clipboard');
      setTimeout(() => { if (result) result.textContent = ''; }, 2000);
    }).catch(() => {
      if (result) result.textContent = 'Copy failed';
    });
  }

  // ── Request body viewer modal ─────────────────────────────────────────────────

  function openRequestModal(id) {
    fetch(`${ADMIN_PREFIX}/api/requests/${id}`)
      .then(r => { if (!r.ok) throw new Error(r.status); return r.json(); })
      .then(d => _renderModal(d))
      .catch(err => showToast('Failed to load request: ' + err));
  }

  function _renderModal(d) {
    _currentModalData = d;
    document.getElementById('modal-risk').textContent     = d.risk_level || '';
    document.getElementById('modal-risk').className       = `risk-badge risk-${(d.risk_level||'').toLowerCase()}`;
    document.getElementById('modal-method').textContent   = d.method || '';
    document.getElementById('modal-path').textContent     = d.path || '';
    document.getElementById('modal-ip').textContent       = d.ip || '';
    document.getElementById('modal-country').textContent  = [d.city, d.country].filter(Boolean).join(', ') || '';
    document.getElementById('modal-ts').textContent       = d.timestamp ? d.timestamp.replace('T',' ').slice(0,19)+' UTC' : '';

    // Headers table
    const hBody = document.getElementById('modal-headers-body');
    hBody.innerHTML = '';
    const headers = typeof d.headers === 'string' ? JSON.parse(d.headers || '{}') : (d.headers || {});
    Object.entries(headers).sort(([a],[b]) => a.localeCompare(b)).forEach(([k,v]) => {
      const row = document.createElement('tr');
      row.innerHTML = `<td>${esc(k)}</td><td>${esc(String(v))}</td>`;
      hBody.appendChild(row);
    });
    document.getElementById('modal-headers-table').style.display = 'none';
    document.getElementById('modal-header-toggle').textContent = '(click to expand)';

    // Body
    const bodyEl = document.getElementById('modal-body');
    if (d.body) {
      try {
        bodyEl.textContent = JSON.stringify(JSON.parse(d.body), null, 2);
      } catch {
        bodyEl.textContent = d.body;
      }
    } else {
      bodyEl.textContent = '(empty body)';
    }

    // Patterns
    const patList = document.getElementById('modal-patterns-list');
    patList.innerHTML = '';
    const patterns = typeof d.flagged_patterns === 'string'
      ? JSON.parse(d.flagged_patterns || '[]') : (d.flagged_patterns || []);
    if (patterns.length === 0) {
      const li = document.createElement('li');
      li.className = 'empty-note'; li.textContent = 'No flagged patterns';
      patList.appendChild(li);
    } else {
      patterns.forEach(p => {
        const li = document.createElement('li');
        li.textContent = p;
        patList.appendChild(li);
      });
    }

    // Reset to request tab
    switchModalTab('request', document.querySelector('.modal-tab'));

    document.getElementById('req-modal').style.display = 'flex';
  }

  function closeRequestModal() {
    document.getElementById('req-modal').style.display = 'none';
  }

  function copyModalAsCurl() {
    if (!_currentModalData) return;
    const d = _currentModalData;
    const headers = typeof d.headers === 'string' ? JSON.parse(d.headers || '{}') : (d.headers || {});
    const headerLines = Object.entries(headers)
      .filter(([k]) => k.toLowerCase() !== 'host' && k.toLowerCase() !== 'content-length')
      .map(([k, v]) => `  -H '${k}: ${String(v).replace(/'/g, "'\\''")}' \\`)
      .join('\n');
    const bodyLine = d.body ? `  -d '${d.body.replace(/'/g, "'\\''")}' \\` : '';
    const lines = [
      `curl -X ${d.method || 'GET'} 'http://TARGET_HOST${d.path}' \\`,
      headerLines,
      bodyLine,
    ].filter(Boolean).join('\n').replace(/\s*\\$/, '');
    navigator.clipboard.writeText(lines)
      .then(() => showToast('cURL command copied!'))
      .catch(() => showToast('Copy failed — check clipboard permissions'));
  }

  function switchModalTab(name, btn) {
    document.querySelectorAll('.modal-tab').forEach(b => b.classList.remove('active'));
    if (btn) btn.classList.add('active');
    document.getElementById('modal-tab-request').style.display  = name === 'request'  ? '' : 'none';
    document.getElementById('modal-tab-patterns').style.display = name === 'patterns' ? '' : 'none';
  }

  function toggleModalHeaders() {
    const el = document.getElementById('modal-headers-table');
    const hint = document.getElementById('modal-header-toggle');
    const visible = el.style.display !== 'none';
    el.style.display = visible ? 'none' : '';
    hint.textContent = visible ? '(click to expand)' : '(click to collapse)';
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
    HoneypotCharts.initRiskChart('risk-chart');
    HoneypotCharts.initCategoryChart('category-chart');
    HoneypotCharts.initTimelineChart('timeline-chart');
    HoneypotCharts.initWeeklyChart('weekly-chart');
    HoneypotCharts.initHeatmapChart('heatmap-chart');

    HoneypotMap.init('map');

    refreshStats();
    loadInitialFeed();
    loadMapData();
    loadServices();
    loadWebhookConfig();
    loadCanaryToken();
    loadBlockedIps();
    loadAllowedIps();
    loadIntelCharts();

    // Update auto-block status indicator
    const autoBlockStatus = document.getElementById('auto-block-status');
    if (autoBlockStatus) {
      // Set by server-rendered template or default to off
      autoBlockStatus.textContent = window.AUTO_BLOCK_ENABLED ? 'on' : 'off';
    }

    // ── Search ──────────────────────────────────────────────────────────────
    document.getElementById('feed-search-input')?.addEventListener('input', e => {
      clearTimeout(searchDebounce);
      searchDebounce = setTimeout(() => {
        searchQuery = e.target.value.trim();
        loadFeed(searchQuery);
      }, 300);
    });

    // ── IP drawer + request modal ───────────────────────────────────────────
    document.getElementById('feed-tbody')?.addEventListener('click', e => {
      const cell = e.target.closest('.ip-cell');
      if (cell) { openIpDrawer(cell.dataset.ip); return; }
      const row = e.target.closest('.feed-row');
      if (row && row.dataset.id) openRequestModal(Number(row.dataset.id));
    });

    // ── Keyboard shortcuts ──────────────────────────────────────────────────
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') closeRequestModal();
    });
    document.getElementById('ip-drawer-close')?.addEventListener('click', closeIpDrawer);
    document.getElementById('ip-drawer-overlay')?.addEventListener('click', closeIpDrawer);

    // ── Webhooks + canary ───────────────────────────────────────────────────
    document.getElementById('test-webhook-btn')?.addEventListener('click', testWebhook);
    document.getElementById('copy-canary-btn')?.addEventListener('click', copyCanaryToken);

    // ── Service management ──────────────────────────────────────────────────
    document.getElementById('reset-services-btn')?.addEventListener('click', () => {
      if (!confirm('Reset all services to enabled?')) return;
      fetch(`${ADMIN_PREFIX}/api/services/reset`, { method: 'POST' })
        .then(r => r.json())
        .then(() => loadServices())
        .catch(console.warn);
    });

    document.getElementById('clear-data-btn')?.addEventListener('click', () => {
      if (!confirm('Delete ALL request data? This cannot be undone.')) return;
      fetch(`${ADMIN_PREFIX}/api/requests/clear`, { method: 'POST' })
        .then(r => r.json())
        .then(() => {
          document.getElementById('feed-tbody').innerHTML = '';
          feedRowCount = 0;
          refreshStats();
          loadMapData();
        })
        .catch(console.warn);
    });

    setInterval(refreshStats, 30000);
    setInterval(loadIntelCharts, 300000);  // every 5 min

    connectWS();
    updateFooterTime();
    setInterval(updateFooterTime, 1000);
  });

  // ── Expose functions needed by HTML onclick attributes ────────────────────────
  window.manualBlockIp       = manualBlockIp;
  window.unblockIp           = unblockIp;
  window.blockIpFromDrawer   = blockIpFromDrawer;
  window.blockIpFromModal    = blockIpFromModal;
  window.toggleBlockedSection = toggleBlockedSection;
  window.copyModalAsCurl     = copyModalAsCurl;
  window.closeRequestModal   = closeRequestModal;
  window.switchModalTab      = switchModalTab;
  window.toggleModalHeaders  = toggleModalHeaders;
  window.addAllowedIp        = addAllowedIp;
  window.removeAllowedIp     = removeAllowedIp;
  window.toggleAllowedSection = toggleAllowedSection;
  window.editIpNote          = editIpNote;
  window.saveIpNote          = saveIpNote;
  window.cancelIpNote        = cancelIpNote;
})();
