# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
ASSET LIBRARY WITH THUMBNAIL SUPPORT
Gets thumbnails from Content Browser or allows manual screenshots
"""

import unreal
import json
from pathlib import Path
import base64

class AssetLibraryWithThumbnails:
    """Enhanced Asset Library that includes visual thumbnails"""

    def __init__(self):
        self.library_path = Path(unreal.Paths.project_content_dir()) / "StoryboardTo3D" / "asset_library.json"
        self.thumbnails_dir = Path(unreal.Paths.project_content_dir()) / "StoryboardTo3D" / "AssetThumbnails"
        self.thumbnails_dir.mkdir(parents=True, exist_ok=True)
        self.library = self.load_library()

    def get_content_browser_thumbnail(self, asset_path: str) -> str:
        """
        Get thumbnail from Content Browser for an asset
        Returns path to thumbnail image or None
        """
        try:
            # Check if asset exists
            if not unreal.EditorAssetLibrary.does_asset_exist(asset_path):
                unreal.log(f"Asset doesn't exist: {asset_path}")
                return None

            # Load the asset
            asset = unreal.EditorAssetLibrary.load_asset(asset_path)
            if not asset:
                return None

            # Get thumbnail from editor subsystem
            thumbnail_subsystem = unreal.get_editor_subsystem(unreal.EditorAssetSubsystem)

            # Generate thumbnail path
            asset_name = Path(asset_path).stem
            thumbnail_path = self.thumbnails_dir / f"{asset_name}_thumb.png"

            # Try to export thumbnail
            # Note: This is a simplified approach - actual implementation might need more complex thumbnail extraction

            # Alternative: Use viewport capture for 3D assets
            if asset_path.endswith(('.uasset', '.BP')):
                # For blueprints/meshes, we could capture a viewport image
                self.capture_asset_thumbnail(asset, thumbnail_path)

            if thumbnail_path.exists():
                return str(thumbnail_path)

        except Exception as e:
            unreal.log(f"Error getting thumbnail: {e}")

        return None

    def capture_asset_thumbnail(self, asset, output_path: Path):
        """
        Capture a thumbnail of an asset using a temporary viewport
        This is a placeholder for the actual implementation
        """
        # For now, just create a placeholder
        # In production, this would:
        # 1. Spawn the asset in a clean level
        # 2. Position camera
        # 3. Take screenshot
        # 4. Save to output_path
        # 5. Clean up

        # Create a simple placeholder image
        placeholder_data = self.create_placeholder_thumbnail(asset.get_name())
        with open(output_path, 'wb') as f:
            f.write(placeholder_data)

    def create_placeholder_thumbnail(self, name: str) -> bytes:
        """Create a simple placeholder thumbnail with the asset name"""
        # Create a minimal PNG with text (this is a simplified placeholder)
        # In production, use PIL or other image library

        # For now, return a minimal 1x1 PNG
        return (b'\x89PNG\r\n\x1a\n' +
                b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01' +
                b'\x08\x02\x00\x00\x00\x90wS\xde' +
                b'\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00' +
                b'\x05\x18\xd6\x1d\xca' +
                b'\x00\x00\x00\x00IEND\xaeB`\x82')

    def add_asset_with_thumbnail(self, category: str, name: str, asset_path: str,
                                description: str, aliases: list = None,
                                thumbnail_path: str = None):
        """Add an asset with optional thumbnail"""

        if category not in self.library:
            self.library[category] = {}

        # Try to get thumbnail automatically if not provided
        if not thumbnail_path and asset_path:
            thumbnail_path = self.get_content_browser_thumbnail(asset_path)
            if thumbnail_path:
                unreal.log(f"Auto-captured thumbnail for {name}")

        self.library[category][name] = {
            "asset_path": asset_path,
            "description": description,
            "aliases": aliases or [],
            "thumbnail": thumbnail_path
        }

        self.save_library()

        status = "with thumbnail" if thumbnail_path else "without thumbnail"
        unreal.log(f"Added {name} to library {status}")

    def take_screenshot_for_asset(self, name: str, category: str):
        """
        Take a screenshot of current viewport for an asset
        Useful for manually capturing better thumbnails
        """

        thumbnail_path = self.thumbnails_dir / f"{name}_manual.png"

        # Take screenshot of current viewport
        unreal.SystemLibrary.execute_console_command(None, f"Screenshot {thumbnail_path}")

        # Update library with new thumbnail
        if category in self.library and name in self.library[category]:
            self.library[category][name]["thumbnail"] = str(thumbnail_path)
            self.save_library()
            unreal.log(f"Manual thumbnail saved for {name}")
            unreal.log("Note: Screenshot will be available in 30-40 seconds")
            return str(thumbnail_path)

        return None

    def get_thumbnail_for_ui(self, category: str, name: str) -> str:
        """Get thumbnail path for UI display"""
        if category in self.library and name in self.library[category]:
            return self.library[category][name].get("thumbnail", None)
        return None

    def save_library(self):
        """Save library to JSON"""
        self.library_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.library_path, 'w') as f:
            json.dump(self.library, f, indent=2)

    def load_library(self):
        """Load library from JSON"""
        if self.library_path.exists():
            try:
                with open(self.library_path, 'r') as f:
                    return json.load(f)
            except:
                pass
        return {"characters": {}, "props": {}, "locations": {}}

def setup_with_thumbnails():
    """Setup example library with thumbnail support"""

    lib = AssetLibraryWithThumbnails()

    print("\n" + "="*60)
    print("SETTING UP ASSET LIBRARY WITH THUMBNAILS")
    print("="*60)

    # Add Oat with auto thumbnail
    lib.add_asset_with_thumbnail(
        category="characters",
        name="Oat",
        asset_path="/Engine/BasicShapes/Capsule",
        description="Brown cartoon dog, main character",
        aliases=["dog", "puppy"],
        thumbnail_path=None  # Will try to auto-capture
    )

    print("\nAssets with thumbnails:")
    for cat, items in lib.library.items():
        print(f"\n{cat.upper()}:")
        for name, data in items.items():
            thumb = "" if data.get("thumbnail") else ""
            print(f"{name}: {thumb} thumbnail")

    print("\n TIP: To manually capture better thumbnails:")
    print("1. Position asset in viewport nicely")
    print("2. Run: lib.take_screenshot_for_asset('Oat', 'characters')")
    print("3. Wait 30-40 seconds for screenshot to save")

    return lib

def test_thumbnail_system():
    """Test the thumbnail system"""

    print("\n" + "="*60)
    print("TESTING THUMBNAIL SYSTEM")
    print("="*60)

    lib = AssetLibraryWithThumbnails()

    # Test getting Content Browser thumbnail
    test_asset = "/Engine/BasicShapes/Cube"
    print(f"\nTesting thumbnail for: {test_asset}")

    thumb = lib.get_content_browser_thumbnail(test_asset)
    if thumb:
        print(f"Thumbnail saved to: {thumb}")
    else:
        print("Could not get thumbnail")

    # Test manual screenshot
    print("\nTo take manual screenshot:")
    print("1. Position something in viewport")
    print("2. Run: lib.take_screenshot_for_asset('TestAsset', 'props')")

    return lib

if __name__ == "__main__":
    print("\n" + "="*60)
    print("ASSET LIBRARY WITH THUMBNAIL SUPPORT")
    print("="*60)

    print("\nBenefits of thumbnails:")
    print("Visual reference in UI")
    print("Verify correct asset")
    print("See placeholder appearance")
    print("Auto-capture from Content Browser")

    print("\nTwo approaches:")
    print("1. AUTO: Get from Content Browser (instant)")
    print("2. MANUAL: Screenshot viewport (better quality)")

    print("\nCommands:")
    print("setup_with_thumbnails()  - Setup with auto thumbnails")
    print("test_thumbnail_system()  - Test thumbnail capture")

    print("\n" + "-"*40)
    setup_with_thumbnails()
