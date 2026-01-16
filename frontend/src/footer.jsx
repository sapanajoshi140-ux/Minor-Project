import React, { useState } from 'react';

const Login = ({ img }) => {
  const [isLogin, setIsLogin] = useState(false);

 const handleSubmit = (e) => {
    e.preventDefault();
    
    navigate("/dashboard");
  };


  return (
    <div
      className="w-full min-h-screen flex items-center justify-between px-16"
      style={{
        backgroundImage: `linear-gradient(rgba(0,0,0,0.3), rgba(0,0,0,0.3)), url(${img})`,
        backgroundSize: "cover",
        backgroundPosition: "center",
      }}
    >
      {/* Left side - Heading */}
      <div className="flex-1">
        <h1 className="font-bold text-6xl lg:text-7xl font-serif leading-tight text-black">
          {isLogin ? 'Welcome back!' :  (
    <>
      Sign up to
      <br />
       Get Started
    </>
  )}
        </h1>
      </div>

      {/* Right side - Form that switches between Signup and Login */}
      <div className="w-full max-w-md p-9 rounded-[2rem] bg-white/10 border border-white/20 shadow-2xl text-white backdrop-blur-md">
        
        {/* Show Login Form */}
        {isLogin ? (
          <>
            <div className="mb-7 text-center">
              <h2 className="text-4xl font-semibold mb-2">Welcome back!</h2>
              <h3 className="text-base">Please login to your account</h3>
            </div>

            <div className="space-y-4 text-left">
              <div>
                <label className="text-xs text-white ml-1">Email</label>
                <input
                  type="email"
                  required
                  placeholder="Enter your email"
                  className="w-full mt-1 px-4 py-3 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition text-white placeholder:text-gray-300"
                />
              </div>

              <div>
                <label className="text-xs text-white ml-1">Password</label>
                <div className="relative">
                  <input
                    type="password"
                    required
                    placeholder="Enter your password"
                    className="w-full mt-1 px-4 py-3 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition text-white placeholder:text-gray-300"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 opacity-50 cursor-pointer">👁️</span>
                </div>
              </div>

              <div className="flex justify-between items-center text-xs">
                <label className="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" className="accent-indigo-500" /> Remember me
                </label>
                <a href="#" className="text-blue-700 hover:text-blue-700">Forgot password?</a>
              </div>

              <button onClick={handleSubmit} className="w-full py-3 mt-4 bg-gray-100 text-black font-bold rounded-full hover:bg-white transition shadow-lg">
                Log In
              </button>
            </div>

            <div className="flex items-center my-6">
              <div className="flex-1 h-[1px] bg-white/10"></div>
              <span className="px-3 text-xs text-white uppercase">Or</span>
              <div className="flex-1 h-[1px] bg-white/10"></div>
            </div>

            <button className="w-full py-3 flex items-center justify-center gap-3 border border-white/20 rounded-full hover:bg-white/5 transition">
              <img src="https://upload.wikimedia.org/wikipedia/commons/c/c1/Google_%22G%22_logo.svg" alt="G" className="w-5 h-5" />
              <span className="text-sm font-medium">Sign In with Google</span>
            </button>

            <p className="mt-8 text-sm text-gray-300 text-center font-medium">
              Don't have an account? <a href="#" className="text-blue-700 underline underline-offset-4 hover:text-blue-300" onClick={(e) => { e.preventDefault(); setIsLogin(false); }}>Sign Up</a>
            </p>
          </>
        ) : (
          /* Show Signup Form */
          <>
            <div className="mb-6 text-center">
              <h2 className="text-3xl font-semibold">Create your Account</h2>
            </div>

            <div className="space-y-3 text-left">
              <div>
                <label className="text-xs text-white ml-1">Full Name</label>
                <input
                  type="text"
                  required
                  placeholder="Enter your full name"
                  className="w-full mt-1 px-4 py-2 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition text-white placeholder:text-gray-300"
                />
              </div>

              <div>
                <label className="text-xs text-white ml-1">Email</label>
                <input
                  type="email"
                  required
                  placeholder="Enter your email"
                  className="w-full mt-1 px-4 py-3 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition text-white placeholder:text-neutral-300"
                />
              </div>

              <div>
                <label className="text-xs text-white ml-1">Password</label>
                <div className="relative">
                  <input
                    type="password"
                    required
                   
                    className="w-full mt-1 px-4 py-3 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition text-white"
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 opacity-50 cursor-pointer">👁️</span>
                </div>
              </div>

              <div>
                <label className="text-xs text-white ml-1">Confirm Password</label>
                <div className="relative">
                  <input
                    type="password"
                    required
                  
                    className="w-full mt-1 px-4 py-3 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition text-white "
                  />
                  <span className="absolute right-4 top-1/2 -translate-y-1/2 opacity-50 cursor-pointer">👁️</span>
                </div>
              </div>

              <div className="flex items-center text-xs pt-2">
                <label className="flex items-start gap-2 cursor-pointer">
                  <input type="checkbox" required className="accent-indigo-500 mt-0.5" />
                  <span>I agree to the Terms of Service and Privacy Policy</span>
                </label>
              </div>

              <button onClick={handleSubmit} className="w-full py-3 mt-4 bg-gray-100 text-black font-bold rounded-full hover:bg-white transition shadow-lg">
                Sign Up
              </button>
            </div>

            <div className="flex items-center my-5">
              <div className="flex-1 h-[1px] bg-white/10"></div>
              <span className="px-3 text-xs text-white uppercase">Or</span>
              <div className="flex-1 h-[1px] bg-white/10"></div>
            </div>

            <button className="w-full py-3 flex items-center justify-center gap-3 border border-white/20 rounded-full hover:bg-white/5 transition">
              <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="G" className="w-5 h-5" />
              <span className="text-sm font-medium">Sign Up with Google</span>
            </button>

            <p className="mt-6 text-sm text-gray-300 text-center font-medium">
              Already have an account? <a href="#" className="text-blue-700 underline underline-offset-4 hover:text-blue-300" onClick={(e) => { e.preventDefault(); setIsLogin(true); }}>Log In</a>
            </p>
          </>
        )}
      </div>
    </div>
  );
};

const Footer = () => {
  return (
    <div className="overflow-hidden" id="footer-section">
      <Login 
      img="footer.jpg" />
    </div>
  );
};

export default Footer;