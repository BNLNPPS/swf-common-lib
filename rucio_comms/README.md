# Rucio comms

The rucio_comms package is a Python library that provides a high-level interface for interacting with Rucio. Here are its key components and features:

1. Core Classes:
- `FileManager`: Manages Rucio file operations
  - Registers file replicas with existing PFNs
  - Associates files with datasets
  - Handles batch operations for multiple files
  - Tracks registered files

- `DatasetManager`: Handles Rucio dataset operations
  - Creates and manages datasets
  - Sets metadata, lifetime, and status
  - Follows PanDA-style dataset management patterns

- `FileInfo`: Represents a file with its metadata
  - Handles logical/physical file names (LFN/PFN)
  - Manages checksums, size, and GUIDs
  - Validates file attributes

2. Utility Modules:
- `RucioUtils`: Helper functions for Rucio operations
  - Scope extraction from dataset names
  - GUID and VUID generation
  - PFN parsing and formatting

- `ValidationUtils`: Input validation
  - Validates dataset names, scopes, LFNs, PFNs
  - Checks checksums and file sizes
  - Enforces format rules

- `MetadataUtils`: Metadata handling
  - Creates standardized file metadata
  - Manages dataset metadata
  - Follows PanDA/Rucio metadata conventions
