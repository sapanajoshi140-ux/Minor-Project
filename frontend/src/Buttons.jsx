const Button = ({ children, onClick, disabled, loading, variant = 'primary', type = 'button' }) => {
  const baseStyles = "w-full py-3 font-bold rounded-full transition shadow-lg disabled:opacity-50 disabled:cursor-not-allowed";
  
  const variants = {
    primary: "bg-gray-100 text-black hover:bg-white",
    secondary: "bg-white/20 text-white hover:bg-white/30",
    google: "border border-white/20 hover:bg-white/5"
  };

  return (
    <button 
      type={type}
      onClick={onClick}
      disabled={disabled || loading}
      className={`${baseStyles} ${variants[variant]}`}
    >
      {loading ? 'Loading...' : children}
    </button>
  );
};

export default Button;