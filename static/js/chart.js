document.addEventListener("DOMContentLoaded", async () => {
    const ctx = document.getElementById("financialChart").getContext("2d");

    // Fetch mock data from API (will be replaced by real backend)
    let labels, income, outcome;
    try {
        const res = await fetch("/api/financial-data");
        const data = await res.json();
        labels = data.labels;
        income = data.income;
        outcome = data.outcome;
    } catch {
        // Fallback data if API not available
        labels = ["Week 1", "Week 2", "Week 3", "Week 4", "Week 5", "Week 6", "Week 7", "Week 8"];
        income = [3200, 3400, 3100, 3600, 3300, 3500, 3800, 3400];
        outcome = [2100, 2800, 1900, 3200, 2400, 2600, 3100, 2300];
    }

    new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "Income",
                    data: income,
                    borderColor: "#2ecc71",
                    backgroundColor: "rgba(46, 204, 113, 0.1)",
                    borderWidth: 2.5,
                    tension: 0.3,
                    fill: true,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                },
                {
                    label: "Outcome",
                    data: outcome,
                    borderColor: "#e74c3c",
                    backgroundColor: "rgba(231, 76, 60, 0.1)",
                    borderWidth: 2.5,
                    tension: 0.3,
                    fill: true,
                    pointRadius: 4,
                    pointHoverRadius: 6,
                },
            ],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: "top",
                    labels: {
                        usePointStyle: true,
                        padding: 20,
                    },
                },
                tooltip: {
                    mode: "index",
                    intersect: false,
                    callbacks: {
                        label: function (context) {
                            return context.dataset.label + ": $" + context.parsed.y.toLocaleString();
                        },
                    },
                },
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: {
                        callback: function (value) {
                            return "$" + value.toLocaleString();
                        },
                    },
                    grid: {
                        color: "rgba(0,0,0,0.05)",
                    },
                },
                x: {
                    grid: {
                        display: false,
                    },
                },
            },
            interaction: {
                mode: "nearest",
                axis: "x",
                intersect: false,
            },
        },
    });

    // Update weekly spending summary
    const latestOutcome = outcome[outcome.length - 1];
    const latestIncome = income[income.length - 1];
    document.getElementById("spendingAmount").textContent = "$" + latestOutcome.toLocaleString();
    document.getElementById("incomeValue").textContent = "$" + latestIncome.toLocaleString();
    document.getElementById("outcomeValue").textContent = "$" + latestOutcome.toLocaleString();
});
