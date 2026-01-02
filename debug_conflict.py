print("Importing everything...")
import mysql.connector
import sys
import time
# ...
print("Importing mysql...")
# import mysql.connector
import re
import os
import base64
import subprocess
print("Importing PyQt5...")
from PyQt5.QtWidgets import QApplication
# from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QTextEdit, 
#                              QPushButton, QLabel, QFileDialog, QHBoxLayout, 
#                              QTabWidget, QComboBox, QSlider, QSpinBox, QGroupBox, QDoubleSpinBox, QFormLayout)
# from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
# from PyQt5.QtGui import QPalette, QColor
# print("Importing Selenium...")
# from selenium import webdriver
# from selenium.webdriver.chrome.service import Service
# from selenium.webdriver.chrome.options import Options
# from selenium.webdriver.common.by import By
# from selenium.webdriver.common.keys import Keys
# from selenium.webdriver.support.ui import WebDriverWait
# from selenium.webdriver.support import expected_conditions as EC
# from webdriver_manager.chrome import ChromeDriverManager
# print("Importing PIL...")
# from PIL import Image
print("Importing ElevenLabs...")
from elevenlabs import ElevenLabs
import threading
print("Importing mysql...")
import mysql.connector

print("Imports done.")

config = {
    'user': 'youtubedev',
    'password': 'youtube2122',
    'host': 'devlab.pics',
    'database': 'youtubedevdb',
    'port': 3306
}

try:
    print("Creating app...")
    app = QApplication(sys.argv)
    print("Connecting to DB...")
    conn = mysql.connector.connect(**config)
    print("Connected.")
    conn.close()
    print("Success.")
except Exception as e:
    print(e)
