/**
 * Chart.js wrappers for risk pie, category bar, and timeline charts.
 * Exported as window.HoneypotCharts
 */

(function () {
  'use strict';

  Chart.defaults.color = '#8b949e';
  Chart.defaults.borderColor = '#30363d';
  Chart.defaults.font.family = "'Segoe UI', system-ui, sans-serif";
  Chart.defaults.font.size = 11;

  const RISK_COLORS = {
    CRITICAL: '#f85149',
    HIGH:     '#d29922',
    MEDIUM:   '#e3b341',
    LOW:      '#3fb950',
  };

  const CAT_COLORS = {
    inference:        '#58a6ff',
    model_management: '#d29922',
    embeddings:       '#bc8cff',
    enumeration:      '#79c0ff',
    model_info:       '#56d364',
    openai_compat:    '#f78166',
    scanning:         '#ffa657',
    attack:           '#f85149',
  };

  let riskChart     = null;
  let categoryChart = null;
  let timelineChart = null;

  // ── Risk doughnut ───────────────────────────────────────────────────────────
  function initRiskChart(canvasId) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    riskChart = new Chart(ctx, {
      type: 'doughnut',
      data: {
        labels:   ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'],
        datasets: [{
          data:            [0, 0, 0, 0],
          backgroundColor: [RISK_COLORS.CRITICAL, RISK_COLORS.HIGH, RISK_COLORS.MEDIUM, RISK_COLORS.LOW],
          borderWidth:     2,
          borderColor:     '#161b22',
          hoverOffset:     6,
        }],
      },
      options: {
        responsive:          true,
        maintainAspectRatio: false,
        cutout:              '65%',
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 10, padding: 10 } },
          tooltip: { callbacks: { label: (ctx) => ` ${ctx.label}: ${ctx.parsed}` } },
        },
      },
    });
  }

  // ── Category bar ────────────────────────────────────────────────────────────
  function initCategoryChart(canvasId) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    categoryChart = new Chart(ctx, {
      type: 'bar',
      data: {
        labels:   [],
        datasets: [{
          label:           'Requests',
          data:            [],
          backgroundColor: [],
          borderRadius:    4,
          borderSkipped:   false,
        }],
      },
      options: {
        responsive:          true,
        maintainAspectRatio: false,
        indexAxis:           'y',
        plugins: {
          legend: { display: false },
        },
        scales: {
          x: { grid: { color: '#21262d' }, ticks: { precision: 0 } },
          y: { grid: { display: false } },
        },
      },
    });
  }

  // ── 24h timeline ────────────────────────────────────────────────────────────
  function initTimelineChart(canvasId) {
    const ctx = document.getElementById(canvasId).getContext('2d');
    timelineChart = new Chart(ctx, {
      type: 'line',
      data: {
        labels:   [],
        datasets: [{
          label:           'Requests/hr',
          data:            [],
          borderColor:     '#58a6ff',
          backgroundColor: 'rgba(88,166,255,0.12)',
          fill:            true,
          tension:         0.3,
          pointRadius:     3,
          pointHoverRadius: 5,
        }],
      },
      options: {
        responsive:          true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { grid: { color: '#21262d' }, ticks: { maxTicksLimit: 8 } },
          y: { grid: { color: '#21262d' }, beginAtZero: true, ticks: { precision: 0 } },
        },
      },
    });
  }

  // ── Update functions ────────────────────────────────────────────────────────
  function updateRisk(byRisk) {
    if (!riskChart) return;
    const order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'];
    riskChart.data.datasets[0].data = order.map(k => byRisk[k] || 0);
    riskChart.update('none');
  }

  function updateCategory(byCategory) {
    if (!categoryChart) return;
    const entries = Object.entries(byCategory).sort((a, b) => b[1] - a[1]);
    categoryChart.data.labels   = entries.map(([k]) => k);
    categoryChart.data.datasets[0].data            = entries.map(([, v]) => v);
    categoryChart.data.datasets[0].backgroundColor = entries.map(([k]) => CAT_COLORS[k] || '#58a6ff');
    categoryChart.update('none');
  }

  function updateTimeline(hourlyTrend) {
    if (!timelineChart) return;
    timelineChart.data.labels                    = hourlyTrend.map(h => h.hour ? h.hour.slice(11, 16) : '');
    timelineChart.data.datasets[0].data         = hourlyTrend.map(h => h.cnt);
    timelineChart.update('none');
  }

  function incrementRisk(riskLevel) {
    if (!riskChart) return;
    const idx = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].indexOf(riskLevel);
    if (idx >= 0) {
      riskChart.data.datasets[0].data[idx]++;
      riskChart.update('none');
    }
  }

  function incrementCategory(category) {
    if (!categoryChart) return;
    const idx = categoryChart.data.labels.indexOf(category);
    if (idx >= 0) {
      categoryChart.data.datasets[0].data[idx]++;
    } else {
      categoryChart.data.labels.push(category);
      categoryChart.data.datasets[0].data.push(1);
      categoryChart.data.datasets[0].backgroundColor.push(CAT_COLORS[category] || '#58a6ff');
    }
    categoryChart.update('none');
  }

  // ── Weekly trend chart ───────────────────────────────────────────────────────
  let weeklyChart = null;

  function initWeeklyChart(canvasId) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    weeklyChart = new Chart(ctx, {
      type: 'bar',
      data: { labels: [], datasets: [
        { label: 'CRITICAL', data: [], backgroundColor: '#f85149', stack: 'risk' },
        { label: 'HIGH',     data: [], backgroundColor: '#d29922', stack: 'risk' },
        { label: 'MEDIUM',   data: [], backgroundColor: '#388bfd', stack: 'risk' },
        { label: 'LOW',      data: [], backgroundColor: '#3fb950', stack: 'risk' },
      ]},
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: 'bottom', labels: { boxWidth: 10, font: { size: 10 } } } },
        scales: {
          x: { stacked: true, grid: { color: '#21262d' }, ticks: { font: { size: 10 } } },
          y: { stacked: true, grid: { color: '#21262d' }, ticks: { font: { size: 10 } } },
        },
      },
    });
  }

  function updateWeeklyChart(rows) {
    if (!weeklyChart) return;
    weeklyChart.data.labels                = rows.map(r => r.day.slice(5));   // MM-DD
    weeklyChart.data.datasets[0].data = rows.map(r => r.critical || 0);
    weeklyChart.data.datasets[1].data = rows.map(r => r.high     || 0);
    weeklyChart.data.datasets[2].data = rows.map(r => r.medium   || 0);
    weeklyChart.data.datasets[3].data = rows.map(r => r.low      || 0);
    weeklyChart.update('none');
  }

  // ── Hour-of-day heatmap ──────────────────────────────────────────────────────
  const DOW_LABELS = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat'];

  function initHeatmapChart(containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    // Build skeleton — data comes from updateHeatmapChart
    el.innerHTML = '<div style="color:var(--text-muted);font-size:11px">Loading…</div>';
  }

  function updateHeatmapChart(rows) {
    const el = document.getElementById('heatmap-chart');
    if (!el) return;

    // Build a 7×24 count matrix
    const matrix = Array.from({length: 7}, () => new Array(24).fill(0));
    let maxVal = 1;
    rows.forEach(r => {
      const d = parseInt(r.dow, 10);
      const h = parseInt(r.hour, 10);
      if (d >= 0 && d < 7 && h >= 0 && h < 24) {
        matrix[d][h] += r.cnt;
        if (matrix[d][h] > maxVal) maxVal = matrix[d][h];
      }
    });

    // Hour labels row
    let html = '<div class="heatmap-hour-labels"><div class="heatmap-hour-label"></div>';
    for (let h = 0; h < 24; h++) {
      html += `<div class="heatmap-hour-label">${h}</div>`;
    }
    html += '</div>';

    // Grid rows
    html += '<div class="heatmap-grid">';
    for (let d = 0; d < 7; d++) {
      html += `<div class="heatmap-label">${DOW_LABELS[d]}</div>`;
      for (let h = 0; h < 24; h++) {
        const count = matrix[d][h];
        const intensity = count === 0 ? 0 : Math.max(0.08, count / maxVal);
        const alpha = (intensity * 0.9).toFixed(2);
        const title = `${DOW_LABELS[d]} ${String(h).padStart(2,'0')}:00 — ${count} requests`;
        html += `<div class="heatmap-cell" style="background:rgba(248,81,73,${alpha})" title="${title}"></div>`;
      }
    }
    html += '</div>';
    el.innerHTML = html;
  }

  window.HoneypotCharts = {
    initRiskChart,
    initCategoryChart,
    initTimelineChart,
    initWeeklyChart,
    initHeatmapChart,
    updateRisk,
    updateCategory,
    updateTimeline,
    updateWeeklyChart,
    updateHeatmapChart,
    incrementRisk,
    incrementCategory,
  };
})();
