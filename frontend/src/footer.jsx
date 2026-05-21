import { useState, useEffect } from 'react';
import { useAuth } from './AuthContext';
import { useNavigate, useSearchParams } from 'react-router-dom';
import LoginModal from './LoginModal';
import SignupModal from './SignUpModal';
import ForgotPasswordModal from './ForgotPasswordModal';
import {  FaInstagram, FaLinkedinIn, FaGithub } from 'react-icons/fa6';
import { SiGmail } from 'react-icons/si';
import './App.css';

/* ── Login section ─────────────────────────────────────────────── */
const Login = ({ img }) => {
  const [showLogin, setShowLogin]   = useState(false);
  const [showSignup, setShowSignup] = useState(true);
  const [showForgot, setShowForgot] = useState(false);

  const { isAuthenticated } = useAuth();
  const navigate            = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  useEffect(() => {
    if (searchParams.get('showLogin') === 'true') {
      setShowLogin(true);
      setShowSignup(false);
      const p = new URLSearchParams(searchParams);
      p.delete('showLogin');
      setSearchParams(p, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (isAuthenticated) navigate('/dashboard');
  }, [isAuthenticated, navigate]);

  return (
    <div
      className="w-full min-h-screen flex items-center justify-between px-16 relative"
      style={{
        backgroundImage: `linear-gradient(rgba(22,20,18,0.92),rgba(22,20,18,0.88)),url(${img})`,
        backgroundSize: 'cover',
        backgroundPosition: 'center',
      }}
    >
      <div className="flex-1">
        <h1 className="font-bold text-6xl lg:text-7xl font-serif leading-tight text-amber-100">
          {showLogin ? 'Welcome back!' : (<>Sign up to<br />Get Started</>)}
        </h1>
      </div>

      <div className="w-full max-w-md rounded-[2rem] text-white backdrop-blur-md relative">
        {showSignup && (
          <SignupModal
            isOpen={true} onClose={() => {}} hideCloseButton={true}
            onSwitchToLogin={() => { setShowSignup(false); setShowLogin(true); }}
          />
        )}
        {showLogin && (
          <LoginModal
            isOpen={true} onClose={() => {}} hideCloseButton={true}
            onSwitchToSignup={() => { setShowLogin(false); setShowSignup(true); }}
            onSwitchToForgotPassword={() => setShowForgot(true)}
          />
        )}
      </div>

      <ForgotPasswordModal
        isOpen={showForgot}
        onClose={() => setShowForgot(false)}
        onSwitchToLogin={() => {
          setShowForgot(false);
          setShowSignup(false);
          setShowLogin(true);
        }}
      />
    </div>
  );
};

/* ── Book icon ─────────────────────────────────────────────────── */
const BookIcon = () => (
  <div className="w-9 h-9 border border-[#c8a455] rounded-lg flex items-center justify-center shrink-0">
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none"
      stroke="#c8a455" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"/>
      <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z"/>
      <line x1="9" y1="7" x2="15" y2="7"/>
      <line x1="9" y1="11" x2="13" y2="11"/>
    </svg>
  </div>
);

/* ── Nav column ────────────────────────────────────────────────── */
const NavCol = ({ title, links }) => (
  <div className="min-w-[120px]">
    <p className="text-[10.5px] font-bold tracking-[0.13em] uppercase text-[#c8a455] mb-4 font-serif">
      {title}
    </p>
    <ul className="flex flex-col gap-3 list-none p-0 m-0">
      {links.map((link) => (
        <li key={link}>
          <a
            href="#"
            className="text-[13.5px] italic text-white/80 no-underline font-serif
                       transition-colors duration-150 hover:text-white/90"
          >
            {link}
          </a>
        </li>
      ))}
    </ul>
  </div>
);

/* ── Social icon button ────────────────────────────────────────── */
const SocialBtn = ({ label, icon: Icon }) => (
  <a
    href="#"
    aria-label={label}
    className="w-[33px] h-[33px] border border-white/[0.13] rounded-md
               flex items-center justify-center text-white/40 no-underline
               transition-all duration-200 hover:border-[#c8a455] hover:text-[#c8a455]"
  >
    <Icon size={14} />
  </a>
);

/* ── Minimal footer ────────────────────────────────────────────── */
const MinimalFooter = () => {
  const navData = [
    { title: 'Product', links: ['Features', 'How It Works'] },
    { title: 'Company', links: ['About', 'Blog', 'Contact'] },
    { title: 'Legal',   links: ['Privacy Policy', 'Terms of Service'] },
  ];

  const socials = [
    { label: 'Gmail',       icon:SiGmail  },
    { label: 'Instagram',   icon: FaInstagram  },
    { label: 'LinkedIn',    icon: FaLinkedinIn },
    { label: 'GitHub',      icon: FaGithub     },
  ];

  return (
    <footer className="bg-[#181818] border-t border-white/[0.08] font-serif">

      {/* Top grid */}
      <div className="max-w-[1080px] mx-auto px-9 pt-12 pb-12 flex flex-wrap gap-14 items-start">

        {/* Brand column */}
        <div className="flex-1 min-w-[200px] max-w-[230px]">

          {/* Logo */}
          <div className="flex items-center gap-2.5 mb-4">
            <BookIcon />
            <span className="text-[17px] font-bold text-white tracking-tight font-serif">
              Read<span className="text-[#c8a455]">With</span>Ease
            </span>
          </div>

          
        </div>

        {/* Nav columns */}
        <div className="flex gap-12 flex-wrap flex-[2_1_380px] pt-1">
          {navData.map((col) => (
            <NavCol key={col.title} {...col} />
          ))}
        </div>
      </div>

      {/* Divider */}
      <div className="max-w-[1080px] mx-auto px-9">
        <div className="h-px bg-white/[0.08]" />
      </div>

      {/* Bottom bar */}
      <div className="max-w-[1080px] mx-auto px-9 pt-[18px] pb-7
                      flex items-center justify-between flex-wrap gap-3">
        <p className="text-[12.5px] italic text-white/40 m-0">
          © {new Date().getFullYear()}{' '}
          <a href="#" className="text-[#c8a455] no-underline hover:text-[#e0bb77] transition-colors duration-150">
            ReadWithEase
          </a>
          . All rights reserved.
        </p>

        <div className="flex gap-2">
          {socials.map((s) => (
            <SocialBtn key={s.label} label={s.label} icon={s.icon} />
          ))}
        </div>
      </div>

    </footer>
  );
};

/* ── Page-level Footer export ──────────────────────────────────── */
const Footer = () => (
  <div className="overflow-hidden" id="footer-section">
    <Login img="footer.jpg" />
    <MinimalFooter />
  </div>
);

export default Footer;