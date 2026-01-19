# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
ENHANCED ASSET LIBRARY WITH DESCRIPTIONS
Stores asset mappings with descriptions to help AI recognize elements
STANDARDIZED ON 'asset_path' FIELD
"""

import json
from pathlib import Path
import unreal

class AssetLibraryManager:
    """Manages the asset library with descriptions for AI recognition"""

    def __init__(self):
        self.library_path = Path(unreal.Paths.project_content_dir()) / "StoryboardTo3D" / "asset_library.json"
        self.library = self.load_library()

    def load_library(self):
        """Load the asset library from file"""
        if self.library_path.exists():
            try:
                with open(self.library_path, 'r') as f:
                    return json.load(f)
            except:
                pass

        # Default library structure with descriptions
        #  STANDARDIZED: Using 'asset_path' everywhere
        return {
            "characters": {
                "Oat": {
                    "asset_path": "/Game/Characters/BP_OatDog",  #  asset_path
                    "description": "Brown cartoon dog, main character, face",
                    "aliases": ["dog", "puppy", "canine", "brown dog"]
                }
            },
            "props": {
                "Ball": {
                    "asset_path": "/Game/Props/SM_Ball",  #  asset_path
                    "description": "Red ball toy",
                    "aliases": ["toy", "sphere"]
                },
                "Bench": {
                    "asset_path": "/Game/Props/SM_Bench",  #  asset_path
                    "description": "Park bench",
                    "aliases": ["seat", "chair"]
                }
            },
            "locations": {
                "Park": {
                    "asset_path": "/Game/Maps/Park_Level",
                    "description": "Outdoor park with grass, trees, benches, playground",
                    "aliases": ["outdoor", "playground", "garden"]
                }
            }
        }

    def save_library(self):
        """Save the library to file"""
        self.library_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.library_path, 'w') as f:
            json.dump(self.library, f, indent=2)

    def add_asset(self, category: str, name: str, asset_path: str, description: str, aliases: list = None):
        """Add or update an asset in the library - STANDARDIZED"""
        if category not in self.library:
            self.library[category] = {}

        #  ALWAYS use 'asset_path' field
        self.library[category][name] = {
            "asset_path": asset_path,  #  Standardized field name
            "description": description,
            "aliases": aliases or []
        }

        self.save_library()
        unreal.log(f"Added to library: {name} - {description}")

    def get_formatted_for_ai(self):
        """Get library formatted as text for AI to understand"""
        formatted = "AVAILABLE ASSETS IN PROJECT:\n\n"

        # Characters
        formatted += "CHARACTERS:\n"
        for name, data in self.library.get("characters", {}).items():
            formatted += f"- {name}: {data['description']}\n"

        # Props
        formatted += "\nPROPS:\n"
        for name, data in self.library.get("props", {}).items():
            formatted += f"- {name}: {data['description']}\n"

        # Locations
        formatted += "\nLOCATIONS:\n"
        for name, data in self.library.get("locations", {}).items():
            formatted += f"- {name}: {data['description']}\n"

        return formatted

    def find_match(self, detected_text: str, category: str):
        """Find best match for detected text in library"""
        detected_lower = detected_text.lower()

        # Check exact name match
        for name, data in self.library.get(category, {}).items():
            if name.lower() == detected_lower:
                return name, data["asset_path"]  #  Standardized

        # Check aliases
        for name, data in self.library.get(category, {}).items():
            for alias in data.get("aliases", []):
                if alias.lower() in detected_lower or detected_lower in alias.lower():
                    return name, data["asset_path"]  #  Standardized

        # Check description
        for name, data in self.library.get(category, {}).items():
            if detected_lower in data["description"].lower():
                return name, data["asset_path"]  #  Standardized

        return None, None

# Global instance
_asset_library = None

def get_asset_library():
    """Get or create the asset library instance"""
    global _asset_library
    if _asset_library is None:
        _asset_library = AssetLibraryManager()
    return _asset_library

# Functions for easy use
def add_character(name: str, asset_path: str, description: str, aliases: list = None):
    """Add a character to the library"""
    lib = get_asset_library()
    lib.add_asset("characters", name, asset_path, description, aliases)

def add_prop(name: str, asset_path: str, description: str, aliases: list = None):
    """Add a prop to the library"""
    lib = get_asset_library()
    lib.add_asset("props", name, asset_path, description, aliases)

def add_location(name: str, asset_path: str, description: str, aliases: list = None):
    """Add a location to the library - NOTE: asset_path not level_path"""
    lib = get_asset_library()
    lib.add_asset("locations", name, asset_path, description, aliases)

def setup_example_library():
    """Setup example library with common assets - STANDARDIZED"""

    # Add characters
    add_character(
        "Oat",
        "/Game/Characters/BP_OatDog",  #  asset_path
        "Brown cartoon dog, friendly, wears collar, main character",
        ["dog", "puppy", "brown dog", "canine"]
    )

    # Add props
    add_prop(
        "Ball",
        "/Game/Props/SM_Ball",  #  asset_path
        "Red rubber ball toy",
        ["toy", "sphere"]
    )

    add_prop(
        "Bench",
        "/Game/Props/Park/SM_Bench",  #  asset_path
        "Wooden park bench for sitting",
        ["seat", "chair"]
    )

    add_prop(
        "Tree",
        "/Game/Props/Nature/SM_Tree",  #  asset_path
        "Large oak tree with green leaves",
        ["oak", "plant"]
    )

    # Add locations
    add_location(
        "Park",
        "/Game/Maps/Park_Day",  #  asset_path (NOT level_path)
        "Sunny outdoor park with grass, trees, playground, and walking paths",
        ["outdoor", "playground", "garden", "outside"]
    )

    unreal.log("Example library setup complete!")

if __name__ == "__main__":
    print("\n" + "="*60)
    print("ASSET LIBRARY MANAGER - UE 5.6 STANDARDIZED")
    print("="*60)

    lib = get_asset_library()

    print("\nCurrent Library:")
    print(lib.get_formatted_for_ai())

    print("\nCommands:")
    print("setup_example_library()  - Add example assets")
    print("add_character(name, asset_path, description, aliases)")
    print("add_prop(name, asset_path, description, aliases)")
    print("add_location(name, asset_path, description, aliases)")

    print("\n IMPORTANT: All functions now use 'asset_path' parameter")
    print("Example:")
    print('add_character("Oat", "/Game/Characters/BP_OatDog", "Brown cartoon dog", ["dog", "puppy"])')
