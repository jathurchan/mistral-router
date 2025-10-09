# Design Document

## Background

Online platforms like YouTube that host massive volumes of user-generated content — including comments, titles, and support queries — must maintain safe and trustworthy environments.
To do so, they rely on content classification, moderation, and automated responses that align with platform policies, user trust, and regulatory standards.

Traditional rule-based systems and static machine learning models have helped to a degree, but the volume, complexity, and sensitivity of modern content ecosystems demand more adaptive and transparent solutions.

## Problem Statement

Many platforms combine rules, static classifiers, and general-purpose LLMs to handle moderation and support at scale.
These approaches face widely recognized industry challenges:

- Unsupported or inconsistent answers from LLMs when they aren’t grounded in authoritative policy sources.

- Low transparency, making it difficult to trace or justify moderation decisions.

- Policy evolution requiring constant re-tuning of models and rules.

- Gaps in detection for borderline or sensitive content that falls between rigid rules and classifiers.

This project focuses on addressing these common industry pain points in a lean, demonstrable way.

## Goal

Build Aegis — a lightweight, policy-aware Retrieval-Augmented Generation (RAG) chatbot designed to:

- Detect and classify policy-relevant or unsafe content.

- Ground responses in authoritative policy sources for consistency and transparency.

- Expose a clean API suitable for integration with moderation or support pipelines.

- Demonstrate a minimal yet realistic solution that mirrors key challenges faced in real-world trust & safety systems.

### Core Capabilities

- Policy grounding via retrieval from authoritative documents (FAISS + embeddings).

- Topic & safety classification (e.g., monetization, copyright, borderline, unsafe).

- Policy-aligned answers with citations for traceability.

- Lightweight API for modular integration.

### Implementation Plan

- **Retrieval**: FAISS + embeddings (Lightweight and fast grounding)

- **RAG Generation**: Policy-aligned answers with citations (Reduces hallucination)

- **Classification**: Prompt- or model-based topic & safety labels (Enables structured moderation)

- **Evaluation**: Retrieval recall & classification accuracy (Focus on measurable signal)

- **Deployment**: Dockerized FastAPI service (Realistic and portable)