# Affiliate Modules: Visual Operations Guide

This guide provides a graphical representation of how the affiliate and monetization systems flow within the bot.

## 1. Fashion Scout (Amazon / Myntra Affiliate)
This module analyzes celebrity imagery to generate high-intent commerce links.

```mermaid
graph TD
    A["Main Bot Engine"] -->|"Provides Video Frames"| B["Monetization Brain"]
    B -->|"Multimodal Request"| C["Gemini 2.5-Flash"]
    C -->|"Identifies Outfit"| D["Fashion Scout Module"]
    D -->|"Generates Queries"| E["Search Strings"]
    E -->|"Amazon / Myntra / Nykaa"| F["Affiliate Search Links"]
    D -->|"Multi-Language AI"| G["Imaginative CTAs"]
    F --> H["Telegram Report UI"]
    G --> H
```

---

## 2. Los Pollos Integration (Smartlinks)
This module handles traffic monetization via smartlinks and rotated CTAs.

```mermaid
graph LR
    A["The_json/links.json"] -->|"Link Pool"| B["Monetization Brain"]
    C["Content Analysis"] --> B
    B -->|"Generate Persuasive CTA"| D["Editorial AI Commentary"]
    B -->|"Pick Rotated Link"| E["Smartlink (Los Pollos)"]
    D & E -->|"Community Task (main.py)"| F["YouTube Pinned Comment"]
    D & E -->|"Traffic Report"| G["Telegram"]
    H["uploader.py"] -->|"Post-Upload Trigger"| F
```

---

## 3. The Transformation Lifecycle
How the bot ensures content is monetizable through transformations.

```mermaid
sequenceDiagram
    participant Source
    participant Transform as Processing Pipeline
    participant AI as Gemini 2.5
    participant Affiliate as Affiliate Modules
    
    Source->>Transform: Original Video
    Transform->>Transform: Clear Watermark
    Transform->>Transform: Heavy Audio Remix
    Transform->>AI: Enhanced Frames + Metadata
    AI->>AI: Policy Check (YPP Approved?)
    AI->>Affiliate: approved=True
    Affiliate->>Affiliate: Generate CTAs & Links
    Affiliate->>Transform: Integration Complete
```

## 4. Commentary Priority Logic (Pinned Comments)

The bot follows a strict priority for YouTube pinned comments and community posts to maximize monetization quality:

| Priority | Strategy | Source | Description |
| :--- | :--- | :--- | :--- |
| **1 🔥** | **Partner-Gift** | `fashion_scout.py` | If an outfit is found, use a romantic "gift for her" CTA in Hinglish/Urdu/English. |
| **2 🧠** | **Editorial AI** | `monetization_brain.py` | If no outfit, use Gemini's custom editorial commentary for the video. |
| **3 📢** | **Telegram Promo** | `community_promoter.py` | Fallback: Use "Spicy Bait" templates to drive users to the raw Telegram channel. |

### How it Decides (Full Loop):
```mermaid
graph TD
    A["Video Uploaded"] --> B{"Outfit Identified?"}
    B -- "Yes" --> C["Priority 1: Partner-Gift CTA<br>+ Amazon/Myntra Link"]
    B -- "No" --> D{"AI CTA Available?"}
    D -- "Yes" --> E["Priority 2: Editorial AI CTA<br>+ Los Pollos Smartlink"]
    D -- "No" --> F["Priority 3: Telegram Promo<br>+ Smartlink Fallback"]
    C & E & F --> G["Pinned Comment on YouTube"]
```
