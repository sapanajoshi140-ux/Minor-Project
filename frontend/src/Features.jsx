import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { motion } from "framer-motion";

const Feature = () => {
  const [showLogin, setShowLogin] = useState(false);
const [showSignup, setShowSignup] = useState(false);
  const navigate = useNavigate();
const handleSubmit = (e) => {
    e.preventDefault();
    setShowLogin(false);
    navigate("/dashboard");
  };

  const features = [
    {
      title: "Upload Documents",
      desc: "Upload the documents and read in clean and distraction-free environment",
      img: "upload.png",
      bgColor: "bg-[#F2F2F2]",
       button:"Upload",
      reverse: true,
    },
    {
      title: "Reading Mode Interface",
      desc: "Tap or click on the word to view meaning and pronounciation or select sentence for text to speech feature",
      img: "word.png",
       button:"Try now",
      bgColor: "bg-[#F2F2F2]",
    },
    {
      title: "AI Assistant",
      desc: "Query AI about any topics in you document and summarise your content for quick revision",
      img: "summarize.png",
      bgColor: "bg-[#F2F2F2]",
      button:"Ask AI",
      reverse: true,
    },
  ];
  
  // Animation variants
  const featureVariants = {
    hidden: { opacity: 0, y: 50 },
    visible: { 
      opacity: 1, 
      y: 0, 
      transition: { duration: 1.3 } 
    },
  };

  return (
    <section className="bg-[#F1EADA] w-full py-24 min-h-screen">
      <div className="max-w-6xl mx-auto px-6">
        <div className="max-w-4xl mx-auto px-6">
          {/* Header */}
          <h1 className="md:text-5xl font-bold font-serif text-center text-black mb-2 leading-tight tracking-tight">
            Elevate Your Learning With ReadWithEase
          </h1>
          <p className="text-2xl text-black justify-center text-center mb-20">
             "ReadWithEase helps you access tools that simplify your reading and find deeper insights."
          </p>

          {/* Features Container */}
          <div className="space-y-24">
            {features.map((f, i) => (
              <motion.div
                key={i}
                className={`flex flex-col md:flex-row items-center gap-12 ${f.reverse ? "md:flex-row-reverse" : ""}`} //if reverse is true then text on left and image on right and if false than default
                initial="hidden"
                whileInView="visible"   //starts animation if I scroll the section
                viewport={{ once:false, amount: 0.3}} // animate once when 30% of element is visible and animate whenver i scroll down
                variants={featureVariants}
              >
                {/* Image Box */}
                <div className={`w-full md:w-1/2 aspect-[4/5] ${f.bgColor} rounded-[40px] shadow-lg flex items-center justify-center overflow-hidden transition-transform hover:scale-105 duration-300`}>
                  <img
                    src={f.img}
                    alt={f.title}
          
                  />
                </div>
            
                {/* Text Box */}
                <div className="w-full md:w-1/2 text-center md:text-left px-2">
                  <h3 className="text-4xl font-semibold text-black mb-3">{f.title}</h3>
                  <p className="text-xl max-w-lg  text-black leading-relaxed font-medium mb-3">
                    {f.desc}
                  </p>
                  <button 
                   onClick={() => setShowSignup(true)}
                  className="bg-brand-btn text-white bg-gray-900 px-10 py-4 rounded-full text-lg font-bold hover:scale-105 transition-all shadow-xl active:scale-95">
                    {f.button}
                  </button>
                </div>
              </motion.div>

))}
              {/* login form */}
      {showLogin && (     /* if showlogin is true only then it will render after    */
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-md"    
          onClick={() => setShowLogin(false)}
        >
          <div 
            className="relative w-full max-w-md p-12 rounded-[2rem] bg-white/10 border border-white/20 shadow-2xl text-white text-center"
            onClick={(e) => e.stopPropagation()}
          >
            <button 
              className="absolute top-6 right-6 text-2xl opacity-70 hover:opacity-100"
              onClick={() => setShowLogin(false)}
            >
              &times;                    
            </button>

            <div className="mb-7">
              
              <h1 className="text-4xl font-semibold mb-2">Welcome back!</h1>
              <h3 className="text-l ">Please login to your account</h3>
            </div>

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

              <button type="submit" className="w-full py-3 mt-4 bg-gray-100 text-black font-bold rounded-full hover:bg-white transition shadow-lg">
                Log In
              </button>
            </form>

            <div className="flex items-center my-6">
              <div className="flex-1 h-[1px] bg-white/10"></div>
              <span className="px-3 text-xs text-white uppercase">Or</span>
              <div className="flex-1 h-[1px] bg-white/10"></div>
            </div>

            <button className="w-full py-3 flex items-center justify-center gap-3 border border-white/20 rounded-full hover:bg-white/5 transition">
              <img src="https://upload.wikimedia.org/wikipedia/commons/c/c1/Google_%22G%22_logo.svg" alt="G" className="w-5 h-5" />
              <span className="text-sm font-medium">Sign In with Google</span>
            </button>

            <p className="mt-8 text-sm text-gray-400">
              Don't have an account? <a href="#" className="text-blue-700 underline underline-offset-4 font-medium" onClick={(e) => { e.preventDefault(); setShowLogin(false); setShowSignup(true); }}>Sign Up</a>
            </p>
          </div>
        </div>
      )}

      {/* Signup Modal Overlay */}
      {showSignup && (
        <div 
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-md"
          onClick={() => setShowSignup(false)}
        >
          <div 
            className="relative w-full max-w-md p-9 mx-9 rounded-[2rem] bg-white/10 border border-white/20 shadow-2xl text-white text-center"
            onClick={(e) => e.stopPropagation()}
          >
            <button 
              className="absolute top-4 right-4 text-2xl opacity-70 hover:opacity-100"
              onClick={() => setShowSignup(false)}
            >
              &times;
            </button>

            <div className="mb-4">
              
              <h1 className="text-3xl font-semibold ">Create your Account</h1>
              </div>

            <form className="space-y-3 text-left" onSubmit={(e) => { e.preventDefault(); setShowSignup(false); navigate("/dashboard"); }}>
              <div>
                <label className="text-xs text-white ml-1">Full Name</label>
                <input 
                  type="text" 
                  required
                  placeholder="Enter your full name" 
                  className="w-full mt-1 px-4 py-2 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition"
                />
              </div>

              <div>
                <label className="text-xs text-white ml-1">Email</label>
                <input 
                  type="email" 
                  required
                  placeholder="Enter your email" 
                  className="w-full mt-3 px-4 py-3 bg-white/5 border border-white/20 rounded-xl focus:outline-none focus:border-white/50 transition"
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

              <div>
                <label className="text-xs text-white ml-1">Confirm Password</label>
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

              <div className="flex items-center text-xs pt-2">
                <label className="flex items-start gap-2 cursor-pointer">
                  <input type="checkbox" required className="accent-indigo-500 mt-0.5" /> 
                  <span>I agree to the Terms of Service and Privacy Policy</span>
                </label>
              </div>

              <button type="submit" className="w-full py-3 mt-4 bg-gray-100 text-black font-bold rounded-full hover:bg-white transition shadow-lg">
                Sign Up
              </button>
            </form>

            <div className="flex items-center my-6">
              <div className="flex-1 h-[1px] bg-white/10"></div>
              <span className="px-3 text-xs text-white uppercase">Or</span>
              <div className="flex-1 h-[1px] bg-white/10"></div>
            </div>

            <button className="w-full py-3 flex items-center justify-center gap-3 border border-white/20 rounded-full hover:bg-white/5 transition">
              <img src="https://www.gstatic.com/firebasejs/ui/2.0.0/images/auth/google.svg" alt="G" className="w-5 h-5" />
              <span className="text-sm font-medium">Sign Up with Google</span>
            </button>

            <p className="mt-6 text-sm text-gray-400">
              Already have an account? <a href="#" className="text-blue-700 underline underline-offset-4 font-medium" onClick={(e) => { e.preventDefault(); setShowSignup(false); setShowLogin(true); }}>Log In</a>
            </p>
          </div>
        </div>
      )}
    
  


          
          </div>

        </div>
        </div>
 </section>
      );
};
export default Feature;
