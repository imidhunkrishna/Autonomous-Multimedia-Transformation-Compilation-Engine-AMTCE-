import os
import random
import logging

logger = logging.getLogger("anchors")

class DigitalAnchor:
    """
    Manages the 'Virtual Host' (AI Anchor) for the Synthetic Newsroom.
    Provides FFmpeg filters to overlay the host onto the video.
    """
    def __init__(self):
        # We assume a dedicated directory for anchor assets (Video loops with Alpha or Green Screen)
        self.anchor_dir = "assets/anchors"
        os.makedirs(self.anchor_dir, exist_ok=True)
        
        # Default fallback: A circular static frame if no video loop exists
        self.default_anchor = os.path.join(self.anchor_dir, "default_host.png")

    def get_overlay_filter(self, video_width=1080, video_height=1920):
        """
        Generates the FFmpeg filter for the circular anchor in the corner.
        Position: Bottom Right (standardized for reaction videos).
        """
        # Host size: 25% of width
        host_w = int(video_width * 0.25)
        host_h = host_w # Square/Circular
        
        # Offset: 50px from edges
        x = video_width - host_w - 50
        y = video_height - host_h - 150 # Leave room for captions
        
        # Filter logic:
        # 1. Take anchor input [1:v]
        # 2. Scale it
        # 3. Create a circular mask
        # 4. Overlay onto [0:v]
        
        # Shorthand for simple overlay (assuming alpha channel in host)
        # For a full implementation, we would use a mask filter.
        return f"[1:v]scale={host_w}:{host_h}[anchor];[0:v][anchor]overlay={x}:{y}"

    def get_anchor_path(self):
        """Returns the path to the current active anchor asset."""
        anchors = [f for f in os.listdir(self.anchor_dir) if f.endswith(('.png', '.mp4'))]
        if not anchors:
            return self.default_anchor
        return os.path.join(self.anchor_dir, random.choice(anchors))

engine = DigitalAnchor()
