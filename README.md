# 📚 READWITHEASE - A Document Intelligence Platform

**A modern, AI-powered document management and analysis system with intelligent RAG-based Q&A, OCR support, and real-time collaboration features.**

---

## 📋 Overview

The **Document Intelligence Platform** is a comprehensive 3rd-year academic project that combines modern web technologies with advanced AI/ML capabilities. It enables users to upload, process, and intelligently analyze documents through a powerful RAG pipeline, OCR processing, and an intuitive interface.

**Key Capabilities:**
- 🔐 **Secure Authentication** - JWT tokens, OAuth 2.0 integration, email verification
- 📄 **Multi-Format Support** - PDF, DOCX, PPTX, TXT, PNG, JPG with automatic conversion
- 🤖 **AI Q&A** - Retrieval-Augmented Generation using Ollama LLM with streaming responses
- 🔍 **Advanced OCR** - EasyOCR, TrOCR (handwritten), Tesseract with confidence scoring
- 📊 **Analytics Dashboard** - Reading stats, word frequency, time tracking
- 🎨 **Interactive PDF Viewer** - Built-in annotations, highlighting, note-taking

**Target Users:**
- Students and researchers analyzing academic papers
- Professionals managing document-heavy workflows
- Anyone seeking intelligent document insights without manual reading

---

## ✨ Features

### **User Authentication & Security**
- ✅ Email-based signup and login with JWT authentication
- ✅ Google OAuth 2.0 integration
- ✅ Email verification with secure token-based links
- ✅ Password reset with expiring reset tokens
- ✅ Password strength validation (8+ chars, uppercase, lowercase, digits)
- ✅ Token blacklisting on logout with automatic cleanup
- ✅ Secure refresh token mechanism (2-hour access tokens, 7-day refresh tokens)
- ✅ Role-based access patterns with user storage quotas

### **Document Management**
- ✅ Multi-format support: PDF, DOCX, PPTX, TXT, PNG, JPG, JPEG
- ✅ Automatic PDF generation from Office documents (searchable)
- ✅ Intelligent text extraction and chunking
- ✅ Storage quota tracking (100 MB per user)
- ✅ Document versioning and metadata tracking
- ✅ Batch document listing and deletion

### **Advanced OCR & Text Processing**
- ✅ **EasyOCR** - Fast, accurate text extraction from scanned documents
- ✅ **TrOCR (Handwritten OCR)** - Transformer-based handwritten text recognition
- ✅ **Tesseract OCR** - Fallback OCR with multi-language support
- ✅ **PyMuPDF** - Fast PDF processing and rendering
- ✅ Confidence scoring for extracted text
- ✅ Bidi text support for RTL languages
- ✅ Image preprocessing using OpenCV and PIL

### **AI-Powered Q&A (RAG Pipeline)**
- ✅ **Retrieval-Augmented Generation** using Ollama LLM
- ✅ **Vector embeddings** via nomic-embed-text (768-dim)
- ✅ **ChromaDB** for efficient semantic search
- ✅ **Hybrid search** combining semantic and keyword matching
- ✅ **Streaming responses** for real-time token generation
- ✅ **Multi-document context** retrieval with top-k ranking
- ✅ **Session-based conversation** history
- ✅ **Smart disambiguation** for ambiguous queries (multi-topic handling)
- ✅ **Context-aware responses** with citation tracking

### **Intelligent Summarization**
- ✅ Configurable summary lengths (short, medium, long, bullets)
- ✅ Streaming summarization for real-time feedback
- ✅ Text selection summarization from PDF
- ✅ Preserves key terms and numerical data

### **Interactive PDF Viewer**
- ✅ Embedded PDF reading with page navigation
- ✅ Text selection and highlighting (per-page notes)
- ✅ Page-specific note-taking with auto-save
- ✅ Real-time theme switching (light/dark/custom)
- ✅ Responsive design for desktop and tablet

### **Reading Dashboard**
- ✅ Multi-document workspace with split-view layout
- ✅ Integrated chat panel for document Q&A
- ✅ Real-time AI assistant response streaming
- ✅ Text-to-speech for accessibility
- ✅ Theme customization with 6+ preset themes
- ✅ Resizable panels with persistent state
- ✅ Reading progress tracking

