from pathlib import Path
import json,sys
from faster_whisper import WhisperModel
# argv: audio.wav transcript.json model-cache-dir
model=WhisperModel('base',device='cpu',compute_type='int8',cpu_threads=4,download_root=sys.argv[3])
segments,info=model.transcribe(sys.argv[1],beam_size=1,vad_filter=True,condition_on_previous_text=False)
Path(sys.argv[2]).write_text(json.dumps([{'start':s.start,'end':s.end,'text':s.text.strip()} for s in segments]))
