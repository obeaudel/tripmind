---
title: TripMind
emoji: 🧳
colorFrom: blue
colorTo: green
sdk: gradio
sdk_version: 5.49.1 
app_file: app.py
pinned: false
---

# TripMind

A conversational travel agent. Tell it about your trip and it returns a curated itinerary with real hotels, restaurants, and activities.

Built as independent services:
- **Intake Service** — conversation to understand the trip
- **Search + Format Service** — searches Google Places, returns structured data
- **Renderers** — terminal and PDF output
