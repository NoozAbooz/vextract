import yt_dlp
import re
import ctypes
import os
import sys
from src.ocr import OCR
from src.api import API
from tkinter import filedialog
import tkinter as tk

import shutil

class Client:
    def __init__(self, team, url, use_custom_path=False, include_up_next=False):
        self.url = url
        self.team = team
        self.app = None
        self.id = API.get_id(team)
        self.event = ""
        self.use_custom_path = use_custom_path
        self.include_up_next = include_up_next
        self.video_path = None

    def sanitize_filename(self, filename):
        """Remove or replace characters that are invalid in Windows filenames"""
        # Replace problematic characters with underscores or remove them
        invalid_chars = r'[<>:"/\\|?*#]'
        sanitized = re.sub(invalid_chars, '_', filename)
        # Remove multiple consecutive underscores
        sanitized = re.sub(r'_+', '_', sanitized)
        # Remove trailing periods and spaces
        sanitized = sanitized.rstrip('. ')
        return sanitized

    def progress_hook(self, d):
        if d['status'] == 'downloading':
            percent_str = d.get('_percent_str', '0%')
            clean_percent_str = re.sub(r'\x1b\[[0-9;]*[mK]', '', percent_str)
            self.app.progress_value = float(f"{float(clean_percent_str.strip('%').replace(' ', '')):.2f}")

    def download(self):
        if self.use_custom_path:
            # Skip download when using custom video path
            return
            
        zxt = self.url.strip()

        base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))

        # Sanitize the event name for filename
        sanitized_event = self.sanitize_filename(self.event)

        options = {
            'outtmpl': os.path.join(base_dir, re.sub(r'[\\/*?:"<>| ]', '_', f"{sanitized_event}.%(ext)s")),
            'format': 'bestaudio+bestevideo/best',
            'merge_output_format': 'mp4',
            'concurrent-fragments': '2',
            #'extractor-args': 'youtube:player-client=web_embedded,web,tv',
            'progress_hooks': [self.progress_hook],
            'postprocessors': [{
                'key': 'FFmpegVideoConvertor',
                'preferedformat': 'mp4',
            }],
            'postprocessor_args': [
                '-ac', '2', 
                '-ar', '44100'
            ],
        }

        if os.name == 'posix':
            options['cookiesfrombrowser'] = ('firefox', )
        
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.download([zxt])

        # Update self.event to use sanitized version for consistency
        self.event = sanitized_event

    def select_video_file(self):
        """Open file dialog to select a video file"""
        root = tk.Tk()
        root.withdraw()  # Hide the root window
        
        file_path = filedialog.askopenfilename(
            title="Select Video File",
            filetypes=[
                ("Video files", "*.mp4 *.avi *.mov *.mkv *.wmv *.flv *.webm"),
                ("MP4 files", "*.mp4"),
                ("All files", "*.*")
            ]
        )
        
        root.destroy()
        return file_path

    def extract(self, event, app):
        self.app = app
        
        if self.use_custom_path:
            # Open file dialog to select video file
            video_path = self.select_video_file()
            print(f"Selected video file: {video_path}")
            if not video_path:
                raise ValueError("No video file selected")
            
            self.video_path = video_path
            # Extract event name from filename for consistency
            self.event = os.path.splitext(os.path.basename(video_path))[0]
            output_dir = self.sanitize_filename(self.event)
        else:
            # Get base directory and create output template for downloaded videos
            base_dir = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else os.path.dirname(os.path.abspath(__file__))
            sanitized_event = self.sanitize_filename(self.event)
            output_dir = sanitized_event
        
        # Pass the video path and output directory to OCR
        if self.use_custom_path:
            self.ocr = OCR(self, video_path=self.video_path, output_dir=output_dir)
        else:
            self.ocr = OCR(self, output_dir=output_dir)
            
        self.ocr.perform_ocr(interval=60 * 2)
        print(self.ocr.ocr)

        matches = self.get_matches(self.app.season, event)
        print(matches)
        l = len(matches)

        self.app.text = "Seeking clips"

        for i, match in enumerate(matches):
            self.app.progress_value = int((i / l) * 100)
            self.ocr.seek(match.replace(" ", ""))
        
        return self.team
    
    def delete(self):
        current_dir = os.getcwd()
        
        # Use sanitized event name for file operations
        sanitized_event = self.sanitize_filename(self.event)
        folder_path = os.path.join(current_dir, sanitized_event)
        mp4_path = os.path.join(current_dir, f"{sanitized_event}.mp4")

        def force_delete(file_path):
            try:
                FILE_ATTRIBUTE_NORMAL = 0x80
                ctypes.windll.kernel32.SetFileAttributesW(file_path, FILE_ATTRIBUTE_NORMAL)
                os.remove(file_path)
                print(f"File '{file_path}' has been forcefully deleted.")
            except Exception as e:
                print(f"Failed to delete file '{file_path}': {e}")

        if os.path.exists(folder_path):
            try:
                shutil.rmtree(folder_path, onerror=lambda func, path, exc_info: force_delete(path))
                print(f"Folder '{sanitized_event}' and its contents have been deleted.")
            except Exception as e:
                print(f"Failed to delete folder '{sanitized_event}': {e}")
        else:
            print(f"Folder '{sanitized_event}' not found.")

        if os.path.exists(mp4_path):
            try:
                os.remove(mp4_path)
                print(f"MP4 file '{sanitized_event}.mp4' has been deleted.")
            except PermissionError:
                print(f"MP4 file '{sanitized_event}.mp4' is locked. Attempting forced deletion.")
                force_delete(mp4_path)
        else:
            print(f"MP4 file '{sanitized_event}.mp4' not found.")
    
    def get_matches(self, season, event):
        matches = API.get_matches(self.id, season, event)
        result = []
        for match in matches:
            if "Final" in match["name"]:
                result.append(f'FINALS {match["name"].replace("#", "")[-3]}'.replace(" ", ""))
            else:
                result.append(match["name"].replace("Qualifier", "QUAL").replace("#", "").replace(" ", ""))

        return result