### **Performance & Reliability**
- ✅ Rate limiting (signup 5/min, login 5/min, password reset 3/hour)
- ✅ Automatic token cleanup via APScheduler (daily)
- ✅ Database connection pooling
- ✅ CORS protection with environment-based origin validation
- ✅ Comprehensive error handling and user feedback

---

## 🛠️ Tech Stack

### **Frontend** (43.8% JavaScript)
| Category | Technologies |
|----------|--------------|
| **Framework** | React 19.2.0, Vite 7.2.4 |
| **State Management** | Context API, Custom Hooks |
| **UI/Styling** | Tailwind CSS 4.1.18, Framer Motion 12.24.12 |
| **Icons** | Lucide React 0.562, React Icons 5.6.0 |
| **PDF Handling** | react-pdf 10.4.1, pdfjs-dist 3.4.120 |
| **Charts** | Chart.js 4.5.1, react-chartjs-2 5.3.1 |
| **Routing** | React Router DOM 7.12.0 |
| **Auth** | @react-oauth/google 0.13.4 |
| **Development** | ESLint 9.39.1, Vite 7.2.4 |

### **Backend - Authentication Service** (Python)
| Category | Technologies |
|----------|--------------|
| **Framework** | FastAPI 0.128.0, Uvicorn 0.40.0 |
| **Auth** | PyJWT 2.10.1, bcrypt 5.0.0 |
| **Database** | SQLAlchemy 2.0.45, PyMySQL 1.1.2 |
| **Security** | Rate Limiting (slowapi 0.1.9) |
| **Scheduling** | APScheduler 3.10.4 |
| **Email** | fastapi-mail 1.6.1, aiosmtplib 5.0.0 |
| **Validation** | Pydantic 2.12.5 |

### **Backend - Document & RAG Service** (Python)
| Category | Technologies |
|----------|--------------|
| **Framework** | FastAPI 0.128.0, Uvicorn 0.40.0 |
| **Document Processing** | python-docx 1.2.0, python-pptx 1.0.2, PyMuPDF 1.26.7, lxml 6.0.2 |
| **OCR** | EasyOCR 1.7.2, pytesseract 0.3.13, TrOCR (transformers 4.51.3) |
| **Image Processing** | opencv-python 4.10.0, Pillow 12.1.0, numpy 2.4.2 |
| **AI/ML** | torch 2.10.0, torchvision 0.25.0, transformers 4.51.3, huggingface_hub |
| **Vector DB** | ChromaDB (in-memory/persistent) |
| **Embeddings** | Ollama nomic-embed-text |
| **LLM** | Ollama llama3 (or configurable) |
| **Text Processing** | langchain, RecursiveCharacterTextSplitter |
| **PDF Generation** | reportlab 4.4.1 |

### **Infrastructure**
| Component | Technology |
|-----------|-----------|
| **Environment** | python-dotenv 1.2.1 |
| **HTTP Client** | httpx 0.28.1 |
| **Async** | asyncio (Python standard), greenlet 3.3.0 |

---

## 📁 Folder Structure

