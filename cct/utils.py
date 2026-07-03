"""
Utility functions for the NATO Camp Cleaning Tracker.
"""

def generate_barcode_data(*args):
    """
    Generate barcode data string for a room.
    Supports two signatures:
    1. generate_barcode_data(room_obj)
    2. generate_barcode_data(camp_code, compound_code, building_code, floor_code, room_code)
    """
    if len(args) == 1:
        # A single room object
        from accounts.barcode_service import BarcodeService
        return BarcodeService.generate_barcode_data(args[0])
        
    elif len(args) >= 5:
        # Five separate string parameters
        camp_code, compound_code, building_code, floor_code, room_code = args[:5]
        
        # Normalize and construct
        camp_code = camp_code[:2].upper()
        if len(camp_code) < 2:
            camp_code = camp_code.ljust(2, '0')
            
        compound_code = compound_code[:1].upper()
        
        building_num = ''.join(filter(str.isdigit, building_code))
        if not building_num:
            building_num = building_code[:3].upper()
        else:
            building_num = f"B{building_num}"
            
        if len(building_num) > 3:
            building_num = building_num[:3]
        elif len(building_num) < 3:
            building_num = building_num.ljust(3, '0')
            
        room_code_norm = ''.join(ch for ch in room_code.upper() if ch.isalnum())
        
        barcode_data = f"{camp_code}-{compound_code}-{building_num}-{room_code_norm}"
        
        if len(barcode_data) > 16:
            max_room_chars = 16 - len(f"{camp_code}-{compound_code}-{building_num}-")
            max_room_chars = max(0, max_room_chars)
            room_code_norm = room_code_norm[:max_room_chars]
            barcode_data = f"{camp_code}-{compound_code}-{building_num}-{room_code_norm}"
            
        return barcode_data
        
    return ""