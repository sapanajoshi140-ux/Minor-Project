

import { useState } from 'react';

const Input = ({ label, type = 'text', value, onChange, placeholder, onKeyPress, error }) => {
  const [showPassword, setShowPassword] = useState(false);
  
  const isPasswordField = type === 'password';
  const inputType = isPasswordField && showPassword ? 'text' : type;

  return (
    <div>
      {label && <label className="text-xs text-white ml-1">{label}</label>}
      <div className="relative">
        <input 
          type={inputType}
          value={value}
          onChange={onChange}
          onKeyPress={onKeyPress}
          placeholder={placeholder}
          className={`w-full mt-1 px-4 py-3 bg-white/5 border ${error ? 'border-red-500' : 'border-white/20'} rounded-xl focus:outline-none focus:border-white/50 transition text-white placeholder-gray-400`}
        />
        {isPasswordField && (
          <button
            type="button"
            onClick={() => setShowPassword(!showPassword)}
            className="absolute right-4 top-1/2 -translate-y-1/2 opacity-50 hover:opacity-100 transition text-lg"
          >
            {showPassword ? '🙈' : '👁️'}
          </button>
        )}
      </div>
      {error && <p className="text-red-300 text-xs mt-1 ml-1">{error}</p>}
    </div>
  );
};

export default Input;
