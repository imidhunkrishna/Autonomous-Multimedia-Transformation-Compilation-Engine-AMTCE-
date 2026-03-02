"""
Self-Healing Adaptive Intelligence Engine v3
--------------------------------------------
A "Biological" system for long-term monetization survival.
Prioritizes channel health and trust accumulation over speed.

Components:
- RiskSystem: Volatility & Drift monitoring
- TrustSystem: Trust score buffering
- SafeModeController: 4-level defense system
- PsychometricEngine: Entropy control
- ReinforcementLearner: CTA optimization
"""

import os
import json
import time
import math
import logging
import random
from datetime import datetime, timedelta
from collections import deque
from pathlib import Path

logger = logging.getLogger("adaptive_intelligence")

# --- MATH UTILS ---
def calculate_std_dev(data):
    if len(data) < 2: return 0.0
    mean = sum(data) / len(data)
    variance = sum((x - mean) ** 2 for x in data) / (len(data) - 1)
    return math.sqrt(variance)

def clamp(n, minn, maxn):
    return max(min(n, maxn), minn)

# --- COMPONENT 1: RISK SYSTEM ---
class RiskSystem:
    def __init__(self, history_days=7):
        self.history_days = history_days
        # Queue of (timestamp, score)
        self.risk_history = deque()
        self.current_volatility = 0.0
        self.rolling_avg = 0.0
        self.drift = 0.0

    def add_risk_sample(self, score):
        now = time.time()
        self.risk_history.append((now, score))
        self._prune_history()
        self._recalculate()

    def _prune_history(self):
        now = time.time()
        cutoff = now - (self.history_days * 86400)
        while self.risk_history and self.risk_history[0][0] < cutoff:
            self.risk_history.popleft()

    def _recalculate(self):
        if not self.risk_history:
            self.rolling_avg = 0.0
            self.current_volatility = 0.0
            self.drift = 0.0
            return

        scores = [s[1] for s in self.risk_history]
        self.rolling_avg = sum(scores) / len(scores)
        self.current_volatility = calculate_std_dev(scores)
        if scores:
            self.drift = scores[-1] - self.rolling_avg

    def get_risk_state(self):
        return {
            "avg": self.rolling_avg,
            "volatility": self.current_volatility,
            "drift": self.drift
        }

# --- COMPONENT 2: TRUST SYSTEM ---
class TrustSystem:
    def __init__(self, start_score=50.0):
        self.trust_score = start_score
        self.consecutive_errors = 0

    def update_trust(self, outcome, risk_level="LOW"):
        """
        Outcome: 'success', 'reject', 'error'
        """
        if outcome == 'success':
            self.consecutive_errors = 0
            # Bonus varies by risk taken
            bonus = 1.0 if risk_level == "LOW" else 0.5
            self.trust_score = clamp(self.trust_score + bonus, 0, 100)
        
        elif outcome == 'reject':
            self.consecutive_errors = 0
            # Rejection is a warning
            penalty = 5.0
            self.trust_score = clamp(self.trust_score - penalty, 0, 100)
            
        elif outcome == 'error':
            self.consecutive_errors += 1
            # Errors compound
            penalty = 2.0 * self.consecutive_errors
            self.trust_score = clamp(self.trust_score - penalty, 0, 100)

    def get_trust_level(self):
        return self.trust_score

# --- COMPONENT 3: SAFE MODE CONTROLLER ---
class SafeModeController:
    def __init__(self):
        self.level = 0 # 0=Normal, 1=Cautious, 2=Defensive, 3=Survival

    def determine_level(self, risk_state, trust_score):
        """
        The Core Logic for Protection.
        """
        avg = risk_state['avg']
        vol = risk_state['volatility']
        
        # Default Normal
        new_level = 0
        
        # Level 1: Cautious (High Avg or Low Trust)
        if avg > 60 or trust_score < 40:
            new_level = 1
            
        # Level 2: Defensive (High Volatility)
        if vol > 15 or trust_score < 20:
            new_level = 2
            
        # Level 3: Survival (Critical Drift or Zero Trust)
        if risk_state['drift'] > 25 or trust_score < 10:
            new_level = 3
            
        if new_level != self.level:
            logger.info(f"🛡️ Safe Mode Shift: L{self.level} -> L{new_level}")
            self.level = new_level
            
        return self.level

    def get_constraints(self):
        """Returns restrictive parameters based on level."""
        # --- CASH-MAXIMIZER OVERRIDE ---
        if os.getenv("CASH_MAX_MODE", "no").lower() == "yes":
            return {
                "upload_delay": 0,
                "cta_aggression": 1.2, # Extra aggression for real-time cash
                "complexity_allowed": True
            }

        # Level 0: Default
        constraints = {
            "upload_delay": 0,
            "cta_aggression": 1.0,
            "complexity_allowed": True
        }
        
        if self.level == 1:
            constraints["upload_delay"] = 120 # 2 mins
            constraints["cta_aggression"] = 0.7
            
        elif self.level == 2:
            constraints["upload_delay"] = 600 # 10 mins
            constraints["cta_aggression"] = 0.3
            constraints["complexity_allowed"] = False
            
        elif self.level == 3:
            constraints["upload_delay"] = 3600 # 1 hour
            constraints["cta_aggression"] = 0.0 # No CTA
            constraints["complexity_allowed"] = False
            
        return constraints

