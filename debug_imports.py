import sys
import os

print(f"Python version: {sys.version}")
print(f"Current working directory: {os.getcwd()}")

try:
    import PyQt5.QtWidgets
    print("✅ PyQt5.QtWidgets imported successfully")
except ImportError as e:
    print(f"❌ PyQt5.QtWidgets import failed: {e}")

try:
    import PyQt5.QtCore
    print("✅ PyQt5.QtCore imported successfully")
except ImportError as e:
    print(f"❌ PyQt5.QtCore import failed: {e}")

try:
    import PyQt5.QtGui
    print("✅ PyQt5.QtGui imported successfully")
except ImportError as e:
    print(f"❌ PyQt5.QtGui import failed: {e}")

try:
    import selenium
    print("✅ selenium imported successfully")
except ImportError as e:
    print(f"❌ selenium import failed: {e}")

try:
    import moviepy.editor
    print("✅ moviepy.editor imported successfully")
except ImportError as e:
    print(f"❌ moviepy.editor import failed: {e}")

try:
    import mysql.connector
    print("✅ mysql.connector imported successfully")
except ImportError as e:
    print(f"❌ mysql.connector import failed: {e}")

try:
    import numpy
    print(f"✅ numpy imported successfully (version: {numpy.__version__})")
except ImportError as e:
    print(f"❌ numpy import failed: {e}")
except Exception as e:
    print(f"❌ numpy import error: {e}")

try:
    import PIL.Image
    print("✅ PIL.Image imported successfully")
except ImportError as e:
    print(f"❌ PIL.Image import failed: {e}")

try:
    from elevenlabs_client import ElevenLabsClient
    print("✅ ElevenLabsClient imported successfully")
    client = ElevenLabsClient()
    print("✅ ElevenLabsClient initialized")
except ImportError as e:
    print(f"❌ ElevenLabsClient import failed: {e}")
except Exception as e:
    print(f"❌ ElevenLabsClient error: {e}")
