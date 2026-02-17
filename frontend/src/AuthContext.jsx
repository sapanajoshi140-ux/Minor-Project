import { createContext, useContext, useState, useEffect } from 'react';

const API_URL = import.meta.env.VITE_API_URL ;

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  const [accessToken, setAccessToken] = useState(localStorage.getItem('access_token'));
  const [refreshToken, setRefreshToken] = useState(localStorage.getItem('refresh_token'));
  const [loading, setLoading] = useState(true);

  // Clear tokens helper
  const clearTokens = () => {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    setAccessToken(null);
    setRefreshToken(null);
    setUser(null);
  };

  // Check authentication on mount
  useEffect(() => {
    const checkAuth = async () => {
      const storedAccessToken = localStorage.getItem('access_token');
      
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

  // Google Login
  const googleLogin = async (googleAccessToken) => {
    try {
      const response = await fetch(`${API_URL}/google-login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ google_access_token: googleAccessToken })
      });

      const data = await response.json();
      
      if (!response.ok) {
        throw new Error(data.detail || 'Google Login failed');
      }

      // Save tokens
      localStorage.setItem('access_token', data.access_token);
      localStorage.setItem('refresh_token', data.refresh_token);
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

  // Regular Login
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
      
      localStorage.setItem('access_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
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

  // Signup
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

      return { success: true, message: data.message };
    } catch (error) {
      return { success: false, error: error.message };
    }
  };

  // Resend Verification
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

  // Forgot Password
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

  // Logout
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