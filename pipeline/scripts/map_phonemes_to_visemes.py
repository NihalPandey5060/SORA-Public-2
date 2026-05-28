import json
import os
from pipeline.scripts.phoneme_to_viseme import to_viseme
from pathlib import Path
import time

# BASE = os.path.dirname(os.path.abspath(__file__))
# proj = os.path.abspath(os.path.join(BASE, ".."))

def mappinf_phonems_to_vismes(folder_path): 
  start = time.time()
  folder_path = Path(folder_path) 
  alignment_path = folder_path / "alignment.json"
  phoneme_lines_path = folder_path / "text_phonemes.txt"
  out_path = folder_path / "viseme_timeline.json" 

  with open(alignment_path, "r", encoding="utf-8") as f:
      alignment = json.load(f)

  fragments = alignment.get("fragments", [])

  with open(phoneme_lines_path, "r", encoding="utf-8") as f:
      phoneme_lines = [ln.strip() for ln in f.readlines()]

  if len(phoneme_lines) != len(fragments):
      raise ValueError(
          f"Mismatch: {len(phoneme_lines)} phoneme lines vs {len(fragments)} alignment fragments. "
          "Ensure Day-2 phoneme lines correspond 1:1 to Day-3 fragments."
      )

  viseme_timeline = []

  for frag, ph_line in zip(fragments, phoneme_lines):
      start = float(frag["begin"])
      end = float(frag["end"])
      duration = max(1e-6, end - start)

      phs = [p for p in ph_line.split() if p.strip()]

      if not phs:
          viseme_timeline.append({
              "start_time": round(start, 3),
              "end_time": round(end, 3),
              "phoneme": "sil",
              "viseme_id": 0
          })
          continue

      step = duration / len(phs)

      cur = start
      for p in phs:
          v = to_viseme(p)
          next_t = min(end, cur + step)
          viseme_timeline.append({
              "start_time": round(cur, 3),
              "end_time": round(next_t, 3),
              "phoneme": p,
              "viseme_id": v
          })
          cur = next_t

  with open(out_path, "w", encoding="utf-8") as f:
      json.dump(viseme_timeline, f, indent=2, ensure_ascii=False)

  print(f"Wrote {out_path} with {len(viseme_timeline)} entries")
  end = time.time() 
  return end-start
