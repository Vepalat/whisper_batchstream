import subprocess
from typing import NamedTuple
import numpy as np
from typing import List, Optional
import json
import signal

from model import Base, WhisperProcesserAbstruct
from encodec import encode_bin, encode_str, decode

# from faster_whisper.transcribe.Word
class Word(NamedTuple):
    start: float
    end: float
    word: str
    probability: float

# from faster_whisper.transcribe.Segment
class Segment(NamedTuple):
    id: int
    seek: int
    start: float
    end: float
    text: str
    tokens: List[int]
    temperature: float
    avg_logprob: float
    compression_ratio: float
    no_speech_prob: float
    words: Optional[List[Word]]

class SubprocWhisper:
	def __init__(self) -> None:
		self.proc = None
	def process(self, model_name: str, audio: np.ndarray, language: str, initial_prompt: str|None):
		self.spawn()
		b = bytearray()
		b += encode_str(model_name)
		b += encode_str(str(audio.dtype))
		b += encode_str(json.dumps(audio.shape))
		b += encode_bin(audio.tobytes())
		b += encode_str(language)
		b += encode_str("Some" if initial_prompt is not None else "None")
		b += encode_str(initial_prompt if initial_prompt is not None else "")
		self.proc.stdin.write(b)
		self.proc.stdin.flush()

		payload = bytearray()
		while True:
			fin = int.from_bytes(self.proc.stdout.read(1))
			op = int.from_bytes(self.proc.stdout.read(1))
			length = int.from_bytes(self.proc.stdout.read(2), "big")
			payload += self.proc.stdout.read(length)
			if fin == 2: # fin
				break
			if fin == 0:
				raise
		assert op == 0
		data = json.loads(payload)
		a = {}
		a["segments"] = [Segment(**i) for i in data["segments"]]
		return a

	def spawn(self):
		if self.proc is None:
			self.proc = subprocess.Popen(["python", "subproc_inner.py"], stdin=subprocess.PIPE, stdout=subprocess.PIPE)

	def release(self):
		if self.proc is not None:
			self.proc.stdin.close()
			self.proc.stdout.close()
			self.proc.send_signal(signal.SIGINT)
			self.proc = None

class WhisperSubProcesser(Base):
	@staticmethod
	def passfn():
		global subp
		subp = SubprocWhisper()
	@staticmethod
	def transcribe_func(model_name: str, audio: np.ndarray, language: str, initial_prompt: str | None = None, vad: bool = False) -> dict[str, str | list]:
		return subp.process(model_name, audio, language, initial_prompt)
	def release(self):
		super().release()
		
