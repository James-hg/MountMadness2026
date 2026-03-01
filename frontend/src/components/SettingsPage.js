import NavBar from './NavBar';
import { useAuth } from '../context/AuthContext';

export default function SettingsPage() {
  const { user } = useAuth();

  return (
    <>
      <NavBar />
      <div className="page-container">
        <div className="page-header">
          <h1 className="page-title">Settings</h1>
        </div>

        {/* Profile Section */}
        <div className="card">
          <h2 className="card-title">Profile</h2>
          <form className="page-form" onSubmit={(e) => e.preventDefault()}>
            <div className="form-row">
              <div className="form-group">
                <label>Name</label>
                <input type="text" value={user?.name || ''} disabled />
              </div>
              <div className="form-group">
                <label>Email</label>
                <input type="email" value={user?.email || ''} disabled />
              </div>
            </div>
          </form>
        </div>

        {/* Currency Section */}
        <div className="card">
          <h2 className="card-title">Currency</h2>
          <form className="page-form" onSubmit={(e) => e.preventDefault()}>
            <div className="form-group" style={{ maxWidth: 280 }}>
              <label>Default Currency</label>
              <select className="form-select" disabled>
                <option value="CAD">🇨🇦 CAD – Canadian Dollar</option>
                <option value="USD">🇺🇸 USD – US Dollar</option>
                <option value="KRW">🇰🇷 KRW – Korean Won</option>
                <option value="INR">🇮🇳 INR – Indian Rupee</option>
                <option value="CNY">🇨🇳 CNY – Chinese Yuan</option>
                <option value="EUR">🇪🇺 EUR – Euro</option>
                <option value="GBP">🇬🇧 GBP – British Pound</option>
              </select>
            </div>
          </form>
        </div>

        {/* Change Password Section */}
        <div className="card">
          <h2 className="card-title">Change Password</h2>
          <form className="page-form" onSubmit={(e) => e.preventDefault()}>
            <div className="form-group" style={{ maxWidth: 400 }}>
              <label>Current Password</label>
              <input type="password" placeholder="Enter current password" disabled />
            </div>
            <div className="form-group" style={{ maxWidth: 400 }}>
              <label>New Password</label>
              <input type="password" placeholder="Enter new password" disabled />
            </div>
            <div className="form-group" style={{ maxWidth: 400 }}>
              <label>Confirm New Password</label>
              <input type="password" placeholder="Confirm new password" disabled />
            </div>
            <button className="primary-btn" style={{ maxWidth: 200 }} disabled>
              Update Password
            </button>
          </form>
        </div>

        {/* Save */}
        <div style={{ display: 'flex', justifyContent: 'flex-end', marginTop: 8 }}>
          <button className="primary-btn" style={{ maxWidth: 200 }} disabled>
            Save Changes
          </button>
        </div>
      </div>
    </>
  );
}
