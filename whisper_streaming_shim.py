from asyncio import Queue
import json
from whisper_online import FasterWhisperASR, OnlineASRProcessor
import numpy as np
from datetime import datetime, timedelta
from model import FasterWhisperProcesser


# TODO: proc%がvadアリでも高い


class FasterWhisperASRAsync:
	sep = ""
	def __init__(self, ws: FasterWhisperProcesser, language: str):
		self.ws = ws
		self.language = language
		self.vad = False
	def load_model(self, modelsize, cache_dir, model_dir):
		pass
	async def transcribe(self, audio, init_prompt=""):
		ignorelist = ["・・・", "…", "ご視聴ありがとうございました", "。。。"]
		for word in ignorelist:
			init_prompt = init_prompt.replace(word, "")
		a = await self.ws.transcribe_async(audio, language=self.language, initial_prompt=init_prompt, vad=self.vad)
		return a["segments"]

	def ts_words(self, segments):
		o = []
		for segment in segments:
			for word in segment.words:
				# not stripping the spaces -- should not be merged with them!
				w = word["word"]
				t = (word["start"], word["end"], w)
				o.append(t)
		return o

	def segments_end_ts(self, res):
		return [s.end for s in res]

	def use_vad(self):
		self.vad = True


async def func(iqueue: Queue[tuple[np.ndarray, datetime]], oqueue: Queue[str], ws: FasterWhisperProcesser, language: str, secs: int):
	"""
		iqueue: Queue[(arr[f32], datetime)]
		oqueue: Queue[json[text, starttime(%H:%M:%S), endtime(%H:%M:%S)]]
	"""
	asr = FasterWhisperASRAsync(ws, language)
	asr.use_vad()
	online = OnlineASRProcessor(asr)

	buf, starttime = await iqueue.get()
	# buf f32 [n] sr=16000
	online.insert_audio_chunk(buf)
	while True:
		buf, _starttime = await iqueue.get()
		online.insert_audio_chunk(buf)
		while not iqueue.empty():
			buf, _starttime = iqueue.get_nowait()
			online.insert_audio_chunk(buf)
		if online.audio_buffer.size < secs * 16000:
			continue
		begin_timestamp, end_timestamp, text = await online.process_iter()
		
		if begin_timestamp is None or end_timestamp is None:
			continue
		# print(begin_timestamp, end_timestamp)
		begin_timestamp = starttime + timedelta(seconds=begin_timestamp)
		end_timestamp = starttime + timedelta(seconds=end_timestamp)
		await oqueue.put(json.dumps([text, begin_timestamp.strftime('%H:%M:%S'), end_timestamp.strftime('%H:%M:%S')]))

	# o = online.finish()
