# Copyright (c) 2025 Tyler Varacchi. All Rights Reserved.
# This code is proprietary. Unauthorized copying or use is prohibited.
"""
Configuration Package
Centralized settings and environment management
"""

# Import and expose config manager
from .config_manager import (
    Config,
    get_config,
    get,
    set,
    get_api_key,
    set_api_key
)

__all__ = [
    'Config',
    'get_config',
    'get',
    'set',
    'get_api_key',
    'set_api_key'
]

# Auto-initialize config on import
_config = get_config()
