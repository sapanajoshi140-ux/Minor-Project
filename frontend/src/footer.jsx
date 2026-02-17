import { useState, useEffect } from 'react';
import { useAuth } from './AuthContext';
import { useNavigate, useSearchParams } from 'react-router-dom';
import LoginModal from './LoginModal';
import SignupModal from './SignUpModal';
import ForgotPasswordModal from './ForgotPasswordModal';
import './App.css';

const Login = ({ img }) => {
  const [showLogin, setShowLogin] = useState(false);
  const [showSignup, setShowSignup] = useState(true);
  const [showForgotPasswordOverlay, setShowForgotPasswordOverlay] = useState(false);

  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();

  useEffect(() => {
    if (searchParams.get('showLogin') === 'true') {
      setShowLogin(true);
      setShowSignup(false);
      const newParams = new URLSearchParams(searchParams);
      newParams.delete('showLogin');
      setSearchParams(newParams, { replace: true });
    }
  }, [searchParams, setSearchParams]);

  useEffect(() => {
    if (isAuthenticated) {
      navigate("/dashboard");
    }
  }, [isAuthenticated, navigate]);

  const handleOpenForgotPassword = () => {
    setShowForgotPasswordOverlay(true);
  };

  const handleCloseForgotPassword = () => {
    setShowForgotPasswordOverlay(false);
  };

  return (
    <div
      className="w-full min-h-screen flex items-center justify-between px-16 relative"
      style={{
        backgroundImage: `linear-gradient(rgba(0,0,0,0.3), rgba(0,0,0,0.3)), url(${img})`,
        backgroundSize: "cover",
        backgroundPosition: "center",
      }}
    >
      {/* Left side - Heading */}
      <div className="flex-1">
        <h1 className="font-bold text-6xl lg:text-7xl font-serif leading-tight text-black">
          {showLogin ? 'Welcome back!' : (
            <>
              Sign up to
              <br />
              Get Started
            </>
          )}
        </h1>
      </div>

      {/* Right side - Glassmorphism Card with Inline Forms */}
      <div className="w-full max-w-md rounded-[2rem] text-white backdrop-blur-md relative">
        
        {/* Inline Signup Form - hideCloseButton prop added */}
        {showSignup && (
          <SignupModal 
            isOpen={true}
            onClose={() => {}} 
            hideCloseButton={true}  // Hide X button
            onSwitchToLogin={() => {
              setShowSignup(false);
              setShowLogin(true);
            }}
          />
        )}

        {/* Inline Login Form - hideCloseButton prop added */}
        {showLogin && (
          <LoginModal 
            isOpen={true}
            onClose={() => {}} 
            hideCloseButton={true}  // Hide X button
            onSwitchToSignup={() => {
              setShowLogin(false);
              setShowSignup(true);
            }}
            onSwitchToForgotPassword={handleOpenForgotPassword}
          />
        )}
      </div>

      {/* Forgot Password Overlay Modal - keep X button for overlay */}
      <ForgotPasswordModal 
        isOpen={showForgotPasswordOverlay}
        onClose={handleCloseForgotPassword}
        onSwitchToLogin={() => {
          handleCloseForgotPassword();
          setShowSignup(false);
          setShowLogin(true);
        }}
      />
    </div>
  );
};

const Footer = () => {
  return (
    <div className="overflow-hidden" id="footer-section">
      <Login img="footer.jpg" />
    </div>
  );
};

export default Footer;