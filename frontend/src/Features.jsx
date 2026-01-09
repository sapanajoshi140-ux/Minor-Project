
import { motion } from "framer-motion";

const Feature = () => {
  const features = [
    {
      title: "Upload Documents",
      desc: "Upload the documents and read in clean and distraction-free environment",
      img: "upload.png",
      bgColor: "bg-[#B59E7D]",
      reverse: true,
    },
    {
      title: "Reading Mode Interface",
      desc: "Tap or click on the word to view meaning and pronounciation or select sentence for text to speech feature",
      img: "word.png",
      bgColor: "bg-[#B59E7D]",
    },
    {
      title: "AI Summarizer",
      desc: "Let AI summarise your content for quick revision",
      img: "summarize.png",
      bgColor: "bg-[#B59E7D]",
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
          <h1 className="md:text-5xl font-bold text-center text-black mb-1.5 leading-tight tracking-tight">
            Elevate Your Learning With NoteShare
          </h1>
          <p className="text-2xl text-black justify-center text-center mb-20">
            With NoteShare, you can access tools that simplify your reading and help you find deeper insights.
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
                  <p className="text-lg text-black leading-relaxed font-medium mb-3">
                    {f.desc}
                  </p>
                  <button className="bg-brand-btn text-white bg-gray-900 px-10 py-4 rounded-full text-lg font-bold hover:scale-105 transition-all shadow-xl active:scale-95">
                    Get Started
                  </button>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
};

export default Feature;
