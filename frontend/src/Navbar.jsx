import React, { createContext, useContext, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import './App.css';
import { useGoogleLogin } from '@react-oauth/google';
// API Configuration
const API_URL = 'http://localhost:8000';

// Auth Context
const AuthContext = createContext(null);

// Auth Provider Component
export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [accessToken, setAccessToken] = useState(sessionStorage.getItem('access_token'));
  const [refreshToken, setRefreshToken] = useState(sessionStorage.getItem('refresh_token'));
  const [loading, setLoading] = useState(true);
  

const googleLogin = async (googleAccessToken) => {
  try {
    const response = await fetch(`${API_URL}/google-login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ google_access_token: googleAccessToken })
    });

    const data = await response.json();
    if (!response.ok) throw new Error(data.detail || 'Google Login failed');

    // Save tokens exactly like your regular login
    sessionStorage.setItem('access_token', data.access_token);
    sessionStorage.setItem('refresh_token', data.refresh_token);
    setAccessToken(data.access_token);
    setRefreshToken(data.refresh_token);

    // Fetch user info
    const userResponse = await fetch(`${API_URL}/me`, {
      headers: { 'Authorization': `Bearer ${data.access_token}` }
    });
    const userData = await userResponse.json();
    setUser(userData);

    return { success: true };
  } catch (error) {
    return { success: false, error: error.message };
  }
};


  useEffect(() => {
    const checkAuth = async () => {
      const storedAccessToken = sessionStorage.getItem('access_token');
      
      if (storedAccessToken) {
        try {
          const response = await fetch(`${API_URL}/me`, {
            headers: { 'Authorization': `Bearer ${storedAccessToken}` }
          });
          
          if (response.ok) {
            const userData = await response.json();
            setUser(userData);
            setAccessToken(storedAccessToken);
          } else {
            clearTokens();
          }
        } catch (error) {
          console.error('Auth check failed:', error);
          clearTokens();
        }
      }
      setLoading(false);
    };

    checkAuth();
  }, []);

  const clearTokens = () => {
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('refresh_token');
    setAccessToken(null);
    setRefreshToken(null);
    setUser(null);
  };

  const signup = async (fullName, email, password, confirmPassword) => {
    try {
      const response = await fetch(`${API_URL}/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          full_name: fullName,
          email: email,
          password: password,
          confirm_password: confirmPassword
        })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Signup failed');
      }

     return { success: true, message: data.message }; // REMOVE verifyLink
  } catch (error) {
    return { success: false, error: error.message };
  }
  };

  const login = async (email, password) => {
    try {
      const response = await fetch(`${API_URL}/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Login failed');
      }

      const { access_token, refresh_token } = data;
      
      sessionStorage.setItem('access_token', access_token);
      sessionStorage.setItem('refresh_token', refresh_token);
      setAccessToken(access_token);
      setRefreshToken(refresh_token);

      const userResponse = await fetch(`${API_URL}/me`, {
        headers: { 'Authorization': `Bearer ${access_token}` }
      });
      
      const userData = await userResponse.json();
      setUser(userData);

      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  };
  const resendVerification = async (email) => {
    try {
      const response = await fetch(`${API_URL}/resend-verification`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to resend verification');
      }

      return { success: true, message: data.message };
    } catch (error) {
      return { success: false, error: error.message };
    }
  };
  const forgotPassword = async (email) => {
    try {
      const response = await fetch(`${API_URL}/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email })
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || 'Failed to send reset link');
      }

      return { success: true, message: data.message };
    } catch (error) {
      return { success: false, error: error.message };
    }
  };

  const logout = () => {
    clearTokens();
  };

  const value = {
    user,
    accessToken,
    signup,
    login,
    googleLogin,
    resendVerification,
    forgotPassword,
    logout,
    isAuthenticated: !!accessToken,
    loading
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}

