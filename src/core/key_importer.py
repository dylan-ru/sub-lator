import os
import zipfile
from typing import List
from PyQt6.QtWidgets import QMessageBox

# Try to import pyzipper, but don't fail if it's not available
try:
    import pyzipper
    HAS_PYZIPPER = True
except ImportError:
    HAS_PYZIPPER = False

class KeyImporter:
    def __init__(self, password: str):
        self.password = password.encode('utf-8')  # Convert password to bytes

    def import_keys_from_file(self, file_path: str) -> List[str]:
        """
        Import API keys directly from a text file.
        """
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                api_keys = [line.strip() for line in content.splitlines() if line.strip()]
                if not api_keys:
                    raise ValueError("No API keys found in the text file")
                return api_keys
        except Exception as e:
            raise ValueError(f"Error reading text file: {str(e)}")

    def import_keys_from_zip(self, zip_path: str) -> List[str]:
        """
        Import API keys from a password-protected zip file.
        Returns a list of API keys if successful.
        Raises ValueError if the file is invalid or cannot be opened.
        """
        try:
            # Check if file exists
            if not os.path.exists(zip_path):
                raise ValueError("File not found")

            # First, verify the file is password protected
            try:
                with zipfile.ZipFile(zip_path, 'r') as test_zip:
                    # Try to read without password first
                    files = [f for f in test_zip.namelist() if not f.startswith('__MACOSX')]
                    if not files:
                        raise ValueError("No files found in the zip archive")
                    
                    txt_files = [f for f in files if f.endswith('.txt')]
                    if not txt_files:
                        raise ValueError("No text file found in the zip archive")
                        
                    try:
                        # Try to read without password
                        test_zip.read(txt_files[0])
                        # If we get here, the file is not password protected
                        raise ValueError("File is not password protected. Please create a password-protected zip file.")
                    except RuntimeError as e:
                        if "password required" in str(e).lower() or "encrypted" in str(e).lower():
                            # This is what we want - file is password protected
                            pass
                        else:
                            raise
            except zipfile.BadZipFile:
                raise ValueError("Invalid zip file format")

            # Now try to read with password
            try:
                if HAS_PYZIPPER:
                    # Try with pyzipper first for AES encryption
                    with pyzipper.AESZipFile(zip_path, 'r') as zip_file:
                        zip_file.setpassword(self.password)
                        return self._process_zip_file(zip_file)
                else:
                    # Fallback to standard zipfile
                    with zipfile.ZipFile(zip_path, 'r') as zip_file:
                        return self._process_zip_file(zip_file, use_password=True)
                        
            except (zipfile.BadZipFile, RuntimeError):
                raise ValueError("File cannot be imported - incorrect password")
                    
        except Exception as e:
            if isinstance(e, ValueError):
                raise e
            raise ValueError(f"Error importing keys: {str(e)}")

    def _process_zip_file(self, zip_file, use_password=False):
        """Helper method to process the contents of a zip file."""
        # Get all non-macOS files
        files = [f for f in zip_file.namelist() if not f.startswith('__MACOSX')]
        if not files:
            raise ValueError("No files found in the zip archive")

        # Get the first .txt file
        txt_files = [f for f in files if f.endswith('.txt')]
        if not txt_files:
            raise ValueError("No text file found in the zip archive")

        first_txt = txt_files[0]
        
        try:
            # Read the file content
            if use_password:
                txt_content = zip_file.read(first_txt, pwd=self.password).decode('utf-8')
            else:
                txt_content = zip_file.read(first_txt).decode('utf-8')
            
            # Split content into lines and filter empty lines
            api_keys = [line.strip() for line in txt_content.splitlines() if line.strip()]
            
            if not api_keys:
                raise ValueError("No API keys found in the text file")
            
            return api_keys
            
        except RuntimeError as e:
            if "password" in str(e).lower() or "encrypted" in str(e).lower():
                raise ValueError("File cannot be imported - incorrect password")
            raise ValueError(f"Error reading file: {str(e)}") 