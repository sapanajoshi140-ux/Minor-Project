
import { useState, useEffect, useRef } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { motion } from "framer-motion";
import { useAuth } from './AuthContext';
import LoginModal from './LoginModal';
import SignupModal from './SignUpModal';
import ForgotPasswordModal from './ForgotPasswordModal';

const Feature = () => {
  const [showLogin, setShowLogin] = useState(false);
  const [showSignup, setShowSignup] = useState(false);
  const [showForgotPassword, setShowForgotPassword] = useState(false);
  
  const [searchParams, setSearchParams] = useSearchParams();
  const navigate = useNavigate();
  const { isAuthenticated, loading } = useAuth();
  
  //  Ref to track if we've already processed URL params
  const processedParams = useRef(false);

  // Redirect authenticated users to dashboard immediately
  useEffect(() => {
    if (!loading && isAuthenticated) {
      navigate('/dashboard', { replace: true });
    }
  }, [isAuthenticated, loading, navigate]);

  //  Handle URL parameters (for email verification, password reset redirect, etc.)
  useEffect(() => {
    if (loading) return;
    
    // Only process URL params once to avoid re-opening modals
    if (processedParams.current) return;
    
    const shouldShowLogin = searchParams.get('showLogin') === 'true';
    const shouldShowSignup = searchParams.get('showSignup') === 'true';
    const shouldShowForgotPassword = searchParams.get('showForgotPassword') === 'true';
    
    if (shouldShowLogin || shouldShowSignup || shouldShowForgotPassword) {
      processedParams.current = true;
      
      if (shouldShowLogin) {
        setShowLogin(true);
      } else if (shouldShowSignup) {
        setShowSignup(true);
      } else if (shouldShowForgotPassword) {
        setShowForgotPassword(true);
      }
      
      // Clean up URL immediately after opening modal
      const params = new URLSearchParams(searchParams);
      params.delete('showLogin');
      params.delete('showSignup');
      params.delete('showForgotPassword');
      // Keep 'verified' param temporarily for LoginModal to read
      if (!shouldShowLogin) {
        params.delete('verified');
      }
      setSearchParams(params, { replace: true });
    }
  }, [searchParams, setSearchParams, loading]);

  const features = [
    {
      title: "Upload Documents",
      desc: "Upload the documents and read in clean and distraction-free environment",
      img: "upload.png",
      bgColor: "bg-[#F2F2F2]",
      button: "Upload",
      action: "signup",
      reverse: true,
    },
    {
      title: "Reading Mode Interface",
      desc: "Tap or click on the word to view meaning and pronunciation or select sentence for text to speech feature",
      img: "word.png",
      button: "Try Now",
      action: "signup",
      bgColor: "bg-[#F2F2F2]",
    },
    {
      title: "AI Assistant",
      desc: "Query AI about any topics in your document and summarise your content for quick revision",
      img: "summarize.png",
      bgColor: "bg-[#F2F2F2]",
      button: "Ask AI",
      action: "signup",
      reverse: true,
    },
  ];

  const handleFeatureClick = (action) => {
    if (action === 'signup') {
      setShowSignup(true);
    } else if (action === 'login') {
      setShowLogin(true);
    }
  };

  // Simplified modal close handlers - just close the modal
  const handleCloseLogin = () => {
    setShowLogin(false);
    // Clean up any remaining URL params
    const params = new URLSearchParams(searchParams);
    params.delete('verified');
    if (params.toString() !== searchParams.toString()) {
      setSearchParams(params, { replace: true });
    }
  };

  const handleCloseSignup = () => {
    setShowSignup(false);
  };

  const handleCloseForgotPassword = () => {
    setShowForgotPassword(false);
  };

  const featureVariants = {
    hidden: { opacity: 0, y: 50 },
    visible: { 
      opacity: 1, 
      y: 0, 
      transition: { duration: 1.3 } 
    },
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-[#F1EADA]">
        <div className="text-center">
          <div className="w-16 h-16 border-4 border-gray-900/20 border-t-gray-900 rounded-full animate-spin mx-auto"></div>
          <p className="text-gray-900 mt-4 font-medium">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <section className="bg-[#F1EADA] w-full py-24 min-h-screen">
      <div className="max-w-6xl mx-auto px-6">

        <div className="max-w-4xl mx-auto px-6">
          {/* Hero Section */}
          <div className="text-center mb-20">
            <h1 className="text-5xl md:text-6xl font-bold font-serif text-black mb-4 leading-tight tracking-tight">
              Elevate Your Learning With ReadWithEase
            </h1>
            <p className="text-xl md:text-2xl text-black/80 mb-8">
              "ReadWithEase helps you access tools that simplify your reading and find deeper insights."
            </p>
            
            {/* CTA Buttons */}
            
               
          </div>

          {/* Features */}
          <div className="space-y-24">
            {features.map((f, i) => (
              <motion.div
                key={i}
                className={`flex flex-col md:flex-row items-center gap-12 ${
                  f.reverse ? "md:flex-row-reverse" : ""
                }`}
                initial="hidden"
                whileInView="visible"
                viewport={{ once: false, amount: 0.3 }}
                variants={featureVariants}
              >
                <div className={`w-full md:w-1/2 aspect-[4/5] ${f.bgColor} rounded-[40px] shadow-lg flex items-center justify-center overflow-hidden transition-transform hover:scale-105 duration-300`}>
                  <img src={f.img} alt={f.title} />
                </div>

                <div className="w-full md:w-1/2 text-center md:text-left px-2">
                  <h3 className="text-4xl font-semibold text-black mb-3">{f.title}</h3>
                  <p className="text-xl max-w-lg text-black leading-relaxed font-medium mb-6">
                    {f.desc}
                  </p>
                  <button 
                    onClick={() => handleFeatureClick(f.action)}
                    className="bg-gray-900 text-white px-10 py-4 rounded-full text-lg font-bold hover:scale-105 transition-all shadow-xl active:scale-95 inline-flex items-center gap-2"
                  >
                    {f.button}
                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 7l5 5m0 0l-5 5m5-5H6" />
                    </svg>
                  </button>
                </div>
              </motion.div>
            ))}
          </div>

          {/* Footer CTA */}
         
        </div>
      </div>

      {/* ALL THREE MODALS */}
      
      {/* Login Modal */}
      <LoginModal 
        isOpen={showLogin}
        onClose={handleCloseLogin}
        onSwitchToSignup={() => {
          handleCloseLogin();
          setShowSignup(true);
        }}
        onSwitchToForgotPassword={() => {
          handleCloseLogin();
          setShowForgotPassword(true);
        }}
      />

      {/* Signup Modal */}
      <SignupModal 
        isOpen={showSignup}
        onClose={handleCloseSignup}
        onSwitchToLogin={() => {
          handleCloseSignup();
          setShowLogin(true);
        }}
      />

      {/* Forgot Password Modal */}
      <ForgotPasswordModal 
        isOpen={showForgotPassword}
        onClose={handleCloseForgotPassword}
        onSwitchToLogin={() => {
          handleCloseForgotPassword();
          setShowLogin(true);
        }}
      />
    </section>
  );
};

export default Feature;