```
Minor-Project/
├── backend/
│   ├── Login_signup/
│   │   ├── auth.py              # JWT token creation, password hashing, Google OAuth
│   │   ├── database.py          # SQLAlchemy models (User, RevokedToken)
│   │   ├── email_config.py      # SMTP email setup and HTML templates
│   │   ├── main.py              # Auth endpoints (signup, login, refresh, logout, etc.)
│   │   └── schemas.py           # Pydantic request/response models
│   ├── document_workspace/
│   │   ├── app/
│   │   │   ├── config.py        # Configuration loading from .env
│   │   │   ├── database.py      # SQLAlchemy models for documents/pages
│   │   │   ├── dependencies.py  # FastAPI dependency injection
│   │   │   ├── main.py          # Document upload, OCR, RAG endpoints
│   │   │   ├── schemas.py       # Pydantic models for document operations
│   │   │   ├── services/        # Business logic services
│   │   │   ├── routes/          # Route handlers
│   │   │   ├── utils/           # Utility functions
│   │   │   └── wordlogic.py     # Word extraction and analysis
│   │   ├── rag/
│   │   │   ├── ingest.py        # Document ingestion, chunking, embedding
│   │   │   ├── generate.py      # LLM answer generation, summarization, streaming
│   │   │   ├── retrieve.py      # Hybrid search and chunk retrieval
│   │   │   └── vector_db.py     # ChromaDB wrapper and Chunk dataclass
│   │   ├── uploads/             # User-uploaded files (runtime)
│   │   ├── download_models.py   # Script to pre-download OCR models
│   │   └── requirement.txt      # Backend dependencies
│   └── .gitignore
├── frontend/
│   ├── src/
│   │   ├── App.jsx              # Main app router and layout
│   │   ├── AuthContext.jsx      # Auth state and token management
│   │   ├── Workspace.jsx        # Main document workspace (63KB)
│   │   ├── Chatpanel.jsx        # AI chat panel with streaming (21KB)
│   │   ├── ReadingDashboard.jsx # Dashboard with analytics (57KB)
│   │   ├── PdfViewer.jsx        # PDF viewer component
│   │   ├── LoginModal.jsx       # Login form with Google OAuth
│   │   ├── SignUpModal.jsx      # Signup with email verification
│   │   ├── ForgotPasswordModal.jsx  # Password reset flow
│   │   ├── SettingsModal.jsx    # User preferences and themes
│   │   ├── NoteSection.jsx      # Per-page note management
│   │   ├── UploadSection.jsx    # Multi-file upload handler
│   │   ├── Dashboard.jsx        # User dashboard
│   │   ├── Features.jsx         # Landing page features
│   │   ├── Navbar.jsx           # Navigation bar
│   │   ├── HeroSlider.jsx       # Hero carousel
│   │   ├── footer.jsx           # Footer component
│   │   ├── Modal.jsx            # Base modal component
│   │   ├── Hooks.jsx            # Custom React hooks
│   │   ├── VerifyEmail.jsx      # Email verification page
│   │   ├── Passwordreset.jsx    # Password reset page
│   │   ├── assets/              # Images, icons, media
│   │   ├── App.css              # App-level styles
│   │   ├── index.css            # Global styles and variables
│   │   ├── main.jsx             # React entry point
│   │   └── Buttons.jsx          # Reusable button components
│   ├── public/                  # Static assets
│   ├── package.json             # Frontend dependencies
│   ├── vite.config.js           # Vite build configuration
│   ├── eslint.config.js         # ESLint rules
│   └── .gitignore
├── README.md                    # This file
└── .github/
    └── workflows/               # CI/CD pipelines (if any)
```

### **Key Directories Explained**

| Directory | Purpose |
|-----------|---------|
| `backend/Login_signup/` | Complete authentication service with JWT, OAuth, email verification |
| `backend/document_workspace/app/` | Document upload, OCR, and workspace management APIs |
| `backend/document_workspace/rag/` | RAG pipeline (ingestion, embedding, retrieval, generation) |
| `frontend/src/` | React components, hooks, and application logic |

---

## 🚀 Installation

### **Prerequisites**
- **Node.js 18+** & npm/pnpm
- **Python 3.10+**
- **MySQL 8.0+**
- **Ollama** (with llama3 and nomic-embed-text models)
- **Git**

### **Step 1: Clone the Repository**
```bash
git clone https://github.com/sapanajoshi140-ux/Minor-Project.git
cd Minor-Project
```

### **Step 2: Setup Backend - Authentication Service**

#### Install Python Dependencies
```bash
cd backend
pip install -r requirement.txt
```

#### Configure Environment Variables
Create a `.env` file in `backend/Login_signup/`:
```env
# Database
DATABASE_URL=mysql+pymysql://username:password@localhost:3306/minor_project_auth

# JWT
JWT_SECRET=your-super-secret-jwt-key-change-this-in-production
JWT_ALGORITHM=HS256

# CORS
CORS_ORIGINS=http://localhost:5173,http://localhost:3000,https://yourdomain.com

# Email (SMTP)
MAIL_USERNAME=your-email@gmail.com
MAIL_PASSWORD=your-app-password
MAIL_FROM=noreply@yourapp.com
MAIL_PORT=587
MAIL_SERVER=smtp.gmail.com
MAIL_TLS=true
MAIL_SSL=false

# URLs
FRONTEND_URL=http://localhost:5173
BACKEND_URL=http://localhost:8000
```

#### Initialize Database
```bash
# FastAPI with SQLAlchemy will auto-create tables on startup
# Just ensure your MySQL server is running and DATABASE_URL is correct
```

