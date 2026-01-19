# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Episodes Manager - Handles episode organization within shows
"""

import unreal
import json
import shutil
from pathlib import Path
from datetime import datetime


class EpisodesManager:
    """Manages episodes within shows"""

    def __init__(self):
        # Get the content path
        self.content_path = unreal.Paths.project_content_dir()
        self.plugin_content = Path(self.content_path) / "StoryboardTo3D"
        self.shows_root = self.plugin_content / "Shows"

        # Ensure directories exist
        self.shows_root.mkdir(parents=True, exist_ok=True)

    def get_show_episodes(self, show_name):
        """Get all episodes for a show"""
        show_path = self.shows_root / show_name
        episodes_path = show_path / "Episodes"

        if not episodes_path.exists():
            episodes_path.mkdir(parents=True, exist_ok=True)
            return []

        episodes = []
        for episode_dir in episodes_path.iterdir():
            if episode_dir.is_dir():
                metadata_file = episode_dir / "episode_metadata.json"
                if metadata_file.exists():
                    try:
                        with open(metadata_file, 'r') as f:
                            metadata = json.load(f)
                            episodes.append(metadata)
                    except:
                        # Create metadata if missing
                        metadata = self.create_episode_metadata(episode_dir.name, episode_dir)
                        episodes.append(metadata)
                else:
                    # Create metadata if missing
                    metadata = self.create_episode_metadata(episode_dir.name, episode_dir)
                    episodes.append(metadata)

        return episodes

    def create_episode_metadata(self, name, path):
        """Create metadata for an episode"""
        safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_')

        metadata = {
            'name': name,
            'safe_name': safe_name,
            'created': datetime.now().isoformat(),
            'modified': datetime.now().isoformat(),
            'path': str(path),
            'panel_count': 0,
            'sequence_count': 0,
            'number': self.extract_episode_number(name)
        }

        # Save metadata
        metadata_file = path / "episode_metadata.json"
        with open(metadata_file, 'w') as f:
            json.dump(metadata, f, indent=2)

        return metadata

    def extract_episode_number(self, name):
        """Extract episode number from name"""
        import re
        # Look for patterns like "Episode 1", "Ep1", "E01", etc.
        patterns = [
            r'[Ee]pisode\s*(\d+)',
            r'[Ee]p\s*(\d+)',
            r'[Ee]\s*(\d+)',
            r'(\d+)'
        ]

        for pattern in patterns:
            match = re.search(pattern, name)
            if match:
                return int(match.group(1))
        return 0

    def create_episode(self, show_name, episode_name):
        """Create a new episode"""
        show_path = self.shows_root / show_name
        episodes_path = show_path / "Episodes"
        episodes_path.mkdir(parents=True, exist_ok=True)

        # Create safe name
        safe_name = "".join(c for c in episode_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        safe_name = safe_name.replace(' ', '_')

        # Create episode directory
        episode_path = episodes_path / safe_name
        if episode_path.exists():
            # Add number suffix if exists
            counter = 1
            while episode_path.exists():
                episode_path = episodes_path / f"{safe_name}_{counter}"
                counter += 1

        episode_path.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        (episode_path / "Panels").mkdir(exist_ok=True)
        (episode_path / "Sequences").mkdir(exist_ok=True)
        (episode_path / "Assets").mkdir(exist_ok=True)
        (episode_path / "Scripts").mkdir(exist_ok=True)

        # Create metadata
        metadata = self.create_episode_metadata(episode_name, episode_path)

        unreal.log(f"Created episode: {episode_name} in show: {show_name}")

        # Sync content browser
        self.sync_content_browser()

        return episode_path, metadata

    def rename_episode(self, show_name, old_safe_name, new_name):
        """Rename an episode"""
        show_path = self.shows_root / show_name
        episodes_path = show_path / "Episodes"
        old_path = episodes_path / old_safe_name

        if not old_path.exists():
            unreal.log_error(f"Episode not found: {old_safe_name}")
            return False

        # Create new safe name
        new_safe_name = "".join(c for c in new_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        new_safe_name = new_safe_name.replace(' ', '_')

        new_path = episodes_path / new_safe_name

        # Check if new name already exists
        if new_path.exists() and new_path != old_path:
            unreal.log_error(f"Episode already exists: {new_name}")
            return False

        # Rename directory
        old_path.rename(new_path)

        # Update metadata
        metadata_file = new_path / "episode_metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            metadata['name'] = new_name
            metadata['safe_name'] = new_safe_name
            metadata['modified'] = datetime.now().isoformat()
            metadata['path'] = str(new_path)

            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

        unreal.log(f"Renamed episode: {old_safe_name} to {new_name}")

        # Sync content browser
        self.sync_content_browser()

        return True

    def delete_episode(self, show_name, episode_safe_name):
        """Delete an episode"""
        show_path = self.shows_root / show_name
        episodes_path = show_path / "Episodes"
        episode_path = episodes_path / episode_safe_name

        if not episode_path.exists():
            unreal.log_error(f"Episode not found: {episode_safe_name}")
            return False

        try:
            # Remove directory and all contents
            shutil.rmtree(episode_path)
            unreal.log(f"Deleted episode: {episode_safe_name}")

            # Sync content browser
            self.sync_content_browser()

            return True
        except Exception as e:
            unreal.log_error(f"Failed to delete episode: {e}")
            return False

    def duplicate_episode(self, show_name, episode_safe_name):
        """Duplicate an episode"""
        show_path = self.shows_root / show_name
        episodes_path = show_path / "Episodes"
        source_path = episodes_path / episode_safe_name

        if not source_path.exists():
            unreal.log_error(f"Episode not found: {episode_safe_name}")
            return None

        # Create new name
        base_name = episode_safe_name
        counter = 1
        new_path = episodes_path / f"{base_name}_copy"

        while new_path.exists():
            counter += 1
            new_path = episodes_path / f"{base_name}_copy{counter}"

        # Copy entire directory
        shutil.copytree(source_path, new_path)

        # Update metadata
        metadata_file = new_path / "episode_metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            new_name = f"{metadata['name']} Copy" if counter == 1 else f"{metadata['name']} Copy {counter}"
            metadata['name'] = new_name
            metadata['safe_name'] = new_path.name
            metadata['created'] = datetime.now().isoformat()
            metadata['modified'] = datetime.now().isoformat()
            metadata['path'] = str(new_path)

            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

        unreal.log(f"Duplicated episode: {episode_safe_name}")

        # Sync content browser
        self.sync_content_browser()

        return new_path

    def import_panels_to_episode(self, show_name, episode_safe_name, panel_files):
        """Import panels to an episode"""
        show_path = self.shows_root / show_name
        episode_path = show_path / "Episodes" / episode_safe_name
        panels_path = episode_path / "Panels"
        panels_path.mkdir(parents=True, exist_ok=True)

        imported = []
        for panel_file in panel_files:
            source = Path(panel_file)
            if source.exists():
                # Create unique name if needed
                dest = panels_path / source.name
                if dest.exists():
                    base = source.stem
                    ext = source.suffix
                    counter = 1
                    while dest.exists():
                        dest = panels_path / f"{base}_{counter}{ext}"
                        counter += 1

                # Copy file
                shutil.copy2(source, dest)
                imported.append(str(dest))
                unreal.log(f"Imported panel: {source.name}")

        # Update episode metadata
        metadata_file = episode_path / "episode_metadata.json"
        if metadata_file.exists():
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            metadata['panel_count'] = len(list(panels_path.glob("*.png"))) + len(list(panels_path.glob("*.jpg")))
            metadata['modified'] = datetime.now().isoformat()

            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)

        # Sync content browser
        self.sync_content_browser()

        return imported

    def sync_content_browser(self):
        """Sync the content browser with the file system"""
        try:
            # Force content browser refresh
            content_path = "/Game/StoryboardTo3D/Shows"

            # Use Unreal's asset registry to refresh
            asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()
            asset_registry.scan_paths_synchronous([content_path], force_rescan=True)

            # Refresh content browser
            unreal.EditorAssetLibrary.sync_browser_to_objects([content_path])

        except Exception as e:
            unreal.log_warning(f"Failed to sync content browser: {e}")
