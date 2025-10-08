"""
Utility functions for Rucio workflow operations.

This module provides helper functions for validation, scope extraction,
and common operations, similar to those used in PanDA dataservice modules.
"""

import re
import hashlib, zlib
import os
from typing import Tuple, Dict, Any, List, Optional
from datetime import datetime

from .exceptions import ValidationError


# --- Service utilities

def calculate_file_checksum(filepath, algorithm='md5'):
    """Calculate checksum of a file"""
    hash_func = hashlib.new(algorithm)
    with open(filepath, 'rb') as f:
        for chunk in iter(lambda: f.read(4096), b""):
            hash_func.update(chunk)
    return hash_func.hexdigest()

# ---
def calculate_adler32_from_file(file_path, chunk_size=4096):
    """
    Calculates the Adler-32 checksum of a file.

    Args:
        filepath (str): The path to the file.
        chunk_size (int): The size of chunks to read from the file.

    Returns:
        int: The Adler-32 checksum of the file.
    """
    adler32_checksum = 1  # Initial Adler-32 value

    try:
        with open(file_path, 'rb') as f:
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                adler32_checksum = zlib.adler32(chunk, adler32_checksum)
        return adler32_checksum & 0xffffffff  # Ensure 32-bit unsigned result
    except:
        print(f"Adler-32: problem with file {file_path}, exiting")
        exit(-2)

# --- Main utility classe
class RucioUtils:
    """Utility class for Rucio-specific operations."""
    
    @staticmethod
    def extract_scope(dataset_name: str, strip_slash: bool = False) -> Tuple[str, str]:
        """
        Extract scope from a given dataset name.
        
        Supports both formats:
        - Explicit colon format: scope:name (e.g., "user.pilot:dataset.name")
        - Inferred dot format: scope.name (e.g., "user.pilot.dataset.name")
        
        Similar to the extract_scope method in panda-server/pandaserver/dataservice/ddm.py
        
        Args:
            dataset_name: Dataset name in either format
            strip_slash: Whether to strip trailing slash
            
        Returns:
            Tuple of (scope, dataset_name)
            
        Examples:
            extract_scope("user.pilot:my.dataset.name") -> ("user.pilot", "my.dataset.name")
            extract_scope("user.pilot.dataset.name") -> ("user.pilot", "dataset.name") 
            extract_scope("data.atlas.mc.run123.output") -> ("data.atlas.mc.run123", "output")
        """
        if strip_slash and dataset_name.endswith("/"):
            dataset_name = re.sub("/$", "", dataset_name)
            
        # Handle explicit colon format: scope:name
        if ":" in dataset_name:
            parts = dataset_name.split(":", 1)  # Split on first colon only
            if len(parts) == 2:
                scope, name = parts
                return scope.strip(), name.strip()
            
        # Handle inferred dot format: scope.name
        parts = dataset_name.split(".")
        if len(parts) < 2:
            raise ValidationError(f"Dataset name must contain at least one dot or colon: {dataset_name}")
            
        # For user/group datasets, scope typically includes first two parts
        if dataset_name.startswith("user") or dataset_name.startswith("group"):
            if len(parts) >= 3:
                scope = ".".join(parts[0:2])  # e.g., "user.pilot"
                name = ".".join(parts[2:])    # e.g., "dataset.name"
            else:
                scope = parts[0]              # e.g., "user"
                name = ".".join(parts[1:])    # e.g., "pilot"
        else:
            # For other datasets, last part is name, everything else is scope
            scope = ".".join(parts[:-1])      # e.g., "data.atlas.mc"
            name = parts[-1]                  # e.g., "output"
            
        return scope, name
    
    @staticmethod
    def generate_guid() -> str:
        """
        Generate a GUID for a file.
        
        Returns:
            UUID-like GUID string
        """
        import uuid
        return str(uuid.uuid4())
    
    @staticmethod
    def format_guid(guid: str) -> str:
        """
        Format GUID to standard format used by PanDA/Rucio.
        
        Args:
            guid: Raw GUID string
            
        Returns:
            Formatted GUID string
        """
        # Remove hyphens and ensure proper format
        clean_guid = guid.replace('-', '')
        if len(clean_guid) == 32:
            return f"{clean_guid[0:8]}-{clean_guid[8:12]}-{clean_guid[12:16]}-{clean_guid[16:20]}-{clean_guid[20:32]}"
        return guid
    
    @staticmethod
    def generate_vuid(scope: str, name: str) -> str:
        """
        Generate a Version UID (VUID) for a dataset.
        
        Similar to the vuid generation in PanDA's register_dataset method.
        
        Args:
            scope: Dataset scope
            name: Dataset name
            
        Returns:
            VUID string
        """
        vuid = hashlib.md5((scope + ":" + name).encode()).hexdigest()
        return f"{vuid[0:8]}-{vuid[8:12]}-{vuid[12:16]}-{vuid[16:20]}-{vuid[20:32]}"
    
    @staticmethod
    def parse_pfn(pfn: str) -> Dict[str, str]:
        """
        Parse a Physical File Name (PFN) to extract components.
        
        Args:
            pfn: Physical file name/path
            
        Returns:
            Dictionary with parsed components
        """
        components = {
            'protocol': '',
            'host': '',
            'port': '',
            'path': '',
            'filename': ''
        }
        
        # Handle different protocols (root://, srm://, https://, etc.)
        if '://' in pfn:
            protocol, rest = pfn.split('://', 1)
            components['protocol'] = protocol
            
            if '/' in rest:
                host_port, path = rest.split('/', 1)
                components['path'] = '/' + path
                components['filename'] = os.path.basename(path)
                
                if ':' in host_port and not host_port.startswith('['):  # IPv6 check
                    host, port = host_port.rsplit(':', 1)
                    components['host'] = host
                    components['port'] = port
                else:
                    components['host'] = host_port
            else:
                components['host'] = rest
        else:
            # Local file path
            components['path'] = pfn
            components['filename'] = os.path.basename(pfn)
            
        return components


