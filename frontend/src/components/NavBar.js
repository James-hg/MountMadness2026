import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate, useLocation, Link } from 'react-router-dom';

const NAV_ITEMS = [
  { label: 'Dashboard', path: '/' },
  { label: 'Transactions', path: '/transactions' },
  { label: 'Budget', path: '/budget' },
  { label: 'Reports', path: '/reports' },
  { label: 'Categories', path: '/categories' },
  { label: 'Settings', path: '/settings' },
];

export default function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
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
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={`nav-btn ${location.pathname === item.path ? 'active' : ''}`}
          >
            {item.label}
          </Link>
        ))}
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
