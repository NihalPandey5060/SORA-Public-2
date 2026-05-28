import json
from pathlib import Path
import time

def build_vism_file(folder_path):
  
  start = time.time()
  folder_path = Path(folder_path)
  INPUT_PATH = folder_path / "viseme_timeline.json" 
  OUTPUT_PATH = folder_path / "output.vsim.json" 
  with open(INPUT_PATH, "r", encoding="utf-8") as f:
      viseme_timeline = json.load(f)

  vsim_data = []
  previous_id = None

  for item in viseme_timeline:
      start_time = float(item["start_time"])
      viseme_id = item["viseme_id"]

      offset_ms = int(start_time * 1000)

      if viseme_id == previous_id:
          continue

      vsim_data.append({
          "offset_ms": offset_ms,
          "viseme_id": viseme_id
      })
      previous_id = viseme_id

  with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
      json.dump(vsim_data, f, indent=2)

  print("VSIM file generated successfully:", OUTPUT_PATH)
  end = time.time() 
  return end-start
