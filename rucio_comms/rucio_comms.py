# Based on the Rucio workflow example written up by Xin
# -*- coding: utf-8 -*-
from rucio.client import Client as RucioClient
from rucio.client.uploadclient import UploadClient
from rucio.common.exception import RucioException
from rucio.common.exception import (
    DataIdentifierAlreadyExists,
    DataIdentifierNotFound,
    UnsupportedOperation
)

from rucio.common.exception import (
    FileAlreadyExists,
    DataIdentifierNotFound,
    InvalidObject
)


from typing import Optional, List, Dict, Union, Any

import logging, os

from .exceptions import DatasetError, RucioClientError
from .exceptions import FileRegistrationError, ValidationError

from .utils import RucioUtils, ValidationUtils, MetadataUtils


# ---
class FileInfo:
    """Represents a file with its metadata."""
    
    def __init__(
        self,
        lfn: str,
        pfn: str,
        size: int,
        checksum: str,
        guid: Optional[str] = None,
        scope: Optional[str] = None,
        **metadata
    ):
        """
        Initialize FileInfo.
        
        Args:
            lfn: Logical file name
            pfn: Physical file name (existing location)
            size: File size in bytes
            checksum: File checksum (format: md5:hash or ad:hash)
            guid: File GUID (will be generated if not provided)
            scope: File scope
            **metadata: Additional metadata
        """
        # Validate inputs
        ValidationUtils.validate_lfn(lfn)
        ValidationUtils.validate_pfn(pfn)
        ValidationUtils.validate_file_size(size)
        ValidationUtils.validate_checksum(checksum)
        
        self.lfn = lfn
        self.pfn = pfn
        self.size = size
        self.checksum = checksum
        self.guid = guid if guid else RucioUtils.generate_guid()
        self.scope = scope
        self.metadata = metadata
        
        # Extract filename from LFN if not in metadata
        if 'filename' not in self.metadata:
            self.metadata['filename'] = os.path.basename(lfn)
            
    def to_rucio_dict(self, rse: str) -> Dict[str, Any]:
        """
        Convert to Rucio file dictionary format.
        
        Args:
            rse: RSE where the file is located
            
        Returns:
            Dictionary in Rucio format
        """
        file_dict = {
            "scope": self.scope,
            "name": self.lfn,
            "bytes": self.size,
            "pfn": self.pfn,
            "meta": {"guid": self.guid}
        }
        
        # Add checksum in appropriate format
        if self.checksum.startswith("md5:"):
            file_dict["md5"] = self.checksum[4:]
        elif self.checksum.startswith("ad:"):
            file_dict["adler32"] = self.checksum[3:]
            
        # Add additional metadata
        file_dict["meta"].update(self.metadata)
        
        return file_dict
    
    def __str__(self):
        return f"FileInfo(lfn={self.lfn}, scope={self.scope}, size={self.size})"
    
    def __repr__(self):
        return self.__str__()

