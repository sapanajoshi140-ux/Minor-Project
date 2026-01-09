
import { motion } from "framer-motion";


const AnimatedTitle = ({ text }) => {
  const words = text.replace(/<br\>/, " ").split(" ");  //I have used br tag so it means if i have br in the text then replace it with space and .split will make the string in array so that we can use animation for individual element

  return (
    <motion.h1
      className="text-6xl max-w-4xl text-black font-extrabold leading-tight mb-6 tracking-tight flex flex-wrap justify-center gap-x-3"
      initial="hidden"
      animate="visible"
      variants={{     // its like to tell framermotion whenever element is visible then apply the animation
        visible: {
          transition: {
            staggerChildren: 0.45, // animation start after 0.45s of previous word animation have ended
          },
        },
      }}
    >
      {words.map((word, index) => (           //.map is used to go through each word in array
        <motion.span
          key={index}
          className="inline-block"   //treat every word as separate box 
          variants={{
            hidden: { opacity: 0, x: -25 },  //initially words are hidden and start animating from left
            visible: {
              opacity: 1,
              x: 0,                      //words come back from -25 position to original position
              transition: {
                duration: 0.8, // word animation last 0.8s
              },
            },
          }}
        >
          {word}
        </motion.span>
      ))}
    </motion.h1>
  );
};

const Picture = ({ title, desc, img }) => {
  return (
    <div
      className="w-full h-162.5 px-4 py-1 flex flex-col items-center justify-center text-center"
      style={{
        backgroundImage: `linear-gradient(rgba(0,0,0,0.2), rgba(0,0,0,0.2)), url(${img})`,
        backgroundSize: "cover",
        backgroundPosition: "center",
      }}
    >
      
        <AnimatedTitle text={title} />

        {/* Description section  */}
        <motion.p
          className="text-xl opacity-80 mb-10 mx-auto max-w-lg leading-relaxed"
          initial={{ opacity: 0}}
          animate={{ opacity: 1}}
          transition={{ delay: 1.7, duration: 0.8 }}
        >
          {desc}
        </motion.p>

        {/* Button */}
        <motion.button
          className=" text-white bg-gray-900 px-10 py-4 rounded-full text-lg font-bold hover:scale-105 transition-all shadow-xl active:scale-95"
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ delay: 1.3, duration: 0.8 }}
          whileHover={{ scale: 1.08 }}
          whileTap={{ scale: 0.95 }}
        >
          Get Started
        </motion.button>
      
    </div>
  );
};


const HeroSection = () => {
  return (
    <div className="px-8 py-4">
      <div className="rounded-[48px]  overflow-hidden">
        <Picture
          title="Read, Understand and Summarize"
          desc="Your personal AI powered reading companion"
          img="first.png"
        />
      </div>
    </div>
  );
};

export default HeroSection;
