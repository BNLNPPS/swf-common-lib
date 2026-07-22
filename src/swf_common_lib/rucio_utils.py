"""
Utility functions for Rucio workflow operations.
"""

import hashlib
import logging
import os
import re
import zlib
from typing import Optional

from rucio.client import Client as RucioClient
from rucio.common.exception import (
    DataIdentifierAlreadyExists,
    FileAlreadyExists,
    RSENotFound,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def extract_scope(dataset_name: str, strip_slash: bool = False):
    """
    Extract scope from a given dataset name.

    Supports both formats:
    - Explicit colon format: scope:name (e.g., "user.pilot:dataset.name")
    - Inferred dot format:   scope.name (e.g., "user.pilot.dataset.name")

    Based on the extract_scope method in rucio_comms/utils.py (RucioUtils).

    Args:
        dataset_name: Dataset name in either format.
        strip_slash:  Whether to strip a trailing slash.

    Returns:
        Tuple of (scope, name).
    """
    if strip_slash and dataset_name.endswith("/"):
        dataset_name = re.sub("/$", "", dataset_name)

    # Handle explicit colon format: scope:name
    if ":" in dataset_name:
        parts = dataset_name.split(":", 1)
        if len(parts) == 2:
            return parts[0].strip(), parts[1].strip()

    # Handle inferred dot format
    parts = dataset_name.split(".")
    if len(parts) < 2:
        raise ValueError(f"Dataset name must contain at least one dot or colon: {dataset_name}")

    if dataset_name.startswith("user") or dataset_name.startswith("group"):
        if len(parts) >= 3:
            scope = ".".join(parts[0:2])
            name  = ".".join(parts[2:])
        else:
            scope = parts[0]
            name  = ".".join(parts[1:])
    else:
        scope = ".".join(parts[:-1])
        name  = parts[-1]

    return scope, name


def generate_vuid(scope: str, name: str) -> str:
    """
    Generate a Version UID (VUID) for a dataset.

    Args:
        scope: Dataset scope.
        name:  Dataset name.

    Returns:
        VUID string in UUID-like format.
    """
    vuid = hashlib.md5((scope + ":" + name).encode()).hexdigest()
    return f"{vuid[0:8]}-{vuid[8:12]}-{vuid[12:16]}-{vuid[16:20]}-{vuid[20:32]}"


# ---------------------------------------------------------------------------
# Checksum / file helpers
# ---------------------------------------------------------------------------

def calculate_file_checksum(file_path: str, algorithm: str = 'md5', chunk_size: int = 4096) -> str:
    """
    Calculate the checksum of a file using the specified hash algorithm.

    Args:
        file_path:  Path to the file.
        algorithm:  Hash algorithm name (e.g. ``'md5'``, ``'sha256'``).
        chunk_size: Size of chunks to read from the file.

    Returns:
        Hex-encoded checksum string.
    """
    h = hashlib.new(algorithm)
    with open(file_path, 'rb') as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


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

def register_file_on_rse(data_obj, file_path: str, file_name: str):
    """
    Register an uploaded file on RSE

    This is a helper method to register a file on RSE after it has been uploaded.

    It expects an object with some necessary attributes, e.g. the "data object" defined in relevant class.
    Attributes to be harvested from the "data object": client, rucio_did_client, replica_client, dataset, rse: str, scope: str
    """
    
    adler = calculate_adler32_from_file(file_path)
    print(f"Adler32 checksum of the file {file_path}: {adler}")
  
    try:
        # Step 1: Get file metadata
        file_size       = os.path.getsize(file_path)
        file_checksum   = calculate_file_checksum(file_path, 'md5')
        
        print(f"File: {file_name}")
        print(f"Size: {file_size} bytes")
        print(f"MD5:  {file_checksum}")

      
        # Step 2: Check if DID already exists
        try:
            existing_did = data_obj.rucio_did_client.get_did(data_obj.rucio_scope, file_name)
            print(f"DID already exists: {existing_did}")
        except:
            # DID doesn't exist, we'll create it
            print("DID doesn't exist yet, will create new one")

        dataset_folder = data_obj.dataset

        # Register the replica
        data_obj.rucio_replica_client.add_replica(
            rse         = data_obj.rse,
            scope       = data_obj.rucio_scope,
            name        = file_name,
            bytes_      = file_size,
            adler32     = f'{adler:x}',
            pfn         = f'root://dcintdoor.sdcc.bnl.gov:1094/pnfs/sdcc.bnl.gov/eic/epic/disk/swfdaqtest/{dataset_folder}/{file_name}'
            )
        
        print(f"✓ Replica registered on RSE: {data_obj.rse}")

        return True

    except RSENotFound:
        print(f"✗ Error: RSE '{data_obj.rse}' not found")
        return False
    except Exception as e:
        print(f"✗ Error registering file: {str(e)}")
        return False


# ---------------------------------------------------------------------------
# Dataset operations  (standalone equivalents of DatasetManager methods)
# ---------------------------------------------------------------------------

def create_dataset(dataset_name: str, lifetime_days: Optional[int] = None,
                   open_dataset: bool = True, client=None):
    """
    Create a Rucio dataset.

    Standalone equivalent of ``DatasetManager.create_dataset``.

    Args:
        dataset_name:  Full dataset identifier (``scope:name`` or dot-separated).
        lifetime_days: Optional lifetime in days.
        open_dataset:  Whether the dataset should be left open (default True).
        client:        An existing ``rucio.client.Client`` instance.
                       A new one is created when *None*.

    Returns:
        dict with keys ``scope``, ``name``, ``duid`` on success, or *None* on
        failure.
    """
    if client is None:
        client = RucioClient()

    try:
        scope, name = extract_scope(dataset_name)
        logger.info(f"Creating dataset: {scope}:{name}")

        # Build metadata
        meta = {}
        if lifetime_days is not None:
            meta['lifetime'] = lifetime_days * 86400  # seconds

        # Create the dataset DID
        try:
            client.add_dataset(scope=scope, name=name, meta=meta,
                               lifetime=meta.get('lifetime'))
            logger.info(f"Dataset created: {scope}:{name}")
        except DataIdentifierAlreadyExists:
            logger.info(f"Dataset already exists: {scope}:{name}")
            # Apply lifetime to existing dataset if requested
            if lifetime_days is not None:
                client.set_metadata(scope=scope, name=name,
                                    key='lifetime',
                                    value=lifetime_days * 86400)
                logger.info(f"Updated lifetime for existing dataset: "
                            f"{scope}:{name} -> {lifetime_days} days")

        # Set open/closed status
        if open_dataset:
            try:
                client.set_status(scope=scope, name=name, open=True)
            except Exception:
                pass  # may already be open

        # Generate identifiers
        vuid = generate_vuid(scope, name)
        duid = vuid
        result = {
            'scope': scope,
            'name':  name,
            'duid':  duid,
            'vuid':  vuid,
        }
        logger.info(f"Dataset ready: {scope}:{name}  duid={duid}")
        return result

    except Exception as e:
        logger.error(f"Failed to create dataset {dataset_name}: {e}")
        print(f"✗ Error creating dataset: {e}")
        return None


# ---------------------------------------------------------------------------
# File-to-dataset attachment  (standalone equivalent of FileManager method)
# ---------------------------------------------------------------------------

def add_files_to_dataset(files, dataset_name: str,
                         dataset_scope: Optional[str] = None, rse: Optional[str] = None,
                         client=None):
    """
    Add files to a Rucio dataset.

    Standalone equivalent of ``FileManager.add_files_to_dataset``.

    Args:
        files:         List of LFN strings (``scope:name`` or dot-separated).
        dataset_name:  Target dataset name (``scope:name`` or dot-separated).
        dataset_scope: Explicit dataset scope (extracted from *dataset_name*
                       when *None*).
        rse:           Optional RSE constraint.
        client:        An existing ``rucio.client.Client`` instance.
                       A new one is created when *None*.

    Returns:
        True on success.

    Raises:
        RuntimeError: If the operation fails.
    """
    if client is None:
        client = RucioClient()

    try:
        if dataset_scope is None:
            dataset_scope, dataset_name = extract_scope(dataset_name)

        logger.info(f"Adding {len(files)} file(s) to dataset: "
                    f"{dataset_scope}:{dataset_name}")

        # Build Rucio file dicts
        file_dicts = []
        for item in files:
            if isinstance(item, str):
                file_scope, lfn = extract_scope(item)
                file_dicts.append({'scope': file_scope, 'name': lfn})
            else:
                raise ValueError(f"Invalid file item type: {type(item)}")

        # Attach in batches of 1000
        batch_size = 1000
        for i in range(0, len(file_dicts), batch_size):
            batch = file_dicts[i:i + batch_size]
            try:
                client.add_files_to_dataset(
                    scope=dataset_scope, name=dataset_name,
                    files=batch, rse=rse,
                )
                logger.debug(f"Added batch of {len(batch)} file(s) to dataset")
            except FileAlreadyExists:
                # Retry individually so we skip only true duplicates
                for fd in batch:
                    try:
                        client.add_files_to_dataset(
                            scope=dataset_scope, name=dataset_name,
                            files=[fd], rse=rse,
                        )
                    except FileAlreadyExists:
                        logger.debug(f"File already in dataset: {fd['name']}")

        logger.info(f"Successfully added files to dataset: "
                    f"{dataset_scope}:{dataset_name}")
        return True

    except Exception as e:
        error_msg = (f"Failed to add files to dataset "
                     f"{dataset_scope}:{dataset_name}: {e}")
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e
