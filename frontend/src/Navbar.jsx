import React from "react";
import "./App.css"; 

const Navbar = () => {
  return (
    <nav className="navbar">
    {/* Logo of Noteshare */}
      <div className="text-3xl font-serif font-bold">NoteShare</div>

      {/* Navigation Links */}
      <ul className="nav-links">
        <li className="hover:scale-105"><a href="/home" className="nav-link-item ">Home</a></li>
        <li className="hover:scale-105"><a href="/features" className="nav-link-item">Features</a></li>  
        <li className="hover:scale-105"><a href="/upload" className="nav-link-item">Contact</a></li>  
      </ul>

      {/* Buttons for login and signup */}
      <div className="auth-pill-container">
        <button className="pill-btn">Login</button>
        <button className="pill-btn">Sign Up</button>
      </div>
    </nav>
  );
};

export default Navbar;