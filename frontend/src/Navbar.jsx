import { useState, useEffect } from 'react';
import { useAuth } from './AuthContext';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import LoginModal from './LoginModal';
import SignupModal from './SignUpModal';
import ForgotPasswordModal from './ForgotPasswordModal';
import './App.css';

const Navbar = () => {
  const [showLogin, setShowLogin] = useState(false);
  const [showSignup, setShowSignup] = useState(false);
  const [showForgotPassword, setShowForgotPassword] = useState(false);

  const { isAuthenticated, user, logout } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  // ✅ Check for showLogin query parameter
  useEffect(() => {
    if (searchParams.get('showLogin') === 'true') {
      setShowLogin(true);
      // Remove the query parameter from URL without adding to history
      const newParams = new URLSearchParams(searchParams);
      newParams.delete('showLogin');
      setSearchParams(newParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  const handleLogout = () => {
    logout();
    navigate('/', { replace: true });
  };

  // Smooth scroll to sections on the same page
  const scrollToSection = (sectionId) => {
    const element = document.getElementById(sectionId);
    if (element) {
      element.scrollIntoView({ behavior: 'smooth' });
    }
  };

  return (
    <>
      <nav className={`navbar flex justify-between bg-blue-50 items-center p-4 ${(showLogin || showSignup || showForgotPassword) ? "blur-sm" : ""}`}>
        <div className="text-3xl font-serif font-bold cursor-pointer" onClick={() => navigate('/')}>
          ReadWithEase
        </div>

        <ul className="nav-links flex gap-6">
         
          <li className="hover:scale-105">
            <Link to="/">Home</Link>
          </li>
          <li className="hover:scale-105">
            <button onClick={() => scrollToSection('features')} className="hover:underline">
              Features
            </button>
          </li>
          <li className="hover:scale-105">
            <button onClick={() => scrollToSection('contact')} className="hover:underline">
              Contact
            </button>
          </li>
        </ul>

        <div className="auth-pill-container flex gap-4">
          {isAuthenticated ? (
            <>
              <span className="text-gray-700 px-4 py-2">
                Welcome, {user?.full_name || user?.email}
              </span>
              <button 
                onClick={handleLogout}
                className="pill-btn bg-red-500 px-6 py-2 rounded-full text-white hover:bg-red-600 transition"
              >
                Logout
              </button>
            </>
          ) : (
            <>
              <button 
                onClick={() => setShowLogin(true)} 
                className="pill-btn bg-white/20 px-6 py-2 rounded-full text-white hover:bg-white/30 transition"
              >
                Login
              </button>
              <button 
                onClick={() => setShowSignup(true)}
                className="pill-btn bg-white px-6 py-2 rounded-full text-black font-semibold"
              >
                Sign Up
              </button>
            </>
          )}
        </div>
      </nav>

      {/* Modals */}
      <LoginModal 
        isOpen={showLogin}
        onClose={() => setShowLogin(false)}
        onSwitchToSignup={() => {
          setShowLogin(false);
          setShowSignup(true);
        }}
        onSwitchToForgotPassword={() => {
          setShowLogin(false);
          setShowForgotPassword(true);
        }}
      />

      <SignupModal 
        isOpen={showSignup}
        onClose={() => setShowSignup(false)}
        onSwitchToLogin={() => {
          setShowSignup(false);
          setShowLogin(true);
        }}
      />

      <ForgotPasswordModal 
        isOpen={showForgotPassword}
        onClose={() => setShowForgotPassword(false)}
        onSwitchToLogin={() => {
          setShowForgotPassword(false);
          setShowLogin(true);
        }}
      />
    </>
  );
};

export default Navbar;