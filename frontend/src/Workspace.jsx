import React, { useState, useEffect, useRef } from 'react';


const Workspace = ({ extractedText, onBack }) => {
  const [selectedText, setSelectedText] = useState("");
  const [menuConfig, setMenuConfig] = useState({ 
    show: false, 
    x: 0, 
    y: 0, 
    type: 'word', 
    mode: 'options' 
  });
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  const [loadingAudio, setLoadingAudio] = useState(false);
const editorRef = useRef(null);
const hasInitialized = useRef(false);

  const mockMeaning = "The core substance or concept extracted from the text for analysis.";
  
  const mockSummary = "This paragraph explores this paragraph explores the fundamental concepts detected in the uploaded document.Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book. It has survived not only five ";

  // --- FIX: DETECT WHEN TEXT IS DESELECTED ---
  useEffect(() => {
  if (!hasInitialized.current && editorRef.current) {
    editorRef.current.innerHTML = extractedText
      ? `<p>${extractedText.replace(/\n/g, "<br/>")}</p>`
      : `<p><br/></p>`;
    hasInitialized.current = true;
  }
}, [extractedText]);


    

  const handleMouseUp = (e) => {
    // Prevent the menu from repositioning if we are clicking inside the menu itself
    if (e.target.closest('.floating-menu')) return;

    const selection = window.getSelection();
    const selectionText = selection.toString().trim();

    if (!selectionText) {
      setMenuConfig(prev => ({ ...prev, show: false }));
      return;
    }

    const range = selection.getRangeAt(0);
    const rect = range.getBoundingClientRect();
    const wordCount = selectionText.split(/\s+/).length;

    setSelectedText(selectionText);

    let menuType = 'word';
    if (wordCount > 1 && wordCount <= 20) menuType = 'short';
    if (wordCount > 20) menuType = 'paragraph';

    setMenuConfig({
      show: true,
      x: rect.left + rect.width / 2,
      y: rect.top - 60,
      type: menuType,
      mode: 'options'
    });
  };

  const handleMeaningClick = (e) => {
    e.stopPropagation();
    setMenuConfig(prev => ({ ...prev, mode: 'definition' }));
  };

  const handleBackToOptions = (e) => {
    e.stopPropagation();
    setMenuConfig(prev => ({ ...prev, mode: 'options' }));
  };

  const handleSummaryClick = (e) => {
    e.stopPropagation();
    setMenuConfig(prev => ({ ...prev, show: false }));
    setIsDrawerOpen(true);
  };

  const handleBackendTTS = async (e) => {
    e.stopPropagation();
    setMenuConfig(prev => ({ ...prev, show: false }));
    setLoadingAudio(true);
    setTimeout(() => {
      setLoadingAudio(false);
      alert(`Playing audio...`);
    }, 800);
  };

  return (
    <div className="flex h-screen bg-stone-100 relative overflow-hidden" onMouseUp={handleMouseUp}>
      
      {/* FLOATING MENU */}
      {menuConfig.show && (
        <div 
          className="floating-menu fixed z-50 bg-stone-900 text-white rounded-xl shadow-2xl border border-stone-800 flex flex-col overflow-hidden"
          style={{ top: `${menuConfig.y}px`, left: `${menuConfig.x}px`, transform: 'translateX(-50%)' }}
          onMouseUp={(e) => e.stopPropagation()}
          onMouseDown={(e) => e.stopPropagation()}
        >
          {menuConfig.mode === 'options' ? (
            <div className="flex divide-x divide-stone-800 whitespace-nowrap">
              {menuConfig.type === 'word' ? (
                <>
                  <button onClick={handleMeaningClick} className="px-5 py-3 text-xs font-bold hover:bg-stone-800 transition">Meaning</button>
                  <button onClick={handleBackendTTS} className="px-5 py-3 text-xs font-bold hover:bg-stone-800 transition">🔊</button>
                </>
              ) : menuConfig.type === 'short' ? (
                <button onClick={handleBackendTTS} className="px-6 py-3 text-xs font-bold hover:bg-stone-800 transition">Speak Selection 🔊</button>
              ) : (
                <>
                  <button onClick={handleSummaryClick} className="px-5 py-3 text-xs font-bold hover:bg-stone-800 flex items-center gap-2 transition">✨ AI Summary</button>
                  <button onClick={handleBackendTTS} className="px-5 py-3 text-xs font-bold hover:bg-stone-800 transition">Read Aloud 🔊</button>
                </>
              )}
            </div>
          ) : (
            <div className="p-4 w-64 animate-in fade-in zoom-in duration-150">
              <div className="flex justify-between items-center mb-2">
                <span className="text-[10px] text-blue-400 font-bold uppercase tracking-widest">Definition</span>
                <button onClick={handleBackToOptions} className="text-stone-500 hover:text-white p-1">✕</button>
              </div>
              <h4 className="font-bold text-base mb-1 text-white truncate">{selectedText}</h4>
              <p className="text-sm leading-relaxed text-stone-300">{mockMeaning}</p>
            </div>
          )}
        </div>
      )}

      {/* SIDEBAR */}
      <aside className="w-12 bg-stone-900 flex flex-col items-center py-8 text-white shrink-0 z-20 shadow-xl">
        <button onClick={onBack} className="p-3 bg-stone-800 hover:bg-stone-700 rounded-xl transition-all shadow-lg active:scale-95">
          ⬅
        </button>
      </aside>

      {/* MAIN LAYOUT */}
      <main className="flex-1 flex flex-col h-screen">
        <header className="px-5 pt- pb-6 shrink-0">
            
             
        </header>

        <div className="flex-1 overflow-hidden pl-4 pb-12">
          <div className=" h-screen max-w-5xl bg-white shadow-2xl  border-stone-200 overflow-y-auto custom-scrollbar">
            <div
  ref={editorRef}
  contentEditable
  suppressContentEditableWarning
  spellCheck={false}
  className="px-15 py-25 text-xl leading-[1.5] text-black font-serif
             selection:bg-blue-100 selection:text-blue-900
             outline-none cursor-text min-h-full"
  style={{ whiteSpace: 'pre-wrap' }}
/>

          </div>
        </div>
      </main>

      {/* SUMMARY DRAWER */}
<div className={`fixed top-0 right-0 h-full w-[550px] bg-white shadow-[-20px_0_50px_rgba(0,0,0,0.1)] border-l z-[200] transition-transform duration-500 ease-out flex flex-col ${isDrawerOpen ? 'translate-x-0' : 'translate-x-full'}`}>
  
  {/* FIXED DRAWER HEADER */}
  <div className="p-7 pb-6 border-b shrink-0 flex justify-between items-center">
    <h2 className="text-2xl font-black text-stone-900 uppercase">AI Summary</h2>
    <button onClick={() => setIsDrawerOpen(false)} className="text-stone-300 hover:text-stone-900 text-2xl font-light transition-colors">✕</button>
  </div>

  {/* SCROLLABLE DRAWER CONTENT */}
  <div className="flex-1 overflow-y-auto p-1 custom-scrollbar bg-stone-50/50">
    <div className="bg-white p-4 rounded-xl border border-stone-100 shadow-sm mb-10">
     
      
      {/* The text inside here can now be as long as you want */}
      <div className="text-xl text-black leading-relaxed font-serif">
        <p>"{mockSummary}"</p>
        
       
      </div>
    </div>
  </div>

  
  </div>
</div>
       
      
  );
};

export default Workspace;