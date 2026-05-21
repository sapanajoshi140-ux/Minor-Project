import React, { useState } from 'react';
import { Upload, FileText, AlertCircle } from 'lucide-react';


const UploadSection = ({ onUpload, isProcessing = false, error = '', className = '', dropzoneClassName = '' }) => {
  const [file, setFile]           = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [localError, setLocalError] = useState('');

  const displayError = error || localError;

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') setDragActive(true);
    else if (e.type === 'dragleave') setDragActive(false);
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    const dropped = e.dataTransfer.files?.[0];
    if (dropped) { setFile(dropped); setLocalError(''); }
  };

  const handleFileChange = (e) => {
    const selected = e.target.files?.[0];
    if (selected) { setFile(selected); setLocalError(''); }
  };

  const handleSubmit = () => {
    if (!file || isProcessing) return;
    onUpload?.(file);
  };

  return (
    <div className={`bg-white/10 backdrop-blur-xl border border-white/20 rounded-3xl p-8 shadow-2xl ${className}`}>
      {/* Drop zone */}
      <div
        onDragEnter={handleDrag}
        onDragLeave={handleDrag}
        onDragOver={handleDrag}
        onDrop={handleDrop}
        className={`border-2 border-dashed rounded-2xl p-12 text-center transition-all ${
          dragActive
            ? 'border-white bg-gray-900'
            : 'border-white/30 hover:border-white hover:bg-white/5'
        } ${dropzoneClassName}`}
      >
        <div className="flex flex-col items-center gap-4">
          {/* Upload icon */}
          <div
            className={`w-20 h-20 rounded-full flex items-center justify-center transition-all ${
              dragActive ? 'bg-gray-600' : 'bg-gradient-to-br from-black to-gray-500'
            }`}
          >
            <Upload className="w-10 h-10 text-white" />
          </div>

          {/* File preview or placeholder */}
          {file ? (
            <div className="flex items-center gap-3 bg-white/5 border border-white/20 rounded-xl p-4 max-w-md">
              <FileText className="w-10 h-10 text-white flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-white font-medium text-sm truncate">{file.name}</p>
                <p className="text-white/50 text-xs">{(file.size / 1024).toFixed(2)} KB</p>
              </div>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  setFile(null);
                  setLocalError('');
                }}
              >
                <span className="text-red-400 hover:text-white text-xl font-bold">×</span>
              </button>
            </div>
          ) : (
            <div className="space-y-2">
              <p className="text-white font-medium text-lg">Drag &amp; drop your file here</p>
              <p className="text-white/60 text-sm">or click to browse</p>
              <p className="text-white/30 text-xs">PDF, DOCX, PPTX, TXT, PNG, JPG</p>
            </div>
          )}

          {/* Hidden file input + visible label */}
          <input
            type="file"
            id="file-upload"
            className="hidden"
            accept=".pdf,.jpg,.jpeg,.png,.docx,.doc,.pptx,.ppt,.txt"
            onChange={handleFileChange}
          />
          <label
            htmlFor="file-upload"
            className="px-6 py-3 bg-white/10 hover:bg-white/20 border border-white/30 rounded-xl text-white font-medium cursor-pointer transition"
          >
            Browse Files
          </label>
        </div>
      </div>

      {/* Error banner */}
      {displayError && (
        <div className="mt-4 flex items-start gap-3 bg-red-500/20 border border-red-500/40 text-red-200 px-4 py-3 rounded-xl text-sm">
          <AlertCircle className="w-5 h-5 shrink-0 mt-0.5" />
          <span>{displayError}</span>
        </div>
      )}

      {/* Submit button */}
      <button
        onClick={handleSubmit}
        disabled={!file || isProcessing}
        className={`w-full mt-6 py-4 rounded-xl font-bold text-lg transition-all transform ${
          isProcessing
            ? 'bg-black text-white cursor-wait scale-95'
            : !file
            ? 'bg-white/5 text-white/30 cursor-not-allowed'
            : 'bg-gradient-to-r from-gray-800 to-black text-white hover:scale-105 hover:shadow-2xl hover:shadow-gray-500/50'
        }`}
      >
        {isProcessing ? (
          <span className="flex items-center justify-center gap-3">
            <div className="w-5 h-5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            Processing… please wait
          </span>
        ) : (
          'Start Reading'
        )}
      </button>
    </div>
  );
};

export default UploadSection;