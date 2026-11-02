"""Room classes, their zero-shot text prompts, and where each class sits in an Airbnb-style gallery.

The text side of CLIP is run once offline (scripts/build_text_embeddings.py) and stored in clip_text.npz,
so the server only needs the small image encoder.
"""
from __future__ import annotations

PROMPTS: dict[str, list[str]] = {
    "living": ["a photo of a living room", "a living room interior with a sofa and a TV",
               "a lounge area with a couch, armchairs and a coffee table", "a cozy sitting room"],
    "bedroom": ["a photo of a bedroom", "a bedroom interior with a bed and pillows",
                "a bed with white linen in a hotel room", "a bedroom with a wardrobe and bedside tables"],
    "kitchen": ["a photo of a kitchen", "a modern kitchen with cabinets, a stove and a refrigerator",
                "a kitchen counter with a sink and appliances", "a small kitchenette"],
    "bathroom": ["a photo of a bathroom", "a bathroom with a toilet, a sink and a shower",
                 "a bathroom with a bathtub and tiles", "a shower room with a mirror and a washbasin"],
    "dining": ["a photo of a dining area", "a dining table with chairs", "a dining room with a table set for a meal"],
    "workspace": ["a home office with a desk and a laptop", "a study room with a desk and a chair"],
    "balcony": ["a photo of a balcony or terrace", "an outdoor balcony with chairs and a railing",
                "a terrace with outdoor furniture"],
    "amenity": ["a swimming pool", "a gym with fitness equipment",
                "a shared lounge or recreation area of a residential building", "a children's playground or a garden"],
    "view": ["a view from a window or balcony over a city", "a scenic view of a city skyline",
             "a view of the sea or mountains from a window", "an outdoor landscape view"],
    "exterior": ["a photo of the exterior of an apartment building", "a building facade seen from the street",
                 "a residential tower seen from outside"],
    "entrance": ["a photo of an apartment entrance hallway", "a corridor or hallway inside an apartment with a door",
                 "a front door and entry foyer", "a building lobby or entrance hall"],
    "parking": ["a photo of a parking lot or car park", "an underground parking garage", "parking spaces with cars"],
    "other": ["a close-up detail of an object or decoration", "a laundry room with a washing machine",
              "a storage room or a utility area"],
}
CLASSES = list(PROMPTS)

APPEAL_POS = ["a bright, spacious, beautifully styled room, professional real estate photography",
              "a clean, tidy, well-lit interior with a wide-angle view"]
APPEAL_NEG = ["a dark, cluttered, messy room with poor lighting", "a blurry, badly composed amateur photo"]

# Gallery order requested for Airbnb: hero, living, bedrooms, kitchen, bathrooms, dining/amenities, views/entrances/parking.
CATEGORY = {"living": 2, "bedroom": 3, "kitchen": 4, "bathroom": 5,
            "dining": 6, "workspace": 6, "balcony": 6, "amenity": 6, "other": 6,
            "view": 7, "exterior": 7, "entrance": 7, "parking": 7}
SUBORDER = {"living": 0, "bedroom": 0, "kitchen": 0, "bathroom": 0,
            "dining": 0, "workspace": 1, "balcony": 2, "amenity": 3, "other": 4,
            "view": 0, "exterior": 1, "entrance": 2, "parking": 3}
# How well a class represents the whole apartment as the main (cover) photo.
HERO_PRIOR = {"living": 1.0, "bedroom": 0.8, "view": 0.7, "balcony": 0.6, "kitchen": 0.55, "dining": 0.5, "exterior": 0.45,
              "amenity": 0.35, "workspace": 0.3, "entrance": 0.2, "bathroom": 0.2, "other": 0.1, "parking": 0.05}
