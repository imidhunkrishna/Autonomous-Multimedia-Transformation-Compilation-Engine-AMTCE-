import os
import logging
from PIL import Image, ImageDraw, ImageFont
import numpy as np

logger = logging.getLogger("smart_price_tag")

class SmartPriceTag:
    def __init__(self):
        # Use relative path assuming execution from root
        self.font_path = os.path.abspath("assets/fonts/Inter-Bold.ttf")
        # Final fallback
        if not os.path.exists(self.font_path):
             self.font_path = "arial.ttf" 

    def _draw_glass_box(self, draw, x, y, w, h, radius=15):
        """Draws a premium glass-morphism background."""
        # Main Background: Dark, High Opacity
        draw.rounded_rectangle([x, y, x+w, y+h], radius=radius, fill=(20, 20, 20, 220))
        # Border: Subtle White/Gold
        draw.rounded_rectangle([x, y, x+w, y+h], radius=radius, outline=(255, 255, 255, 40), width=1)

    def generate(self, width: int, height: int, human_box: list, item_name: str, price_text: str, location_hint: str) -> str:
        """
        Generates a transparent PNG overlay with Smart Price Tag (Premium Edition).
        Returns the path to the generated image.
        """
        try:
            # 1. Create Transparent Canvas
            img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            # 2. Determine Item Target Point
            hx, hy, hw, hh = human_box
            
            y_ratios = {
                'head': 0.15, 'torso': 0.45, 'legs': 0.75, 'feet': 0.95,
                'bag': 0.50, 'accessories': 0.35, 'unknown': 0.50
            }
            target_ratio = y_ratios.get(location_hint.lower(), 0.50)
            target_y = int(hy + (hh * target_ratio))
            
            # --- STRICT FACE PROTECTION ---
            # The top 25% of the bounding box usually contains the head/face.
            # Never let the anchor point render in this zone unless explicitly requested.
            face_zone_bottom = hy + int(hh * 0.25)
            if target_y < face_zone_bottom and location_hint.lower() not in ['head', 'hat', 'glasses']:
                target_y = face_zone_bottom + 20 # Push it down to the chest area
            
            # 3. Determine Side (Left or Right)
            space_left = hx
            space_right = width - (hx + hw)
            is_right_side = space_right > space_left
            
            # 4. Calculate Anchor Points
            AIR_GAP = 40 # px (increased for breathing room)
            
            if is_right_side:
                target_x = hx + hw + 20 # Start slightly off body
                line_start_x = target_x 
            else:
                target_x = hx - 20 
                line_start_x = target_x
                
            # 5. Prepare Text & Font
            if "est" not in price_text.lower():
                price_text = f"Est. {price_text}"
                
            item_name = item_name.upper()
            
            # Fonts (Extra Small and Minimalist)
            title_size = int(height * 0.016) # Shrunk significantly
            price_size = int(height * 0.020) # Shrunk significantly
            
            try:
                font_title = ImageFont.truetype(self.font_path, title_size)
                font_price = ImageFont.truetype(self.font_path, price_size)
            except:
                font_title = ImageFont.load_default()
                font_price = ImageFont.load_default()
                
            # Dimensions
            title_bbox = draw.textbbox((0, 0), item_name, font=font_title)
            price_bbox = draw.textbbox((0, 0), price_text, font=font_price)
            
            t_w = title_bbox[2] - title_bbox[0]
            t_h = title_bbox[3] - title_bbox[1]
            p_w = price_bbox[2] - price_bbox[0]
            p_h = price_bbox[3] - price_bbox[1]
            
            padding_x = 10 # Ultra-minimal horizontal padding (Shortens the box width)
            padding_y = 8  # Ultra-minimal vertical padding
            gap = 4
            
            box_w = max(t_w, p_w) + (padding_x * 2)
            box_h = t_h + p_h + gap + (padding_y * 2)
            
            # 6. Positioning Box
            box_y = target_y - (box_h // 2)
            
            # Leader line heavily shortened to keep it compact
            LEADER_LENGTH = 15 
            if is_right_side:
                box_x = line_start_x + LEADER_LENGTH
            else:
                box_x = line_start_x - LEADER_LENGTH - box_w
                
            # Clamp strictly to screen bounds with a safe margin
            SAFE_MARGIN = 35 # Increased margin to prevent edge bumping
            box_x = max(SAFE_MARGIN, min(width - box_w - SAFE_MARGIN, box_x))
            box_y = max(SAFE_MARGIN, min(height - box_h - SAFE_MARGIN, box_y))
            
            # Additional Face Protection: If the box itself floats up into the face zone, push it down
            if box_y < face_zone_bottom and location_hint.lower() not in ['head', 'hat', 'glasses']:
                box_y = face_zone_bottom + 10
            
            # 7. Draw Visuals
            
            # A. Connector Line
            # Calculate updated end points based on clamped box
            if is_right_side:
                # The line should connect slightly inside the left edge of the glass box
                line_end_x = box_x + 2 
                line_end_y = box_y + (box_h // 2)
            else:
                # The line should connect slightly inside the right edge of the glass box
                line_end_x = box_x + box_w - 2
                line_end_y = box_y + (box_h // 2)
                
            # Draw Line (Solid White, 2px)
            draw.line([(line_start_x, target_y), (line_end_x, line_end_y)], fill=(255, 255, 255, 255), width=2)
            
            # B. Anchor Dot (The 'Pin' on the item)
            dot_r = 5 # Larger dot
            draw.ellipse([line_start_x-dot_r, target_y-dot_r, line_start_x+dot_r, target_y+dot_r], fill=(255, 255, 255, 255), outline=(0,0,0,100), width=1)
            
            # C. Glass Box
            self._draw_glass_box(draw, box_x, box_y, box_w, box_h)
            
            # D. Text
            # Title (White)
            text_x_title = box_x + padding_x
            text_y_title = box_y + padding_y
            draw.text((text_x_title, text_y_title), item_name, font=font_title, fill=(255, 255, 255, 255))
            
            # Price (Gold)
            text_x_price = box_x + padding_x
            text_y_price = text_y_title + t_h + gap
            # Gold Color: #FFD700 -> (255, 215, 0)
            draw.text((text_x_price, text_y_price), price_text, font=font_price, fill=(255, 215, 0, 255))
            
            # 8. Save
            temp_dir = "temp"
            if not os.path.exists(temp_dir): os.makedirs(temp_dir)
            
            import uuid
            out_name = f"smart_price_{uuid.uuid4().hex[:6]}.png"
            out_path = os.path.join(temp_dir, out_name)
            
            img.save(out_path, "PNG")
            return out_path.replace("\\", "/")
            
        except Exception as e:
            logger.error(f"Generate Smart Price Tag Failed: {e}")
            return None

# Singleton
tag_engine = SmartPriceTag()
