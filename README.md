# 📚 READWITHEASE- A Document Intelligence Platform

**A modern, AI-powered document management and analysis system with intelligent RAG-based Q&A, OCR support, and real-time collaboration features.**

---

## 📋 Overview

The **Document Intelligence Platform** is a comprehensive 3rd-year academic project that combines modern web technologies with advanced AI/ML capabilities. It enables users to upload, process, and intelligently query documents through a conversational AI interface. The platform supports multiple document formats (PDF, DOCX, PPTX, images), processes them using advanced OCR and text extraction, and provides AI-driven insights through a Retrieval-Augmented Generation (RAG) pipeline powered by Ollama LLM.

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

### **Frontend**
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

### **Backend - Authentication Service**
| Category | Technologies |
|----------|--------------|
| **Framework** | FastAPI 0.128.0, Uvicorn 0.40.0 |
| **Auth** | PyJWT 2.10.1, bcrypt 5.0.0 |
| **Database** | SQLAlchemy 2.0.45, PyMySQL 1.1.2 |
| **Security** | Rate Limiting (slowapi 0.1.9) |
| **Scheduling** | APScheduler 3.10.4 |
| **Email** | fastapi-mail 1.6.1, aiosmtplib 5.0.0 |
| **Validation** | Pydantic 2.12.5 |

### **Backend - Document & RAG Service**
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
│   │   ├── download models.py   # Script to pre-download OCR models
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
# python download\ models.py  # Downloads EasyOCR, TrOCR models
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

#### **reading_goals** table
```sql
CREATE TABLE reading_goals (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_id INT NOT NULL UNIQUE,
  daily_goal_min INT DEFAULT 60,
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
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);
```

#### **user_vocabulary** table
```sql
CREATE TABLE user_vocabulary (
  id INT PRIMARY KEY AUTO_INCREMENT,
  user_id INT NOT NULL,
  word VARCHAR(255) NOT NULL,
  document_id VARCHAR(36),
  looked_up_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
```

#### **dictionary** table
```sql
CREATE TABLE dictionary (
  id INT PRIMARY KEY AUTO_INCREMENT,
  word VARCHAR(255) UNIQUE NOT NULL,
  meaning LONGTEXT,
  synonym VARCHAR(255),
  phonetic VARCHAR(255),
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🤖 AI/ML Features

### **Document Ingestion Pipeline**

```
┌─────────────────────────────────────┐
│   User Uploads Document             │
│ (PDF, DOCX, PPTX, TXT, IMG)        │
└──────────────┬──────────────────────┘
               │
       ┌───────▼────────┐
       │ Is it Office?  │
       ├────────────────┤
       │ DOCX/PPTX/PPT  │◄──┐
       └────────────────┘   │
            │               │
    ┌───────▼───────────────┘
    │ Generate Searchable PDF
    │ (python-pptx, python-docx)
    └───────┬────────────────────────┐
            │                        │
    ┌───────▼────────┐    ┌─────────▼──┐
    │ Is Image/PNG?  │    │ Text/PDF?  │
    └────────────────┘    └────────────┘
        │                      │
    ┌───▼──────────────────────▼──────┐
    │  Run OCR                        │
    │ (EasyOCR, TrOCR, Tesseract)    │
    └────────────┬────────────────────┘
                 │
          ┌──────▼──────────────┐
          │ Extract Text        │
          │ (PyMuPDF, TextLoader)
          └──────┬───────────────┘
                 │
          ┌──────▼──────────────────────┐
          │ Split into Chunks           │
          │ (RecursiveCharacterSplitter)│
          │ Chunk Size: 400 chars       │
          │ Overlap: 80 chars           │
          └──────┬─────────────────────┘
                 │
          ┌──────▼──────────────────────┐
          │ Generate Embeddings         │
          │ (Ollama nomic-embed-text)   │
          │ Dim: 768                    │
          └──────┬─────────────────────┘
                 │
          ┌──────▼──────────────────────┐
          │ Store in ChromaDB           │
          │ + Metadata (page, doc_id)   │
          └──────────────────────────────┘