#### Start Auth Service
```bash
cd backend/Login_signup
uvicorn main:app --reload --host 0.0.0.0 --port 8000
# Visit: http://localhost:8000/docs (Swagger UI)
```

---

### **Step 3: Setup Backend - Document & RAG Service**

#### Install Python Dependencies
```bash
cd backend/document_workspace
pip install -r ../requirement.txt

# Or manually install OCR models:
# python download_models.py  # Downloads EasyOCR, TrOCR models
```

#### Configure Environment Variables
Create a `.env` file in `backend/document_workspace/`:
```env
# Database
DATABASE_URL=mysql+pymysql://username:password@localhost:3306/minor_project_documents

# Ollama (for LLM and embeddings)
OLLAMA_BASE_URL=http://localhost:11434
LLM_MODEL=llama3
EMBEDDING_MODEL=nomic-embed-text
CONTEXT_WINDOW=4096
LLM_TIMEOUT=120

# Chunking
CHUNK_SIZE=400
CHUNK_OVERLAP=80
EMBEDDING_DIM=768
EMBED_BATCH_SIZE=32
EMBED_TIMEOUT=60

# JWT Auth (same as auth service)
JWT_SECRET=your-super-secret-jwt-key-change-this-in-production

# CORS
CORS_ORIGINS=http://localhost:5173,http://localhost:3000

# Auth Backend URL
AUTH_BACKEND_URL=http://localhost:8000

# File Upload
MAX_FILE_SIZE_MB=100
UPLOAD_DIR=./uploads
```

#### Verify Ollama is Running
```bash
# In another terminal, start Ollama:
ollama serve

# In another terminal, pull required models:
ollama pull llama3
ollama pull nomic-embed-text

# Test:
curl http://localhost:11434/api/tags
```

#### Start Document Service
```bash
cd backend/document_workspace/app
uvicorn main:app --reload --host 0.0.0.0 --port 8001
# Visit: http://localhost:8001/docs
```

---

### **Step 4: Setup Frontend**

#### Install Dependencies
```bash
cd frontend
npm install
# or
pnpm install
```

#### Configure Environment Variables
Create a `.env.local` file in `frontend/`:
```env
VITE_AUTH_API_URL=http://localhost:8000
VITE_RAG_API_URL=http://localhost:8001
VITE_GOOGLE_CLIENT_ID=your-google-client-id.apps.googleusercontent.com
```

#### Start Development Server
```bash
npm run dev
# Frontend will be available at http://localhost:5173
```

---

### **Step 5: Verify the Setup**

1. **Auth Backend:** http://localhost:8000/docs
2. **RAG Backend:** http://localhost:8001/docs
3. **Frontend:** http://localhost:5173

Try signing up with a test email and uploading a PDF!

---

## 🔧 Environment Variables

### **Backend - Auth Service (.env)**

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | - | MySQL connection string: `mysql+pymysql://user:pass@host/db` |
| `JWT_SECRET` | - | Secret key for JWT signing (min 32 chars) |
| `JWT_ALGORITHM` | `HS256` | JWT algorithm |
| `CORS_ORIGINS` | - | Comma-separated allowed origins |
| `MAIL_USERNAME` | - | SMTP email address |
| `MAIL_PASSWORD` | - | SMTP password or app-specific password |
| `MAIL_FROM` | - | Sender email address |
| `MAIL_SERVER` | `smtp.gmail.com` | SMTP server |
| `MAIL_PORT` | `587` | SMTP port |
| `MAIL_TLS` | `true` | Use TLS |
| `FRONTEND_URL` | - | Frontend base URL (for verification links) |
| `BACKEND_URL` | - | Backend base URL |

### **Backend - Document Service (.env)**

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | - | MySQL connection string |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama API endpoint |
| `LLM_MODEL` | `llama3` | Language model to use |
| `EMBEDDING_MODEL` | `nomic-embed-text` | Embedding model |
| `CONTEXT_WINDOW` | `4096` | Context window size |
| `LLM_TIMEOUT` | `120` | LLM request timeout (seconds) |
| `CHUNK_SIZE` | `400` | Document chunk size (characters) |
| `CHUNK_OVERLAP` | `80` | Overlap between chunks |
| `EMBEDDING_DIM` | `768` | Embedding dimensions |
| `EMBED_BATCH_SIZE` | `32` | Batch size for embedding |
| `JWT_SECRET` | - | Same JWT secret as auth service |
| `CORS_ORIGINS` | - | Allowed frontend origins |
| `MAX_FILE_SIZE_MB` | `100` | Max upload file size |

