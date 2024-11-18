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

        except ValueError:
            return None

def get_ffmpeg_path():
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        return os.path.join(sys._MEIPASS, 'ffmpeg.exe')
    else:
        # Running as script
        return 'ffmpeg'

class ImageToVideoConverter:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Image to Video Converter")
        self.root.geometry("600x450")
        self.root.configure(bg="#1a1a1a")
        
        # Variables
        self.image_files = []
        self.fps = tk.StringVar(value="30")
        self.status_text = tk.StringVar(value="No files selected")
        self.use_gpu = tk.BooleanVar(value=True)
        self.bitrate = tk.StringVar(value="20000")  # Default 20,000 kbps (20 Mbps)
        self.resolution = tk.StringVar(value="")   # Empty means original size
        self.target_size = tk.StringVar(value="")  # Empty means no target size
        self.size_unit = tk.StringVar(value="MB")  # MB or KB
        
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
            text="Select Images",
            command=self.select_images
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
        
    def select_images(self):
        files = filedialog.askopenfilenames(
            title="Select Images",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.tiff *.bmp"),
                ("All files", "*.*")
            ]
        )
        
        if files:
            self.image_files = sorted(files, key=self.natural_sort_key)
            self.status_text.set(f"Selected {len(self.image_files)} images")
        
    def natural_sort_key(self, text):
        return [int(c) if c.isdigit() else c.lower() for c in re.split('([0-9]+)', text)]
        
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
                        frame_num = int(line.split("frame=")[1].split()[0])
                        progress = (frame_num / total_frames) * 100
                        
                        # Calculate current encoding FPS
                        current_time = time.time()
                        time_diff = current_time - self.last_time
                        if time_diff >= 0.5:  # Update every half second
                            frame_diff = frame_num - self.last_frame
                            current_fps = frame_diff / time_diff
                            progress_window.fps_text.set(f"Encoding speed: {current_fps:.1f} fps")
                            
                            # Calculate estimated time remaining
                            elapsed_time = current_time - self.start_time
                            if progress > 0:
                                total_time = elapsed_time * 100 / progress
                                remaining_time = total_time - elapsed_time
                                progress_window.time_text.set(
                                    f"Time remaining: {datetime.fromtimestamp(remaining_time).strftime('%M:%S')}"
                                )
                            
                            self.last_frame = frame_num
                            self.last_time = current_time
                        
                        progress_window.progress_var.set(progress)
                        progress_window.status_text.set(
                            f"Processing frame {frame_num}/{total_frames}"
                        )
                        
                    except (ValueError, IndexError):
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

        except ValueError:
            return None

    def convert_to_video(self):
        if not self.image_files:
            messagebox.showerror("Error", "Please select images first!")
            return
            
        try:
            fps = float(self.fps.get())
            if fps <= 0:
                raise ValueError
        except ValueError:
            messagebox.showerror("Error", "Please enter a valid FPS value!")
            return
            
        # Calculate duration
        duration_seconds = len(self.image_files) / fps

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
            initialdir=str(Path(self.image_files[0]).parent.parent),
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
            
            try:
                # Reset timing variables
                self.last_frame = 0
                self.last_time = time.time()
                self.start_time = time.time()
                
                # Create temporary file list
                with open(temp_list_path, "w", encoding='utf-8') as f:
                    for image in self.image_files:
                        f.write(f"file '{image}'\n")
                
                # Store temp file path in progress window
                progress_window.temp_file = temp_list_path
                
                # Base command
                cmd = [
                    get_ffmpeg_path(),
                    "-y",
                    "-r", str(fps),
                    "-f", "concat",
                    "-safe", "0",
                    "-i", temp_list_path,
                ]
                
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
                
                # Add resolution parameter if specified
                if self.resolution.get().strip():
                    cmd.extend(["-s", self.resolution.get().strip()])
                
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
                total_frames = len(self.image_files)
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
                def show_error():
                    messagebox.showerror("Error", str(error))
                self.root.after(0, show_error)
            
            finally:
                # Clean up temp file
                try:
                    if os.path.exists(temp_list_path):
                        os.remove(temp_list_path)
                except Exception as e:
                    print(f"Error cleaning up temp file: {e}")
                
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