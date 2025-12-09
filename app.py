import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from PIL import Image, ImageTk, ImageDraw
import numpy as np
import rasterio
from rasterio.transform import from_bounds
import xml.etree.ElementTree as ET
import zipfile
import requests
from io import BytesIO
import math
import cv2
import warnings

Image.MAX_IMAGE_PIXELS = None
warnings.filterwarnings('ignore', category=Image.DecompressionBombWarning)


class GeoReferencingTool:
    def __init__(self, root):
        self.root = root
        self.root.title("Manual GCP Georeferencing Tool")
        self.root.geometry("1400x850")
        
        self.input_image = None
        self.input_image_array = None
        self.satellite_image = None
        self.satellite_bounds = None
        
        self.gcp_points_input = []
        self.gcp_points_satellite = []
        
        self.display_scale_left = 1.0
        self.display_scale_right = 1.0
        
        self.current_mode = "input"
        
        self.create_widgets()
    
    def create_widgets(self):
        top_frame = tk.Frame(self.root)
        top_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)
        
        tk.Button(top_frame, text="1. Select KML/KMZ", command=self.load_kml, height=2).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="2. Select Image", command=self.load_image, height=2).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="Clear All Points", command=self.clear_points, bg="orange", height=2).pack(side=tk.LEFT, padx=5)
        tk.Button(top_frame, text="3. Apply Georeferencing", command=self.apply_georeferencing, bg="green", fg="white", height=2).pack(side=tk.LEFT, padx=5)
        
        info_frame = tk.Frame(self.root, bg="lightblue")
        info_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)
        
        self.info_label = tk.Label(info_frame, text="Instructions: Click matching points on both images (minimum 4 pairs needed)", 
                                    bg="lightblue", font=("Arial", 11, "bold"), pady=5)
        self.info_label.pack()
        
        canvas_frame = tk.Frame(self.root)
        canvas_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        left_frame = tk.Frame(canvas_frame)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5)
        
        left_label_frame = tk.Frame(left_frame)
        left_label_frame.pack(side=tk.TOP, fill=tk.X)
        tk.Label(left_label_frame, text="Input Image", font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        self.gcp_count_left = tk.Label(left_label_frame, text="Points: 0", fg="blue", font=("Arial", 10))
        self.gcp_count_left.pack(side=tk.RIGHT)
        
        self.canvas_left = tk.Canvas(left_frame, bg="gray", width=650, height=650)
        self.canvas_left.pack(fill=tk.BOTH, expand=True)
        self.canvas_left.bind("<Button-1>", self.on_click_left)
        
        right_frame = tk.Frame(canvas_frame)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=5)
        
        right_label_frame = tk.Frame(right_frame)
        right_label_frame.pack(side=tk.TOP, fill=tk.X)
        tk.Label(right_label_frame, text="Satellite Image", font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        self.gcp_count_right = tk.Label(right_label_frame, text="Points: 0", fg="blue", font=("Arial", 10))
        self.gcp_count_right.pack(side=tk.RIGHT)
        
        self.canvas_right = tk.Canvas(right_frame, bg="gray", width=650, height=650)
        self.canvas_right.pack(fill=tk.BOTH, expand=True)
        self.canvas_right.bind("<Button-1>", self.on_click_right)
        
        self.status_label = tk.Label(self.root, text="Step 1: Load KML/KMZ file to download satellite image", 
                                     relief=tk.SUNKEN, anchor=tk.W, font=("Arial", 10))
        self.status_label.pack(side=tk.BOTTOM, fill=tk.X)
    
    def load_kml(self):
        kml_path = filedialog.askopenfilename(filetypes=[("KML/KMZ files", "*.kml *.kmz")])
        if not kml_path:
            return
        
        try:
            self.status_label.config(text="Parsing KML and downloading satellite image...")
            self.root.update()
            
            coords = self.parse_kml(kml_path)
            center_lon, center_lat = self.get_polygon_center(coords)
            
            self.satellite_image, self.satellite_bounds = self.download_satellite_image(center_lon, center_lat)
            
            self.display_satellite_image()
            self.status_label.config(text=f"Satellite image loaded ({self.satellite_image.shape[1]}x{self.satellite_image.shape[0]}px). Step 2: Load your input image")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load KML: {str(e)}")
            self.status_label.config(text="Error loading KML")
    
    def load_image(self):
        image_path = filedialog.askopenfilename(filetypes=[("Image files", "*.jpg *.jpeg *.tif *.tiff *.png")])
        if not image_path:
            return
        
        try:
            if image_path.lower().endswith(('.tif', '.tiff')):
                with rasterio.open(image_path) as src:
                    if src.count >= 3:
                        self.input_image_array = src.read([1, 2, 3]).transpose(1, 2, 0)
                    else:
                        self.input_image_array = src.read(1)
                        self.input_image_array = np.stack([self.input_image_array]*3, axis=-1)
            else:
                self.input_image_array = np.array(Image.open(image_path))
            
            if len(self.input_image_array.shape) == 2:
                self.input_image_array = np.stack([self.input_image_array]*3, axis=-1)
            
            if self.input_image_array.shape[2] == 4:
                self.input_image_array = self.input_image_array[:, :, :3]
            
            self.input_image = Image.fromarray(self.input_image_array)
            self.display_input_image()
            self.status_label.config(text=f"Image loaded ({self.input_image.size[0]}x{self.input_image.size[1]}px). Step 3: Click matching points on both images")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image: {str(e)}")
            self.status_label.config(text="Error loading image")
    
    def display_input_image(self):
        if self.input_image is None:
            return
        
        canvas_width = self.canvas_left.winfo_width()
        canvas_height = self.canvas_left.winfo_height()
        
        if canvas_width <= 1:
            canvas_width = 650
        if canvas_height <= 1:
            canvas_height = 650
        
        img_copy = self.input_image.copy()
        draw = ImageDraw.Draw(img_copy)
        
        for i, (x, y) in enumerate(self.gcp_points_input):
            real_x = int(x / self.display_scale_left)
            real_y = int(y / self.display_scale_left)
            r = 8
            draw.ellipse([real_x-r, real_y-r, real_x+r, real_y+r], fill="red", outline="white", width=2)
            draw.text((real_x+12, real_y-12), str(i+1), fill="white", font=None)
        
        img_copy.thumbnail((canvas_width, canvas_height), Image.Resampling.LANCZOS)
        self.display_scale_left = min(canvas_width / self.input_image.width, canvas_height / self.input_image.height)
        
        self.input_photo = ImageTk.PhotoImage(img_copy)
        self.canvas_left.delete("all")
        self.canvas_left.create_image(canvas_width//2, canvas_height//2, image=self.input_photo)
    
    def display_satellite_image(self):
        if self.satellite_image is None:
            return
        
        canvas_width = self.canvas_right.winfo_width()
        canvas_height = self.canvas_right.winfo_height()
        
        if canvas_width <= 1:
            canvas_width = 650
        if canvas_height <= 1:
            canvas_height = 650
        
        img = Image.fromarray(self.satellite_image)
        draw = ImageDraw.Draw(img)
        
        for i, (x, y) in enumerate(self.gcp_points_satellite):
            real_x = int(x / self.display_scale_right)
            real_y = int(y / self.display_scale_right)
            r = 8
            draw.ellipse([real_x-r, real_y-r, real_x+r, real_y+r], fill="red", outline="white", width=2)
            draw.text((real_x+12, real_y-12), str(i+1), fill="white", font=None)
        
        img.thumbnail((canvas_width, canvas_height), Image.Resampling.LANCZOS)
        self.display_scale_right = min(canvas_width / self.satellite_image.shape[1], canvas_height / self.satellite_image.shape[0])
        
        self.satellite_photo = ImageTk.PhotoImage(img)
        self.canvas_right.delete("all")
        self.canvas_right.create_image(canvas_width//2, canvas_height//2, image=self.satellite_photo)
    
    def on_click_left(self, event):
        if self.input_image is None:
            return
        
        canvas_width = self.canvas_left.winfo_width()
        canvas_height = self.canvas_left.winfo_height()
        
        img_display_width = int(self.input_image.width * self.display_scale_left)
        img_display_height = int(self.input_image.height * self.display_scale_left)
        
        offset_x = (canvas_width - img_display_width) // 2
        offset_y = (canvas_height - img_display_height) // 2
        
        click_x = event.x - offset_x
        click_y = event.y - offset_y
        
        self.gcp_points_input.append((click_x, click_y))
        self.gcp_count_left.config(text=f"Points: {len(self.gcp_points_input)}")
        
        self.display_input_image()
        self.update_status()
    
    def on_click_right(self, event):
        if self.satellite_image is None:
            return
        
        canvas_width = self.canvas_right.winfo_width()
        canvas_height = self.canvas_right.winfo_height()
        
        img_display_width = int(self.satellite_image.shape[1] * self.display_scale_right)
        img_display_height = int(self.satellite_image.shape[0] * self.display_scale_right)
        
        offset_x = (canvas_width - img_display_width) // 2
        offset_y = (canvas_height - img_display_height) // 2
        
        click_x = event.x - offset_x
        click_y = event.y - offset_y
        
        self.gcp_points_satellite.append((click_x, click_y))
        self.gcp_count_right.config(text=f"Points: {len(self.gcp_points_satellite)}")
        
        self.display_satellite_image()
        self.update_status()
    
    def update_status(self):
        left_count = len(self.gcp_points_input)
        right_count = len(self.gcp_points_satellite)
        
        if left_count != right_count:
            self.status_label.config(text=f"⚠️ Point mismatch! Input: {left_count}, Satellite: {right_count}. Click on the other image to match.")
        elif left_count < 4:
            self.status_label.config(text=f"Need {4-left_count} more point pairs (minimum 4 required)")
        else:
            self.status_label.config(text=f"✓ {left_count} point pairs ready! Click 'Apply Georeferencing' to process.")
    
    def clear_points(self):
        self.gcp_points_input = []
        self.gcp_points_satellite = []
        self.gcp_count_left.config(text="Points: 0")
        self.gcp_count_right.config(text="Points: 0")
        self.display_input_image()
        self.display_satellite_image()
        self.status_label.config(text="All points cleared. Start clicking matching points on both images.")
    
    def apply_georeferencing(self):
        if self.input_image_array is None or self.satellite_image is None:
            messagebox.showerror("Error", "Please load both KML and image first")
            return
        
        if len(self.gcp_points_input) != len(self.gcp_points_satellite):
            messagebox.showerror("Error", f"Point mismatch! Input: {len(self.gcp_points_input)}, Satellite: {len(self.gcp_points_satellite)}")
            return
        
        if len(self.gcp_points_input) < 4:
            messagebox.showerror("Error", f"Need at least 4 point pairs. You have {len(self.gcp_points_input)}.")
            return
        
        output_path = filedialog.asksaveasfilename(defaultextension=".tif", filetypes=[("GeoTIFF", "*.tif")])
        if not output_path:
            return
        
        try:
            self.status_label.config(text="Calculating transformation matrix...")
            self.root.update()
            
            src_points = []
            for x, y in self.gcp_points_input:
                real_x = x / self.display_scale_left
                real_y = y / self.display_scale_left
                src_points.append([real_x, real_y])
            
            dst_points = []
            for x, y in self.gcp_points_satellite:
                real_x = x / self.display_scale_right
                real_y = y / self.display_scale_right
                dst_points.append([real_x, real_y])
            
            src_points = np.float32(src_points)
            dst_points = np.float32(dst_points)
            
            if len(src_points) == 4:
                M = cv2.getPerspectiveTransform(src_points[:4], dst_points[:4])
            else:
                M, _ = cv2.findHomography(src_points, dst_points, cv2.RANSAC, 5.0)
            
            self.status_label.config(text="Warping image...")
            self.root.update()
            
            h, w = self.satellite_image.shape[:2]
            aligned = cv2.warpPerspective(self.input_image_array, M, (w, h))
            
            self.status_label.config(text="Saving georeferenced GeoTIFF...")
            self.root.update()
            
            self.save_geotiff(aligned, self.satellite_bounds, output_path)
            
            messagebox.showinfo("Success", f"Georeferenced image saved!\nPoints used: {len(src_points)}\nFile: {output_path}")
            self.status_label.config(text=f"✓ Success! Saved: {output_path}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to georeference: {str(e)}")
            self.status_label.config(text=f"Error: {str(e)}")
    
    def parse_kml(self, kml_path):
        with open(kml_path, 'rb') as f:
            magic_bytes = f.read(2)
            f.seek(0)
        
        is_zip = magic_bytes == b'PK'
        
        if is_zip or kml_path.endswith('.kmz'):
            with zipfile.ZipFile(kml_path, 'r') as z:
                kml_file = [f for f in z.namelist() if f.endswith('.kml')][0]
                kml_content = z.read(kml_file)
        else:
            encodings = ['utf-8', 'utf-16', 'utf-16-le', 'utf-16-be', 'latin-1', 'windows-1252']
            kml_content = None
            for enc in encodings:
                try:
                    with open(kml_path, 'r', encoding=enc) as f:
                        kml_content = f.read()
                    break
                except (UnicodeDecodeError, UnicodeError):
                    continue
            
            if kml_content is None:
                with open(kml_path, 'rb') as f:
                    kml_content = f.read()
        
        if isinstance(kml_content, bytes):
            if kml_content.startswith(b'\xff\xfe') or kml_content.startswith(b'\xfe\xff'):
                try:
                    kml_content = kml_content.decode('utf-16')
                except:
                    kml_content = kml_content.decode('utf-8', errors='ignore')
            else:
                kml_content = kml_content.decode('utf-8', errors='ignore')
        
        kml_content = kml_content.strip()
        if kml_content.startswith('\ufeff'):
            kml_content = kml_content[1:]
        
        root = ET.fromstring(kml_content)
        ns = {'kml': 'http://www.opengis.net/kml/2.2'}
        
        coords_text = root.find('.//kml:coordinates', ns)
        if coords_text is None:
            ns = {'kml': 'http://earth.google.com/kml/2.0'}
            coords_text = root.find('.//kml:coordinates', ns)
        if coords_text is None:
            coords_text = root.find('.//coordinates')
        
        coords = []
        for line in coords_text.text.strip().split():
            parts = line.split(',')
            if len(parts) >= 2:
                lon, lat = float(parts[0]), float(parts[1])
                coords.append((lon, lat))
        
        return coords
    
    def get_polygon_center(self, coords):
        lons = [c[0] for c in coords]
        lats = [c[1] for c in coords]
        return (sum(lons) / len(lons), sum(lats) / len(lats))
    
    def download_satellite_image(self, center_lon, center_lat, width_m=1000, height_m=1000, zoom=17):
        meters_per_pixel = 156543.03392 * math.cos(math.radians(center_lat)) / (2 ** zoom)
        
        tile_x, tile_y = self.lat_lon_to_tile(center_lat, center_lon, zoom)
        
        tiles_x = int(width_m / (256 * meters_per_pixel)) + 2
        tiles_y = int(height_m / (256 * meters_per_pixel)) + 2
        
        tiles_x = min(tiles_x, 8)
        tiles_y = min(tiles_y, 8)
        
        start_x = tile_x - tiles_x // 2
        start_y = tile_y - tiles_y // 2
        
        images = []
        for y in range(start_y, start_y + tiles_y):
            row = []
            for x in range(start_x, start_x + tiles_x):
                url = f"https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={zoom}"
                try:
                    response = requests.get(url, timeout=10)
                    img = Image.open(BytesIO(response.content))
                    row.append(np.array(img))
                except:
                    row.append(np.zeros((256, 256, 3), dtype=np.uint8))
            images.append(row)
        
        rows = [np.concatenate(row, axis=1) for row in images]
        full_image = np.concatenate(rows, axis=0)
        
        deg_per_pixel = 360 / (256 * (2 ** zoom))
        
        west = (start_x * 256) * deg_per_pixel - 180
        east = ((start_x + tiles_x) * 256) * deg_per_pixel - 180
        
        north = self.y_to_lat(start_y * 256, zoom)
        south = self.y_to_lat((start_y + tiles_y) * 256, zoom)
        
        bounds = (west, south, east, north)
        
        return full_image, bounds
    
    def lat_lon_to_tile(self, lat, lon, zoom):
        lat_rad = math.radians(lat)
        n = 2.0 ** zoom
        x = int((lon + 180.0) / 360.0 * n)
        y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
        return x, y
    
    def y_to_lat(self, y, zoom):
        n = math.pi - 2 * math.pi * y / (256 * 2 ** zoom)
        return math.degrees(math.atan(math.sinh(n)))
    
    def save_geotiff(self, image, bounds, output_path):
        h, w = image.shape[:2]
        
        transform = from_bounds(bounds[0], bounds[1], bounds[2], bounds[3], w, h)
        
        if len(image.shape) == 2:
            count = 1
            image = image[:, :, np.newaxis]
        else:
            count = image.shape[2]
        
        with rasterio.open(
            output_path,
            'w',
            driver='GTiff',
            height=h,
            width=w,
            count=count,
            dtype=image.dtype,
            crs='EPSG:4326',
            transform=transform
        ) as dst:
            if count == 1:
                dst.write(image[:, :, 0], 1)
            else:
                for i in range(count):
                    dst.write(image[:, :, i], i + 1)


if __name__ == "__main__":
    root = tk.Tk()
    root.update_idletasks()
    app = GeoReferencingTool(root)
    root.mainloop()