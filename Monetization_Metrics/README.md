# 💰 Affiliate Traffics (The Cash Cow)

## Use Case
This module is the "Revenue Generator." It analyzes the visual content for products (like clothes in fashion videos) and generates affiliate search links to drive traffic to marketplaces like Amazon or Myntra.

## What it is good at
1.  **Fashion Scouting**: It can identify styles and brands in a video and generate specific search URLs for viewers.
2.  **CTA Generation**: Creates the "Click here to buy" call-to-action text for the descriptions.

## Step-by-Step Usage

1.  **Run Standalone**:
    ```python
    from fashion_scout import get_product_links
    
    # Analyze image and get links
    links = get_product_links("outfit_frame.jpg")
    print(links)
    ```
2.  **Requirement**:
    Uses the Gemini API for visual recognition.
