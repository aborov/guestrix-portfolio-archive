# GuestrixAI (Archive)

**A Real-Time Conversational AI for Hospitality**

> **Note:** This repository is a sanitized code archive of GuestrixAI, a startup developed in 2025. It is presented here for non-commercial portfolio demonstration purposes. Some proprietary assets and keys have been removed.

## Project Overview
GuestrixAI was designed to solve a critical problem in the short-term rental market: providing immediate, context-aware support to guests. The system enabled guests to speak naturally with an AI agent that possessed deep knowledge of the specific property (e.g., "How do I turn on the heater?").

## Technical Architecture
* **Frontend Voice:** JavaScript (Web Audio API + ScriptProcessor) for raw PCM capture.
* **Real-Time Transport:**
    * **Voice:** Direct WebSocket connection from Client to Gemini Live API (to minimize latency).
    * **State/Chat:** Socket.IO for session management and fallback text chat.
* **Backend:** Python (Flask) for orchestration and Auth.
* **RAG Engine:** Firestore Vector Search (embedding-based retrieval).

## Key Features (Archive Status)
* **Hybrid Latency Architecture:** Decoupled audio streaming (Direct-to-API) from state management (Server-based) to ensure sub-second voice response times.
* **Vector-Based RAG:** Implemented a `find_similar_knowledge_items` pipeline that retrieves property metadata from Firestore and injects it into the system prompt context window.
* **Resilient Audio:** Custom `AudioContext` logic to handle browser-specific microphone constraints and stream stability.

## Status
The project was sunset in late 2025 due to a pivot in market strategy. This codebase represents the engineering work completed during the alpha prototyping phase.
