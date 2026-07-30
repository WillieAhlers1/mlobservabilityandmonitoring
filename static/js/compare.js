/* Compare page chart logic – reads MA and MB from the page. */
(function () {
    'use strict';

    function shortDate(d) {
        var dt = new Date(d);
        return dt.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (typeof MA === 'undefined' || typeof MB === 'undefined') return;

        /* ── Performance trend comparison ─────────────────────── */
        var primaryKeyA = MA.metric_type === 'classification' ? 'accuracy' : 'r2_score';
        var primaryKeyB = MB.metric_type === 'classification' ? 'accuracy' : 'r2_score';
        var labelA = MA.metrics[primaryKeyA] ? MA.metrics[primaryKeyA].label : 'Performance';
        var labelB = MB.metrics[primaryKeyB] ? MB.metrics[primaryKeyB].label : 'Performance';

        var ctx = document.getElementById('compareTrendChart');
        if (ctx) {
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: MA.dates.map(shortDate),
                    datasets: [
                        {
                            label: MA.model.name + ' (' + labelA + ')',
                            data: MA.metrics[primaryKeyA].values,
                            borderColor: '#3b82f6', backgroundColor: '#3b82f620',
                            fill: false, tension: 0.4,
                            pointRadius: 0, pointHoverRadius: 4, borderWidth: 2,
                        },
                        {
                            label: MB.model.name + ' (' + labelB + ')',
                            data: MB.metrics[primaryKeyB].values,
                            borderColor: '#0a9396', backgroundColor: '#0a939620',
                            fill: false, tension: 0.4,
                            pointRadius: 0, pointHoverRadius: 4, borderWidth: 2,
                        },
                    ],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { position: 'top', labels: { usePointStyle: true } } },
                    scales: {
                        x: { ticks: { maxTicksAutoSkip: true, maxRotation: 0 }, grid: { display: false } },
                        y: { grid: { color: '#f1f5f9' } },
                    },
                    interaction: { mode: 'nearest', axis: 'x', intersect: false },
                },
            });
        }

        /* ── Drift trend comparison ───────────────────────────── */
        var dCtx = document.getElementById('compareDriftChart');
        if (dCtx) {
            var len = MA.drift.dates.length;
            new Chart(dCtx, {
                type: 'line',
                data: {
                    labels: MA.drift.dates.map(shortDate),
                    datasets: [
                        {
                            label: MA.model.name + ' Drift',
                            data: MA.drift.values,
                            borderColor: '#ee6f27', backgroundColor: '#ee6f2720',
                            fill: false, tension: 0.4,
                            pointRadius: 0, pointHoverRadius: 4, borderWidth: 2,
                        },
                        {
                            label: MB.model.name + ' Drift',
                            data: MB.drift.values,
                            borderColor: '#0a9396', backgroundColor: '#0a939620',
                            fill: false, tension: 0.4,
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

        /* ── Feature importance A ─────────────────────────────── */
        function drawFeatureChart(canvasId, fi, color) {
            var el = document.getElementById(canvasId);
            if (!el || !fi) return;
            var top5 = fi.slice(0, 5);
            new Chart(el, {
                type: 'bar',
                data: {
                    labels: top5.map(function (d) { return d.feature; }),
                    datasets: [{
                        label: 'Importance',
                        data: top5.map(function (d) { return d.importance; }),
                        backgroundColor: color, borderRadius: 4,
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

        drawFeatureChart('featureImpA', MA.feature_importance, '#ee6f27');
        drawFeatureChart('featureImpB', MB.feature_importance, '#0a9396');
    });
})();
