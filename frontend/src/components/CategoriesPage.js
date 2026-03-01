import NavBar from './NavBar';

const EXPENSE_CATEGORIES = [
  { name: 'Food', icon: '🍔' },
  { name: 'Housing/Rent', icon: '🏠' },
  { name: 'Transport', icon: '🚌' },
  { name: 'Insurance', icon: '🛡️' },
  { name: 'Tuition', icon: '🎓' },
  { name: 'Bills/Utilities', icon: '💡' },
  { name: 'Shopping', icon: '🛒' },
  { name: 'Entertainment', icon: '🎮' },
  { name: 'Health', icon: '🏥' },
  { name: 'Other', icon: '📦' },
];

const INCOME_CATEGORIES = [
  { name: 'Allowance/Transfer', icon: '💸' },
  { name: 'Part-time Job', icon: '💼' },
  { name: 'Scholarship', icon: '🎓' },
  { name: 'Refund', icon: '🔄' },
  { name: 'Other Income', icon: '💵' },
];

export default function CategoriesPage() {
  return (
    <>
      <NavBar />
      <div className="page-container">
        <div className="page-header">
          <h1 className="page-title">Categories</h1>
        </div>

        {/* Expense Categories */}
        <div className="card">
          <div className="card-title-row">
            <h2 className="card-title">Expense Categories</h2>
            <button className="secondary-btn" disabled>+ Add</button>
          </div>
          <div className="category-list">
            {EXPENSE_CATEGORIES.map((cat) => (
              <div key={cat.name} className="category-row">
                <span className="category-icon">{cat.icon}</span>
                <span className="category-name">{cat.name}</span>
                <span className="category-badge">System</span>
                <div className="category-actions">
                  <button className="icon-btn" disabled title="Edit">✏️</button>
                  <button className="icon-btn" disabled title="Delete">🗑️</button>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Income Categories */}
        <div className="card">
          <div className="card-title-row">
            <h2 className="card-title">Income Categories</h2>
            <button className="secondary-btn" disabled>+ Add</button>
          </div>
          <div className="category-list">
            {INCOME_CATEGORIES.map((cat) => (
              <div key={cat.name} className="category-row">
                <span className="category-icon">{cat.icon}</span>
                <span className="category-name">{cat.name}</span>
                <span className="category-badge">System</span>
                <div className="category-actions">
                  <button className="icon-btn" disabled title="Edit">✏️</button>
                  <button className="icon-btn" disabled title="Delete">🗑️</button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </>
  );
}
