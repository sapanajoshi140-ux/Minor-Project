import React, { useState } from 'react';
import { Upload, FileText, Sparkles, LogOut, ChevronRight } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import Workspace from './Workspace.jsx';

const Dashboard = () => {
  const navigate = useNavigate();
  const [file, setFile] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isProcessed, setIsProcessed] = useState(false);
  const [dragActive, setDragActive]=useState(false);
  // Mock text that simulates what the backend would eventually send
  const mockText = "This paragraph explores this paragraph explores the fundamental concepts detected in the uploaded document.Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book. It has survived not only five centuries, but also the leap into electronic typesetting, remaining essentially unchanged. It was popularised in the 1960s with the release of Letraset sheets containing Lorem Ipsum passages, and more recently with desktop publishing software like Aldus PageMaker including versions of Lorem Ipsum.Why do we use ithe fundamental concepts detected in the uploaded document.Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book. It has survived not only five centuries, but also the leap into his paragraph explores the fundamental concepts detected in the uploaded document.Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book. It has survived not only five centuries, but also the leap into electronic typesetting, remaining essentially unchanged. It was popularised in the 1960s with the release of Letraset sheets containing Lorem Ipsum passages, and more recently with desktop publishing software like Aldus PageMaker including versions of Lorem Ipsum.Why do we use itThis paragraph explores this paragraph explores the fundamental concepts detected in the uploaded document.Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book. It has survived not only five centuries, but also the leap into electronic typesetting, remaining essentially unchanged. It was popularised in the 1960s with the release of Letraset sheets containing Lorem Ipsum passages, and more recently with desktop publishing software like Aldus PageMaker including versions of Lorem Ipsum.Why do we use ithe fundamental concepts detected in the uploaded document.Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book. It has survived not only five centuries, but also the leap into his paragraph explores the fundamental concepts detected in the uploaded document.Lorem Ipsum is simply dummy text of the printing and typesetting industry. Lorem Ipsum has been the industry's standard dummy text ever since the 1500s, when an unknown printer took a galley of type and scrambled it to make a type specimen book. It has survived not only five centuries, but also the leap into electronic typesetting, remaining essentially unchanged. It was popularised in the 1960s with the release of Letraset sheets containing Lorem Ipsum passages, and more recently with desktop publishing software like Aldus PageMaker including versions of Lorem Ipsum.Why do we use it";

  

  const handleUpload = () => {
    if (!file) return;
    setIsProcessing(true);
    
    // Simulate a 2-second delay for the backend OCR process
    setTimeout(() => {
      setIsProcessing(false);
      setIsProcessed(true);
    }, 2000);
  };
  const handleDrag = (e) => {     //drag  handler
    e.preventDefault();               //by default browser want to open that file in new tab so it  prevents that
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);                      
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };
 
  const handleDrop = (e) => {      //handles drop
    e.preventDefault();                   
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      setFile(e.dataTransfer.files[0]);
    }
  };

  // IF PROCESSED: Show the Workspace
  if (isProcessed) {
    return <Workspace extractedText={mockText} onBack={() => setIsProcessed(false)} />;
  }

  // ELSE: Show the Upload UI
  return (
    <div className="flex h-screen bg-neutral-900 ">
      {/* Sidebar */}
      <aside className="w-72 bg-black/20 backdrop-blur-xl border-r border-white/10 flex flex-col">
        <div className="p-6 border-b border-white/10">
          <div className="flex items-center gap-3">
           
             
           
            <div>
              <h1 className="text-2xl font-bold font-serif text-white">ReadWithEase</h1>
              <p className="text-xs text-gray-400">Your AI-Powered Reading Companion</p>
            </div>
          </div>
        </div>
        
        <nav className="flex-1 p-4 space-y-2">
         
          
          <button className="w-full p-4 bg-white/5 backdrop-blur-sm border border-white/10 rounded-xl text-white/60 flex items-center gap-3 hover:bg-white/10 hover:text-white transition group">
            <FileText className="w-5 h-5" />
            <span className="font-medium">Recent Files</span>
            <ChevronRight className="w-4 h-4 ml-auto opacity-0 group-hover:opacity-100 transition" />
          </button>
        </nav>

        <div className="p-4 border-t border-white/10">
          <button className="w-full p-4 bg-red-500/10 backdrop-blur-sm border border-red-500/30 rounded-xl text-red-300 flex items-center gap-3 hover:bg-red-500/20 transition">
            <LogOut className="w-5 h-5" />
            <span className="font-medium">Logout</span>
          </button>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex items-center justify-center p-8">
        <div className="max-w-2xl w-full">
          {/* Header */}
          <div className="text-center mb-8">
            <h2 className="text-4xl font-bold text-white mb-3 ">
              Upload Your Document
            </h2>
            <p className="text-gray-100 text-lg">
              Drop your document and start learning
            </p>
          </div>

          {/* Upload Card */}
          <div className="bg-white/10 backdrop-blur-xl border border-white/20 rounded-3xl p-8 shadow-2xl">
            {/* Drag & Drop Area */}
            <div
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              className={`border-2 border-dashed rounded-2xl p-12 text-center transition-all ${
                dragActive
                  ? 'border-white bg-gray-900'
                  : 'border-white/30 hover:border-white hover:bg-white/5'
              }`}
            >
              <div className="flex flex-col items-center gap-4">
                <div className={`w-20 h-20 rounded-full flex items-center justify-center transition-all ${
                  dragActive ? 'bg-gray-600' : 'bg-gradient-to-br from-black to-gray-500'
                }`}>
                  <Upload className="w-10 h-10 text-white" />
                </div>
                
                {file ? (
                  <div className="flex items-center gap-3 bg-white/5 border border-white/20 rounded-xl p-4 max-w-md">
                    <FileText className="w-10 h-10 text-white flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-white font-medium text-sm truncate">{file.name}</p>
                      <p className="text-white text-xs">{(file.size / 1024).toFixed(2)} KB</p>
                    </div>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        setFile(null);
                      }}
                      
                    >
                      <span className="text-red-400 hover:text-white text-xl font-bold leading-none">×</span>
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-white font-medium text-lg">
                      Drag & drop your file here
                    </p>
                    <p className="text-white text-sm">or click to browse</p>
                  </div>
                )}
                
                <input
                  type="file"
                  onChange={(e) => setFile(e.target.files[0])}
                  className="hidden"
                  id="file-upload"
                  accept=".pdf,.jpg,.jpeg,.png,.docx"
                />
                <label
                  htmlFor="file-upload"
                  className="px-6 py-3 bg-white/10 hover:bg-white/20 border border-white/30 rounded-xl text-white font-medium cursor-pointer transition"
                >
                  Browse Files
                </label>
              </div>
            </div>

          

            {/* Upload Button */}
            <button
              onClick={handleUpload}
              disabled={!file || isProcessing}
              className={`w-full mt-8 py-4 rounded-xl font-bold text-lg transition-all transform ${
                isProcessing
                  ? ' bg-black text-white cursor-wait scale-95'
                  : !file
                  ? 'bg-white/5 text-white/30 cursor-not-allowed'
                  : 'bg-gradient-to-r from-gray-800 to-black text-white hover:scale-105 hover:shadow-2xl hover:shadow-gray-500/50'
              }`}
            >
              {isProcessing ? (
                <span className="flex items-center justify-center gap-3">
                  <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin"></div>
                  Processing...
                </span>
              ) : (
                'Start Reading'
              )}
            </button>
          </div>

          
        </div>
      </main>
    </div>
  );
};

export default Dashboard;