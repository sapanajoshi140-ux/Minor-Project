import { useState, useRef } from 'react';

// Reusable Picture Slide Component
const Picture = ({ title, desc, img }) => {
  return (
    // this div section handles background image
    <div 
      className="w-full h-162.5 flex flex-col items-center justify-center text-center px-6 transition-all duration-700 rounded-[48px]"
    //  Passing javascript object as style for imageUrl
      style={{ 
        backgroundImage: `linear-gradient(rgba(0,0,0,0.4), rgba(0,0,0,0.4)), url(${img})`,
        backgroundSize: 'cover',
        
      }}
    > 
    {/* this div section is for the content */}
      <div className="max-w-4xl text-black">
        <h1 
          className="text-6xl font-extrabold leading-tight mb-6 tracking-tight"
          dangerouslySetInnerHTML={{ __html: title }}  /* I have used br tag and react reads it as plain text so using this will tell react to treat it as html element  */
        />
        <p className="text-xl opacity-80 mb-10 mx-auto max-w-lg leading-relaxed">
          {desc}
        </p>
        <button className="bg-white text-black px-10 py-4 rounded-full text-lg font-bold hover:scale-105 transition-all shadow-xl active:scale-95">
          Get Started
        </button>
      </div>
    </div>
  );
};

const HeroSlider = () => {
  const [activeSlide, setActiveSlide] = useState(0);
  
  // useRef hook is used here to change slider without re-rendering(calling function to update UI)
  const scrollRef = useRef(null);

  const slides = [
    { 
      title: "Read, Understand and Summarize", 
      desc: "Your personal AI powered reading companion", 
      img: "first.png" 
    },
    { 
      title: "Tap for meanings <br /> & pronunciation", 
      desc: "Instantly understand difficult words with a single tap.", 
      img: "second.png" 
    },
    { 
      title: "Smart AI <br /> Summarization", 
      desc: "Save hours of reading. Let AI extract the core insights.", 
      img: "third.png" 
    }
  ];

  const scroll = (direction) => {
    const current = scrollRef.current;
    if (current) { // Safety check to element exist before trying to scroll because the useRef starts with null
      const width = current.offsetWidth;  //automatically check physical width of the user and then assign width accordingly
      if (direction === 'left') {
        current.scrollBy({ left: -width, behavior: 'smooth' });  //if we want to go in previous slide then we have to do negative of width and for right positive of width means move the width by that width 
      } else {
        current.scrollBy({ left: width, behavior: 'smooth' });
      }
    }
  };

  const handleScroll = (e) => {     //to know which slide is visible
    const index = Math.round(e.target.scrollLeft / e.target.offsetWidth);  //if on first slide then scrollleft value is 0 then index value is zero means we are on the first slide
    setActiveSlide(index);
  };

  return (
    <div className="relative px-8 py-4 group mb-12">
      
      {/* Left Arrow Button */}
      <button 
        onClick={() => scroll('left')}
        className="absolute left-14 top-1/2 -translate-y-1/2 z-20 bg-white/20 hover:bg-white/40 text-white p-4 rounded-full backdrop-blur-md transition-all opacity-0 group-hover:opacity-100 cursor-pointer"
      >
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={3} stroke="currentColor" className="w-6 h-6 text-white">
          <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
        </svg>
      </button>

      {/* Right Arrow Button */}
      <button 
        onClick={() => scroll('right')}
        className="absolute right-14 top-1/2 -translate-y-1/2 z-20 bg-white/20 hover:bg-white/40 text-white p-4 rounded-full backdrop-blur-md transition-all opacity-0 group-hover:opacity-100 cursor-pointer"
      >
        <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth={3} stroke="currentColor" className="w-6 h-6 text-white">
          <path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" />
        </svg>
      </button>

      {/* Scroll Container */}
      <div 
        ref={scrollRef} // Ref is now correctly attached to the container
        onScroll={handleScroll}
        className="flex overflow-x-auto snap-x snap-mandatory scrollbar-hide rounded-[48px] shadow-2xl"
        style={{ scrollBehavior: 'smooth' }}
      >
        {slides.map((slide, index) => (
          <div key={index} className="min-w-full snap-center">
            <Picture 
              title={slide.title} 
              desc={slide.desc} 
              img={slide.img} 
            />
          </div>
        ))}
      </div>

      {/* Dots */}
      <div className="absolute bottom-12 left-1/2 -translate-x-1/2 flex gap-3 z-10">
        {slides.map((_, index) => (
          <div 
            key={index}
            className={`h-2 transition-all duration-300 rounded-full ${
              activeSlide === index ? "w-10 bg-white" : "w-2 bg-white/40"
            }`}
          />
        ))}
      </div>
    </div>
  );
};

export default HeroSlider;