"""PythonAnywhere WSGI entry point.

On PythonAnywhere:
1. Upload project to /home/{username}/smart-qa/
2. Go to Web tab -> Add a new web app -> Manual configuration -> Python 3.x
3. Set source code path: /home/{username}/smart-qa/backend
4. Set working directory: /home/{username}/smart-qa/backend
5. Edit WSGI config file to point to this file
6. Install requirements: pip install --user -r /home/{username}/smart-qa/backend/requirements.txt
7. Configure static files in Web tab:
   - URL: /css/ -> Directory: /home/{username}/smart-qa/frontend/css/
   - URL: /js/ -> Directory: /home/{username}/smart-qa/frontend/js/
   - URL: /assets/ -> Directory: /home/{username}/smart-qa/frontend/assets/
"""
import sys
import os

# Add project path
project_home = os.environ.get("PROJECT_HOME", "")
if project_home:
    path = os.path.join(project_home, "backend")
    if path not in sys.path:
        sys.path.insert(0, path)
else:
    # Local fallback
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.insert(0, current_dir)

from app import create_app

application = create_app()