// Your Navbar Component with Backend Integration
const Navbar = () => {
  const [showLogin, setShowLogin] = useState(false);
  const [showSignup, setShowSignup] = useState(false);
  const [showForgotPassword, setShowForgotPassword] = useState(false); 
  const [showResendOption, setShowResendOption] = useState(false);
  const [loginEmail, setLoginEmail] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [signupFullName, setSignupFullName] = useState('');
  const [signupEmail, setSignupEmail] = useState('');
  const [signupPassword, setSignupPassword] = useState('');
  const [signupConfirmPassword, setSignupConfirmPassword] = useState('');
   const [forgotPasswordEmail, setForgotPasswordEmail] = useState(''); // ADD THIS
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const navigate = useNavigate();
  const { login, signup,googleLogin,resendVerification, forgotPassword  } = useAuth();
  const handleGoogleSuccess = async (tokenResponse) => {
    setIsLoading(true);
    setError('');
    const result = await googleLogin(tokenResponse.access_token);
    
    if (result.success) {
      setShowLogin(false);
      setShowSignup(false);
      navigate("/dashboard");
    } else {
      setError(result.error);
    }
    setIsLoading(false);
  };

  // 3. Initialize the popup hook
  const loginWithGoogle = useGoogleLogin({
    onSuccess: handleGoogleSuccess,
    onError: () => setError("Google Login Failed"),
  });

  const handleLoginSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setIsLoading(true);

    const result = await login(loginEmail, loginPassword);

    if (result.success) {
      setShowLogin(false);
      navigate("/dashboard");
    } else {
      setError(result.error);
     if (result.error.includes("Verify email first")) {
        setShowResendOption(true);
      }
      setIsLoading(false);
    }
  };
