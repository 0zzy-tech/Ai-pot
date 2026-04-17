/**
 * Leaflet map initialisation and pin management.
 * Exported as window.HoneypotMap
 */

(function () {
  'use strict';

  const RISK_COLORS = {
    CRITICAL: '#f85149',
    HIGH:     '#d29922',
    MEDIUM:   '#e3b341',
    LOW:      '#3fb950',
  };

  let map = null;
  // ip → marker (so we can update existing pins)
  const markers = {};

  function init(elementId) {
    map = L.map(elementId, {
      center:    [20, 10],
      zoom:      2,
      minZoom:   2,
      zoomControl: true,
      attributionControl: true,
    });

    // Dark OpenStreetMap tile layer via CartoDB
    L.tileLayer(
      'https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
      {
        attribution:
          '&copy; <a href="https://www.openstreetmap.org/copyright">OSM</a> contributors &copy; <a href="https://carto.com/">CARTO</a>',
        subdomains: 'abcd',
        maxZoom:    19,
      }
    ).addTo(map);
  }

  function addOrUpdatePin(data) {
    if (!map || data.lat == null || data.lng == null) return;

    const color = RISK_COLORS[data.risk_level] || RISK_COLORS.LOW;
    const ip    = data.ip;

    if (markers[ip]) {
      // Update colour if risk level changed
      markers[ip].setStyle({ fillColor: color });
      // Refresh popup
      markers[ip].setPopupContent(_popupHtml(data));
      return;
    }

    const m = L.circleMarker([data.lat, data.lng], {
      radius:      6,
      fillColor:   color,
      color:       '#fff',
      weight:      1,
      opacity:     0.9,
      fillOpacity: 0.85,
    }).addTo(map);

    m.bindPopup(_popupHtml(data), { maxWidth: 220 });
    markers[ip] = m;

    // Brief flash effect for new pin
    m.setStyle({ radius: 10, weight: 2 });
    setTimeout(() => m.setStyle({ radius: 6, weight: 1 }), 600);
  }

  function loadInitial(rows) {
    rows.forEach(addOrUpdatePin);
  }

  function _popupHtml(d) {
    const risk = d.risk_level || 'LOW';
    const riskColor = RISK_COLORS[risk] || RISK_COLORS.LOW;
    return `
      <div style="min-width:160px">
        <div style="font-weight:700;margin-bottom:4px">${_esc(d.ip)}</div>
        <div style="color:#8b949e;font-size:11px;margin-bottom:6px">
          ${_esc(d.city || '')}${d.city && d.country ? ', ' : ''}${_esc(d.country || 'Unknown')}
        </div>
        <div style="display:flex;gap:6px;flex-wrap:wrap">
          <span style="color:${riskColor};font-weight:600;font-size:11px">${risk}</span>
          <span style="color:#8b949e;font-size:11px">${_esc(d.category || '')}</span>
        </div>
        ${d.cnt ? `<div style="margin-top:4px;color:#8b949e;font-size:11px">${d.cnt} request${d.cnt > 1 ? 's' : ''}</div>` : ''}
        ${d.path ? `<div style="margin-top:2px;color:#79c0ff;font-size:11px;word-break:break-all">${_esc(d.path)}</div>` : ''}
      </div>`;
  }

  function _esc(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  window.HoneypotMap = { init, addOrUpdatePin, loadInitial };
})();