```

### **Query/Answer Generation Pipeline**

```
┌──────────────────────────┐
│ User Question            │
└────────┬─────────────────┘
         │
  ┌──────▼────────────────┐
  │ Query → Embedding      │
  │ (Ollama nomic-embed)   │
  └──────┬─────────────────┘
         │
  ┌──────▼──────────────────────────┐
  │ Hybrid Search                   │
  │ • Semantic (vector similarity)   │
  │ • Keyword (BM25)                │
  │ Top-K: 5 chunks                 │
  └──────┬───────────────────────────┘
         │
  ┌──────▼────────────────────────┐
  │ Disambiguation Check            │
  │ (Multi-topic handling)          │
  │ Request clarification if needed │
  └──────┬─────────────────────────┘
         │
  ┌──────▼─────────────────────────┐
  │ Build Context + Citations       │
  │ Format: [Source 1] (doc, page)  │
  └──────┬──────────────────────────┘
         │
  ┌──────▼──────────────────────────┐
  │ Send to LLM (Ollama llama3)      │
  │ • System prompt + context       │
  │ • Chat history (last 6 turns)   │
  │ • Temperature: 0 (deterministic)│
  │ • Context window: 4096 tokens   │
  └──────┬──────────────────────────┘
         │
  ┌──────▼──────────────────────────┐
  │ Stream Response                 │
  │ (Server-Sent Events)            │
  │ • Token-by-token delivery       │
  │ • Real-time UI updates          │
  └──────────────────────────────────┘
```

### **Summarization**

```
┌────────────────────────────┐
│ Selected Text (from PDF)   │
└────────┬───────────────────┘
         │
  ┌──────▼──────────────────┐
  │ Summarization Request    │
  │ Length: short/medium/long│
  └──────┬──────────────────┘
         │
  ┌──────▼──────────────────┐
  │ Send to Ollama llama3    │
  │ • Summarization prompt  │
  │ • Length instruction    │
  │ • Streaming enabled     │
  └──────┬──────────────────┘
         │
  ┌──────▼──────────────────┐
  │ Stream Summary          │
  │ (Real-time display)     │
  └──────────────────────────┘
```

### **OCR & Text Extraction**

| Document Type | Processing Method |
|---|---|
| **PDF** | PyMuPDF (fast, accurate) |
| **DOCX/DOC** | python-docx → searchable PDF → PyMuPDF |
| **PPTX/PPT** | python-pptx → searchable PDF → PyMuPDF |
| **TXT** | Direct text loading |
| **PNG/JPG/JPEG** | EasyOCR (primary) → TrOCR (handwritten) → Tesseract (fallback) |

### **Smart Chunking**

- **Chunk Size:** 400 characters (configurable)
- **Overlap:** 80 characters (to maintain context)
- **Metadata:** Page number, chunk position
- **Splitter:** RecursiveCharacterTextSplitter (respects paragraph/sentence boundaries)

### **Embedding & Vector Search**

- **Model:** Ollama nomic-embed-text
- **Dimensions:** 768
- **Vector DB:** ChromaDB (in-memory or persistent)
- **Search Types:**
  - **Semantic:** Cosine similarity on embeddings
  - **Keyword:** BM25-style full-text search
  - **Hybrid:** Combination of both

### **LLM Configuration**

- **Model:** Ollama llama3 (or configurable via .env)
- **Context Window:** 4096 tokens
- **Temperature:** 0 (deterministic, no randomness)
- **Timeout:** 120 seconds
- **Streaming:** Enabled for real-time token delivery

### **OCR Features**

#### **EasyOCR**
- Fast text extraction from images
- Multi-language support
- GPU acceleration capable
- Confidence scoring

#### **TrOCR (Handwritten OCR)**
- Transformer-based handwritten text recognition
- Specialized for cursive and handwriting
- Uses Microsoft's TrOCR model
- Better accuracy on historical documents

#### **Tesseract OCR**
- Fallback OCR engine
- Multi-language support (100+ languages)
- High accuracy for printed text
- Legacy document support

---

## 🔐 Authentication & Security

### **Authentication Flow**

```
┌──────────────────────────────┐
│ User/Frontend                │
└──────────┬───────────────────┘
           │
    ┌──────▼────────────────────────┐
    │ POST /login or /google-login  │
    └──────┬─────────────────────────┘
           │
    ┌──────▼────────────────────────┐
    │ Backend Validates Credentials │
    │ • Email + bcrypt password     │
    │ • Google token verification   │
    │ • Check email verified flag   │
    └──────┬─────────────────────────┘
           │
    ┌──────▼────────────────────────────┐
    │ Generate JWT Tokens               │
    │ • Access token (2h validity)      │
    │ • Refresh token (7d validity)     │
    │ • Include unique JTI per token    │
    └──────┬─────────────────────────────┘
           │
    ┌──────▼──────────────────────────────┐
    │ Return to Frontend                  │
    │ • access_token → Authorization      │
    │ • refresh_token → localStorage      │
    └──────────────────────────────────────┘

