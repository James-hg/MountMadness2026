import { useState } from 'react';
import NavBar from './NavBar';

export default function TransactionsPage() {
  const [showForm, setShowForm] = useState(false);

  return (
    <>
      <NavBar />
      <div className="page-container">
        <div className="page-header">
          <h1 className="page-title">Transactions</h1>
          <button className="primary-btn" onClick={() => setShowForm(!showForm)}>
            {showForm ? 'Cancel' : '+ Add Transaction'}
          </button>
        </div>

        {showForm && (
          <div className="card">
            <h2 className="card-title">New Transaction</h2>
            <form className="page-form" onSubmit={(e) => e.preventDefault()}>
              <div className="form-row">
                <div className="form-group">
                  <label>Type</label>
                  <select className="form-select" disabled>
                    <option>Expense</option>
                    <option>Income</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Amount</label>
                  <input type="number" placeholder="0.00" disabled />
                </div>
                <div className="form-group">
                  <label>Date</label>
                  <input type="date" disabled />
                </div>
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label>Category</label>
                  <select className="form-select" disabled>
                    <option value="">Select category...</option>
                    <option>Food</option>
                    <option>Housing/Rent</option>
                    <option>Transport</option>
                    <option>Insurance</option>
                    <option>Tuition</option>
                    <option>Bills/Utilities</option>
                    <option>Shopping</option>
                    <option>Entertainment</option>
                    <option>Health</option>
                    <option>Other</option>
                  </select>
                </div>
                <div className="form-group" style={{ flex: 2 }}>
                  <label>Note</label>
                  <input type="text" placeholder="Optional note..." disabled />
                </div>
              </div>
              <button className="primary-btn" disabled>Save Transaction</button>
            </form>
          </div>
        )}

        {/* Filters */}
        <div className="card">
          <div className="filter-row">
            <div className="filter-item">
              <label>Date Range</label>
              <select className="form-select" disabled>
                <option>This Month</option>
                <option>Last Month</option>
                <option>Last 3 Months</option>
                <option>All Time</option>
              </select>
            </div>
            <div className="filter-item">
              <label>Category</label>
              <select className="form-select" disabled>
                <option>All Categories</option>
              </select>
            </div>
            <div className="filter-item">
              <label>Type</label>
              <select className="form-select" disabled>
                <option>All</option>
                <option>Expense</option>
                <option>Income</option>
              </select>
            </div>
          </div>
        </div>

        {/* Transaction List – Empty State */}
        <div className="card">
          <div className="empty-state">
            <div className="empty-state-icon">📋</div>
            <h3>No transactions yet</h3>
            <p>Add your first transaction to start tracking your spending.</p>
          </div>
        </div>
      </div>
    </>
  );
}
