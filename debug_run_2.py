import sys
import traceback
print("Importing PyQt5...")
from PyQt5.QtWidgets import QApplication
print("Importing genspark_2tab_tool...")
import genspark_2tab_tool 

try:
    print("Starting App...")
    app = QApplication(sys.argv)
    print("App instance created.")
    
    print("Instantiating MainApp...")
    ex = genspark_2tab_tool.MainApp()
    print("MainApp instantiated successfully.")
    
    ex.show()
    print("Window show() called.")
    
    print("Running event loop (will exit after 2 seconds for test)...")
    from PyQt5.QtCore import QTimer
    QTimer.singleShot(2000, app.quit)
    app.exec_()
    print("Event loop finished.")
    
except Exception:
    print("CRASHED:")
    traceback.print_exc()