### **Frontend (.env.local)**

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_AUTH_API_URL` | - | Auth backend base URL |
| `VITE_RAG_API_URL` | - | Document/RAG backend base URL |
| `VITE_GOOGLE_CLIENT_ID` | - | Google OAuth 2.0 client ID |

---

## 📖 Usage

### **User Workflow**

#### **1. Authentication**
```bash
# Signup
POST /signup
{
  "email": "user@example.com",
  "full_name": "John Doe",
  "password": "SecurePass123",
  "confirm_password": "SecurePass123"
}

# Login
POST /login
{
  "email": "user@example.com",
  "password": "SecurePass123"
}
# Response:
{
  "access_token": "eyJ0eXAiOiJKV1QiLC...",
  "refresh_token": "eyJ0eXAiOiJKV1QiLC..."
}
```

#### **2. Upload Document**
1. Click "Upload" in the frontend
2. Select a file (PDF, DOCX, PPTX, TXT, PNG, JPG)
3. System extracts text/OCR automatically
4. Document appears in workspace

#### **3. Chat with Document**
1. Open document in PDF viewer
2. Type question in chat panel
3. AI streams contextual answer from document
4. Select text → "Summarize" for instant summary

#### **4. View Analytics**
- Reading Dashboard shows document stats
- Word frequency charts
- Reading time estimates
- Multiple theme options

---

## 🔌 API Documentation

### **Authentication Endpoints** (Port 8000)

#### **Signup**
```
POST /signup
Content-Type: application/json

{
  "email": "user@example.com",
  "full_name": "John Doe",
  "password": "SecurePass123",
  "confirm_password": "SecurePass123"
}

Response 200:
{
  "message": "Signup successful. Please check your email to verify."
}
```

#### **Login**
```
POST /login
Content-Type: application/json

{
  "email": "user@example.com",
  "password": "SecurePass123"
}

Response 200:
{
  "access_token": "eyJ0eXAi...",
  "refresh_token": "eyJ0eXAi..."
}
```

#### **Google Login**
```
POST /google-login
Content-Type: application/json

{
  "google_access_token": "ya29.a0Af..."
}

Response 200:
{
  "access_token": "eyJ0eXAi...",
  "refresh_token": "eyJ0eXAi..."
}
```

#### **Refresh Token**
```
POST /refresh
Content-Type: application/json
Authorization: Bearer <refresh_token>

{
  "refresh_token": "eyJ0eXAi..."
}

Response 200:
{
  "access_token": "eyJ0eXAi..."
}
```

#### **Logout**
```
POST /logout
Authorization: Bearer <access_token>

{
  "refresh_token": "eyJ0eXAi..."
}

Response 200:
{
  "message": "Logged out successfully"
}
```

#### **Verify Email**
```
GET /verify-email?token=<email_verification_token>

Response 200:
{
  "message": "Email verified successfully!",
  "redirect": "http://localhost:5173/login"
}
```

#### **Change Password**
```
POST /change-password
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "current_password": "OldPass123",
  "new_password": "NewPass456",
  "confirm_new_password": "NewPass456"
}

Response 200:
{
  "message": "Password changed successfully"
}
```

#### **Get Current User**
```
GET /me
Authorization: Bearer <access_token>

Response 200:
{
  "email": "user@example.com",
  "full_name": "John Doe",
  "is_google_user": false,
  "has_password": true
}
```

---

### **Document & RAG Endpoints** (Port 8001)

#### **Upload Document**
```
POST /upload
Authorization: Bearer <access_token>
Content-Type: multipart/form-data

file: <binary_file>

Response 201:
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "report.pdf",
  "file_size": 2048576,
  "pages": 25,
  "extraction_status": "completed",
  "extracted_text": "...",
  "created_at": "2025-05-24T10:30:00Z"
}
```

#### **List Documents**
```
GET /documents
Authorization: Bearer <access_token>

Response 200:
{
  "documents": [
    {
      "document_id": "550e8400-e29b-41d4-a716-446655440000",
      "filename": "report.pdf",
      "created_at": "2025-05-24T10:30:00Z",
      "pages": 25
    }
  ]
}
```

#### **Get Document**
```
GET /documents/{document_id}
Authorization: Bearer <access_token>

