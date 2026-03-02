"""
Money Flow Logic v1 (The Intent-Warming Engine)
-----------------------------------------------
Handles dynamic mapping of fashion categories to high-conversion CPA offers.
Pivots from "Cold Sales" to "Warm Lead Magnets" (Style Blueprints).
"""

import random
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("money_flow_logic")

# --- INTENT-WARMING CONFIG ---
OFFER_MAP = {
    "LUXURY": {
        "lead_magnet": "Elite Style Blueprint",
        "offer_types": ["high_ticket_signup", "private_vault"],
        "hooks": ["Unlock the Luxury Blueprint", "Access the Private Style Vault"]
    },
    "STREETWEAR": {
        "lead_magnet": "Street Flux Archive",
        "offer_types": ["app_install", "limited_drop_signup"],
        "hooks": ["Leaked Streetwear Archive", "Get the Drop Blueprint"]
    },
    "MINIMALIST": {
        "lead_magnet": "Quiet Luxury Layout",
        "offer_types": ["newsletter_signup", "curated_vault"],
        "hooks": ["Access the Minimalist Layout", "The Quiet Luxury Secret"]
    },
    "BOHEMIAN": {
        "lead_magnet": "Earth-Tone Blueprint",
        "offer_types": ["social_follow", "style_guide"],
        "hooks": ["Download the Earth-Tone Guide", "Free Bohemian Blueprint"]
    },
    "FORMAL": {
        "lead_magnet": "Couture Construction File",
        "offer_types": ["pro_service_signup", "mastery_vault"],
        "hooks": ["The Couture Construction Secret", "Unlock the Formal Mastery Vault"]
    }
}

DEFAULT_OFFER = {
    "lead_magnet": "Global Style Blueprint",
    "offer_types": ["general_signup"],
    "hooks": ["Unlock the Secret Blueprint", "Access the Style Vault"]
}

class MoneyFlowEngine:
    def __init__(self):
        self.conversion_tracking = {}

    def get_optimized_offer(self, fashion_category: str = "GLOBAL") -> Dict:
        """
        Returns the best offer data based on the identified fashion category.
        """
        category = fashion_category.upper()
        offer_data = OFFER_MAP.get(category, DEFAULT_OFFER)
        
        # Add dynamic randomness for entropy
        selected_hook = random.choice(offer_data["hooks"])
        
        return {
            "category": category,
            "lead_magnet": offer_data["lead_magnet"],
            "hook": selected_hook,
            "offer_type": random.choice(offer_data["offer_types"])
        }

    def get_law_bending_cta(self, offer: Dict) -> str:
        """
        Formats a CTA that uses the "Verification Step" loophole.
        """
        return f"{offer['hook']} (Complete Verification Step)"

engine = MoneyFlowEngine()
