import sys
import traceback

try:
    print("Attempting to import genspark_2tab_tool...")
    import genspark_2tab_tool
    print("Import successful. Running main...")
    if hasattr(genspark_2tab_tool, 'main'):
        genspark_2tab_tool.main()
    else:
        # If no main function, replicate the if __name__ == "__main__" block logic
        from PyQt5.QtWidgets import QApplication
        from PyQt5.QtGui import QPalette, QColor, QColorConstants
        from PyQt5.QtCore import Qt
        
        app = QApplication(sys.argv)
        app.setStyle("Fusion")
        # Palette setup omitted for brevity in debug
        ex = genspark_2tab_tool.MainApp()
        ex.show()
        print("App initialized. Executing...")
        sys.exit(app.exec_())
except Exception:
    editor = traceback.format_exc()
    print("CRASHED:")
    print(editor)
except SystemExit as e:
    print(f"SystemExit: {e}")
