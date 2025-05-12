**Create venv:**
`uv venv .venv311 --python 3.11`

**Activate venv (Windows):**
`.venv311\Scripts\activate`

**Activate venv (Unix):**
`source .venv311\Scripts\activate`

**Install dependencies:**
`uv pip install -e .`

**Excute program:**
`python main.py`

**External dependencies:**
*Chocolately to download FFMPEG for Windows*

- Chocolately: `Set-ExecutionPolicy Bypass -Scope Process -Force; [System.Net.ServicePointManager]::SecurityProtocol = [System.Net.ServicePointManager]::SecurityProtocol -bor 3072; iex ((New-Object System.Net.WebClient).DownloadString('https://community.chocolatey.org/install.ps1'))
`

- FFMPEG: `choco install ffmpeg
`