# --- COMPONENT 4: PSYCHOMETRIC ENGINE ---
class PsychometricEngine:
    def __init__(self):
        self.history = deque(maxlen=20)
        # [Refined Triggers]: Less academic, more "Fashion Editor"
        self.triggers = ["Unmissable Trend", "Styling Secret", "Luxury Vibe", "Bold Statement", "Detail Focus", "Color Theory"]

    def track_trigger(self, trigger):
        self.history.append(trigger)

    def force_diversity(self):
        """
        Calculates entropy. If low, suggests a neglected trigger.
        """
        if not self.history: return None
        
        counts = {t: 0 for t in self.triggers}
        for h in self.history:
            if h in counts: counts[h] += 1
            
        total = len(self.history)
        entropy = 0.0
        for count in counts.values():
            if count > 0:
                p = count / total
                entropy -= p * math.log2(p)
                
        # Low entropy means effective repetition.
        # Max entropy for 6 items is ~2.58
        if entropy < 1.5:
            # Find least used
            least_used = min(counts, key=counts.get)
            logger.info(f"🧠 Low Entropy ({entropy:.2f}). Forcing shift to: {least_used}")
            return least_used
        return None

# --- COMPONENT 5: REINFORCEMENT LEARNER ---
class ReinforcementLearner:
    def __init__(self, triggers):
        # Weights default to 1.0
        self.weights = {t: 1.0 for t in triggers}
        self.learning_rate = 0.05

    def update_weight(self, trigger, reward):
        """
        Reward: -1.0 to 1.0
        """
        if trigger not in self.weights: return
        
        current = self.weights[trigger]
        # Simple Gradient: New = Old + LR * Reward
        # We assume 'Expected Reward' is implicit in the goal to maximize
        new = current + (self.learning_rate * reward)
        
        # Clamp weights to prevent total extinction or domination/
        self.weights[trigger] = clamp(new, 0.2, 5.0)

    def select_trigger(self):
        """Probabilistic selection based on weights."""
        triggers = list(self.weights.keys())
        weights = list(self.weights.values())
        return random.choices(triggers, weights=weights, k=1)[0]

# --- MAIN: ADAPTIVE BRAIN ---
class AdaptiveBrain:
    def __init__(self, state_file="The_json/adaptive_state_v3.json"):
        self.state_file = state_file
        
        # Initialize Sub-Systems
        self.risk_system = RiskSystem()
        self.trust_system = TrustSystem()
        self.safe_controller = SafeModeController()
        self.psych_engine = PsychometricEngine()
        # Initialize RL with psych triggers
        self.rl_learner = ReinforcementLearner(self.psych_engine.triggers)
        
        # Load State
        self.load_state()

    # --- STATE MANAGEMENT ---
    def load_state(self):
        if not os.path.exists(self.state_file): return
        try:
            with open(self.state_file, 'r') as f:
                data = json.load(f)
                
            # Restore Risk History
            rh = data.get('risk_history', [])
            self.risk_system.risk_history = deque(rh)
            self.risk_system._recalculate()
            
            # Restore Trust
            self.trust_system.trust_score = data.get('trust_score', 50.0)
            
            # Restore Safe Level
            self.safe_controller.level = data.get('safe_level', 0)
            
            # Restore Weights
            w = data.get('cta_weights', {})
            if w: self.rl_learner.weights = w
            
        except Exception as e:
            logger.error(f"Failed to load adaptive state: {e}")

    def save_state(self):
        try:
            data = {
                'risk_history': list(self.risk_system.risk_history),
                'trust_score': self.trust_system.trust_score,
                'safe_level': self.safe_controller.level,
                'cta_weights': self.rl_learner.weights
            }
            with open(self.state_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save adaptive state: {e}")

    # --- PUBLIC API ---

    def register_upload_outcome(self, outcome: str, risk_score: float = 0.0):
        """
        Called after every upload attempt.
        outcome: 'success', 'reject', 'error'
        """
        # 1. Update Trust
        level = "HIGH" if risk_score > 50 else "LOW"
        if outcome == 'reject': level = "HIGH" # Rejections imply high risk realized
        
        self.trust_system.update_trust(outcome, level)
        
        # 2. Update Risk System (only on analyzed content)
        if risk_score > 0:
            self.risk_system.add_risk_sample(risk_score)
            
        # 3. Recalculate Safe Mode
        risk_state = self.risk_system.get_risk_state()
        trust = self.trust_system.get_trust_level()
        self.safe_controller.determine_level(risk_state, trust)
        
        self.save_state()

    def get_execution_constraints(self):
        """
        Called by main.py to throttle or limit features.
        """
        return self.safe_controller.get_constraints()

    def get_optimized_psychology(self):
        """
        Called by MonetizationBrain.
        Returns: Selected Trigger (String)
        """
        # 1. Check Entropy
        forced_choice = self.psych_engine.force_diversity()
        if forced_choice:
            trigger = forced_choice
        else:
            # 2. RL Selection
            trigger = self.rl_learner.select_trigger()
            
        # Track choice
        self.psych_engine.track_trigger(trigger)
        return trigger

    def update_cta_reward(self, trigger, reward_score):
        """
        Called when engagement metrics come in (or simulated success).
        """
        self.rl_learner.update_weight(trigger, reward_score)
        self.save_state()

    def compute_efficiency_score(self, duration, time_taken, quality_score):
        # Legacy support for main.py logging
        if time_taken <= 0: return 0
        ratio = duration / time_taken
        score = ratio * (quality_score / 50.0)
        return round(score, 2)
        
    def check_momentum(self, user_id):
        # Forward to Safe Mode Constraints which handle "Delay"
        # We keep this for backward compatibility with main.py calls if any
        # But real throttling happens via 'get_execution_constraints' -> 'upload_delay'
        constraints = self.get_execution_constraints()
        delay = constraints.get("upload_delay", 0)
        
        # If we are in L1+, we force delay.
        # But this method in main.py was per-user rapid fire check.
        # Let's keep the basic rapid fire check here too, but layer SafeMode.
        
        # ... (Simplified stateless Momentum for now since SafeMode is dominant)
        return True, delay

# Singleton
brain = AdaptiveBrain()