Response 200:
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "filename": "report.pdf",
  "file_size": 2048576,
  "pages": 25,
  "extracted_text": "...",
  "created_at": "2025-05-24T10:30:00Z"
}
```

#### **Delete Document**
```
DELETE /documents/{document_id}
Authorization: Bearer <access_token>

Response 200:
{
  "message": "Document deleted successfully"
}
```

#### **Chat with Document (Streaming)**
```
POST /chat/stream
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "question": "What is the main topic?",
  "doc_ids": ["550e8400-e29b-41d4-a716-446655440000"],
  "session_id": null,
  "top_k": 5,
  "use_hybrid": true
}

Response 200 (Server-Sent Events / Streaming):
event: meta
data: {"session_id": "sess_abc123"}

data: The
data: main
data: topic
data: is...

event: meta
data: [DONE]
```

#### **Summarize Text (Streaming)**
```
POST /summarize/stream
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "text": "Long text to summarize...",
  "length": "medium"
}

Response 200 (Streaming):
data: This
data: is
data: a
data: summary...
```

#### **Get Session History**
```
GET /session/{session_id}
Authorization: Bearer <access_token>

Response 200:
{
  "session_id": "sess_abc123",
  "messages": [
    {"role": "user", "content": "What is the topic?"},
    {"role": "assistant", "content": "The main topic is..."}
  ]
}
```

#### **Delete Session**
```
DELETE /session/{session_id}
Authorization: Bearer <access_token>

Response 200:
{
  "message": "Session deleted successfully"
}
```

#### **Get Storage Usage**
```
GET /me/storage
Authorization: Bearer <access_token>

Response 200:
{
  "used_bytes": 52428800,
  "limit_bytes": 104857600,
  "used_mb": 50.0,
  "limit_mb": 100.0,
  "available_bytes": 52428800
}
```

#### **Get Dashboard**
```
GET /me/dashboard
Authorization: Bearer <access_token>

Response 200:
{
  "stats": {
    "total_time_read_minutes": 245.5,
    "today_read_minutes": 45.0,
    "daily_goal_minutes": 60,
    "documents_read": 12,
    "total_documents_uploaded": 18,
    "current_streak_days": 5,
    "best_streak_days": 12
  },
  "daily_chart": [...],
  "recent_documents": [...],
  "vocabulary": [...]
}
```

#### **Set Reading Goal**
```
PUT /me/reading-goal
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "daily_goal_min": 90
}

Response 200:
{
  "user_id": 1,
  "daily_goal_min": 90,
  "message": "Daily reading goal set to 90 minutes."
}
```

#### **Start Reading Session**
```
POST /reading-session/start
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "document_id": "550e8400-e29b-41d4-a716-446655440000"
}

Response 200:
{
  "session_id": "sess_abc123",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "started_at": "2025-05-24T10:30:00Z",
  "message": "Reading session started."
}
```

#### **End Reading Session**
```
POST /reading-session/end
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "session_id": "sess_abc123",
  "active_seconds": 1800
}

Response 200:
{
  "session_id": "sess_abc123",
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "duration_seconds": 1800,
  "duration_minutes": 30.0,
  "message": "Reading session recorded."
}
```

#### **Get Page Notes**
```
GET /documents/{document_id}/notes
Authorization: Bearer <access_token>

Response 200:
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "notes": [
    {
      "document_id": "550e8400-e29b-41d4-a716-446655440000",
      "page_number": 5,
      "note_text": "Important concept here",
      "updated_at": "2025-05-24T10:30:00Z"
    }
  ]
}
```

#### **Upsert Page Note**
```
PUT /documents/{document_id}/pages/{page_number}/note
Authorization: Bearer <access_token>
Content-Type: application/json

{
  "note_text": "Important concept here"
}

Response 200:
{
  "document_id": "550e8400-e29b-41d4-a716-446655440000",
  "page_number": 5,
  "note_text": "Important concept here",
  "updated_at": "2025-05-24T10:30:00Z"
}
```

#### **Delete Page Note**
```
DELETE /documents/{document_id}/pages/{page_number}/note
Authorization: Bearer <access_token>

Response 204: No Content
```

#### **Get Word Meaning**
```
GET /dictionary/{word}/meaning?document_id=<doc_id>
Authorization: Bearer <access_token>

