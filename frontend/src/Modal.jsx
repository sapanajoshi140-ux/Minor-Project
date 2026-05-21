const Modal = ({ isOpen, onClose, children, title, hideCloseButton = false }) => {
  if (!isOpen) return null;

  return (
    <div 
      className={`fixed inset-0 z-1100 flex items-center justify-center ${
        hideCloseButton ? '' : 'bg-black/50 backdrop-blur-md'
      }`}
      onClick={hideCloseButton ? undefined : onClose}
    >
      <div 
        className={`relative w-full max-w-md p-10 mx-9 rounded-[2rem] bg-white/10 border border-white/20 text-white ${
          hideCloseButton ? '' : 'shadow-2xl'
        }`}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        {/* Only show close button if hideCloseButton is false */}
        {!hideCloseButton && (
          <button 
            className="absolute top-4 right-4 text-2xl opacity-70 hover:opacity-100"
            onClick={onClose}
            aria-label="Close modal"
          >
            &times;
          </button>
        )}

        {title && (
          <div className="mb-6 text-center">
            <h1 id="modal-title" className="text-3xl font-semibold">{title}</h1>
          </div>
        )}

        {children}
      </div>
    </div>
  );
};

export default Modal;