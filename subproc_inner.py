import whisper
import sys
import json
import numpy as np
from encodec import encode_str

TEXT = 0
BINARY = 1

class FinError(Exception):
	def __str__(self):
		return "FinError"

class ModelManager:
	def __init__(self) -> None:
		self.model = None
		self.model_name = None
	def load(self, name: str):
		if self.model_name != name:
			self.model_name = name
			self.model = whisper.load_model(self.model_name)
	def transcribe(self, audio: np.ndarray, language: str, initial_prompt: str|None):
		return self.model.transcribe(audio, language=language, initial_prompt=initial_prompt, word_timestamps=True)

model = ModelManager()

def load_stdin():
	payload = bytearray()
	while True:
		fin = int.from_bytes(sys.stdin.buffer.read(1))
		op = int.from_bytes(sys.stdin.buffer.read(1))
		length = int.from_bytes(sys.stdin.buffer.read(2), "big")
		payload += sys.stdin.buffer.read(length)
		if fin == 2: # fin
			break
		elif fin == 0: # error
			raise FinError
	return op, bytes(payload)

def main():
	while True:
		""" host code
		b = bytearray()
		b += encode_str(model_name)
		b += encode_str(str(audio.dtype))
		b += encode_str(json.dumps(audio.shape))
		b += encode_bin(audio.tobytes())
		b += encode_str(language)
		b += encode_str("Some" if initial_prompt is not None else "None")
		b += encode_str(initial_prompt)
		"""

		op, payload = load_stdin()
		assert op == TEXT
		model_name = payload.decode()

		op, payload = load_stdin()
		assert op == TEXT
		audiodtype = payload.decode()

		op, payload = load_stdin()
		assert op == TEXT
		audioshape = json.loads(payload.decode())

		op, payload = load_stdin()
		assert op == BINARY
		audio = np.reshape(np.frombuffer(payload, dtype=audiodtype), audioshape).copy()

		op, payload = load_stdin()
		assert op == TEXT
		langauge = payload.decode()

		op, payload = load_stdin()
		assert op == TEXT
		initial_prompt_some = payload.decode()

		op, payload = load_stdin()
		assert op == TEXT
		initial_prompt = payload.decode()

		model.load(model_name)
		res = model.transcribe(audio, langauge, initial_prompt if initial_prompt_some == "Some" else None)

		sys.stdout.buffer.write(encode_str(json.dumps(res)))
		sys.stdout.buffer.flush()


if __name__ == "__main__":
	try:
		main()
	except FinError:
		pass