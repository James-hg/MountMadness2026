import { useState } from 'react';
import NavBar from './NavBar';

const SAMPLE_CATEGORIES = [
  'Food',
  'Housing/Rent',
  'Transport',
  'Insurance',
  'Tuition',
  'Bills/Utilities',
  'Shopping',
  'Entertainment',
  'Health',
  'Other',
];

export default function BudgetPage() {
  const [showForm, setShowForm] = useState(false);

  return (
    <>
      <NavBar />
      <div className="page-container">
        <div className="page-header">
          <h1 className="page-title">Budget</h1>
          <button className="primary-btn" onClick={() => setShowForm(!showForm)}>
            {showForm ? 'Cancel' : '+ Add Budget'}
          </button>
        </div>

        {showForm && (
          <div className="card">
            <h2 className="card-title">New Budget</h2>
            <form className="page-form" onSubmit={(e) => e.preventDefault()}>
              <div className="form-row">
                <div className="form-group">
                  <label>Category</label>
                  <select className="form-select" disabled>
                    <option value="">Select category...</option>
                    {SAMPLE_CATEGORIES.map((cat) => (
                      <option key={cat}>{cat}</option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>Monthly Limit (CAD)</label>
                  <input type="number" placeholder="0.00" disabled />
                </div>
              </div>
              <button className="primary-btn" disabled>Save Budget</button>
            </form>
          </div>
        )}

        {/* Budget Items – Example Shell */}
        <div className="card">
          <h2 className="card-title">Monthly Budgets</h2>
          <div className="budget-list">
            {/* Example disabled budget item to show structure */}
            <div className="budget-item">
              <div className="budget-item-header">
                <span className="budget-category">Food</span>
                <span className="budget-amounts">$0 / $0</span>
              </div>
              <div className="progress-bar">
                <div className="progress-fill" style={{ width: '0%' }}></div>
              </div>
              <span className="budget-percent">0% used</span>
            </div>
          </div>

          <div className="empty-state" style={{ marginTop: 16 }}>
            <div className="empty-state-icon">💰</div>
            <h3>No budgets set yet</h3>
            <p>Create a budget to track your spending limits by category.</p>
          </div>
        </div>
      </div>
    </>
  );
}
