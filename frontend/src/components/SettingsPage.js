import { useState } from 'react';
import NavBar from './NavBar';
import { useAuth } from '../context/AuthContext';
import { apiPatch, apiPost } from '../api';

export default function SettingsPage() {
  const { user, updateUser } = useAuth();

  const [name, setName] = useState(user?.name || '');
  const [email, setEmail] = useState(user?.email || '');
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState('');
  const [profileSuccess, setProfileSuccess] = useState('');

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordError, setPasswordError] = useState('');
  const [passwordSuccess, setPasswordSuccess] = useState('');

  const handleSaveProfile = async (e) => {
    e.preventDefault();
    setProfileError('');
    setProfileSuccess('');

    if (!name.trim()) {
      setProfileError('Name is required.');
      return;
    }

    setProfileLoading(true);
    try {
      const updatedUser = await apiPatch('/auth/me', { name: name.trim(), email });
      updateUser(updatedUser);
      setProfileSuccess('Profile updated successfully.');
    } catch (err) {
      setProfileError(err.message);
    } finally {
      setProfileLoading(false);
    }
  };

  const handleChangePassword = async (e) => {
    e.preventDefault();
    setPasswordError('');
    setPasswordSuccess('');

    if (!currentPassword || !newPassword || !confirmPassword) {
      setPasswordError('Please fill in all password fields.');
      return;
    }

    if (newPassword.length < 8) {
      setPasswordError('New password must be at least 8 characters.');
      return;
    }

    if (newPassword !== confirmPassword) {
      setPasswordError('New passwords do not match.');
      return;
    }

    setPasswordLoading(true);
    try {
      await apiPost('/auth/change-password', {
        current_password: currentPassword,
        new_password: newPassword,
      });
      setPasswordSuccess('Password updated successfully.');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err) {
      setPasswordError(err.message);
    } finally {
      setPasswordLoading(false);
    }
  };

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
          {profileError && <div className="auth-error" style={{ marginBottom: 12 }}>{profileError}</div>}
          {profileSuccess && <div className="settings-success" style={{ marginBottom: 12 }}>{profileSuccess}</div>}
          <form className="page-form" onSubmit={handleSaveProfile}>
            <div className="form-row">
              <div className="form-group">
                <label>Name</label>
                <input type="text" value={name} onChange={(e) => setName(e.target.value)} />
              </div>
              <div className="form-group">
                <label>Email</label>
                <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} />
              </div>
            </div>
            <button className="primary-btn" style={{ maxWidth: 200 }} type="submit" disabled={profileLoading}>
              {profileLoading ? 'Saving...' : 'Save Changes'}
            </button>
          </form>
        </div>

        {/* Change Password Section */}
        <div className="card">
          <h2 className="card-title">Change Password</h2>
          {passwordError && <div className="auth-error" style={{ marginBottom: 12 }}>{passwordError}</div>}
          {passwordSuccess && <div className="settings-success" style={{ marginBottom: 12 }}>{passwordSuccess}</div>}
          <form className="page-form" onSubmit={handleChangePassword}>
            <div className="form-group" style={{ maxWidth: 400 }}>
              <label>Current Password</label>
              <input type="password" placeholder="Enter current password" value={currentPassword} onChange={(e) => setCurrentPassword(e.target.value)} />
            </div>
            <div className="form-group" style={{ maxWidth: 400 }}>
              <label>New Password</label>
              <input type="password" placeholder="Enter new password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
            </div>
            <div className="form-group" style={{ maxWidth: 400 }}>
              <label>Confirm New Password</label>
              <input type="password" placeholder="Confirm new password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
            </div>
            <button className="primary-btn" style={{ maxWidth: 200 }} type="submit" disabled={passwordLoading}>
              {passwordLoading ? 'Updating...' : 'Update Password'}
            </button>
          </form>
        </div>
      </div>
    </>
  );
}