┌───────────────────────────────────────┐
│ Protected Endpoint Request            │
│ Authorization: Bearer <access_token>  │
└──────────┬────────────────────────────┘
           │
    ┌──────▼──────────────────────────┐
    │ Extract & Decode JWT            │
    │ • Check signature (JWT_SECRET)  │
    │ • Check expiration              │
    │ • Check if revoked (blacklist)  │
    └──────┬───────────────────────────┘
           │
    ┌──────▼────────────────────────┐
    │ Grant/Deny Access             │
    │ • Valid: Continue              │
    │ • Invalid: Return 401          │
    └────────────────────────────────┘
```

### **Security Features**

| Feature | Implementation |
|---------|-----------------|
| **Password Hashing** | bcrypt with salt rounds |
| **Password Strength** | Minimum 8 chars, 1 uppercase, 1 lowercase, 1 digit |
| **Email Verification** | Token-based verification links (1h expiry) |
| **Password Reset** | Time-limited reset tokens (30m expiry) |
| **Token Blacklisting** | JTI-based logout (in revoked_tokens table) |
| **Token Refresh** | Separate long-lived refresh tokens (7 days) |
| **Rate Limiting** | slowapi (5 signup/min, 5 login/min, 3 password reset/hour) |
| **CORS Protection** | Environment-based origin validation |
| **JWT Validation** | Signature, expiry, and type checks |
| **Automatic Cleanup** | APScheduler job removes expired tokens daily |
| **Storage Quota** | Per-user storage limits (100 MB default) |

### **Token Structure**

```json
{
  "sub": "user@example.com",
  "type": "access|refresh|email|reset",
  "jti": "550e8400-e29b-41d4-a716-446655440000",
  "exp": 1716546600,
  "iat": 1716539400
}
```

---

## 📄 File Processing Pipeline

### **Complete Document Upload Workflow**

```
1. User selects file in frontend
   │
2. Frontend validates file type & size
   │
3. POST /upload (multipart/form-data)
   │
4. Backend stores file to disk (/uploads)
   │
5. File type detection
   │
   ├─ PDF → PyMuPDF extract
   ├─ DOCX/PPTX → generate_searchable_pdf()
   ├─ TXT → TextLoader
   └─ PNG/JPG → Run OCR
   │
6. OCR Processing (for images/scans)
   ├─ EasyOCR (primary, fast)
   ├─ TrOCR (handwritten detection)
   └─ Tesseract (fallback)
   │
7. Store extracted text in DocumentPage rows
   │
8. Trigger RAG ingestion
   │
9. Split into chunks (400 chars, 80 overlap)
   │
10. Generate embeddings (nomic-embed-text)
   │
11. Store in ChromaDB
   │
12. Return document metadata to frontend
   │
