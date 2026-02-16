import struct
import os

def find_float_in_file(file_path, target_values, tolerance=1e-6):
    with open(file_path, 'rb') as f:
        content = f.read()
    
    print(f"File size: {len(content)} bytes")
    
    found_offsets = []
    
    for val in target_values:
        print(f"Searching for value: {val}")
        # Search for float (32-bit)
        packed_float = struct.pack('<f', val)
        offset = 0
        while True:
            try:
                idx = content.index(packed_float, offset)
                print(f"  Found float32 {val} at offset {idx} (0x{idx:X})")
                found_offsets.append((val, 'float32', idx))
                offset = idx + 1
            except ValueError:
                break
                
        # Search for double (64-bit)
        packed_double = struct.pack('<d', val)
        offset = 0
        while True:
            try:
                idx = content.index(packed_double, offset)
                print(f"  Found float64 {val} at offset {idx} (0x{idx:X})")
                found_offsets.append((val, 'float64', idx))
                offset = idx + 1
            except ValueError:
                break
    
    return found_offsets

# Values from R19S1_ProDOT_CB_40mgml_64E-2mms_44C_111um_13uL.csv
# Line 3: 799.9984131,0.01515086647
# Line 4: 798.9951172,0.01449121442
# Line 5: 797.9915161,0.01608264074

target_values = [
    799.9984131,
    0.01515086647,
    798.9951172,
    0.01449121442,
    797.9915161,
    0.01608264074
]

dsw_path = r"C:\Users\chwang12\PycharmProjects\uvvis_converter\data\R19S1_ProDOT_CB_40mgml_64E-2mms_44C_111um_13uL.DSW"

if os.path.exists(dsw_path):
    find_float_in_file(dsw_path, target_values)
else:
    print(f"File not found: {dsw_path}")
