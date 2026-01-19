# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Shows Manager - Handles show folder structure and organization
"""

import unreal
import json
import shutil
from pathlib import Path
from datetime import datetime


class ShowsManager:
    """Manages shows folder structure and organization"""

    def __init__(self):
        # Get the project content directory
        self.content_dir = Path(unreal.Paths.project_content_dir())
        self.shows_root = self.content_dir / "StoryboardTo3D" / "Shows"

        # Create root directories if they don't exist
        self.initialize_folders()

    def initialize_folders(self):
        """Create the base folder structure"""
        self.shows_root.mkdir(parents=True, exist_ok=True)
        unreal.log(f"Shows directory initialized at: {self.shows_root}")

    def create_show(self, show_name):
        """Create a new show with proper folder structure"""
        # Sanitize show name for folder
        safe_name = "".join(c for c in show_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_')
        show_path = self.shows_root / safe_name

        # Create show folder and subfolders
        show_path.mkdir(exist_ok=True)
        panels_path = show_path / "Panels"
        panels_path.mkdir(exist_ok=True)

        # Create show metadata file
        metadata = {
            'name': show_name,
            'safe_name': safe_name,
            'created': datetime.now().isoformat(),
            'modified': datetime.now().isoformat(),
            'panels': [],
            'sequences': []
        }

        metadata_file = show_path / "show_metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        unreal.log(f"Created show '{show_name}' at: {show_path}")
        return show_path, metadata

    def import_panels_to_show(self, show_name, source_files):
        """Import panels to the show's panels folder"""
        show_path = self.shows_root / show_name
        panels_path = show_path / "Panels"

        if not panels_path.exists():
            unreal.log_error(f"Show '{show_name}' panels folder not found")
            return []

        imported_files = []
        for source_file in source_files:
            source = Path(source_file)
            if source.exists():
                # Copy to panels folder with organized naming
                existing_count = len(list(panels_path.glob('*')))
                dest_name = f"{existing_count:03d}_{source.name}"
                dest_path = panels_path / dest_name
                shutil.copy2(source, dest_path)
                imported_files.append(str(dest_path))
                unreal.log(f"Imported panel: {dest_name}")

        # Update show metadata
        self.update_show_metadata(show_name, imported_files)

        return imported_files

    def update_show_metadata(self, show_name, new_panels):
        """Update show metadata with new panels"""
        show_path = self.shows_root / show_name
        metadata_file = show_path / "show_metadata.json"

        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            metadata['modified'] = datetime.now().isoformat()
            metadata['panels'].extend([str(Path(p).name) for p in new_panels])

            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

    def get_all_shows(self):
        """Get list of all shows"""
        shows = []
        if self.shows_root.exists():
            for show_dir in self.shows_root.iterdir():
                if show_dir.is_dir():
                    metadata_file = show_dir / "show_metadata.json"
                    if metadata_file.exists():
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                            shows.append(metadata)
        return shows

    def load_show(self, show_name):
        """Load a show's data"""
        show_path = self.shows_root / show_name
        metadata_file = show_path / "show_metadata.json"

        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                return json.load(f)
        return None

    def delete_show(self, show_name):
        """Delete a show and all its contents"""
        show_path = self.shows_root / show_name
        if show_path.exists():
            shutil.rmtree(show_path)
            unreal.log(f"Deleted show: {show_name}")
            return True
        return False

    def rename_show(self, old_name, new_name):
        """Rename a show"""
        old_path = self.shows_root / old_name
        safe_new_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_new_name = safe_new_name.replace(' ', '_')
        new_path = self.shows_root / safe_new_name

        if old_path.exists() and not new_path.exists():
            old_path.rename(new_path)

            # Update metadata
            metadata_file = new_path / "show_metadata.json"
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                metadata['name'] = new_name
                metadata['safe_name'] = safe_new_name
                metadata['modified'] = datetime.now().isoformat()

                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2)

            unreal.log(f"Renamed show from '{old_name}' to '{new_name}'")
            return True
        return False

    def duplicate_show(self, show_name):
        """Duplicate a show with all its contents"""
        source_path = self.shows_root / show_name
        if source_path.exists():
            # Find unique name for copy
            copy_num = 1
            while True:
                new_name = f"{show_name}_copy{copy_num}"
                new_path = self.shows_root / new_name
                if not new_path.exists():
                    break
                copy_num += 1

            # Copy entire directory
            shutil.copytree(source_path, new_path)

            # Update metadata
            metadata_file = new_path / "show_metadata.json"
            if metadata_file.exists():
                with open(metadata_file, 'r') as f:
                    metadata = json.load(f)

                metadata['name'] = f"{metadata['name']} Copy {copy_num}"
                metadata['safe_name'] = new_name
                metadata['created'] = datetime.now().isoformat()
                metadata['modified'] = datetime.now().isoformat()

                with open(metadata_file, 'w') as f:
                    json.dump(metadata, f, indent=2)

            unreal.log(f"Duplicated show '{show_name}' to '{new_name}'")
            return new_path
        return None
