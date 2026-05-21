import { useState, useEffect } from 'react';
import { useAuth } from './AuthContext';
import { useNavigate, useSearchParams, Link } from 'react-router-dom';
import LoginModal from './LoginModal';
import SignupModal from './SignUpModal';
import ForgotPasswordModal from './ForgotPasswordModal';

const BrandIcon = () => (
  <svg width="18" height="18" viewBox="0 0 20 20" fill="none" xmlns="http://www.w3.org/2000/svg">
    <rect x="3" y="2" width="11" height="14" rx="1.5" stroke="#C9A84C" strokeWidth="1.2"/>
    <path d="M6 6h5M6 9h5M6 12h3" stroke="#C9A84C" strokeWidth="1.1" strokeLinecap="round"/>
    <path d="M14 5v12l2-1.5 2 1.5V5" stroke="#C9A84C" strokeWidth="1.1" strokeLinecap="round" strokeLinejoin="round"/>
  </svg>
);

const Navbar = () => {
  const [showLogin, setShowLogin] = useState(false);
  const [showSignup, setShowSignup] = useState(false);
  const [showForgotPassword, setShowForgotPassword] = useState(false);
  const [scrolled, setScrolled] = useState(false);

  const { isAuthenticated, user, logout } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  useEffect(() => {
    if (searchParams.get('showLogin') === 'true') {
      setShowLogin(true);
      const newParams = new URLSearchParams(searchParams);
      newParams.delete('showLogin');
      setSearchParams(newParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 50);
    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const handleLogout = () => {
    logout();
    navigate('/', { replace: true });
  };

  const scrollToSection = (sectionId) => {
    const element = document.getElementById(sectionId);
    if (element) element.scrollIntoView({ behavior: 'smooth' });
  };

  const modalOpen = showLogin || showSignup || showForgotPassword;

  
  const navLinkBase = "font-['Inter'] text-[15px] font-medium text-[rgba(245,240,232,0.75)] bg-transparent border-none cursor-pointer px-4 py-2 rounded-lg transition-colors duration-200 relative hover:text-white hover:bg-white/5";

  return (
    <>
      {/* Add Inter font */}
      <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet" />

      <nav 
        className={`
          sticky top-0 z-[1000] w-full h-[68px] flex items-center justify-between px-8
          transition-all duration-300
          ${scrolled 
            ? 'bg-[rgba(13,13,13,0.55)] backdrop-blur-[20px] saturate-[1.4] border-b-[0.5px] border-[rgba(201,168,76,0.25)] shadow-[0_1px_32px_rgba(0,0,0,0.45),inset_0_0.5px_0_rgba(201,168,76,0.15)]' 
            : 'bg-transparent border-b-[0.5px] border-[rgba(201,168,76,0.15)]'
          }
          ${modalOpen ? 'blur-[4px] pointer-events-none' : ''}
        `}
      >
        {/* Brand */}
        <div 
          className="flex items-center gap-2.5 cursor-pointer no-underline shrink-0 group"
          onClick={() => navigate('/')}
        >
          <div className="w-9 h-9 border border-[rgba(201,168,76,0.25)] rounded-lg bg-[rgba(201,168,76,0.07)] flex items-center justify-center transition-all duration-200 group-hover:bg-[rgba(201,168,76,0.14)] group-hover:border-[#C9A84C]">
            <BrandIcon />
          </div>
          <span className="font-['Inter'] text-[22px] font-bold text-[#F5F0E8] tracking-[-0.01em] whitespace-nowrap">
            Read<span className="text-[#C9A84C]">With</span>Ease
          </span>
        </div>

        {/* Nav Links */}
        <ul className="flex items-center gap-1 list-none m-0 p-0">
          <li>
            <Link to="/" className={navLinkBase}>About</Link>
          </li>
          <li>
            <button className={navLinkBase} onClick={() => scrollToSection('features')}>Features</button>
          </li>
          <li>
            <button className={navLinkBase} onClick={() => scrollToSection('contact')}>Contact</button>
          </li>
        </ul>

        {/* Auth */}
        <div className="flex items-center gap-3">
          {isAuthenticated ? (
            <>
              <span className="font-['Inter'] text-sm font-medium text-[rgba(245,240,232,0.55)] px-1">
                Welcome, {user?.full_name || user?.email}
              </span>
              <button 
                className="font-['Inter'] text-sm font-medium text-[rgba(220,80,80,0.85)] bg-transparent border-[0.5px] border-[rgba(220,80,80,0.3)] rounded-full px-5 py-2 cursor-pointer transition-all duration-200 hover:text-[#e05555] hover:border-[rgba(220,80,80,0.7)] hover:bg-[rgba(220,80,80,0.07)]"
                onClick={handleLogout}
              >
                Logout
              </button>
            </>
          ) : (
            <>
              <button 
                className="font-['Inter'] text-sm font-medium text-[rgba(245,240,232,0.75)] bg-transparent border-[0.5px] border-[rgba(201,168,76,0.25)] rounded-full px-5 py-2 cursor-pointer transition-all duration-200 hover:text-white hover:border-[#C9A84C] hover:bg-[rgba(201,168,76,0.06)]"
                onClick={() => setShowLogin(true)}
              >
                Login
              </button>
              <button 
                className="font-['Inter'] text-sm font-semibold text-[#0D0D0D] bg-[#C9A84C] border-none rounded-full px-5 py-2 cursor-pointer transition-all duration-200 hover:bg-[#E8C96A] hover:-translate-y-px"
                onClick={() => setShowSignup(true)}
              >
                Sign Up
              </button>
            </>
          )}
        </div>
      </nav>

      {/* Modals */}
      <LoginModal isOpen={showLogin} onClose={() => setShowLogin(false)} onSwitchToSignup={() => { setShowLogin(false); setShowSignup(true); }} onSwitchToForgotPassword={() => { setShowLogin(false); setShowForgotPassword(true); }} />
      <SignupModal isOpen={showSignup} onClose={() => setShowSignup(false)} onSwitchToLogin={() => { setShowSignup(false); setShowLogin(true); }} />
      <ForgotPasswordModal isOpen={showForgotPassword} onClose={() => setShowForgotPassword(false)} onSwitchToLogin={() => { setShowForgotPassword(false); setShowLogin(true); }} />
    </>
  );
};

export default Navbar;