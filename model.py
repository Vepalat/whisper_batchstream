import asyncio
import gc
from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor
from functools import partial
from typing import Any, Callable

import numpy as np


async def timer(interval: int, func: Callable[[], None], sharelist: list):
	await asyncio.sleep(interval)
	if len(sharelist) == 0:
		func()

class WhisperProcesserAbstruct(ABC):
	@abstractmethod
	def __init__(self, model: str) -> None:...
	@abstractmethod
	def transcribe(self, audio: np.ndarray, language: str, initial_prompt: str|None=None, vad: bool=False) -> dict[str, Any]:...
	@abstractmethod
	async def transcribe_async(self, audio: np.ndarray, language: str, initial_prompt: str|None=None, vad: bool=False) -> dict[str, Any]:...
	@abstractmethod
	def release(self) -> None:...

class Base(WhisperProcesserAbstruct):
	def __init__(self, model: str) -> None:
		self.executor = ProcessPoolExecutor(1)
		self.executor.submit(self.passfn).result()
		self.model_name = model
		self.interval = 30
		self.unload_task = None
		self.unload_task_q = []
	def transcribe(self, audio: np.ndarray, language: str, initial_prompt: str|None=None, vad: bool=False):
		try:
			if self.unload_task is not None:
				self.unload_task_q.append(None)
				self.unload_task = None
			result = self.executor.submit(self.transcribe_func, self.model_name, audio, language, initial_prompt, vad).result()
		finally:
			self.unload_task_q = []
			self.unload_task = asyncio.create_task(timer(self.interval, self.release, self.unload_task_q))
		return result
	async def transcribe_async(self, audio: np.ndarray, language: str, initial_prompt: str|None=None, vad: bool=False):
		try:
			if self.unload_task is not None:
				self.unload_task_q.append(None)
				self.unload_task = None
			result = await asyncio.get_event_loop().run_in_executor(self.executor, partial(self.transcribe_func, self.model_name, audio, language, initial_prompt, vad))
		finally:
			self.unload_task_q = []
			self.unload_task = asyncio.create_task(timer(self.interval, self.release, self.unload_task_q))
		return result
	def release(self):
		self.executor.shutdown(wait=False)
		del self.executor
		self.executor = ProcessPoolExecutor(1)
		self.executor.submit(self.passfn).result()
		gc.collect()

	@staticmethod
	@abstractmethod
	def passfn():...
	@staticmethod
	@abstractmethod
	def transcribe_func(model_name: str, audio: np.ndarray, language: str, initial_prompt: str|None=None, vad: bool=False) -> dict[str, str | list]:...

class WhisperProcesser(Base):
	@staticmethod
	def passfn():
		import faster_whisper
		import whisper
	@staticmethod
	def transcribe_func(model_name: str, audio: np.ndarray, language: str, initial_prompt: str|None=None, vad: bool=False):
		import faster_whisper
		import whisper
		global model, before_model_name
		g = globals()
		if g.get("before_model_name", None) != model_name:
			model = whisper.load_model(model_name, "cuda")
			before_model_name = model_name
		result = model.transcribe(audio, language=language, initial_prompt=initial_prompt)
		result["segments"] = [faster_whisper.transcribe.Segment(**i, words=None) for i in result["segments"]]
		return result

class FasterWhisperProcesser(Base):
	@staticmethod
	def passfn():
		import faster_whisper
	@staticmethod
	def transcribe_func(model_name: str, audio: np.ndarray, language: str, initial_prompt: str | None = None, vad: bool = False) -> dict[str, str | list]:
		import faster_whisper
		global model, before_model_name
		g = globals()
		if g.get("before_model_name", None) != model_name:
			model = faster_whisper.WhisperModel(model_name, device="cuda", compute_type="float16", cpu_threads=1, local_files_only=True)
			before_model_name = model_name
		audio = np.array(audio)
		if audio.size > 0:
			segments, _ = model.transcribe(audio, language=language, initial_prompt=initial_prompt, word_timestamps=True, vad_filter=vad, beam_size=5)
		else:
			segments = []
		segments = list(segments)
		return {
			"segments": segments,
			"text": "".join([segment.text for segment in segments]),
			# "language": info.language
		}
