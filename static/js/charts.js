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

  window.HoneypotCharts = {
    initRiskChart,
    initCategoryChart,
    initTimelineChart,
    updateRisk,
    updateCategory,
    updateTimeline,
    incrementRisk,
    incrementCategory,
  };
})();
