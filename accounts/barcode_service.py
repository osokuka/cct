"""
Barcode Generation Service for Room Identification
Generates Code128 barcodes with format: C1-D-B87-R101 (max 16 chars)
"""

import os
import io
from typing import Optional
from django.conf import settings
from django.core.files.base import ContentFile
from barcode import Code128
from barcode.writer import ImageWriter
from PIL import Image, ImageDraw, ImageFont
import tempfile


class BarcodeService:
    """Service for generating room barcodes"""
    
    @staticmethod
    def generate_barcode_data(room) -> str:
        """
        Generate barcode data string for a room
        Format: C1-D-B87-R101 (max 16 characters)
        """
        # Get camp code (first 2 characters, pad if needed)
        camp_code = room.floor.building.compound.camp.code[:2].upper()
        if len(camp_code) < 2:
            camp_code = camp_code.ljust(2, '0')
        
        # Get compound code (first character)
        compound_code = room.floor.building.compound.code[:1].upper()
        
        # Extract building number from building code (e.g., "BLDG15" -> "15")
        building_code = room.floor.building.code
        building_num = ''.join(filter(str.isdigit, building_code))
        if not building_num:
            building_num = building_code[:3].upper()
        else:
            building_num = f"B{building_num}"
        
        # Ensure building code is max 3 characters
        if len(building_num) > 3:
            building_num = building_num[:3]
        elif len(building_num) < 3:
            building_num = building_num.ljust(3, '0')
        
        # Get room code candidate and normalize by removing non-alphanumeric characters
        # Using more of the room code helps avoid collisions like "26-F" vs "26-FI"
        raw_room_code = (room.room_code or "")
        room_code = ''.join(ch for ch in raw_room_code.upper() if ch.isalnum())
        
        # Construct barcode data
        barcode_data = f"{camp_code}-{compound_code}-{building_num}-{room_code}"
        
        # Ensure it doesn't exceed 16 characters
        if len(barcode_data) > 16:
            # Truncate room code if needed to fit exactly within 16 characters maximum
            max_room_chars = 16 - len(f"{camp_code}-{compound_code}-{building_num}-")
            # Guard against negative in case prefixes alone exceed target (very unlikely with current scheme)
            max_room_chars = max(0, max_room_chars)
            room_code = room_code[:max_room_chars]
            barcode_data = f"{camp_code}-{compound_code}-{building_num}-{room_code}"
        
        return barcode_data
    
    @staticmethod
    def generate_barcode_image(barcode_data: str, width: int = 600, height: int = 200) -> bytes:
        """
        Generate barcode image as bytes
        """
        try:
            # Create Code128 barcode
            code = Code128(barcode_data, writer=ImageWriter())
            
            # Calculate appropriate module width for high quality
            data_length = len(barcode_data)
            if data_length <= 8:
                module_width = 1.2  # Increased for better quality
            elif data_length <= 12:
                module_width = 1.0
            else:
                module_width = 0.8
            
            # Generate image
            buffer = io.BytesIO()
            # Ensure module_height is positive
            module_height = max(50, height - 40)  # Minimum 50px height
            
            code.write(buffer, options={
                'module_width': module_width,
                'module_height': module_height,
                'quiet_zone': 10.0,  # Increased quiet zone for better scanning
                'font_size': 0,  # No text in base barcode
                'text_distance': 0,
                'background': 'white',
                'foreground': 'black',
                'write_text': False,  # Explicitly disable text
            })
            
            # Get the image
            buffer.seek(0)
            image_data = buffer.getvalue()
            
            return image_data
            
        except Exception as e:
            print(f"Error generating barcode: {e}")
            return None
    
    @staticmethod
    def generate_barcode_with_text(barcode_data: str, width: int = 600, height: int = 240) -> bytes:
        """
        Generate barcode image with text underneath
        """
        try:
            # Generate base barcode with more space
            barcode_height = max(100, height - 60)  # Leave 60px for text, minimum 100px
            barcode_bytes = BarcodeService.generate_barcode_image(barcode_data, width, barcode_height)
            
            if not barcode_bytes:
                return None
            
            # Open the barcode image
            barcode_img = Image.open(io.BytesIO(barcode_bytes))
            
            # Resize barcode to fit properly with high quality
            barcode_img = barcode_img.resize((width, barcode_height), Image.Resampling.LANCZOS)
            
            # Create a new image with space for text
            final_img = Image.new('RGB', (width, height), 'white')
            
            # Paste barcode at the top
            final_img.paste(barcode_img, (0, 0))
            
            # Add text below barcode
            draw = ImageDraw.Draw(final_img)
            
            # Use a larger, high-quality font
            font_size = 18  # Increased font size for better readability
            try:
                font = ImageFont.truetype("arial.ttf", font_size)
            except:
                try:
                    font = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", font_size)
                except:
                    font = ImageFont.load_default()
            
            # Calculate text position (centered)
            text_bbox = draw.textbbox((0, 0), barcode_data, font=font)
            text_width = text_bbox[2] - text_bbox[0]
            text_height = text_bbox[3] - text_bbox[1]
            
            # Center text horizontally and position below barcode with better spacing
            text_x = max(10, (width - text_width) // 2)  # At least 10px from edge
            text_y = barcode_height + 15  # 15px below barcode for better spacing
            
            # Ensure text doesn't go outside image bounds with better margins
            if text_x + text_width > width - 10:
                text_x = width - text_width - 10
            if text_y + text_height > height - 10:
                text_y = height - text_height - 10
            
            # Draw text
            draw.text((text_x, text_y), barcode_data, fill='black', font=font)
            
            # Convert to bytes
            output = io.BytesIO()
            final_img.save(output, format='PNG')
            return output.getvalue()
            
        except Exception as e:
            print(f"Error generating barcode with text: {e}")
            return None
    
    @staticmethod
    def generate_barcode_pdf(rooms, filename: str = "room_barcodes.pdf") -> bytes:
        """
        Generate PDF with multiple barcodes
        """
        try:
            from reportlab.lib.pagesizes import letter, A4
            from reportlab.lib.units import inch
            from reportlab.platypus import SimpleDocTemplate, Image as RLImage, Spacer, Paragraph
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.lib import colors
            
            # Create PDF buffer
            buffer = io.BytesIO()
            doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=0.5*inch, bottomMargin=0.5*inch)
            
            # Container for the 'Flowable' objects
            elements = []
            styles = getSampleStyleSheet()
            
            # Add title
            title = Paragraph("Room Barcodes", styles['Title'])
            elements.append(title)
            elements.append(Spacer(1, 12))
            
            # Generate barcodes for each room with high quality
            barcodes_per_row = 2  # Fewer per row for larger, higher quality barcodes
            barcode_width = 300  # Increased width for better quality
            barcode_height = 120  # Increased height for better quality
            
            for i, room in enumerate(rooms):
                barcode_data = BarcodeService.generate_barcode_data(room)
                barcode_bytes = BarcodeService.generate_barcode_with_text(
                    barcode_data, barcode_width, barcode_height
                )
                
                if barcode_bytes:
                    # Use in-memory image instead of temporary file
                    try:
                        # Create PIL image from bytes
                        from PIL import Image
                        pil_img = Image.open(io.BytesIO(barcode_bytes))
                        
                        # Convert to RGB if needed
                        if pil_img.mode != 'RGB':
                            pil_img = pil_img.convert('RGB')
                        
                        # Save to BytesIO
                        img_buffer = io.BytesIO()
                        pil_img.save(img_buffer, format='PNG')
                        img_buffer.seek(0)
                        
                        # Add image to PDF
                        img = RLImage(img_buffer, width=barcode_width, height=barcode_height)
                        elements.append(img)
                        
                        # Add room code only (no description)
                        room_info = f"{room.room_code}"
                        #room_para = Paragraph(room_info, styles['Normal'])
                        #elements.append(room_para)
                        elements.append(Spacer(1, 6))
                        
                    except Exception as img_error:
                        print(f"Error processing image for room {room.room_code}: {img_error}")
                        continue
                
                # Add page break every 6 barcodes (2 rows of 3)
                if (i + 1) % 6 == 0:
                    elements.append(Spacer(1, 12))
            
            # Build PDF
            doc.build(elements)
            buffer.seek(0)
            return buffer.getvalue()
            
        except Exception as e:
            print(f"Error generating PDF: {e}")
            return None
