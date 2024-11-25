import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import subprocess
import os
from pathlib import Path
import re
import threading
import time
from datetime import datetime
import queue
import sys
from subprocess import CREATE_NO_WINDOW
from tkinterdnd2 import DND_FILES, TkinterDnD
class ModernButton(tk.Button):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self.configure(
            bg="#2c3e50",
            fg="white",
            activebackground="#34495e",
            activeforeground="white",
            relief=tk.FLAT,
            padx=20,
            pady=10,
            font=("Segoe UI", 10),
            cursor="hand2"
        )
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)

    def on_enter(self, e):
        self['background'] = "#34495e"

    def on_leave(self, e):
        self['background'] = "#2c3e50"

class ProgressWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Converting...")
        
        # Window setup
        window_width = 400
        window_height = 200
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        x = (screen_width - window_width) // 2
        y = (screen_height - window_height) // 2
        self.geometry(f"{window_width}x{window_height}+{x}+{y}")
        
        self.configure(bg="#1a1a1a")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        
        # Progress variables
        self.progress_var = tk.DoubleVar()
        self.status_text = tk.StringVar(value="Initializing...")
        self.fps_text = tk.StringVar(value="Encoding speed: calculating...")
        self.time_text = tk.StringVar(value="Time remaining: calculating...")
        
        # Status labels
        self.status_label = tk.Label(
            self,
            textvariable=self.status_text,
            bg="#1a1a1a",
            fg="white",
            font=("Segoe UI", 10)
        )
        self.status_label.pack(pady=10)
        
        self.fps_label = tk.Label(
            self,
            textvariable=self.fps_text,
            bg="#1a1a1a",
            fg="white",
            font=("Segoe UI", 10)
        )
        self.fps_label.pack(pady=5)
        
        self.time_label = tk.Label(
            self,
            textvariable=self.time_text,
            bg="#1a1a1a",
            fg="white",
            font=("Segoe UI", 10)
        )
        self.time_label.pack(pady=5)
        
        # Progress bar
        self.progress_bar = ttk.Progressbar(
            self,
            variable=self.progress_var,
            mode='determinate',
            length=350
        )
        self.progress_bar.pack(pady=10)
        
        self.process = None
        
        # For FPS calculation
        self.last_frame = 0
        self.last_time = time.time()
        self.start_time = time.time()
        
    def read_output(self, process, output_queue):
        """Read the process output in a separate thread"""
        for line in iter(process.stderr.readline, ''):
            if line:
                output_queue.put(line)
        process.stderr.close()
        
    def process_ffmpeg_output(self, output_queue, total_frames):
        """Process FFmpeg output from the queue"""
        try:
            while True:
                try:
                    line = output_queue.get_nowait()
                except queue.Empty:
                    break
                
                if "frame=" in line:
                    try:
                        frame_num = int(line.split("frame=")[1].split()[0])
                        progress = (frame_num / total_frames) * 100
                        
                        # Calculate current encoding FPS
                        current_time = time.time()
                        time_diff = current_time - self.last_time
                        if time_diff >= 0.5:  # Update every half second
                            frame_diff = frame_num - self.last_frame
                            current_fps = frame_diff / time_diff
                            self.fps_text.set(f"Encoding speed: {current_fps:.1f} fps")
                            
                            # Calculate estimated time remaining
                            elapsed_time = current_time - self.start_time
                            if progress > 0:
                                total_time = elapsed_time * 100 / progress
                                remaining_time = total_time - elapsed_time
                                self.time_text.set(
                                    f"Time remaining: {datetime.fromtimestamp(remaining_time).strftime('%M:%S')}"
                                )
                            
                            self.last_frame = frame_num
                            self.last_time = current_time
                        
                        self.progress_var.set(progress)
                        self.status_text.set(
                            f"Processing frame {frame_num}/{total_frames}"
                        )
                        
                    except (ValueError, IndexError):
                        continue
            
            # Schedule the next update
            self.root.after(100, lambda: self.process_ffmpeg_output(
                output_queue, total_frames
            ))
        except tk.TclError:  # Window was closed
            pass
        
    def calculate_target_bitrate(self, duration_seconds):
        """Calculate required bitrate for target file size"""
        if not self.target_size.get().strip():
            return None

        try:
            target_size = float(self.target_size.get().strip())
            if target_size <= 0:
                raise ValueError

            # Convert target size to bits
            multiplier = 1024 * 1024 * 8 if self.size_unit.get() == "MB" else 1024 * 8
            target_bits = target_size * multiplier

            # Calculate required bitrate (bits per second)
            # Using 98% of target to ensure we stay under limit
            target_bitrate = int((target_bits / duration_seconds) * 0.98)

            # Convert to kbps
            target_kbps = target_bitrate // 1000

            # Ensure minimum viable bitrate (500 kbps)
            return max(500, target_kbps)

        except (ValueError, TypeError):
            return None

