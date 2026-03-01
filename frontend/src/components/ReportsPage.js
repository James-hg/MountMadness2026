import NavBar from './NavBar';

export default function ReportsPage() {
  return (
    <>
      <NavBar />
      <div className="page-container">
        <div className="page-header">
          <h1 className="page-title">Reports &amp; Insights</h1>
        </div>

        {/* Summary Cards */}
        <div className="summary-cards">
          <div className="summary-card">
            <span className="summary-label">Current Balance</span>
            <span className="summary-value">&mdash;</span>
            <span className="summary-sub">Total income − expenses</span>
          </div>
          <div className="summary-card">
            <span className="summary-label">Monthly Spend</span>
            <span className="summary-value">&mdash;</span>
            <span className="summary-sub">This month's total</span>
          </div>
          <div className="summary-card">
            <span className="summary-label">Burn Rate</span>
            <span className="summary-value">&mdash;</span>
            <span className="summary-sub">Avg daily spending</span>
          </div>
          <div className="summary-card accent">
            <span className="summary-label">Runway</span>
            <span className="summary-value">&mdash;</span>
            <span className="summary-sub">Days your money lasts</span>
          </div>
        </div>

        {/* Top Categories */}
        <div className="card">
          <h2 className="card-title">Top Spending Categories</h2>
          <div className="empty-state">
            <div className="empty-state-icon">📊</div>
            <h3>No data yet</h3>
            <p>Add transactions to see your top spending categories here.</p>
          </div>
        </div>

        {/* Spending Trend Chart Placeholder */}
        <div className="card">
          <h2 className="card-title">Spending Trends</h2>
          <div className="empty-state">
            <div className="empty-state-icon">📈</div>
            <h3>Chart coming soon</h3>
            <p>Spending trends over time will appear here once you have transaction data.</p>
          </div>
        </div>
      </div>
    </>
  );
}
