// ================= DASHBOARD CHARTS =================
(function () {
  const dataEl = document.getElementById("dashboardData");
  if (!dataEl || typeof Chart === "undefined") return;

  const data = JSON.parse(dataEl.textContent);
  let charts = [];

  // Read colors from the CSS variables (so charts follow light/dark mode)
  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function alpha(hex, a) {
    let c = hex.replace("#", "");
    if (c.length === 3) c = c.split("").map((x) => x + x).join("");
    const n = parseInt(c, 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }

  function colors() {
    return {
      text: css("--muted"),
      grid: css("--border"),
      surface: css("--surface"),
      primary: css("--primary"),
      primary2: css("--primary-2"),
      success: css("--success"),
      warning: css("--warning"),
      danger: css("--danger"),
      info: css("--info"),
    };
  }

  function legend(c, position = "top") {
    return {
      position,
      labels: { color: c.text, usePointStyle: true, boxWidth: 8, padding: 14 },
    };
  }

  function axes(c, { horizontal = false, money = false, stacked = false } = {}) {
    const valueAxis = {
      beginAtZero: true,
      stacked,
      grid: { color: c.grid },
      ticks: {
        color: c.text,
        precision: 0,
        callback: (v) => (money ? Number(v).toLocaleString() : v),
      },
    };
  const labelAxis = {
      stacked,
      grid: { display: false },
      // Horizontal charts show every label; date charts show at most 8
      ticks: horizontal ? { color: c.text, autoSkip: false } : { color: c.text, maxTicksLimit: 8 },
    };
    return horizontal ? { x: valueAxis, y: labelAxis } : { x: labelAxis, y: valueAxis };
  }

  const tooltip = { backgroundColor: "#0f172a", padding: 10, cornerRadius: 10, titleColor: "#fff", bodyColor: "#e2e8f0" };

  function buildCharts() {
    charts.forEach((chart) => chart.destroy());
    charts = [];

    const c = colors();
    Chart.defaults.font.family = '"Plus Jakarta Sans", system-ui, sans-serif';
    Chart.defaults.color = c.text;

    // 1. Appointments over the last 30 days
    charts.push(new Chart(document.getElementById("trendChart"), {
      type: "line",
      data: {
        labels: data.trend.labels,
        datasets: [
          {
            label: "All appointments",
            data: data.trend.total,
            borderColor: c.primary2,
            backgroundColor: alpha(c.primary2, 0.12),
            fill: true,
            tension: 0.35,
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 5,
          },
          {
            label: "Completed",
            data: data.trend.completed,
            borderColor: c.success,
            backgroundColor: "transparent",
            borderDash: [5, 4],
            tension: 0.35,
            borderWidth: 2,
            pointRadius: 0,
            pointHoverRadius: 5,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: { legend: legend(c), tooltip },
        scales: axes(c),
      },
    }));

    // 2. Appointment status (donut)
    const statusColors = { scheduled: c.info, completed: c.success, cancelled: c.danger, no_show: c.warning };
    charts.push(new Chart(document.getElementById("statusChart"), {
      type: "doughnut",
      data: {
        labels: data.status.labels,
        datasets: [{
          data: data.status.values,
          backgroundColor: data.status.keys.map((k) => statusColors[k]),
          borderColor: c.surface,
          borderWidth: 3,
          hoverOffset: 6,
        }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "68%",
                plugins: {
          legend: legend(c, "bottom"),
          tooltip: {
            ...tooltip,
            callbacks: {
              label: (ctx) => {
                const total = ctx.dataset.data.reduce((sum, v) => sum + v, 0);
                const pct = total ? ((ctx.parsed / total) * 100).toFixed(1) : 0;
                return ` ${ctx.label}: ${ctx.parsed} (${pct}%)`;
              },
            },
          },
        },
      },
    }));

    // 3. Revenue: billed vs collected
    charts.push(new Chart(document.getElementById("revenueChart"), {
      type: "bar",
      data: {
        labels: data.revenue.labels,
        datasets: [
          { label: "Billed", data: data.revenue.billed, backgroundColor: alpha(c.primary2, 0.35), borderRadius: 8, maxBarThickness: 34 },
          { label: "Collected", data: data.revenue.collected, backgroundColor: c.primary, borderRadius: 8, maxBarThickness: 34 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: legend(c),
          tooltip: { ...tooltip, callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toLocaleString()} EGP` } },
        },
        scales: axes(c, { money: true }),
      },
    }));

    // 4. Busiest departments (horizontal bars)
    charts.push(new Chart(document.getElementById("specialtyChart"), {
      type: "bar",
      data: {
        labels: data.specialty.labels,
        datasets: [{
          label: "Appointments",
          data: data.specialty.values,
          backgroundColor: data.specialty.values.map((_, i) => alpha(c.primary, 1 - i * 0.07)),
          borderRadius: 6,
          maxBarThickness: 18,
        }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false }, tooltip },
        scales: axes(c, { horizontal: true }),
      },
    }));

    // 5. Patients by age group (stacked by gender)
    charts.push(new Chart(document.getElementById("ageChart"), {
      type: "bar",
      data: {
        labels: data.ages.labels,
        datasets: [
          { label: "Male", data: data.ages.male, backgroundColor: c.primary2, borderRadius: 6, maxBarThickness: 36 },
          { label: "Female", data: data.ages.female, backgroundColor: alpha(c.danger, 0.75), borderRadius: 6, maxBarThickness: 36 },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: legend(c), tooltip },
        scales: axes(c, { stacked: true }),
      },
    }));
  }

  buildCharts();

  // Rebuild the charts with new colors when dark mode is toggled
  new MutationObserver(buildCharts).observe(document.documentElement, {
    attributes: true,
    attributeFilter: ["data-theme"],
  });
})();