def get_ffmpeg_path():
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return os.path.join(sys._MEIPASS, 'ffmpeg.exe')
    else:
        # Running as script
        return 'ffmpeg'

class DraggableListbox(tk.Listbox):
    def __init__(self, master=None, app=None, **kwargs):
        super().__init__(master, **kwargs)
        self.app = app  # Store reference to main application
        self.bind('<Button-1>', self.on_click)
        self.bind('<B1-Motion>', self.on_drag)
        self.bind('<ButtonRelease-1>', self.on_drop)
        
        # For drag and drop files from outside
        self.drop_target_register(DND_FILES)
        self.dnd_bind('<<Drop>>', self.on_drop_file)
        
        self._drag_data = {'item': None, 'index': None}
    
    def on_click(self, event):
        index = self.nearest(event.y)
        if index >= 0:
            self._drag_data['item'] = self.get(index)
            self._drag_data['index'] = index
    
    def on_drag(self, event):
        if self._drag_data['item']:
            # Get the new position
            new_index = self.nearest(event.y)
            if new_index >= 0:
                # Move item to new position
                old_index = self._drag_data['index']
                if new_index != old_index:
                    self.app.move_item(old_index, new_index)
                    self._drag_data['index'] = new_index
    
    def on_drop(self, event):
        self._drag_data = {'item': None, 'index': None}
    
    def on_drop_file(self, event):
        files = self.tk.splitlist(event.data)
        self.app.add_files(files)  # Use app reference instead of master.master

