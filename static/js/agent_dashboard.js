/* Agent dashboard chart logic – reads AD from the page. */
(function () {
    'use strict';

    function shortDate(d) {
        return new Date(d).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (typeof AD === 'undefined') return;

        /* ── Performance trend ────────────────────────────────── */
        var ctx = document.getElementById('agentPerfChart');
        if (ctx) {
            new Chart(ctx, {
                type: 'line',
                data: {
                    labels: AD.dates.map(shortDate),
                    datasets: [
                        { label: 'Task Completion', data: AD.task_completion.values, borderColor: '#ee6f27', backgroundColor: '#ee6f2720', fill: false, tension: 0.4, pointRadius: 0, pointHoverRadius: 4, borderWidth: 2 },
                        { label: 'Groundedness', data: AD.groundedness.values, borderColor: '#0a9396', backgroundColor: '#0a939620', fill: false, tension: 0.4, pointRadius: 0, pointHoverRadius: 4, borderWidth: 2 },
                        { label: 'Safety', data: AD.safety.values, borderColor: '#4c9a2a', backgroundColor: '#4c9a2a20', fill: false, tension: 0.4, pointRadius: 0, pointHoverRadius: 4, borderWidth: 2 },
                    ],
                },
                options: {
                    responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { position: 'top', labels: { usePointStyle: true } } },
                    scales: {
                        x: { ticks: { maxTicksAutoSkip: true, maxRotation: 0 }, grid: { display: false } },
                        y: { min: 0.5, max: 1, grid: { color: '#f1f5f9' } },
                    },
                },
            });
        }

        /* ── Task breakdown ───────────────────────────────────── */
        var tbCtx = document.getElementById('taskBreakdownChart');
        if (tbCtx && AD.task_breakdown) {
            new Chart(tbCtx, {
                type: 'bar',
                data: {
                    labels: AD.task_breakdown.map(function (t) { return t.category; }),
                    datasets: [{
                        label: 'Completion Rate',
                        data: AD.task_breakdown.map(function (t) { return t.completion_rate; }),
                        backgroundColor: '#ee6f27', borderRadius: 4,
                    }],
                },
                options: {
                    indexAxis: 'y', responsive: true, maintainAspectRatio: false,
                    plugins: { legend: { display: false } },
                    scales: { x: { min: 0.5, max: 1, grid: { color: '#f1f5f9' } }, y: { grid: { display: false } } },
                },
            });
        }

        /* ── Lazy init for other tabs ─────────────────────────── */
        var inited = {};
        document.querySelectorAll('#agentTabs button[data-bs-toggle="tab"]').forEach(function (tab) {
            tab.addEventListener('shown.bs.tab', function (e) {
                var target = e.target.getAttribute('data-bs-target');

                if (target === '#agent-cost' && !inited.cost) {
                    inited.cost = true;
                    /* Cost trend */
                    var costCtx = document.getElementById('costTrendChart');
                    if (costCtx) {
                        new Chart(costCtx, {
                            type: 'line',
                            data: {
                                labels: AD.tokens.dates.map(shortDate),
                                datasets: [{
                                    label: 'Daily Cost ($)', data: AD.tokens.cost_per_day,
                                    borderColor: '#ee6f27', backgroundColor: '#ee6f2720',
                                    fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2,
                                }],
                            },
                            options: {
                                responsive: true, maintainAspectRatio: false,
                                plugins: { legend: { display: false } },
                                scales: {
                                    x: { ticks: { maxTicksAutoSkip: true, maxRotation: 0 }, grid: { display: false } },
                                    y: { grid: { color: '#f1f5f9' } },
                                },
                            },
                        });
                    }
                    /* Token trend */
                    var tokCtx = document.getElementById('tokenTrendChart');
                    if (tokCtx) {
                        new Chart(tokCtx, {
                            type: 'bar',
                            data: {
                                labels: AD.tokens.dates.slice(-30).map(shortDate),
                                datasets: [
                                    { label: 'Input Tokens', data: AD.tokens.input_tokens.slice(-30), backgroundColor: '#0a9396', borderRadius: 2 },
                                    { label: 'Output Tokens', data: AD.tokens.output_tokens.slice(-30), backgroundColor: '#ee6f27', borderRadius: 2 },
                                ],
                            },
                            options: {
                                responsive: true, maintainAspectRatio: false,
                                plugins: { legend: { position: 'top', labels: { usePointStyle: true } } },
                                scales: {
                                    x: { stacked: true, ticks: { maxRotation: 0 }, grid: { display: false } },
                                    y: { stacked: true, grid: { color: '#f1f5f9' } },
                                },
                            },
                        });
                    }
                }

                if (target === '#agent-safety' && !inited.safety) {
                    inited.safety = true;
                    var sCtx = document.getElementById('safetyTrendChart');
                    if (sCtx) {
                        new Chart(sCtx, {
                            type: 'line',
                            data: {
                                labels: AD.dates.map(shortDate),
                                datasets: [
                                    { label: 'Safety Score', data: AD.safety.values, borderColor: '#4c9a2a', backgroundColor: '#4c9a2a20', fill: true, tension: 0.4, pointRadius: 0, borderWidth: 2 },
                                    { label: 'Threshold (0.90)', data: new Array(AD.dates.length).fill(0.9), borderColor: '#f59e0b', borderWidth: 1, borderDash: [5, 5], pointRadius: 0, fill: false },
                                ],
                            },
                            options: {
                                responsive: true, maintainAspectRatio: false,
                                plugins: { legend: { position: 'top' } },
                                scales: {
                                    x: { ticks: { maxTicksAutoSkip: true, maxRotation: 0 }, grid: { display: false } },
                                    y: { min: 0.7, max: 1, grid: { color: '#f1f5f9' } },
                                },
                            },
                        });
                    }
                }

                if (target === '#agent-policy' && !inited.policy) {
                    inited.policy = true;
                    var vCtx = document.getElementById('voiceTrendChart');
                    if (vCtx && AD.voice_scores) {
                        var dims = AD.voice_scores.dimensions;
                        var colors = ['#ee6f27', '#0a9396', '#4c9a2a', '#d15b18', '#077377'];
                        var datasets = [];
                        var i = 0;
                        for (var key in dims) {
                            var d = dims[key];
                            datasets.push({
                                label: d.label, data: d.values,
                                borderColor: colors[i % colors.length],
                                backgroundColor: colors[i % colors.length] + '20',
                                fill: false, tension: 0.4,
                                pointRadius: 0, pointHoverRadius: 4, borderWidth: 2,
                            });
                            i++;
                        }
                        new Chart(vCtx, {
                            type: 'line',
                            data: { labels: AD.voice_scores.dates.map(shortDate), datasets: datasets },
                            options: {
                                responsive: true, maintainAspectRatio: false,
                                plugins: { legend: { position: 'top', labels: { usePointStyle: true } } },
                                scales: {
                                    x: { ticks: { maxTicksAutoSkip: true, maxRotation: 0 }, grid: { display: false } },
                                    y: { min: 0.5, max: 1, grid: { color: '#f1f5f9' } },
                                },
                            },
                        });
                    }
                }
            });
        });
    });
})();
