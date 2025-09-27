"""Advanced configuration manager for persisting application settings.

This module provides a ConfigManager class that handles saving and loading
configuration settings in a hierarchical manner using JSON as the storage format.
Settings are stored in the user's home directory by default.

Example:
    >>> config = ConfigManager()
    >>> config.set('app.theme', 'dark')
    >>> theme = config.get('app.theme', 'light')
    >>> config.sync()  # Save to disk
"""
from __future__ import annotations

import json
import os
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple, Union, TypeVar, Type, overload
from enum import Enum
import time

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

T = TypeVar('T')

class ConfigManager:
    """Manages application configuration with hierarchical key-value storage.
    
    Configuration is stored in a JSON file located in the user's home directory
    (`~/.sonlab_gui_config.json` by default). Nested dictionaries are supported 
    via dotted keys, e.g. `segmentation.min_distance` will be saved as
    `{"segmentation": {"min_distance": value}}`.
    """
    
    def __init__(self, filename: Optional[Union[str, os.PathLike]] = None) -> None:
        """Initialize the configuration manager.
        
        Args:
            filename: Optional path to the config file. If not provided, uses
                     `~/.sonlab_gui_config.json`.
        """
        # Convert filename to Path object for consistent path handling
        if filename is None:
            # Use appdirs to get appropriate config directory per platform
            try:
                from appdirs import user_config_dir
                config_dir = Path(user_config_dir('sonlab', 'SONLab'))
                config_dir.mkdir(parents=True, exist_ok=True)
                self._path = config_dir / 'config.json'
            except ImportError:
                # Fallback to home directory if appdirs not available
                self._path = Path.home() / '.sonlab_gui_config.json'
        else:
            self._path = Path(filename).expanduser().absolute()
            
        # Ensure parent directory exists
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            logger.warning(f"Could not create config directory {self._path.parent}: {e}")
            # Fall back to a temporary file if we can't write to the desired location
            import tempfile
            self._path = Path(tempfile.gettempdir()) / 'sonlab_temp_config.json'
            
        self._data: Dict[str, Any] = {}
        self._dirty = False
        self._load()
    
    # ------------------------------------------------------------------ Public API
    
    @overload
    def get(self, key: str, default: T) -> T: ...
    
    @overload
    def get(self, key: str, default: None = None) -> Optional[Any]: ...
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key.
        
        Args:
            key: Dotted key path (e.g., 'app.theme')
            default: Default value if key doesn't exist
            
        Returns:
            The configuration value or default if not found
        """
        try:
            node, leaf = self._traverse(key, create=False)
            if node is None or leaf not in node:
                return default
            return node[leaf]
        except Exception as e:
            logger.warning(f"Error getting config key '{key}': {e}")
            return default
    
    def get_bool(self, key: str, default: bool = False) -> bool:
        """Get a boolean configuration value."""
        return bool(self.get(key, default))
    
    def get_int(self, key: str, default: int = 0) -> int:
        """Get an integer configuration value."""
        try:
            return int(self.get(key, default))
        except (TypeError, ValueError):
            return default
    
    def get_float(self, key: str, default: float = 0.0) -> float:
        """Get a float configuration value."""
        try:
            return float(self.get(key, default))
        except (TypeError, ValueError):
            return default
    
    def get_enum(self, key: str, enum_type: Type[Enum], default: Enum) -> Enum:
        """Get an enum configuration value."""
        value = self.get(key)
        if isinstance(value, str):
            try:
                return enum_type[value]
            except (KeyError, AttributeError):
                pass
        return default
    
    def set(self, key: str, value: Any) -> None:
        """Set a configuration value.
        
        Args:
            key: Dotted key path (e.g., 'app.theme')
            value: Value to store (must be JSON-serializable)
        """
        try:
            node, leaf = self._traverse(key, create=True)
            if node.get(leaf) != value:
                node[leaf] = value
                self._dirty = True
        except Exception as e:
            logger.error(f"Error setting config key '{key}': {e}")
    
    def delete(self, key: str) -> bool:
        """Delete a configuration key.
        
        Returns:
            True if the key was deleted, False if it didn't exist
        """
        try:
            node, leaf = self._traverse(key, create=False)
            if node is not None and leaf in node:
                del node[leaf]
                self._dirty = True
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting config key '{key}': {e}")
            return False
    
    def sync(self) -> bool:
        """Write the configuration to disk if it has changed.
        
        Returns:
            True if the sync was successful, False otherwise
        """
        if not self._dirty:
            return True
            
        # Ensure the directory exists
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
        except (OSError, PermissionError) as e:
            logger.error(f"Cannot create config directory {self._path.parent}: {e}")
            return False
            
        # Try multiple times in case of file locking issues
        for attempt in range(3):
            try:
                # Use a temporary file in the same directory for atomic write
                temp_path = self._path.with_suffix('.tmp')
                
                # Write to temporary file
                with temp_path.open('w', encoding='utf-8') as fh:
                    json.dump(self._data, fh, indent=2, ensure_ascii=False)
                
                # On Windows, we need to remove the destination file first
                if self._path.exists():
                    self._path.unlink(missing_ok=True)
                
                # Atomic rename (works across platforms)
                temp_path.replace(self._path)
                
                # Verify the file was written
                if not self._path.exists():
                    raise OSError(f"Failed to verify config file at {self._path}")
                
                self._dirty = False
                logger.debug(f"Successfully saved config to {self._path}")
                return True
                
            except (OSError, IOError, PermissionError) as e:
                import time
                if attempt == 2:  # Last attempt
                    logger.error(f"Failed to write config after 3 attempts: {e}", exc_info=True)
                    return False
                time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                continue
                
        return False
    
    def reload(self) -> None:
        """Reload configuration from disk, discarding any unsaved changes."""
        self._load()
    
    def clear(self) -> None:
        """Clear all configuration data."""
        self._data = {}
        self._dirty = True
    
    # ------------------------------------------------------------------ Helpers
    
    def _load(self) -> None:
        """Load configuration from disk."""
        if not self._path.exists():
            self._data = {}
            logger.info(f"Config file {self._path} does not exist, using empty config")
            return
            
        try:
            with self._path.open('r', encoding='utf-8') as fh:
                self._data = json.load(fh)
            self._dirty = False
            logger.debug(f"Successfully loaded config from {self._path}")
            
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file {self._path}: {e}")
            # Try to back up the corrupted config
            try:
                backup_path = self._path.with_suffix(f'.{int(time.time())}.bak')
                self._path.rename(backup_path)
                logger.warning(f"Backed up corrupted config to {backup_path}")
            except Exception as backup_err:
                logger.error(f"Failed to back up corrupted config: {backup_err}")
                
            self._data = {}
            self._dirty = True
            
        except Exception as e:
            logger.error(f"Failed to load config from {self._path}: {e}", exc_info=True)
            self._data = {}
            self._dirty = True
    
    def _traverse(self, key: str, create: bool = False) -> Tuple[Optional[Dict[str, Any]], str]:
        """Traverse the configuration tree to find a key.
        
        Args:
            key: Dotted key path (e.g., 'app.theme')
            create: If True, create missing nodes
            
        Returns:
            Tuple of (parent_dict, leaf_key)
        """
        if not key:
            raise ValueError("Key cannot be empty")
            
        parts = key.split('.')
        node = self._data
        
        for part in parts[:-1]:
            if part not in node:
                if not create:
                    return None, parts[-1]
                node[part] = {}
                self._dirty = True
                
            if not isinstance(node[part], dict):
                if not create:
                    return None, parts[-1]
                # Convert scalar to dict
                node[part] = {}
                self._dirty = True
            
            node = node[part]
            
        return node, parts[-1]
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - sync changes to disk."""
        self.sync()
    
    def __getitem__(self, key: str) -> Any:
        """Allow dict-style access to config values."""
        value = self.get(key)
        if value is None:
            raise KeyError(key)
        return value
    
    def __setitem__(self, key: str, value: Any) -> None:
        """Allow dict-style setting of config values."""
        self.set(key, value)
    
    def __contains__(self, key: str) -> bool:
        """Check if a key exists in the config."""
        node, leaf = self._traverse(key, create=False)
        return node is not None and leaf in node
