import { useEffect, useState } from 'react';
import { Line } from 'react-chartjs-2';
import {
  Chart as ChartJS,
  CategoryScale, LinearScale, PointElement, LineElement,
  Title, Tooltip, Legend, Filler,
} from 'chart.js';
import { apiGet } from '../api';

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Title, Tooltip, Legend, Filler);

const FALLBACK = {
  labels: ['Week 1', 'Week 2', 'Week 3', 'Week 4', 'Week 5', 'Week 6', 'Week 7', 'Week 8'],
  income: [3200, 3400, 3100, 3600, 3300, 3500, 3800, 3400],
  outcome: [2100, 2800, 1900, 3200, 2400, 2600, 3100, 2300],
};

export default function FinancialChart() {
  const [finData, setFinData] = useState(FALLBACK);

  useEffect(() => {
    apiGet('/financial-data')
      .then(setFinData)
      .catch(() => setFinData(FALLBACK));
  }, []);

  const latestIncome = finData.income[finData.income.length - 1];
  const latestOutcome = finData.outcome[finData.outcome.length - 1];

  const chartData = {
    labels: finData.labels,
    datasets: [
      {
        label: 'Income', data: finData.income,
        borderColor: '#2ecc71', backgroundColor: 'rgba(46,204,113,0.1)',
        borderWidth: 2.5, tension: 0.3, fill: true, pointRadius: 4, pointHoverRadius: 6,
      },
      {
        label: 'Outcome', data: finData.outcome,
        borderColor: '#e74c3c', backgroundColor: 'rgba(231,76,60,0.1)',
        borderWidth: 2.5, tension: 0.3, fill: true, pointRadius: 4, pointHoverRadius: 6,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { display: true, position: 'top', labels: { usePointStyle: true, padding: 20 } },
      tooltip: {
        mode: 'index', intersect: false,
        callbacks: { label: (ctx) => `${ctx.dataset.label}: $${ctx.parsed.y.toLocaleString()}` },
      },
    },
    scales: {
      y: { beginAtZero: true, ticks: { callback: (v) => '$' + v.toLocaleString() }, grid: { color: 'rgba(0,0,0,0.05)' } },
      x: { grid: { display: false } },
    },
    interaction: { mode: 'nearest', axis: 'x', intersect: false },
  };

  return (
    <div className="graph-panel">
      <div className="weekly-spending">
        <h3>Weekly Spending</h3>
        <div className="spending-amount">${latestOutcome.toLocaleString()}</div>
        <div className="spending-details">
          <div className="detail-item">
            <span className="dot income"></span>
            Income: <strong>${latestIncome.toLocaleString()}</strong>
          </div>
          <div className="detail-item">
            <span className="dot outcome"></span>
            Outcome: <strong>${latestOutcome.toLocaleString()}</strong>
          </div>
        </div>
      </div>
      <h2>Financial Overview</h2>
      <div className="chart-wrapper">
        <Line data={chartData} options={options} />
      </div>
    </div>
  );
}