# ---
class FileManager:
    """
    Manages Rucio file operations.
    
    This class provides methods for registering files with existing PFNs
    and associating them with datasets, following patterns from PanDA's
    file registration operations.
    """
    
    def __init__(self, rucio_client: Optional[RucioClient] = None, logger: Optional[logging.Logger] = None):
        """
        Initialize FileManager.
        
        Args:
            rucio_client: Optional Rucio client instance
            logger: Optional logger instance
        """
        
        # if rucio_client is None:
        #     print("No Rucio client provided, using default RucioClient. =======================================================================")
        
        self.client = rucio_client if rucio_client else RucioClient()
        self.logger = logger if logger else logging.getLogger(__name__)
        self._registered_files = set()  # Track registered files
        
    def register_file_replica(
        self,
        file_info: FileInfo,
        rse: str,
        register_in_catalog: bool = True
    ) -> bool:
        """
        Register a file replica with an existing PFN.
        
        This method registers that a file exists at a specific RSE with a known PFN,
        similar to how PanDA registers files after pilot upload.
        
        Args:
            file_info: FileInfo object containing file metadata
            rse: RSE where the file is located
            register_in_catalog: Whether to register in Rucio catalog
            
        Returns:
            True if successful
            
        Raises:
            FileRegistrationError: If registration fails
        """
        try:
            self.logger.info(f"Registering file replica: {file_info.lfn} at {rse}")
            
            # Prepare file dictionary for Rucio
            file_dict = file_info.to_rucio_dict(rse)
            
            if register_in_catalog:
                try:
                    self.client.add_replicas(rse=rse, files=[file_dict])
                    self.logger.info(f"Successfully registered replica: {file_info.lfn}")
                except FileAlreadyExists:
                    self.logger.warning(f"File replica already exists: {file_info.lfn}")
                    
            # Track registered file
            self._registered_files.add(f"{file_info.scope}:{file_info.lfn}")
            
            return True
            
        except Exception as e:
            error_msg = f"Failed to register file replica {file_info.lfn}: {str(e)}"
            self.logger.error(error_msg)
            raise FileRegistrationError(error_msg) from e
            
    def register_multiple_files(
        self,
        files: List[FileInfo],
        rse: str,
        batch_size: int = 100
    ) -> Dict[str, bool]:
        """
        Register multiple file replicas in batches.
        
        Args:
            files: List of FileInfo objects
            rse: RSE where files are located
            batch_size: Number of files to process in each batch
            
        Returns:
            Dictionary mapping LFNs to registration success status
        """
        results = {}
        
        self.logger.info(f"Registering {len(files)} files at {rse} in batches of {batch_size}")
        
        for i in range(0, len(files), batch_size):
            batch = files[i:i + batch_size]
            self.logger.debug(f"Processing batch {i//batch_size + 1}: {len(batch)} files")
            
            # Prepare batch for Rucio
            file_dicts = []
            for file_info in batch:
                try:
                    file_dict = file_info.to_rucio_dict(rse)
                    file_dicts.append(file_dict)
                except Exception as e:
                    self.logger.error(f"Failed to prepare file {file_info.lfn}: {str(e)}")
                    results[file_info.lfn] = False
                    continue
                    
            # Register batch
            if file_dicts:
                try:
                    self.client.add_replicas(rse=rse, files=file_dicts)
                    
                    # Mark all files in batch as successful
                    for file_info in batch:
                        if file_info.lfn not in results:  # Only if not already marked as failed
                            results[file_info.lfn] = True
                            self._registered_files.add(f"{file_info.scope}:{file_info.lfn}")
                            
                    self.logger.info(f"Successfully registered batch of {len(file_dicts)} files")
                    
                except Exception as e:
                    self.logger.error(f"Failed to register batch: {str(e)}")
                    # Try individual registration for this batch
                    for file_info in batch:
                        if file_info.lfn not in results:
                            try:
                                self.register_file_replica(file_info, rse)
                                results[file_info.lfn] = True
                            except Exception:
                                results[file_info.lfn] = False
                                
        successful = sum(1 for success in results.values() if success)
        self.logger.info(f"Registration completed: {successful}/{len(files)} files successful")
        
        return results

    # ---        
    def add_files_to_dataset(
        self,
        files: Union[List[FileInfo], List[str]],
        dataset_name: str,
        dataset_scope: Optional[str] = None,
        rse: Optional[str] = None
    ) -> bool:
        """
        Add files to a dataset.
        
        This method associates files with a dataset, similar to PanDA's
        add_files_to_dataset operations.
        
        Args:
            files: List of FileInfo objects or LFNs
            dataset_name: Target dataset name
            dataset_scope: Dataset scope (will be extracted if not provided)
            rse: Optional RSE constraint
            
        Returns:
            True if successful
            
        Raises:
            FileRegistrationError: If operation fails
        """
        try:
            # Extract dataset scope if not provided
            if dataset_scope is None:
                dataset_scope, dataset_name = RucioUtils.extract_scope(dataset_name)
                
            self.logger.info(f"Adding {len(files)} files to dataset: {dataset_scope}:{dataset_name}")
            
            # Prepare file list for Rucio
            file_dicts = []
            
            for file_item in files:
                if isinstance(file_item, FileInfo):
                    file_dict = file_item.to_rucio_dict(rse or "")
                    # Remove PFN for dataset association (not needed)
                    if "pfn" in file_dict:
                        del file_dict["pfn"]
                elif isinstance(file_item, str):
                    # Assume it's an LFN, need to get scope
                    file_scope, lfn = RucioUtils.extract_scope(file_item)
                    file_dict = {
                        "scope": file_scope,
                        "name": lfn
                    }
                else:
                    raise ValueError(f"Invalid file item type: {type(file_item)}")
                    
                file_dicts.append(file_dict)
                
            # Add files to dataset in batches
            batch_size = 1000
            for i in range(0, len(file_dicts), batch_size):
                batch = file_dicts[i:i + batch_size]
                
                try:
                    self.client.add_files_to_dataset(
                        scope=dataset_scope,
                        name=dataset_name,
                        files=batch,
                        rse=rse
                    )
                    self.logger.debug(f"Added batch of {len(batch)} files to dataset")
                    
                except FileAlreadyExists:
                    # Try adding files individually
                    for file_dict in batch:
                        try:
                            self.client.add_files_to_dataset(
                                scope=dataset_scope,
                                name=dataset_name,
                                files=[file_dict],
                                rse=rse
                            )
                        except FileAlreadyExists:
                            self.logger.debug(f"File already in dataset: {file_dict['name']}")
                            
            self.logger.info(f"Successfully added files to dataset: {dataset_scope}:{dataset_name}")
            return True
            
        except Exception as e:
            error_msg = f"Failed to add files to dataset {dataset_name}: {str(e)}"
            self.logger.error(error_msg)
            raise FileRegistrationError(error_msg) from e

    # ---            
    def create_file_from_pfn(
        self,
        pfn: str,
        lfn: Optional[str] = None,
        scope: Optional[str] = None,
        checksum: Optional[str] = None,
        size: Optional[int] = None,
        **metadata
    ) -> FileInfo:
        """
        Create a FileInfo object from a PFN, extracting metadata where possible.
        
        Args:
            pfn: Physical file name/path
            lfn: Logical file name (will be derived from PFN if not provided)
            scope: File scope
            checksum: File checksum
            size: File size
            **metadata: Additional metadata
            
        Returns:
            FileInfo object
            
        Raises:
            FileRegistrationError: If file metadata cannot be determined
        """
        try:
            # Parse PFN to extract components
            pfn_components = RucioUtils.parse_pfn(pfn)
            
            # Derive LFN if not provided
            if lfn is None:
                lfn = pfn_components['filename']
                if not lfn:
                    raise ValueError("Cannot derive LFN from PFN")
                    
            # Get file size if not provided and file is local
            if size is None and os.path.exists(pfn):
                size = os.path.getsize(pfn)
                
            # Generate checksum if not provided and file is local
            if checksum is None and os.path.exists(pfn):
                checksum = self._calculate_adler32(pfn)
                
            # Validate that we have required information
            if size is None:
                raise ValueError("File size must be provided or file must be accessible")
            if checksum is None:
                raise ValueError("Checksum must be provided or file must be accessible")
                
            return FileInfo(
                lfn=lfn,
                pfn=pfn,
                size=size,
                checksum=checksum,
                scope=scope,
                **metadata
            )
            
        except Exception as e:
            error_msg = f"Failed to create FileInfo from PFN {pfn}: {str(e)}"
            self.logger.error(error_msg)
            raise FileRegistrationError(error_msg) from e
            
    def _calculate_adler32(self, file_path: str) -> str:
        """
        Calculate Adler32 checksum for a file.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Checksum in format "ad:hash"
        """
        import zlib
        
        adler = 1
        with open(file_path, 'rb') as f:
            while True:
                data = f.read(65536)  # 64KB chunks
                if not data:
                    break
                adler = zlib.adler32(data, adler)
                
        # Convert to unsigned 32-bit integer and format as hex
        checksum = format(adler & 0xffffffff, '08x')
        return f"ad:{checksum}"
        
    def get_registered_files(self) -> List[str]:
        """
        Get list of files registered by this manager instance.
        
        Returns:
            List of file names (scope:name format)
        """
        return list(self._registered_files)
        
    def verify_file_registration(
        self,
        file_info: FileInfo,
        rse: str
    ) -> bool:
        """
        Verify that a file is properly registered in Rucio.
        
        Args:
            file_info: FileInfo object to verify
            rse: RSE where file should be located
            
        Returns:
            True if file is properly registered
        """
        try:
            # Check if file replica exists
            replicas = list(self.client.list_replicas([{
                'scope': file_info.scope,
                'name': file_info.lfn
            }]))
            
            if not replicas:
                return False
                
            replica = replicas[0]
            rse_list = list(replica.get('rses', {}))
            
            return rse in rse_list
            
        except Exception as e:
            self.logger.error(f"Failed to verify file registration: {str(e)}")
            return False



