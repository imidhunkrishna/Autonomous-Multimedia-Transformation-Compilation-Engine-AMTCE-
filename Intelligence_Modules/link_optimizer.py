
import json
import os
import random
import time
import logging
from datetime import datetime

logger = logging.getLogger("link_optimizer")

class LinkOptimizer:
    def __init__(self, state_file="The_json/link_performance_state.json"):
        self.state_file = state_file
        self.state = {}
        self.total_clicks = 0
        self.load_state()

    def load_state(self):
        """Loads link performance state from JSON."""
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.state = data.get("links", {})
                    self.total_clicks = data.get("total_clicks", 0)
            except Exception as e:
                logger.error(f"Failed to load link state: {e}")
                self.state = {}
                self.total_clicks = 0
        else:
            self.state = {}
            self.total_clicks = 0

    def save_state(self):
        """Saves current state to JSON."""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
            with open(self.state_file, "w", encoding="utf-8") as f:
                json.dump({
                    "links": self.state,
                    "total_clicks": self.total_clicks
                }, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save link state: {e}")

    def register_click(self, link):
        """Registers a click (impression/usage) for a link."""
        if link not in self.state:
            self._init_link(link)
        
        self.state[link]["clicks"] += 1
        self.state[link]["last_used"] = time.time()
        
        self.total_clicks += 1
        
        # Self-Healing: Decay every 100 clicks
        if self.total_clicks % 100 == 0:
            logger.info("♻️ [LinkOptimizer] Triggering Weight Decay (Self-Healing)...")
            self.decay_weights()
            
        self._update_weight(link)
        self.save_state()

    def register_conversion(self, link):
        """Registers a conversion (if feedback loop exists)."""
        if link not in self.state:
            self._init_link(link)

        self.state[link]["conversions"] += 1
        self._update_weight(link)
        self.save_state()

    def _init_link(self, link):
        """Initializes a new link in the state."""
        self.state[link] = {
            "clicks": 0,
            "conversions": 0,
            "weight": 1.0,
            "last_used": 0
        }

    def _update_weight(self, link):
        """Recalculates weight based on performance."""
        data = self.state[link]
        clicks = max(data["clicks"], 1)
        conversions = data["conversions"]
        
        # Base Performance Logic
        ctr = conversions / clicks
        performance_boost = 1.0 + (ctr * 5.0) # Bonus for high CTR
        
        # Recency Penalty (prevent spamming same link back-to-back)
        # If used within last 30 minutes, penalize
        time_since_last = time.time() - data.get("last_used", 0)
        recency_penalty = 0.5 if time_since_last < 1800 else 1.0
        
        # Final Weight Calculation
        # Base 1.0 * Performance * Recency
        data["weight"] = 1.0 * performance_boost * recency_penalty

    def decay_weights(self):
        """Periodically decay weights to prevent stagnation."""
        for link in self.state:
            # Decay by 5%
            self.state[link]["weight"] *= 0.95 
            # Clamp min weight
            if self.state[link]["weight"] < 0.1:
                self.state[link]["weight"] = 0.1
        self.save_state()

    def get_weighted_link(self, links, category=None):
        """
        Selects a link using Exploration (10%) vs Exploitation (90%).
        Prioritizes links that match the category or show "Lead Magnet" patterns.
        """
        if not links: return None
        
        # Sync state with available links
        for link in links:
            if link not in self.state:
                self._init_link(link)

        # 1. EXPLORATION (10% Chance)
        if random.random() < 0.10:
            selected = random.choice(links)
            logger.info(f"🎲 [LinkOptimizer] EXPLORATION: {selected[:30]}...")
            self.register_click(selected)
            return selected

        # 2. EXPLOITATION (Weighted Choice)
        weights = []
        valid_links = []
        
        for link in links:
            w = self.state.get(link, {}).get("weight", 1.0)
            
            # --- INTENT-WARMING BOOST ---
            # If the link is a "Blueprint" or "Vault" (Lead Magnet), boost its weight
            if any(keyword in link.lower() for keyword in ["blueprint", "vault", "archive"]):
                w *= 2.0
                
            # Category-based local boost
            if category and category.lower() in link.lower():
                w *= 1.5
                
            weights.append(w)
            valid_links.append(link)
            
        # Select
        try:
             selected = random.choices(valid_links, weights=weights, k=1)[0]
             w_val = self.state[selected]["weight"]
             logger.info(f"🎯 [LinkOptimizer] EXPLOITATION: {selected[:30]}... (W: {w_val:.2f})")
             self.register_click(selected)
             return selected
        except Exception as e:
            logger.error(f"Weighted choice failed: {e}")
            return random.choice(links)