class ImageToVideoConverter:
    def __init__(self):
        self.root = TkinterDnD.Tk()
        self.root.title("Image to Video Converter")
        self.root.geometry("600x700")
        self.root.configure(bg="#1a1a1a")
        
        # Variables
        self.media_files = []
        self.file_types = []
        self.fps = tk.StringVar(value="30")
        self.status_text = tk.StringVar(value="No files selected")
        self.use_gpu = tk.BooleanVar(value=True)
        self.bitrate = tk.StringVar(value="20000")  # Default 20,000 kbps (20 Mbps)
        self.resolution = tk.StringVar(value="")   # Empty means original size
        self.target_size = tk.StringVar(value="")  # Empty means no target size
        self.size_unit = tk.StringVar(value="MB")  # MB or KB
        self.listbox = None
        self.video_bitrates = []  # Add this line to store video bitrates
        
        # Add timing variables
        self.last_frame = 0
        self.last_time = time.time()
        self.start_time = time.time()
        
        self.create_widgets()
        
    def create_widgets(self):
        # Main container
        main_frame = tk.Frame(self.root, bg="#1a1a1a", padx=20, pady=20)
        main_frame.pack(expand=True, fill="both")
        
        # Title
        title_label = tk.Label(
            main_frame,
            text="Image to Video Converter",
            font=("Segoe UI", 16, "bold"),
            bg="#1a1a1a",
            fg="white"
        )
        title_label.pack(pady=(0, 20))
        
        # File selection
        select_btn = ModernButton(
            main_frame,
            text="Select Media Files",
            command=self.select_media
        )
        select_btn.pack(pady=10)
        
        # Status frame
        status_frame = tk.Frame(main_frame, bg="#2c3e50", padx=10, pady=10)
        status_frame.pack(fill="x", pady=10)
        
        status_label = tk.Label(
            status_frame,
            textvariable=self.status_text,
            wraplength=400,
            bg="#2c3e50",
            fg="white",
            font=("Segoe UI", 10)
        )
        status_label.pack()
        
        # Media list frame
        list_frame = tk.Frame(main_frame, bg="#2c3e50", padx=10, pady=10)
        list_frame.pack(fill="both", expand=True, pady=10)
        
        # Scrollbar
        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Listbox
        self.listbox = DraggableListbox(
            list_frame,
            app=self,  # Pass reference to main application
            bg="#2c3e50",
            fg="white",
            selectmode=tk.SINGLE,
            height=6,
            yscrollcommand=scrollbar.set,
            font=("Segoe UI", 10)
        )
        self.listbox.pack(fill="both", expand=True)
        scrollbar.config(command=self.listbox.yview)
        
        # Reorder buttons frame
        reorder_frame = tk.Frame(main_frame, bg="#1a1a1a")
        reorder_frame.pack(pady=5)
        
        move_up_btn = ModernButton(
            reorder_frame,
            text="↑",
            command=self.move_up,
            padx=10
        )
        move_up_btn.pack(side=tk.LEFT, padx=5)
        
        move_down_btn = ModernButton(
            reorder_frame,
            text="↓",
            command=self.move_down,
            padx=10
        )
        move_down_btn.pack(side=tk.LEFT, padx=5)
        
        # Add delete button next to up/down buttons
        delete_btn = ModernButton(
            reorder_frame,
            text="×",
            command=self.delete_selected,
            padx=10
        )
        delete_btn.pack(side=tk.LEFT, padx=5)
        
        # Settings frame - modified to allow wrapping
        settings_frame = tk.Frame(main_frame, bg="#1a1a1a")
        settings_frame.pack(pady=10, fill="x")
        
        # Container for settings rows
        settings_row1 = tk.Frame(settings_frame, bg="#1a1a1a")
        settings_row1.pack(pady=(0, 5), fill="x")
        
        settings_row2 = tk.Frame(settings_frame, bg="#1a1a1a")
        settings_row2.pack(fill="x")
        
        # FPS and Bitrate in first row
        fps_frame = tk.Frame(settings_row1, bg="#1a1a1a")
        fps_frame.pack(side=tk.LEFT, padx=10)
        
        fps_label = tk.Label(
            fps_frame,
            text="Output FPS:",
            bg="#1a1a1a",
            fg="white",
            font=("Segoe UI", 10)
        )
        fps_label.pack(side=tk.LEFT, padx=5)
        
        fps_entry = tk.Entry(
            fps_frame,
            textvariable=self.fps,
            width=5,
            bg="#2c3e50",
            fg="white",
            insertbackground="white",
            relief=tk.FLAT,
            font=("Segoe UI", 10)
        )
        fps_entry.pack(side=tk.LEFT, padx=5)
        
        bitrate_frame = tk.Frame(settings_row1, bg="#1a1a1a")
        bitrate_frame.pack(side=tk.LEFT, padx=10)
        
        bitrate_label = tk.Label(
            bitrate_frame,
            text="Bitrate (kbps):",
            bg="#1a1a1a",
            fg="white",
            font=("Segoe UI", 10)
        )
        bitrate_label.pack(side=tk.LEFT, padx=5)
        
        bitrate_entry = tk.Entry(
            bitrate_frame,
            textvariable=self.bitrate,
            width=8,
            bg="#2c3e50",
            fg="white",
            insertbackground="white",
            relief=tk.FLAT,
            font=("Segoe UI", 10)
        )
        bitrate_entry.pack(side=tk.LEFT, padx=5)
        
        # Resolution and GPU checkbox in second row
        resolution_frame = tk.Frame(settings_row2, bg="#1a1a1a")
        resolution_frame.pack(side=tk.LEFT, padx=10)
        
        resolution_label = tk.Label(
            resolution_frame,
            text="Resolution:",
            bg="#1a1a1a",
            fg="white",
            font=("Segoe UI", 10)
        )
        resolution_label.pack(side=tk.LEFT, padx=5)
        
        resolution_entry = tk.Entry(
            resolution_frame,
            textvariable=self.resolution,
            width=10,
            bg="#2c3e50",
            fg="white",
            insertbackground="white",
            relief=tk.FLAT,
            font=("Segoe UI", 10)
        )
        resolution_entry.pack(side=tk.LEFT, padx=5)
        
        # GPU checkbox in second row
        gpu_check = tk.Checkbutton(
            settings_row2,  # Changed parent to settings_row2
            text="Use GPU encoding",
            variable=self.use_gpu,
            bg="#1a1a1a",
            fg="white",
            selectcolor="#2c3e50",
            activebackground="#1a1a1a",
            activeforeground="white",
            font=("Segoe UI", 10)
        )
        gpu_check.pack(side=tk.LEFT, padx=10)
        
        # Add a third row for target size settings
        settings_row3 = tk.Frame(settings_frame, bg="#1a1a1a")
        settings_row3.pack(fill="x")

        target_size_frame = tk.Frame(settings_row3, bg="#1a1a1a")
        target_size_frame.pack(side=tk.LEFT, padx=10)

        target_size_label = tk.Label(
            target_size_frame,
            text="Target Size:",
            bg="#1a1a1a",
            fg="white",
            font=("Segoe UI", 10)
        )
        target_size_label.pack(side=tk.LEFT, padx=5)

        target_size_entry = tk.Entry(
            target_size_frame,
            textvariable=self.target_size,
            width=6,
            bg="#2c3e50",
            fg="white",
            insertbackground="white",
            relief=tk.FLAT,
            font=("Segoe UI", 10)
        )
        target_size_entry.pack(side=tk.LEFT, padx=5)

        # Unit dropdown (MB/KB)
        size_unit_menu = ttk.Combobox(
            target_size_frame,
            textvariable=self.size_unit,
            values=["MB", "KB"],
            width=3,
            state="readonly"
        )
        size_unit_menu.pack(side=tk.LEFT, padx=5)
        
        # Convert button
        convert_btn = ModernButton(
            main_frame,
            text="Convert to Video",
            command=self.convert_to_video
        )
        convert_btn.pack(pady=20)
        
    def select_media(self):
        """Modified to filter file types based on current selection"""
        current_type = self.file_types[0] if self.file_types else None
        
        if current_type == 'video':
            filetypes = [
                ("Video files", "*.mp4 *.mov *.avi *.mkv"),
                ("All files", "*.*")
            ]
        elif current_type == 'image':
            filetypes = [
                ("Image files", "*.png *.jpg *.jpeg *.tiff *.bmp"),
                ("All files", "*.*")
            ]
        else:
            filetypes = [
                ("Media files", "*.png *.jpg *.jpeg *.tiff *.bmp *.mp4 *.mov *.avi *.mkv"),
                ("Image files", "*.png *.jpg *.jpeg *.tiff *.bmp"),
                ("Video files", "*.mp4 *.mov *.avi *.mkv"),
                ("All files", "*.*")
            ]
        
        files = filedialog.askopenfilenames(
            title="Select Media Files",
            filetypes=filetypes
        )
        
        if files:
            self.add_files(files)
    
    def add_files(self, files):
        """Add new files to the existing list"""
        # First check if we already have files and get their type
        current_type = None
        if self.file_types:
            current_type = self.file_types[0]
        
        for file in files:
            if not isinstance(file, str):
                file = str(file)
            
            ext = os.path.splitext(file)[1].lower()
            # Determine file type
            new_type = 'video' if ext in ['.mp4', '.mov', '.avi', '.mkv'] else 'image'
            
            # Check if this would mix types
            if current_type and new_type != current_type:
                messagebox.showerror(
                    "Error", 
                    "Cannot mix images and videos. Please use only one type of media."
                )
                return
            
            # If this is the first file, set the current type
            if not current_type:
                current_type = new_type
            
            self.media_files.append(file)
            self.file_types.append(new_type)
            
            if new_type == 'video':
                # Get video bitrate using ffprobe
                try:
                    cmd = [
                        'ffprobe', 
                        '-v', 'error', 
                        '-select_streams', 'v:0', 
                        '-show_entries', 'stream=bit_rate', 
                        '-of', 'default=noprint_wrappers=1:nokey=1', 
                        file
                    ]
                    result = subprocess.check_output(cmd).decode().strip()
                    # Only try to convert if we got a numeric result
                    if result.isdigit():
                        bitrate = int(result) // 1000  # Convert to kbps
                    else:
                        bitrate = 20000  # Default if we can't parse the bitrate
                    self.video_bitrates.append(bitrate)
                except:
                    self.video_bitrates.append(20000)  # Default 20Mbps if can't detect
            else:
                self.video_bitrates.append(None)
        
        # Update average bitrate
        valid_bitrates = [b for b in self.video_bitrates if b is not None]
        if valid_bitrates:
            avg_bitrate = sum(valid_bitrates) // len(valid_bitrates)
            self.bitrate.set(str(avg_bitrate))
        
        self.update_listbox()
        self.status_text.set(f"Selected {len(self.media_files)} files")
    
    def delete_selected(self):
        """Delete selected item from the list"""
        selection = self.listbox.curselection()
        if not selection:
            return
            
        idx = selection[0]
        del self.media_files[idx]
        del self.file_types[idx]
        del self.video_bitrates[idx]
        
        # Update average bitrate
        valid_bitrates = [b for b in self.video_bitrates if b is not None]
        if valid_bitrates:
            avg_bitrate = sum(valid_bitrates) // len(valid_bitrates)
            self.bitrate.set(str(avg_bitrate))
        
        self.update_listbox()
        
        if idx < self.listbox.size():
            self.listbox.selection_set(idx)
        elif self.listbox.size() > 0:
            self.listbox.selection_set(idx - 1)
    
    def move_item(self, old_index, new_index):
        """Move item from old_index to new_index"""
        self.media_files.insert(new_index, self.media_files.pop(old_index))
        self.file_types.insert(new_index, self.file_types.pop(old_index))
        self.video_bitrates.insert(new_index, self.video_bitrates.pop(old_index))
        self.update_listbox()
        self.listbox.selection_set(new_index)
    
    def update_listbox(self):
        self.listbox.delete(0, tk.END)
        for i, file in enumerate(self.media_files):
            filename = os.path.basename(file)
            file_type = self.file_types[i]
            self.listbox.insert(tk.END, f"[{file_type.upper()}] {filename}")
        
    def move_up(self):
        selection = self.listbox.curselection()
        if not selection or selection[0] == 0:
            return
        
        idx = selection[0]
        self.media_files[idx], self.media_files[idx-1] = self.media_files[idx-1], self.media_files[idx]
        self.file_types[idx], self.file_types[idx-1] = self.file_types[idx-1], self.file_types[idx]
        self.video_bitrates[idx], self.video_bitrates[idx-1] = self.video_bitrates[idx-1], self.video_bitrates[idx]
        self.update_listbox()
        self.listbox.selection_set(idx-1)

    def move_down(self):
        selection = self.listbox.curselection()
        if not selection or selection[0] == len(self.media_files) - 1:
            return
        
        idx = selection[0]
        self.media_files[idx], self.media_files[idx+1] = self.media_files[idx+1], self.media_files[idx]
        self.file_types[idx], self.file_types[idx+1] = self.file_types[idx+1], self.file_types[idx]
        self.video_bitrates[idx], self.video_bitrates[idx+1] = self.video_bitrates[idx+1], self.video_bitrates[idx]
        self.update_listbox()
        self.listbox.selection_set(idx+1)
        
    def read_output(self, process, output_queue):
        """Read the process output in a separate thread"""
        for line in iter(process.stderr.readline, ''):
            if line:
                output_queue.put(line)
        process.stderr.close()
        
    def process_ffmpeg_output(self, progress_window, output_queue, total_frames):
        """Process FFmpeg output from the queue"""
        try:
            while True:
                try:
                    line = output_queue.get_nowait()
                except queue.Empty:
                    break
                
                if "frame=" in line:
                    try:
                        # Extract frame number more safely
                        frame_match = re.search(r"frame=\s*(\d+)", line)
                        if frame_match:
                            frame_num = int(frame_match.group(1))
                        else:
                            continue
                        
                        progress = (frame_num / total_frames) * 100 if total_frames > 0 else 0
                        
                        # Calculate current encoding FPS
                        current_time = time.time()
                        time_diff = current_time - self.last_time
                        if time_diff >= 0.5:  # Update every half second
                            frame_diff = frame_num - self.last_frame
                            current_fps = frame_diff / time_diff if time_diff > 0 else 0
                            progress_window.fps_text.set(f"Encoding speed: {current_fps:.1f} fps")
                            
                            # Calculate estimated time remaining
                            elapsed_time = current_time - self.start_time
                            if progress > 0:
                                total_time = elapsed_time * 100 / progress
                                remaining_time = total_time - elapsed_time
                                minutes = int(remaining_time // 60)
                                seconds = int(remaining_time % 60)
                                progress_window.time_text.set(
                                    f"Time remaining: {minutes:02d}:{seconds:02d}"
                                )
                            
                            self.last_frame = frame_num
                            self.last_time = current_time
                        
                        progress_window.progress_var.set(progress)
                        progress_window.status_text.set(
                            f"Processing frame {frame_num}/{total_frames}"
                        )
                        
                    except (ValueError, AttributeError, TypeError) as e:
                        print(f"Error processing output: {e}")
                        continue
            
            # Schedule the next update
            self.root.after(100, lambda: self.process_ffmpeg_output(
                progress_window, output_queue, total_frames
            ))
            
        except tk.TclError:  # Window was closed
            pass
        
    def calculate_target_bitrate(self, duration_seconds):
        """Calculate required bitrate for target file size"""
        if not self.target_size.get().strip():
            return None

        try:
            target_size = float(self.target_size.get().strip())
            if target_size <= 0:
                raise ValueError

            # Convert target size to bits
            multiplier = 1024 * 1024 * 8 if self.size_unit.get() == "MB" else 1024 * 8
            target_bits = target_size * multiplier

            # Calculate required bitrate (bits per second)
            # Using 98% of target to ensure we stay under limit
            target_bitrate = int((target_bits / duration_seconds) * 0.98)

            # Convert to kbps
            target_kbps = target_bitrate // 1000

            # Ensure minimum viable bitrate (500 kbps)
            return max(500, target_kbps)

        except (ValueError, TypeError):
            return None

    def convert_to_video(self):
        if not self.media_files:
            messagebox.showerror("Error", "Please select media files first!")
            return
        
        try:
            # Validate bitrate before starting
            bitrate = self.bitrate.get().strip()
            if bitrate:  # Only validate if not empty
                try:
                    bitrate = int(bitrate)
                    if bitrate <= 0:
                        raise ValueError
                except ValueError:
                    messagebox.showerror("Error", "Please enter a valid bitrate!")
                    return
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid bitrate!")
            return

        # Calculate duration
        duration_seconds = len(self.media_files) / float(self.fps.get())

        # Calculate target bitrate if target size is set
        target_bitrate = self.calculate_target_bitrate(duration_seconds)
        
        # Determine the bitrate to use
        try:
            if target_bitrate is not None:
                bitrate = target_bitrate
                print(f"Calculated target bitrate: {bitrate} kbps for target size: {self.target_size.get()} {self.size_unit.get()}")
            else:
                bitrate = int(self.bitrate.get().strip().replace(',', ''))
                if bitrate <= 0:
                    raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid bitrate in kbps!")
            return

        # Get save location
        save_path = filedialog.asksaveasfilename(
            defaultextension=".mp4",
            initialdir=str(Path(self.media_files[0]).parent.parent),
            title="Save Video As",
            filetypes=[("MP4 files", "*.mp4")]
        )
        
        if not save_path:
            return
            
        # Create and show progress window
        progress_window = ProgressWindow(self.root)
        progress_window.output_file = save_path
        
        # Store progress window reference
        self.progress_window = progress_window
        
        def conversion_thread():
            temp_list_path = "temp_file_list.txt"
            max_width = 0
            max_height = 0
            temp_videos = []
            
            try:
                # Reset timing variables
                self.last_frame = 0
                self.last_time = time.time()
                self.start_time = time.time()
                
                # First pass: analyze input files for resolution
                for file, file_type in zip(self.media_files, self.file_types):
                    try:
                        cmd = [
                            'ffprobe',
                            '-v', 'error',
                            '-select_streams', 'v:0',
                            '-show_entries', 'stream=width,height',
                            '-of', 'csv=p=0',
                            file
                        ]
                        output = subprocess.check_output(cmd).decode().strip()
                        if output:
                            width, height = map(int, output.split(','))
                            max_width = max(max_width, width)
                            max_height = max(max_height, height)
                    except:
                        continue
                
                # First pass: create temporary videos for any input videos that need transcoding
                temp_video_map = {}  # Add this to map indices to temp files
                for i, (file, file_type) in enumerate(zip(self.media_files, self.file_types)):
                    if file_type == 'video':
                        temp_output = f"temp_video_{i}.mp4"
                        temp_videos.append(temp_output)
                        temp_video_map[i] = temp_output  # Store mapping
                        
                        # Use detected resolution if no custom resolution specified
                        resolution = self.resolution.get().strip()
                        if not resolution and max_width > 0 and max_height > 0:
                            resolution = f"{max_width}x{max_height}"
                        
                        # Transcode video to ensure compatibility
                        transcode_cmd = [
                            get_ffmpeg_path(),
                            "-y",
                            "-i", file,
                            "-c:v", "h264_nvenc" if self.use_gpu.get() else "libx264",
                            "-r", str(self.fps.get()),
                            "-pix_fmt", "yuv420p"
                        ]
                        
                        # Add resolution if specified or detected
                        if resolution:
                            transcode_cmd.extend(["-s", resolution])
                        
                        transcode_cmd.append(temp_output)
                        
                        try:
                            subprocess.run(transcode_cmd, creationflags=CREATE_NO_WINDOW, check=True)
                        except subprocess.CalledProcessError as e:
                            self.root.after(0, lambda: messagebox.showerror("Error", f"FFmpeg error during transcoding: {e}"))
                            return
                
                # Create temporary file list
                with open(temp_list_path, "w", encoding='utf-8') as f:
                    for i, (file, file_type) in enumerate(zip(self.media_files, self.file_types)):
                        if file_type == 'image':
                            # For images, specify duration
                            f.write(f"file '{file}'\n")
                            f.write(f"duration {1/float(self.fps.get())}\n")
                        else:
                            # For videos, use the transcoded temporary file
                            temp_file = temp_video_map[i]  # Get the correct temp file
                            f.write(f"file '{temp_file}'\n")
                
                # Add final command for concatenation
                cmd = [
                    get_ffmpeg_path(),
                    "-y",
                    "-f", "concat",
                    "-safe", "0",
                    "-i", temp_list_path,
                ]
                
                # Add framerate
                cmd.extend(["-r", str(self.fps.get())])
                
                # Add resolution if specified or detected
                resolution = self.resolution.get().strip()
                if not resolution and max_width > 0 and max_height > 0:
                    resolution = f"{max_width}x{max_height}"
                if resolution:
                    cmd.extend(["-s", resolution])
                
                # Add GPU encoding if selected and available
                if self.use_gpu.get():
                    try:
                        nvidia_smi = subprocess.run(
                            ["nvidia-smi"],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE
                        )
                        if nvidia_smi.returncode == 0:
                            cmd.extend([
                                "-c:v", "h264_nvenc",
                                "-preset", "p7",
                                "-tune", "hq",
                                "-rc", "vbr_hq",
                                "-b:v", f"{bitrate}k",
                                "-maxrate", f"{bitrate}k",
                                "-bufsize", f"{bitrate*2}k"
                            ])
                        else:
                            cmd.extend(["-c:v", "libx264"])
                    except FileNotFoundError:
                        cmd.extend(["-c:v", "libx264"])
                else:
                    cmd.extend(["-c:v", "libx264"])
                
                # Move bitrate parameters outside of GPU block if not using GPU
                if not self.use_gpu.get():
                    cmd.extend([
                        "-b:v", f"{bitrate}k",
                        "-maxrate", f"{bitrate}k",
                        "-bufsize", f"{bitrate*2}k"
                    ])
                
                # Print final command for debugging
                print("FFmpeg command:", " ".join(cmd))
                
                # Add remaining parameters
                cmd.extend([
                    "-pix_fmt", "yuv420p",
                    save_path
                ])
                
                # Create output queue and start process
                output_queue = queue.Queue()
                process = subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    universal_newlines=True,
                    bufsize=1,
                    creationflags=subprocess.CREATE_NO_WINDOW
                )
                
                progress_window.process = process
                
                # Start output reader thread
                output_thread = threading.Thread(
                    target=self.read_output,
                    args=(process, output_queue),
                    daemon=True
                )
                output_thread.start()
                
                # Start progress monitoring
                total_frames = len(self.media_files)
                self.root.after(100, lambda: self.process_ffmpeg_output(
                    progress_window, output_queue, total_frames
                ))
                
                # Wait for process to complete
                returncode = process.wait()
                
                if returncode != 0:
                    error_output = process.stderr.read()
                    print(f"FFmpeg error output: {error_output}")
                    def show_error():
                        messagebox.showerror("Error", f"FFmpeg error: {error_output}")
                    self.root.after(0, show_error)
                else:
                    def show_success():
                        messagebox.showinfo("Success", "Video created successfully!")
                    self.root.after(0, show_success)
                
            except Exception as error:
                self.root.after(0, lambda e=error: messagebox.showerror("Error", str(e)))
            
            finally:
                # Clean up temp files
                try:
                    if os.path.exists(temp_list_path):
                        os.remove(temp_list_path)
                    for temp_file in temp_videos:
                        if os.path.exists(temp_file):
                            os.remove(temp_file)
                except Exception as cleanup_error:
                    print(f"Error cleaning up temp files: {cleanup_error}")
                
                # Close progress window
                def cleanup():
                    progress_window.destroy()
                self.root.after(0, cleanup)
        
        # Start conversion in separate thread
        threading.Thread(target=conversion_thread, daemon=True).start()
    
    def run(self):
        self.root.mainloop()

if __name__ == "__main__":
    app = ImageToVideoConverter()
    app.run()