13. Frontend displays document in workspace
```

### **Supported File Types**

| Extension | Processing | Notes |
|-----------|-----------|-------|
| **.pdf** | PyMuPDF | Native support, fast |
| **.docx** | → searchable PDF | Converts to PDF first |
| **.doc** | → searchable PDF | Converts to PDF first |
| **.pptx** | → searchable PDF | Converts to PDF first |
| **.ppt** | → searchable PDF | Converts to PDF first |
| **.txt** | TextLoader | Plain text ingestion |
| **.png** | OCR pipeline | EasyOCR + TrOCR + Tesseract |
| **.jpg/.jpeg** | OCR pipeline | EasyOCR + TrOCR + Tesseract |

---

## 🎨 Themes & UI

### **Theme System**

The frontend includes a CSS variable-based theming system supporting:

- **Light Theme** (default)
- **Dark Theme**
- **Sepia Theme**
- **HighContrast Theme**
- **Custom Themes** (user-configurable)

**Theme Variables:**
```css
--app-bg, --page-bg, --sidebar-bg
--page-text, --muted-text, --page-border
--bubble-user-bg, --bubble-user-text
--bubble-ai-bg, --bubble-ai-text, --bubble-ai-border
--chat-bg
```

### **Responsive Design**

- Mobile-first Tailwind CSS
- Breakpoints: sm (640px), md (768px), lg (1024px)
- Resizable chat panel (drag to resize)
- Touch-friendly on tablets
- PDF viewer optimized for all screen sizes

---

## ⚙️ Configuration

### **Key Config Files**

| File | Purpose |
|------|---------|
| `.env` (Auth) | Database, JWT, email, CORS settings |
| `.env` (RAG) | Ollama, chunking, embedding config |
| `.env.local` (Frontend) | API URLs, Google OAuth client ID |
| `vite.config.js` | Vite build configuration |
| `tailwind.config.js` | Tailwind CSS (implicit) |

### **Important Settings**

**Backend - Auth Service:**
- `JWT_ALGORITHM`: Default HS256
- `PASSWORD_STRENGTH`: Min 8 chars + uppercase + lowercase + digit
- `RATE_LIMITS`: signup 5/min, login 5/min, password reset 3/hour

**Backend - RAG Service:**
- `CHUNK_SIZE`: 400 (larger = more context per chunk)
- `CHUNK_OVERLAP`: 80 (overlap to maintain continuity)
- `EMBEDDING_DIM`: 768 (nomic-embed-text output)
- `LLM_TEMPERATURE`: 0 (deterministic answers)

**Frontend:**
- `VITE_AUTH_API_URL`: Backend URL (must match CORS_ORIGINS)
- `VITE_RAG_API_URL`: Document service URL
- `VITE_GOOGLE_CLIENT_ID`: OAuth 2.0 credential

---

## 🔧 Scripts

### **Frontend**

```bash
npm run dev         # Start Vite dev server (HMR enabled)
npm run build       # Production build (dist/)
npm run lint        # Run ESLint on src/
npm run preview     # Preview production build locally
```

### **Backend - Auth Service**

```bash
# In backend/Login_signup/

# Start development server
uvicorn main:app --reload

# With custom host/port
uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# Production (use gunicorn or similar)
gunicorn -w 4 -k uvicorn.workers.UvicornWorker main:app
```

### **Backend - Document Service**

```bash
# In backend/document_workspace/app/

# Start development server
uvicorn main:app --reload --port 8001

# Download OCR models (one-time)
python download\ models.py
```

### **Database Setup**

```bash
# Create databases
mysql -u root -p -e "CREATE DATABASE minor_project_auth;"
mysql -u root -p -e "CREATE DATABASE minor_project_documents;"

# Tables auto-created by SQLAlchemy on first run
```

---

## 🚢 Deployment

### **Local Deployment (Development)**

1. **Start Ollama:**
   ```bash
   ollama serve
   ```

2. **Start MySQL:**
   ```bash
   # Linux/Mac
   brew services start mysql

   # Windows (if installed via Docker)
   docker run -d -e MYSQL_ROOT_PASSWORD=password -p 3306:3306 mysql:8.0
   ```

3. **Terminal 1 - Auth Service:**
   ```bash
   cd backend/Login_signup
   source venv/bin/activate  # or venv\Scripts\activate on Windows
   uvicorn main:app --reload
   ```

4. **Terminal 2 - Document Service:**
   ```bash
   cd backend/document_workspace/app
   source venv/bin/activate
   uvicorn main:app --reload --port 8001
   ```

5. **Terminal 3 - Frontend:**
   ```bash
   cd frontend
   npm run dev
   ```

6. **Access:**
   - Frontend: http://localhost:5173
   - Auth API: http://localhost:8000/docs
   - RAG API: http://localhost:8001/docs

### **Docker Deployment (Recommended for Production)**

#### **Backend Dockerfile**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY backend/requirement.txt .
RUN pip install --no-cache-dir -r requirement.txt

COPY backend/ ./

CMD ["uvicorn", "Login_signup.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

#### **Frontend Dockerfile**
```dockerfile
FROM node:18-alpine AS builder

