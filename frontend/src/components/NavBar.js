import { useState } from 'react';
import { useAuth } from '../context/AuthContext';
import { useNavigate, useLocation, Link } from 'react-router-dom';

const NAV_ITEMS = [
  { label: 'Dashboard', path: '/' },
  { label: 'Transactions', path: '/transactions' },
  { label: 'Import', path: '/import' },
  { label: 'Budget', path: '/budget' },
  { label: 'Goals', path: '/goals' },
  { label: 'Reports', path: '/reports' },
  { label: 'Categories', path: '/categories' },
  { label: 'Settings', path: '/settings' },
];

export default function NavBar() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);

  const handleLogout = () => {
    logout();
    navigate('/auth/login');
  };

  const initial = user?.name ? user.name.charAt(0).toUpperCase() : 'U';

  return (
    <nav className="top-nav">
      <div className="nav-logo">
        <img src="/MountainFinance.png" alt="Mountain Finance" className="nav-logo-img" />
      </div>
      <button className="nav-hamburger" onClick={() => setMenuOpen(!menuOpen)} aria-label="Menu">
        <span /><span /><span />
      </button>
      <div className={`nav-links${menuOpen ? ' nav-links--open' : ''}`}>
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className={`nav-btn ${location.pathname === item.path ? 'active' : ''}`}
            onClick={() => setMenuOpen(false)}
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
          <button className="profile-dropdown-item" onClick={() => { setDropdownOpen(false); navigate('/settings'); }}>
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
