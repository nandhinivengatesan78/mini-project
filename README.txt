CAMPUSSHARE - FRESH PROJECT

IMPORTANT: Open this extracted CampusShare_New folder in VS Code. Do not run an older app.py from another folder.

EASIEST START:
1. Extract the ZIP using Windows Explorer > Extract All.
2. Open the extracted CampusShare_New folder.
3. Double-click run.bat, or in VS Code terminal run:
   python -m pip install -r requirements.txt
   python app.py
4. Wait until the terminal says CampusShare is running at http://127.0.0.1:5000
5. Open exactly: http://127.0.0.1:5000/

If port 5000 is already occupied by an old CampusShare server, stop the old terminal with Ctrl+C first, then run this project.

Features:
- College email domain restriction (default snsct.org; configure ALLOWED_DOMAINS if needed)
- Register/login
- Create listings with a required real product photo (camera on supported devices or choose a file)
- Browse only real listings; no demo products are inserted
- About/product details and request confirmation
- Listing owner can delete their own listing
- SQLite database is created locally on first run

Note: Gmail OTP, official college location verification, and geofencing are not implemented in this fresh starter. Browser camera/file picker availability depends on device/browser permissions.