WORKDIR /app

COPY frontend/package*.json ./
RUN npm ci

COPY frontend/ ./
RUN npm run build

FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
```

#### **Docker Compose**
```yaml
version: "3.8"

services:
  mysql:
    image: mysql:8.0
    environment:
      MYSQL_ROOT_PASSWORD: rootpass
      MYSQL_DATABASE: minor_project_auth
    volumes:
      - mysql_data:/var/lib/mysql

  ollama:
    image: ollama/ollama:latest
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

  auth_backend:
    build:
      context: .
      dockerfile: backend/Dockerfile.auth
    ports:
      - "8000:8000"
    environment:
      DATABASE_URL: mysql+pymysql://root:rootpass@mysql:3306/minor_project_auth
      JWT_SECRET: ${JWT_SECRET}
      CORS_ORIGINS: http://localhost:5173,http://localhost:3000
      FRONTEND_URL: http://localhost:5173
    depends_on:
      - mysql

  rag_backend:
    build:
      context: .
      dockerfile: backend/Dockerfile.rag
    ports:
      - "8001:8001"
    environment:
      DATABASE_URL: mysql+pymysql://root:rootpass@mysql:3306/minor_project_documents
      OLLAMA_BASE_URL: http://ollama:11434
      JWT_SECRET: ${JWT_SECRET}
    depends_on:
      - mysql
      - ollama

  frontend:
    build:
      context: .
      dockerfile: frontend/Dockerfile
    ports:
      - "80:80"
    environment:
      VITE_AUTH_API_URL: http://localhost:8000
      VITE_RAG_API_URL: http://localhost:8001

volumes:
  mysql_data:
  ollama_data:
```

---

## 🐛 Troubleshooting

### **Common Issues**

#### **1. "CORS_ORIGINS is not set"**
- **Problem:** Backend starts with ValueError
- **Solution:** Add `CORS_ORIGINS` to `.env` file
  ```env
  CORS_ORIGINS=http://localhost:5173,http://localhost:3000
  ```

#### **2. "JWT_SECRET not found"**
- **Problem:** Auth service fails on startup
- **Solution:** Generate a secure key and add to `.env`
  ```bash
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

#### **3. "Database connection refused"**
- **Problem:** Cannot connect to MySQL
- **Solution:** 
  - Verify MySQL is running
  - Check connection string in `.env`
  - Ensure databases exist

#### **4. "Embedding timeout" or "LLM timeout"**
- **Problem:** Ollama is not responding
- **Solution:**
  - Verify `ollama serve` is running
  - Check `OLLAMA_BASE_URL` in `.env`
  - Ensure required models are pulled

#### **5. OCR failing on images**
- **Problem:** EasyOCR or TrOCR models not downloaded
- **Solution:**
  ```bash
  cd backend/document_workspace
  python "download models.py"
  ```

#### **6. "Access token expired"**
- **Problem:** Token is no longer valid
- **Solution:** Use refresh token to get new access token
  ```bash
  POST /refresh
  {"refresh_token": "..."}
  ```

#### **7. Frontend cannot reach backend**
- **Problem:** API URL is incorrect
- **Solution:** Verify `.env.local` in frontend
  ```env
  VITE_AUTH_API_URL=http://localhost:8000
  VITE_RAG_API_URL=http://localhost:8001
  ```

#### **8. "Email verification failed"**
- **Problem:** SMTP configuration incorrect
- **Solution:**
  - Verify email credentials in `.env`
  - For Gmail: Use app-specific password (not regular password)
  - Enable "Less secure app access" if needed
  - Check MAIL_SERVER and MAIL_PORT settings

#### **9. "File upload too large"**
- **Problem:** Document exceeds size limit
- **Solution:**
  - Increase `MAX_FILE_SIZE_MB` in `.env` (up to available disk space)
  - Or split large documents before uploading

