import csv
import os
import glob

def read_csv_data(file_path):
    data = []
    with open(file_path, 'r') as f:
        reader = csv.reader(f)
        try:
            next(reader) # Header
        except StopIteration:
            return []
        for row in reader:
            if len(row) >= 2:
                try:
                    data.append((float(row[0]), float(row[1])))
                except ValueError:
                    continue
    return data

def verify_file(original_csv, converted_csv):
    print(f"Comparing {os.path.basename(original_csv)} vs {os.path.basename(converted_csv)}")
    
    orig_data = read_csv_data(original_csv)
    conv_data = read_csv_data(converted_csv)
    
    # Original CSV has some header lines before data, need to skip them or find data start.
    # The converter outputs clean CSV (Header + Data).
    # The original CSV has complex header.
    
    # Let's align by matching the first common wavelength.
    # Original CSV data starts at line 3 (index 2) usually.
    
    # Find start of data in original
    start_idx = 0
    for i, (wav, abs_val) in enumerate(orig_data):
        if wav > 799.0 and wav < 801.0:
            start_idx = i
            break
            
    orig_data = orig_data[start_idx:]
    
    # Compare
    min_len = min(len(orig_data), len(conv_data))
    print(f"  Points to compare: {min_len}")
    
    errors = 0
    max_error = 0.0
    
    for i in range(min_len):
        w1, a1 = orig_data[i]
        w2, a2 = conv_data[i]
        
        if abs(w1 - w2) > 1e-4:
            print(f"  Mismatch at index {i}: Wavelength {w1} != {w2}")
            errors += 1
        
        diff = abs(a1 - a2)
        if diff > max_error:
            max_error = diff
            
        if diff > 1e-5:
             # print(f"  Mismatch at index {i}: Absorbance {a1} != {a2}")
             errors += 1
             
    if errors == 0:
        print("  MATCH! (Max error: {:.2e})".format(max_error))
    else:
        print(f"  FAILED with {errors} errors. Max error: {max_error:.2e}")

def main():
    raw_dir = r"C:\Users\chwang12\PycharmProjects\uvvis_converter\data\raw"
    conv_dir = r"C:\Users\chwang12\PycharmProjects\uvvis_converter\data\converted"
    
    original_csvs = glob.glob(os.path.join(raw_dir, "*.csv"))
    
    print(f"Found {len(original_csvs)} original CSVs.")
    
    for orig in original_csvs:
        base_name = os.path.basename(orig)
        conv = os.path.join(conv_dir, base_name)
        
        if os.path.exists(conv):
            verify_file(orig, conv)
        else:
            print(f"Converted file missing for {base_name}")

if __name__ == "__main__":
    main()