class ValidationUtils:
    """Utility class for validation operations."""
    
    @staticmethod
    def validate_dataset_name(dataset_name: str) -> bool:
        """
        Validate dataset name format.
        
        Args:
            dataset_name: Dataset name to validate
            
        Returns:
            True if valid
            
        Raises:
            ValidationError: If dataset name is invalid
        """
        if not dataset_name:
            raise ValidationError("Dataset name cannot be empty")
            
        if len(dataset_name) > 255:
            raise ValidationError("Dataset name too long (max 255 characters)")
            
        # Basic pattern check
        if not re.match(r'^[a-zA-Z0-9._-]+$', dataset_name.replace(':', '')):
            raise ValidationError("Dataset name contains invalid characters")
            
        return True
    
    @staticmethod
    def validate_scope(scope: str) -> bool:
        """
        Validate scope format.
        
        Args:
            scope: Scope to validate
            
        Returns:
            True if valid
            
        Raises:
            ValidationError: If scope is invalid
        """
        if not scope:
            raise ValidationError("Scope cannot be empty")
            
        if not re.match(r'^[a-zA-Z0-9._-]+$', scope):
            raise ValidationError("Scope contains invalid characters")
            
        return True
    
    @staticmethod
    def validate_lfn(lfn: str) -> bool:
        """
        Validate Logical File Name (LFN).
        
        Args:
            lfn: LFN to validate
            
        Returns:
            True if valid
            
        Raises:
            ValidationError: If LFN is invalid
        """
        if not lfn:
            raise ValidationError("LFN cannot be empty")
            
        if len(lfn) > 1024:
            raise ValidationError("LFN too long (max 1024 characters)")
            
        return True
    
    @staticmethod
    def validate_pfn(pfn: str) -> bool:
        """
        Validate Physical File Name (PFN).
        
        Args:
            pfn: PFN to validate
            
        Returns:
            True if valid
            
        Raises:
            ValidationError: If PFN is invalid
        """
        if not pfn:
            raise ValidationError("PFN cannot be empty")
            
        # Check if it's a valid URL or file path
        if '://' in pfn:
            # URL format
            if not re.match(r'^[a-zA-Z][a-zA-Z0-9+.-]*://.+', pfn):
                raise ValidationError("Invalid PFN URL format")
        else:
            # File path format
            if not os.path.isabs(pfn):
                raise ValidationError("PFN must be an absolute path")
                
        return True
    
    @staticmethod
    def validate_checksum(checksum: str) -> bool:
        """
        Validate checksum format.
        
        Args:
            checksum: Checksum to validate
            
        Returns:
            True if valid
            
        Raises:
            ValidationError: If checksum is invalid
        """
        if not checksum:
            raise ValidationError("Checksum cannot be empty")
            
        # Check for supported formats (md5:, ad:, etc.)
        if checksum.startswith('md5:'):
            hash_part = checksum[4:]
            if not re.match(r'^[a-fA-F0-9]{32}$', hash_part):
                raise ValidationError("Invalid MD5 hash format")
        elif checksum.startswith('ad:'):
            hash_part = checksum[3:]
            if not re.match(r'^[a-fA-F0-9]{8}$', hash_part):
                raise ValidationError("Invalid Adler32 hash format")
        else:
            raise ValidationError("Unsupported checksum format (use md5: or ad:)")
            
        return True
    
    @staticmethod
    def validate_file_size(size: int) -> bool:
        """
        Validate file size.
        
        Args:
            size: File size in bytes
            
        Returns:
            True if valid
            
        Raises:
            ValidationError: If file size is invalid
        """
        if not isinstance(size, int) or size < 0:
            raise ValidationError("File size must be a non-negative integer")
            
        return True


class MetadataUtils:
    """Utility class for metadata operations."""
    
    @staticmethod
    def create_file_metadata(
        guid: str,
        lfn: str,
        size: int,
        checksum: str,
        scope: str,
        additional_meta: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Create file metadata dictionary in PanDA/Rucio format.
        
        Args:
            guid: File GUID
            lfn: Logical file name
            size: File size in bytes
            checksum: File checksum
            scope: File scope
            additional_meta: Additional metadata
            
        Returns:
            File metadata dictionary
        """
        metadata = {
            "scope": scope,
            "name": lfn,
            "bytes": size,
            "meta": {"guid": guid}
        }
        
        # Add checksum in appropriate format
        if checksum.startswith("md5:"):
            metadata["md5"] = checksum[4:]
        elif checksum.startswith("ad:"):
            metadata["adler32"] = checksum[3:]
            
        # Add additional metadata
        if additional_meta:
            metadata["meta"].update(additional_meta)
            
        return metadata
    
    @staticmethod
    def create_dataset_metadata(
        task_id: Optional[str] = None,
        campaign: Optional[str] = None,
        hidden: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Create dataset metadata dictionary.
        
        Args:
            task_id: Task identifier
            campaign: Campaign name
            hidden: Whether dataset is hidden
            **kwargs: Additional metadata
            
        Returns:
            Dataset metadata dictionary
        """
        metadata = {
            "hidden": hidden,
            "purge_replicas": 0
        }
        
        if task_id:
            metadata["task_id"] = str(task_id)
            
        if campaign:
            metadata["campaign"] = campaign
            
        metadata.update(kwargs)
        return metadata