#### **10. "PDF generation failed"**
- **Problem:** ReportLab cannot generate PDF
- **Solution:**
  - Verify reportlab is installed: `pip install reportlab`
  - Check file permissions on upload directory
  - Ensure sufficient disk space

### **Debugging Tips**

1. **Check API Swagger UI:**
   - Auth: http://localhost:8000/docs
   - RAG: http://localhost:8001/docs

2. **View Backend Logs:**
   - uvicorn prints logs to console
   - Watch for 500 errors and tracebacks

3. **Check Browser Console:**
   - Frontend JS errors
   - Network tab for API requests

4. **Test APIs with cURL:**
   ```bash
   curl -X POST http://localhost:8000/login \
     -H "Content-Type: application/json" \
     -d '{"email":"test@example.com","password":"Test123"}'
   ```

5. **Enable verbose logging:**
   ```python
   # In database.py, change:
   engine = create_engine(DATABASE_URL, echo=True)  # Logs all SQL
   ```

6. **Check Docker logs:**
   ```bash
   docker-compose logs -f service_name
   ```

---

## 🔮 Future Improvements

### **Planned Features**

1. **Advanced Search**
   - Full-text search across all documents
   - Filter by date, author, tags
   - Saved searches and filters

2. **Collaboration**
   - Share documents with teams
   - Real-time collaborative editing
   - Comments and annotations

3. **Advanced Analytics**
   - Document similarity/clustering
   - Reading patterns and insights
   - Productivity metrics

4. **Enhanced OCR**
   - Multi-language OCR support
   - Layout preservation
   - Table structure detection

5. **Extended LLM Support**
   - Support for multiple LLM backends (OpenAI, Anthropic)
   - Fine-tuned models for specific domains
   - Prompt templates library

6. **Mobile App**
   - Native iOS/Android app
   - Offline document access
   - Push notifications

7. **Integrations**
   - Cloud storage (Google Drive, OneDrive)
   - Notion, Obsidian integration
   - Slack notifications

8. **Performance**
   - Caching layer (Redis)
   - Database query optimization
   - Async document processing queue

9. **Accessibility**
   - Screen reader optimization
   - Keyboard navigation
   - High contrast themes

10. **Security Enhancements**
    - Two-factor authentication (2FA)
    - Document encryption
    - Audit logging

---

## 🤝 Contributing

We welcome contributions! Here's how to get started:

### **Development Workflow**

1. **Fork the repository** on GitHub
2. **Create a feature branch:**
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Make your changes** following the code style
4. **Test thoroughly:**
   - Run linters: `npm run lint` (frontend), `pylint` (backend)
   - Test APIs with provided Swagger UI
   - Test on different screen sizes
5. **Commit with clear messages:**
   ```bash
   git commit -m "feat: add new feature" -m "Detailed description"
   ```
6. **Push and create a Pull Request:**
   ```bash
   git push origin feature/your-feature-name
   ```

### **Code Standards**

- **Frontend:** ESLint configured, follow Tailwind conventions
- **Backend:** PEP 8 Python style, type hints recommended
- **Commit Messages:** Use conventional commits (feat:, fix:, docs:, etc.)

### **Testing**

- Test auth flows before/after changes
- Test document upload with various file types
- Verify RAG responses are accurate
- Test on mobile viewport

---

## 📄 License

This project is open-source and available under the [MIT License](LICENSE).

---

## 📞 Support & Contact

- **Issues:** [GitHub Issues](https://github.com/sapanajoshi140-ux/Minor-Project/issues)
- **Discussions:** [GitHub Discussions](https://github.com/sapanajoshi140-ux/Minor-Project/discussions)
- **Email:** contact@sapanajoshi.dev (if available)

---

## 🙏 Acknowledgments

This project incorporates:
- **Ollama** for open-source LLM inference
- **ChromaDB** for vector database
- **LangChain** for RAG utilities
- **FastAPI** for modern async web framework
- **React + Tailwind CSS** for beautiful frontend
- **Open-source OCR** (EasyOCR, TrOCR, Tesseract)

---

**Last Updated:** May 24, 2025  
**Version:** 1.0.0  
**Status:** Active Development

