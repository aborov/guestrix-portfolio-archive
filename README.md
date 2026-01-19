# GuestrixAI (Archive)

**A Real-Time Conversational AI for Hospitality**

> **Note:** This repository is a sanitized code archive of GuestrixAI, a startup developed in 2025. It is presented here for non-commercial portfolio demonstration purposes. Some proprietary assets and keys have been removed.

## Project Overview
GuestrixAI was designed to solve a critical problem in the short-term rental market: providing immediate, context-aware support to guests without active host intervention. The system allowed guests to interact via voice or text with an AI agent capable of answering property-specific questions (e.g., "How do I turn on the heater?") in real-time.

## Technical Architecture
* **Backend:** Python (Flask)
* **Real-Time Communication:** Flask-SocketIO (WebSockets)
* **AI Engine:** Google Gemini (via `google-genai` SDK)
* **Frontend:** JavaScript (Browser-based audio streaming)
* **Data/Context:** Firestore (NoSQL) for property knowledge bases

## Key Features (Archive Status)
* **Bi-directional Audio Streaming:** Implemented logic to handle audio input streaming to the LLM and playback of generated audio responses.
* **Latency Management:** Custom queue management to handle network backpressure during voice sessions.
* **Contextual RAG:** Logic to retrieve property-specific details and inject them into the LLM's system prompt to reduce hallucinations.

## Status
The project was sunset in late 2025 due to a pivot in market strategy. This codebase represents the engineering work completed during the alpha prototyping phase.