Response 200:
{
  "word": "ephemeral",
  "meaning": "lasting for a very short time",
  "synonym": "transitory",
  "example": "The beauty of cherry blossoms is ephemeral.",
  "source": "Dictionary API"
}
```

#### **Get Word Pronunciation**
```
GET /dictionary/{word}/pronounce
Authorization: Bearer <access_token>

Response 200: (Audio MP3 file with X-Phonetic header)
Content-Type: audio/mpeg
X-Phonetic: /ˈefəmərəl/
```

#### **Health Check**
```
GET /health

Response 200:
{
  "status": "ok",
  "sessions": 12
}
```

---

## 💾 Database Schema

### **Auth Service Database**

#### **users** table
```sql
CREATE TABLE users (
  id INT PRIMARY KEY AUTO_INCREMENT,
  email VARCHAR(255) UNIQUE NOT NULL,
  full_name VARCHAR(255) NOT NULL,
  hashed_password VARCHAR(255),
  is_verified BOOLEAN DEFAULT FALSE,
  is_google_user BOOLEAN DEFAULT FALSE,
  has_password BOOLEAN DEFAULT FALSE,
  used_storage_bytes BIGINT DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### **revoked_tokens** table
```sql
CREATE TABLE revoked_tokens (
  id INT PRIMARY KEY AUTO_INCREMENT,
  jti VARCHAR(36) UNIQUE NOT NULL INDEX,
  token_type VARCHAR(20) NOT NULL,
  expires_at DATETIME NOT NULL,
  revoked_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

### **Document Service Database**

#### **documents** table
```sql
CREATE TABLE documents (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_id INT NOT NULL,
  document_id VARCHAR(36) UNIQUE NOT NULL,
  filename VARCHAR(255) NOT NULL,
  file_size BIGINT,
  file_path VARCHAR(512),
  generated_pdf_path VARCHAR(512),
  total_pages INT,
  document_category VARCHAR(20),
  processing_status VARCHAR(20),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

#### **document_pages** table
```sql
CREATE TABLE document_pages (
  id INT PRIMARY KEY AUTO_INCREMENT,
  document_id VARCHAR(36) NOT NULL,
  page_number INT,
  extracted_text LONGTEXT,
  formatted_text LONGTEXT,
  ocr_type VARCHAR(20),
  confidence_score FLOAT,
  formatting_status VARCHAR(20),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

#### **reading_sessions** table
```sql
CREATE TABLE reading_sessions (
  id VARCHAR(36) PRIMARY KEY,
  user_id INT NOT NULL,
  document_id VARCHAR(36),
  started_at DATETIME NOT NULL,
  ended_at DATETIME,
  duration_seconds INT,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

#### **page_notes** table
```sql
CREATE TABLE page_notes (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_id INT NOT NULL,
  document_id VARCHAR(36) NOT NULL,
  page_number INT,
  note_text LONGTEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

#### **user_preferences** table
```sql
CREATE TABLE user_preferences (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_id INT UNIQUE NOT NULL,
  theme VARCHAR(50) DEFAULT 'light',
  daily_goal_min INT DEFAULT 60,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME ON UPDATE CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

---

## 🤝 Contributing

We welcome contributions! Here's how to get started:

1. **Fork the repository**
2. **Create a feature branch** (`git checkout -b feature/amazing-feature`)
3. **Commit changes** (`git commit -m 'Add amazing feature'`)
4. **Push to branch** (`git push origin feature/amazing-feature`)
5. **Open a Pull Request**

### **Development Guidelines**
- Follow existing code style and patterns
- Add tests for new features
- Update documentation accordingly
- Test thoroughly before submitting PR

---

## 📝 License

This project is licensed under the **MIT License** - see the LICENSE file for details.

---

## 🙏 Acknowledgments

- **Ollama** for the amazing open-source LLM infrastructure
- **ChromaDB** for efficient vector database
- **React** and **FastAPI** communities
- **All contributors** who help improve this project

---

## 📧 Contact & Support

For questions, issues, or suggestions:
- **GitHub Issues:** [Report Issues](https://github.com/sapanajoshi140-ux/Minor-Project/issues)
- **Email:** sapanajoshi140@gmail.com

---

**Happy Reading! 📖✨**
