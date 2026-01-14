import React, { useState } from "react";
import { useNavigate } from "react-router-dom"; // 1. Import the navigator
import "./App.css";

const Navbar = () => {
  const [showLogin, setShowLogin] = useState(false);
  const navigate = useNavigate(); // 2. Initialize the navigator

  // 3. This function handles the "Log In" click
  const handleSubmit = (e) => {
    e.preventDefault(); // Stops the page from refreshing
    setShowLogin(false); // Closes the modal
    navigate("/dashboard"); // Sends the user to the new page
  };

  return (
    <>
      {/* Navbar - Blurs when modal is open */}
      <nav className={`navbar flex justify-between bg-blue-50 items-center p-4 ${showLogin ? "blur-sm" : ""}`}>
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
          <button className="pill-btn bg-white px-6 py-2 rounded-full text-black font-semibold">
            Sign Up
          </button>
        </div>
      </nav>

      {/* Login Modal Overlay */}
      {showLogin && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-md"
          onClick={() => setShowLogin(false)}
        >
          {/* Glass Card */}
          <div 
            className="relative w-full max-w-md p-8 mx-4 rounded-[2rem] bg-white/10 border border-white/20 shadow-2xl text-white text-center"
            onClick={(e) => e.stopPropagation()}
          >
            {/* Close Button */}
            <button 
              className="absolute top-6 right-6 text-2xl opacity-70 hover:opacity-100"
              onClick={() => setShowLogin(false)}
            >
              &times;
            </button>

            {/* Header */}
            <div className="mb-8">
              <div className="w-12 h-12 border-2 border-white/40 rounded-full flex items-center justify-center mx-auto mb-4">
                <div className="w-6 h-6 border-2 border-white rounded-full"></div>
              </div>
              <h1 className="text-4xl font-semibold mb-2">Welcome back!</h1>
             
            </div>

            {/* Form - Added onSubmit handler here */}
            <form className="space-y-4 text-left" onSubmit={handleSubmit}>
              <div>
                <label className="text-xs text-white ml-1">Email</label>
                <input 
                  type="email" 
                  required
                  placeholder="Enter your email" 
                  className="w-full mt-1 px-4 py-3 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition"
                />
              </div>

              <div>
                <label className="text-xs text-white ml-1">Password</label>
                <div className="relative">
                  <input 
                    type="password" 
                    required
                    placeholder="" 
                    className="w-full mt-1 px-4 py-3 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 opacity-50 cursor-pointer">👁️</span>
                </div>
              </div>

              <div className="flex justify-between items-center text-xs">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" className="accent-indigo-500" /> Remember me
                </label>
                <a href="#" className="text-blue-700 hover:text-white">Forgot password?</a>
              </div>

              {/* Added type="submit" to ensure it triggers the form */}
              <button type="submit" className="w-full py-3 mt-4 bg-gray-100 text-black font-bold rounded-full hover:bg-white transition shadow-lg">
                Log In
              </button>
            </form>

            {/* Separator */}
            <div className="flex items-center my-6">
              <div className="flex-1 h-[1px] bg-white/10"></div>
              <span className="px-3 text-xs text-gray-500 uppercase">Or</span>
              <div className="flex-1 h-[1px] bg-white/10"></div>
            </div>

            {/* Google Button */}
            <button className="w-full py-3 flex items-center justify-center gap-3 border border-white/20 rounded-full hover:bg-white/5 transition">
              <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="G" className="w-5 h-5" />
              <span className="text-sm font-medium">Sign In with Google</span>
            </button>

            <p className="mt-8 text-sm text-gray-400">
              Don't have an account? <a href="#" className="text-blue-700 underline underline-offset-4 font-medium">Sign Up</a>
            </p>
          </div>
        </div>
      )}
    </>
  );
};

export default Navbar;