# ---
class DatasetManager:
    """
    Manages Rucio dataset operations.
    
    This class provides methods for creating, opening, closing, and managing
    Rucio datasets, following patterns from PanDA's RucioAPI class.
    """
    
    def __init__(self, rucio_client: Optional[RucioClient] = None, logger: Optional[logging.Logger] = None):
        """
        Initialize DatasetManager.
        
        Args:
            rucio_client: Optional Rucio client instance
            logger: Optional logger instance
        """
        self.client = rucio_client if rucio_client else RucioClient()
        self.logger = logger if logger else logging.getLogger(__name__)
        self._created_datasets = set()  # Track created datasets
    
    
    # ---    
    def create_dataset(
        self,
        dataset_name: str,
        scope: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        lifetime_days: Optional[int] = None,
        open_dataset: bool = True
    ) -> Dict[str, str]:
        """
        Create a new dataset in Rucio.
        
        This method follows the pattern from PanDA's register_dataset method.
        
        Args:
            dataset_name: Name of the dataset
            scope: Dataset scope (will be extracted if not provided)
            metadata: Dataset metadata
            lifetime_days: Dataset lifetime in days
            open_dataset: Whether to create dataset in open state
            
        Returns:
            Dictionary containing dataset identifiers (duid, vuid, etc.)
            
        Raises:
            DatasetError: If dataset creation fails
            ValidationError: If input validation fails
        """
        try:
            # Validate inputs
            ValidationUtils.validate_dataset_name(dataset_name)
            
            # Extract scope if not provided
            if scope is None:
                scope, dataset_name = RucioUtils.extract_scope(dataset_name)
            else:
                ValidationUtils.validate_scope(scope)
                
            self.logger.info(f"Creating dataset: {scope}:{dataset_name}")
            
            # Prepare metadata
            if metadata is None:
                metadata = {}
                
            # Add standard metadata
            dataset_metadata = MetadataUtils.create_dataset_metadata(**metadata)
            
            # Create dataset
            try:
                self.client.add_dataset(scope=scope, name=dataset_name, meta=dataset_metadata)
                self.logger.info(f"Successfully created dataset: {scope}:{dataset_name}")
            except DataIdentifierAlreadyExists:
                self.logger.warning(f"Dataset already exists: {scope}:{dataset_name}")
                
            # Set lifetime if specified
            if lifetime_days is not None:
                lifetime_seconds = lifetime_days * 86400
                try:
                    self.client.set_metadata(
                        scope=scope, 
                        name=dataset_name, 
                        key="lifetime", 
                        value=lifetime_seconds
                    )
                    self.logger.info(f"Set lifetime to {lifetime_days} days for {scope}:{dataset_name}")
                except Exception as e:
                    self.logger.warning(f"Failed to set lifetime: {str(e)}")
                    
            # Set dataset status to open if requested
            if open_dataset:
                try:
                    # Check current status first
                    metadata = self.client.get_metadata(scope=scope, name=dataset_name)
                    if not metadata.get('is_open', False):
                        self.client.set_status(scope=scope, name=dataset_name, open=True)
                        self.logger.info(f"Set dataset to open: {scope}:{dataset_name}")
                    else:
                        self.logger.debug(f"Dataset already open: {scope}:{dataset_name}")
                except Exception as e:
                    self.logger.warning(f"Failed to set dataset to open: {str(e)}")
                    
            # Generate identifiers
            vuid = RucioUtils.generate_vuid(scope, dataset_name)
            duid = vuid  # For simplicity, use same as vuid
            
            # Track created dataset
            self._created_datasets.add(f"{scope}:{dataset_name}")
            
            return {
                "duid": duid,
                "version": 1,
                "vuid": vuid,
                "scope": scope,
                "name": dataset_name
            }
            
        except Exception as e:
            error_msg = f"Failed to create dataset {dataset_name}: {str(e)}"
            self.logger.error(error_msg)
            raise DatasetError(error_msg) from e
        
    def get_dataset_metadata(self, dataset_name: str, scope: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """
        Get metadata of a dataset.
        
        Args:
            dataset_name: Name of the dataset
            scope: Dataset scope (will be extracted if not provided)
            
        Returns:
            Dataset metadata dictionary or None if not found
            
        Raises:
            DatasetError: If operation fails
        """    
        try:
            # Extract scope if not provided
            if scope is None:
                scope, dataset_name = RucioUtils.extract_scope(dataset_name)
                
            self.logger.debug(f"Getting metadata for dataset: {scope}:{dataset_name}")
            
            try:
                metadata = self.client.get_metadata(scope=scope, name=dataset_name)
                
                # Add state information like in PanDA
                if metadata.get("is_open", False) and metadata.get("did_type") != "CONTAINER":
                    metadata["state"] = "open"
                else:
                    metadata["state"] = "closed"
                    
                return metadata
                
            except DataIdentifierNotFound:
                self.logger.warning(f"Dataset not found: {scope}:{dataset_name}")
                return None
                
        except Exception as e:
            error_msg = f"Failed to get metadata for dataset {dataset_name}: {str(e)}"
            self.logger.error(error_msg)
            raise DatasetError(error_msg) from e
            

class RucioOrchestrator:
    """
    A class to orchestrate Rucio operations for data management.    
    This class coordinates the following steps:
    1. Create an empty and OPEN rucio dataset
    2. Register files with existing PFNs 
    3. Add these files to the dataset
    4. Close the dataset
    """
    
    def __init__(self, rucio_client: Optional[RucioClient] = None):
        pass
