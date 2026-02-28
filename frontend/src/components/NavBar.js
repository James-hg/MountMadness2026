import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate } from 'react-router-dom';

export default function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [dropdownOpen, setDropdownOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/auth/login');
  };

  const initial = user?.name ? user.name.charAt(0).toUpperCase() : 'U';

  return (
    <nav className="top-nav">
      <div className="nav-logo"></div>
      <div className="nav-links">
        <button className="nav-btn active">Dashboard</button>
        <button className="nav-btn">Transactions</button>
        <button className="nav-btn">Budget</button>
        <button className="nav-btn">Reports</button>
        <button className="nav-btn">Settings</button>
      </div>
      <div className="nav-profile">
        <button className="profile-btn" onClick={() => setDropdownOpen(!dropdownOpen)}>
          {initial}
        </button>
        <div className={`profile-dropdown ${dropdownOpen ? 'open' : ''}`}>
          <button className="profile-dropdown-item" disabled>
            {user?.name || 'User'}
          </button>
          <button className="profile-dropdown-item logout" onClick={handleLogout}>
            Log Out
          </button>
        </div>
      </div>
    </nav>
  );
}