const handleResendVerification = async () => {
    setIsLoading(true);
    setError('');
    const result = await resendVerification(loginEmail);
    setIsLoading(false);

    if (result.success) {
      setSuccess('Verification email sent! Please check your inbox.');
      setShowResendOption(false);
    } else {
      setError(result.error);
    }
  };
  const handleSignupSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');

    if (signupPassword !== signupConfirmPassword) {
      setError('Passwords do not match');
      return;
    }

    setIsLoading(true);
    const result = await signup(signupFullName, signupEmail, signupPassword, signupConfirmPassword);
    setIsLoading(false);

    if (result.success) {
      setSuccess(result.message);
      // Clear form
      setSignupFullName('');
      setSignupEmail('');
      setSignupPassword('');
      setSignupConfirmPassword('');
    } else {
      setError(result.error);
    }
};
const handleForgotPasswordSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSuccess('');
    setIsLoading(true);

    const result = await forgotPassword(forgotPasswordEmail);
    setIsLoading(false);

    if (result.success) {
      setSuccess(result.message);
      setForgotPasswordEmail('');
    } else {
      setError(result.error);
    }
  };

  return (
    <>
      <nav className={`navbar flex justify-between bg-blue-50 items-center p-4 ${showLogin || showSignup || showForgotPassword ? "blur-sm" : ""}`}> 
        <div className="text-3xl font-serif font-bold">ReadWithEase</div>

        <ul className="nav-links flex gap-6">
          <li className="hover:scale-105"><a href="/home">Home</a></li>
          <li className="hover:scale-105"><a href="/features">Features</a></li>
          <li className="hover:scale-105"><a href="/upload">Contact</a></li>
        </ul>

        <div className="auth-pill-container flex gap-4">
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
        </div>
      </nav>
  
      {/* Login Modal */}
      {showLogin && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-md"    
          onClick={() => { setShowLogin(false); setError(''); setSuccess(''); setShowResendOption(false); }}
        >
          <div 
            className="relative w-full max-w-md p-12 rounded-[2rem] bg-white/10 border border-white/20 shadow-2xl text-white text-center"
            onClick={(e) => e.stopPropagation()}
          >
            <button 
              className="absolute top-6 right-6 text-2xl opacity-70 hover:opacity-100"
              onClick={() => { setShowLogin(false); setError(''); setSuccess(''); setShowResendOption(false); }}
            >
              &times;                    
            </button>

            <div className="mb-7">
              <h1 className="text-4xl font-semibold mb-2">Welcome back!</h1>
              <h3 className="text-l">Please login to your account</h3>
            </div>

            <div className="space-y-4 text-left">
              <div>
                <label className="text-xs text-white ml-1">Email</label>
                <input 
                  type="email" 
                  value={loginEmail}
                  onChange={(e) => setLoginEmail(e.target.value)}
                  placeholder="Enter your email" 
                  className="w-full mt-1 px-4 py-3 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition text-white placeholder-gray-400"
                />
              </div>

              <div>
                <label className="text-xs text-white ml-1">Password</label>
                <input 
                  type="password" 
                  value={loginPassword}
                  onChange={(e) => setLoginPassword(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleLoginSubmit(e)}
                  placeholder="Enter your password"
                  className="w-full mt-1 px-4 py-3 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition text-white placeholder-gray-400"
                />
              </div>

              {error && (
                <div className="bg-red-500/20 border border-red-500/50 text-red-200 px-4 py-2 rounded-xl text-sm">
                  {error}
                </div>
              )}

              {showResendOption && (
                <button
                  onClick={handleResendVerification}
                  disabled={isLoading}
                  className="w-full py-2 bg-yellow-500/20 border border-yellow-500/50 text-yellow-200 rounded-lg hover:bg-yellow-500/30 transition text-sm"
                >
                  {isLoading ? 'Sending...' : 'Resend Verification Email'}
                </button>
              )}

              {success && (
                <div className="bg-green-500/20 border border-green-500/50 text-green-200 px-4 py-2 rounded-xl text-sm">
                  {success}
                </div>
              )}

              <div className="flex justify-between items-center text-xs">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" className="accent-indigo-500" /> Remember me
                </label>
                <a 
                  href="#" 
                  onClick={(e) => { 
                    e.preventDefault(); 
                    setShowLogin(false); 
                    setShowForgotPassword(true); 
                    setError(''); 
                  }}
                  className="text-blue-300 hover:text-white"
                >
                  Forgot password?
                </a>
              </div>

              <button 
                onClick={handleLoginSubmit}
                disabled={isLoading}
                className="w-full py-3 mt-4 bg-gray-100 text-black font-bold rounded-full hover:bg-white transition shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? 'Logging in...' : 'Log In'}
              </button>
            </div>

            <div className="flex items-center my-6">
              <div className="flex-1 h-[1px] bg-white/10"></div>
              <span className="px-3 text-xs text-white uppercase">Or</span>
              <div className="flex-1 h-[1px] bg-white/10"></div>
            </div>

            <button 
              onClick={() => loginWithGoogle()}
              className="w-full py-3 flex items-center justify-center gap-3 border border-white/20 rounded-full hover:bg-white/5 transition"
            >
              <img src="https://upload.wikimedia.org/wikipedia/commons/c/c1/Google_%22G%22_logo.svg" alt="G" className="w-5 h-5" />
              <span className="text-sm font-medium">Sign In with Google</span>
            </button>

            <p className="mt-8 text-sm text-gray-400">
              Don't have an account? <a href="#" className="text-blue-300 underline underline-offset-4 font-medium" onClick={(e) => { e.preventDefault(); setShowLogin(false); setShowSignup(true); setError(''); setSuccess(''); }}>Sign Up</a>
            </p>
          </div>
        </div>
      )}

      {/* Signup Modal */}
      {showSignup && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-md"
          onClick={() => { setShowSignup(false); setError(''); setSuccess(''); }}
        >
          <div 
            className="relative w-full max-w-md p-9 mx-9 rounded-[2rem] bg-white/10 border border-white/20 shadow-2xl text-white text-center"
            onClick={(e) => e.stopPropagation()}
          >
            <button 
              className="absolute top-4 right-4 text-2xl opacity-70 hover:opacity-100"
              onClick={() => { setShowSignup(false); setError(''); setSuccess(''); }}
            >
              &times;
            </button>

            <div className="mb-4">
              <h1 className="text-3xl font-semibold">Create your Account</h1>
            </div>

            <div className="space-y-3 text-left">
              <div>
                <label className="text-xs text-white ml-1">Full Name</label>
                <input 
                  type="text" 
                  value={signupFullName}
                  onChange={(e) => setSignupFullName(e.target.value)}
                  placeholder="Enter your full name" 
                  className="w-full mt-1 px-4 py-2 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition text-white placeholder-gray-400"
                />
              </div>

              <div>
                <label className="text-xs text-white ml-1">Email</label>
                <input 
                  type="email" 
                  value={signupEmail}
                  onChange={(e) => setSignupEmail(e.target.value)}
                  placeholder="Enter your email" 
                  className="w-full mt-1 px-4 py-3 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition text-white placeholder-gray-400"
                />
              </div>

              <div>
                <label className="text-xs text-white ml-1">Password</label>
                <input 
                  type="password" 
                  value={signupPassword}
                  onChange={(e) => setSignupPassword(e.target.value)}
                  placeholder="Create a password"
                  className="w-full mt-1 px-4 py-3 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition text-white placeholder-gray-400"
                />
              </div>

              <div>
                <label className="text-xs text-white ml-1">Confirm Password</label>
                <input 
                  type="password" 
                  value={signupConfirmPassword}
                  onChange={(e) => setSignupConfirmPassword(e.target.value)}
                  placeholder="Confirm your password"
                  className="w-full mt-1 px-4 py-3 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition text-white placeholder-gray-400"
                />
              </div>

              {error && (
                <div className="bg-red-500/20 border border-red-500/50 text-red-200 px-4 py-2 rounded-xl text-sm">
                  {error}
                </div>
              )}

              {success && (
                <div className="bg-green-500/20 border border-green-500/50 rounded-xl p-4">
                  <div className="flex items-start gap-3">
                    <div className="w-6 h-6 bg-green-500 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5">
                      <svg className="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
                      </svg>
                    </div>
                    <div className="flex-1">
                      <p className="text-green-100 font-semibold mb-1">Signup Successful!</p>
                      <p className="text-green-200 text-sm">{success}</p>
                      <p className="text-green-200 text-xs mt-2">📧 Check your email inbox (and spam folder) for verification link</p>
                    </div>
                  </div>
                </div>
              )}

              <div className="flex items-center text-xs pt-2">
                <label className="flex items-start gap-2 cursor-pointer">
                  <input type="checkbox" required className="accent-indigo-500 mt-0.5" /> 
                  <span>I agree to the Terms of Service and Privacy Policy</span>
                </label>
              </div>

              <button 
                onClick={handleSignupSubmit}
                disabled={isLoading}
                className="w-full py-3 mt-4 bg-gray-100 text-black font-bold rounded-full hover:bg-white transition shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? 'Signing up...' : 'Sign Up'}
              </button>
            </div>

            <div className="flex items-center my-6">
              <div className="flex-1 h-[1px] bg-white/10"></div>
              <span className="px-3 text-xs text-white uppercase">Or</span>
              <div className="flex-1 h-[1px] bg-white/10"></div>
            </div>

            <button 
              onClick={() => loginWithGoogle()}
              className="w-full py-3 flex items-center justify-center gap-3 border border-white/20 rounded-full hover:bg-white/5 transition"
            >
              <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="G" className="w-5 h-5" />
              <span className="text-sm font-medium">Sign Up with Google</span>
            </button>

            <p className="mt-6 text-sm text-gray-400">
              Already have an account? <a href="#" className="text-blue-300 underline underline-offset-4 font-medium" onClick={(e) => { e.preventDefault(); setShowSignup(false); setShowLogin(true); setError(''); setSuccess(''); }}>Log In</a>
            </p>
          </div>
        </div>
      )}

      {/* Forgot Password Modal */}
      {showForgotPassword && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-md"
          onClick={() => { setShowForgotPassword(false); setError(''); setSuccess(''); }}
        >
          <div 
            className="relative w-full max-w-md p-10 mx-9 rounded-[2rem] bg-white/10 border border-white/20 shadow-2xl text-white text-center"
            onClick={(e) => e.stopPropagation()}
          >
            <button 
              className="absolute top-4 right-4 text-2xl opacity-70 hover:opacity-100"
              onClick={() => { setShowForgotPassword(false); setError(''); setSuccess(''); }}
            >
              &times;
            </button>

            <div className="mb-6">
              <h1 className="text-3xl font-semibold mb-2">Forgot Password?</h1>
              <p className="text-sm text-gray-300">Enter your email to receive a password reset link</p>
            </div>

            <div className="space-y-4 text-left">
              <div>
                <label className="text-xs text-white ml-1">Email</label>
                <input 
                  type="email" 
                  value={forgotPasswordEmail}
                  onChange={(e) => setForgotPasswordEmail(e.target.value)}
                  onKeyPress={(e) => e.key === 'Enter' && handleForgotPasswordSubmit(e)}
                  placeholder="Enter your email" 
                  className="w-full mt-1 px-4 py-3 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition text-white placeholder-gray-400"
                />
              </div>

              {error && (
                <div className="bg-red-500/20 border border-red-500/50 text-red-200 px-4 py-2 rounded-xl text-sm">
                  {error}
                </div>
              )}

              {success && (
                <div className="bg-green-500/20 border border-green-500/50 text-green-200 px-4 py-2 rounded-xl text-sm">
                  {success}
                </div>
              )}

              <button 
                onClick={handleForgotPasswordSubmit}
                disabled={isLoading}
                className="w-full py-3 mt-4 bg-gray-100 text-black font-bold rounded-full hover:bg-white transition shadow-lg disabled:opacity-50 disabled:cursor-not-allowed"
              >
                {isLoading ? 'Sending...' : 'Send Reset Link'}
              </button>
            </div>

            <p className="mt-8 text-sm text-gray-400">
              Remember your password? <a href="#" className="text-blue-300 underline underline-offset-4 font-medium" onClick={(e) => { e.preventDefault(); setShowForgotPassword(false); setShowLogin(true); setError(''); setSuccess(''); }}>Log In</a>
            </p>
          </div>
        </div>
      )}
    </>
  );
};

export default Navbar;