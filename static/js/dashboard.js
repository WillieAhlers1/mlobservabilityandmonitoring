/* Dashboard chart logic – reads MODEL_DATA from the page. */

(function () {
    'use strict';

    var charts = {};

    function destroyChart(id) {
        if (charts[id]) { charts[id].destroy(); delete charts[id]; }
    }

    function shortDate(d) {
        var dt = new Date(d);
        return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }

    /* ── colours (Tredence brand) ────────────────────────────── */
    var COLORS = {
        accuracy:  '#ee6f27',
        precision: '#0a9396',
        recall:    '#4c9a2a',
        f1_score:  '#077377',
        auc_roc:   '#d15b18',
        r2_score:  '#ee6f27',
        mae:       '#ef4444',
        rmse:      '#0a9396',
        mape:      '#4c9a2a',
    };

    /* ── Performance tab ─────────────────────────────────────── */
    function initPerformanceTab(data) {
        /* trend line chart */
        var metrics = data.metrics;
        var dates   = data.dates;

        var datasets = Object.keys(metrics).map(function (key) {
            var m = metrics[key];
            return {
                label: m.label,
                data:  m.values,
                borderColor:     COLORS[key] || '#3b82f6',
                backgroundColor: (COLORS[key] || '#3b82f6') + '20',
                fill: false, tension: 0.4,
                pointRadius: 0, pointHoverRadius: 4, borderWidth: 2,
            };
        });

        destroyChart('performanceTrend');
        var ctx = document.getElementById('performanceTrendChart');
        if (ctx) {
            charts['performanceTrend'] = new Chart(ctx, {
                type: 'line',
                data: { labels: dates.map(shortDate), datasets: datasets },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: {
                        legend: { position: 'top', labels: { usePointStyle: true, padding: 15 } },
                        tooltip: { mode: 'index', intersect: false },
                    },
                    scales: {
                        x: { ticks: { maxTicksAutoSkip: true, maxRotation: 0 }, grid: { display: false } },
                        y: { grid: { color: '#f1f5f9' } },
                    },
                    interaction: { mode: 'nearest', axis: 'x', intersect: false },
                },
            });
        }

        /* cohort bar chart */
        var cohorts = data.cohorts;
        destroyChart('cohortPerformance');
        var cCtx = document.getElementById('cohortPerformanceChart');
        if (cCtx && cohorts) {
            charts['cohortPerformance'] = new Chart(cCtx, {
                type: 'bar',
                data: {
                    labels: cohorts.segments.map(function (s) { return s.name; }),
                    datasets: [
                        { label: 'Accuracy',  data: cohorts.segments.map(function (s) { return s.accuracy; }),  backgroundColor: '#ee6f27', borderRadius: 4 },
                        { label: 'Precision', data: cohorts.segments.map(function (s) { return s.precision; }), backgroundColor: '#0a9396', borderRadius: 4 },
                        { label: 'Recall',    data: cohorts.segments.map(function (s) { return s.recall; }),    backgroundColor: '#4c9a2a', borderRadius: 4 },
                    ],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { position: 'top', labels: { usePointStyle: true } } },
                    scales: {
                        y: { beginAtZero: false, min: 0.5, max: 1.0, grid: { color: '#f1f5f9' } },
                        x: { grid: { display: false } },
                    },
                },
            });
        }

        /* feature accuracy drop */
        var drops = data.feature_accuracy_drop;
        destroyChart('featureAccuracyDrop');
        var dCtx = document.getElementById('featureAccuracyDropChart');
        if (dCtx && drops) {
            var sorted = drops.slice().sort(function (a, b) { return b.accuracy_drop - a.accuracy_drop; });
            charts['featureAccuracyDrop'] = new Chart(dCtx, {
                type: 'bar',
                data: {
                    labels: sorted.map(function (d) { return d.feature; }),
                    datasets: [{
                        label: 'Accuracy Drop',
                        data: sorted.map(function (d) { return d.accuracy_drop; }),
                        backgroundColor: sorted.map(function (d) {
                            return d.accuracy_drop > 0.05 ? '#ef4444'
                                 : d.accuracy_drop > 0.02 ? '#f59e0b' : '#22c55e';
                        }),
                        borderRadius: 4,
                    }],
                },
                options: {
                    indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false },
                        tooltip: { callbacks: {
                            afterLabel: function (ctx2) { return 'Cohort: ' + sorted[ctx2.dataIndex].cohort_affected; }
                        }},
                    },
                    scales: {
                        x: { grid: { color: '#f1f5f9' } },
                        y: { grid: { display: false } },
                    },
                },
            });
        }
    }

    /* ── Drift tab ───────────────────────────────────────────── */
    function initDriftTab(data) {
        destroyChart('driftTrend');
        var ctx = document.getElementById('driftTrendChart');
        if (ctx && data.drift) {
            var len = data.drift.dates.length;
            charts['driftTrend'] = new Chart(ctx, {
                type: 'line',
                data: {
                    labels: data.drift.dates.map(shortDate),
                    datasets: [
                        {
                            label: 'Drift Score (PSI)', data: data.drift.values,
                            borderColor: '#ef4444', backgroundColor: '#ef444420',
                            fill: true, tension: 0.4,
                            pointRadius: 0, pointHoverRadius: 4, borderWidth: 2,
                        },
                        {
                            label: 'Warning (0.10)',
                            data: new Array(len).fill(0.1),
                            borderColor: '#f59e0b', borderWidth: 1, borderDash: [5, 5],
                            pointRadius: 0, fill: false,
                        },
                        {
                            label: 'Critical (0.25)',
                            data: new Array(len).fill(0.25),
                            borderColor: '#ef4444', borderWidth: 1, borderDash: [5, 5],
                            pointRadius: 0, fill: false,
                        },
                    ],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { position: 'top' } },
                    scales: {
                        y: { beginAtZero: true, max: 0.6, grid: { color: '#f1f5f9' } },
                        x: { ticks: { maxTicksAutoSkip: true, maxRotation: 0 }, grid: { display: false } },
                    },
                },
            });
        }

        /* feature drift */
        destroyChart('featureDrift');
        var fCtx = document.getElementById('featureDriftChart');
        if (fCtx && data.feature_drift) {
            var fd = data.feature_drift;
            charts['featureDrift'] = new Chart(fCtx, {
                type: 'bar',
                data: {
                    labels: fd.map(function (d) { return d.feature; }),
                    datasets: [{
                        label: 'PSI Value',
                        data: fd.map(function (d) { return d.psi; }),
                        backgroundColor: fd.map(function (d) {
                            return d.status === 'Critical' ? '#ef4444'
                                 : d.status === 'Warning'  ? '#f59e0b' : '#22c55e';
                        }),
                        borderRadius: 4,
                    }],
                },
                options: {
                    indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { color: '#f1f5f9' } },
                        y: { grid: { display: false } },
                    },
                },
            });
        }
    }

    /* ── Interpretability tab ────────────────────────────────── */
    function initInterpretabilityTab(data) {
        destroyChart('featureImportance');
        var ctx = document.getElementById('featureImportanceChart');
        if (ctx && data.feature_importance) {
            var fi = data.feature_importance;
            var colors = fi.map(function (_, i) {
                return 'rgba(238, 111, 39, ' + (1 - i / fi.length * 0.6) + ')';
            });
            charts['featureImportance'] = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: fi.map(function (d) { return d.feature; }),
                    datasets: [{
                        label: 'Importance Score',
                        data: fi.map(function (d) { return d.importance; }),
                        backgroundColor: colors,
                        borderRadius: 4,
                    }],
                },
                options: {
                    indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: {
                        x: { grid: { color: '#f1f5f9' }, title: { display: true, text: 'Relative Importance' } },
                        y: { grid: { display: false } },
                    },
                },
            });
        }
    }

    /* ── Data Quality tab ────────────────────────────────────── */
    function initDataQualityTab(data) {
        destroyChart('missingRate');
        var ctx = document.getElementById('missingRateChart');
        if (ctx && data.data_quality) {
            var dq = data.data_quality;
            charts['missingRate'] = new Chart(ctx, {
                type: 'bar',
                data: {
                    labels: dq.features.map(function (f) { return f.feature; }),
                    datasets: [
                        { label: 'Missing Rate (%)', data: dq.features.map(function (f) { return f.missing_rate; }), backgroundColor: '#ee6f27', borderRadius: 4 },
                        { label: 'Outlier Rate (%)', data: dq.features.map(function (f) { return f.outlier_rate; }), backgroundColor: '#0a9396', borderRadius: 4 },
                    ],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { position: 'top', labels: { usePointStyle: true } } },
                    scales: {
                        y: { grid: { color: '#f1f5f9' } },
                        x: { grid: { display: false } },
                    },
                },
            });
        }
    }

    /* ── Init ─────────────────────────────────────────────────── */
    document.addEventListener('DOMContentLoaded', function () {
        if (typeof MODEL_DATA === 'undefined') return;
        var data = MODEL_DATA;

        /* performance tab is visible by default */
        initPerformanceTab(data);

        /* lazy-init other tabs on show */
        var inited = { performance: true };
        document.querySelectorAll('#dashboardTabs button[data-bs-toggle="tab"]').forEach(function (tab) {
            tab.addEventListener('shown.bs.tab', function (e) {
                var target = e.target.getAttribute('data-bs-target');
                if (target === '#drift' && !inited.drift) {
                    initDriftTab(data); inited.drift = true;
                } else if (target === '#interpretability' && !inited.interpretability) {
                    initInterpretabilityTab(data); inited.interpretability = true;
                } else if (target === '#data-quality' && !inited.dataQuality) {
                    initDataQualityTab(data); inited.dataQuality = true;
                }
            });
        });
    });
})();
