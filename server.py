import argparse
import asyncio
import datetime
import json
import multiprocessing
import traceback
import weakref
from asyncio import Queue
from functools import partial
from pathlib import Path
from typing import Callable, Generic, TypeVar

import fastapi
import fastapi.staticfiles
import faster_whisper_vad
import uvicorn

from model import FasterWhisperProcesser, WhisperProcesser
from subproc import WhisperSubProcesser
from processer import iq, oq, pr
# from processer import process
from webrtc import offer
from whisper_streaming_shim import func as whisper_streaming

app = fastapi.FastAPI()
japan_standard_time = datetime.timezone(datetime.timedelta(hours=+9), "JST")

_T = TypeVar("_T")
class SingleTon(Generic[_T]):
	def __init__(self, func: Callable[[], _T]) -> None:
		self.instance = None
		self.func = func
	
	def generate(self):
		if self.instance is None:
			value = self.func()
			self.instance = weakref.ref(value)
			return value

		value = self.instance()
		if value is None:
			value = self.func()
			self.instance = weakref.ref(value)
		return value

# @app.post("/")
# async def process_wrapper(file: bytes = fastapi.File()):
# 	await process(wp_factory.generate(), file)

@app.websocket("/ws")
async def websocket_endpoint(websocket: fastapi.WebSocket):
	await websocket.accept()
	iqueue = Queue()
	oqueue = Queue()

	config = await websocket.receive_text()
	config = json.loads(config)
	print(config)
	"""
	config = {
		"vad": bool,
		"keepprompt": bool,
		"secs": int,
		"min_silence_duration_s": float # Option default 5
		"vadconfig": { 
			threshold: float, # Option
			min_speech_duration_ms: int, # Option
			max_speech_duration_s: float, # Option
			min_silence_duration_ms: int, # Option
			window_size_samples: int, # Option
			speech_pad_ms: int # Option
		}
		"codec_format": ["raw", "opus", "flac"] # Option default raw
		// "fasterwhisper_mode": bool # Option default true # deprecated
		"language": ["en", "ja"] # Option default ja
	}
	"""
	vad = config["vad"]
	keepprompt = config["keepprompt"]
	secs = config["secs"]
	min_silence_duration_s = float(config.get("min_silence_duration_s", 5.0))
	vadconfig = faster_whisper_vad.VadOptions(**config["vadconfig"]) if vad is True else None
	codec_format = config.get("codec_format", "raw")
	fasterwhisper_mode = config.get("fasterwhisper_mode", True)
	language = config.get("language", "ja")

	if language not in ["en", "ja"]:
		raise ValueError(f"langauge option must be either one [en, ja], but {language}")

	if not(codec_format == "raw" or codec_format == "flac" or codec_format == "opus"):
		raise ValueError(f"codec_format must be either one [raw, flac, opus], but {codec_format}")

	if secs <= 0:
		raise ValueError("secs must be positive")
	
	if fasterwhisper_mode is True:
		wp = fwp_factory.generate()
	else:
		wp = fwp_factory.generate()
		# wp = wp_factory.generate()

	try:
		async with asyncio.TaskGroup() as group:
			task1 = group.create_task(iq(iqueue, websocket, codec_format))
			task2 = group.create_task(oq(oqueue, websocket))
			task3 = group.create_task(
				pr(iqueue, oqueue, wp, vad, keepprompt, buffer_length=secs, vad_parameters=vadconfig, min_silence_duration_s=min_silence_duration_s, language=language))
	except* fastapi.websockets.WebSocketDisconnect as e:
		r = []
		tmp = list(e.exceptions)
		newtmp = []
		while len(tmp) > 0:
			for i in tmp:
				if isinstance(i, BaseExceptionGroup):
					for j in i.exceptions:
						newtmp.append(j)
				else:
					r.append(i)
			
			tmp = newtmp
			newtmp = []
		
		for i in r:
			if not(i.code == 1000 or i.code == 1001):
				raise
		traceback.print_exception(e, limit=0)

@app.websocket("/ws2")
async def websocket_endpoint2(websocket: fastapi.WebSocket):
	await websocket.accept()
	iqueue = Queue()
	oqueue = Queue()

	config = await websocket.receive_text()
	config = json.loads(config)
	print(config)
	"""
	config = {
		"codec_format": ["raw", "opus", "flac"] # Option default raw
		"language": ["en", "ja"] # Option default ja
		"secs": int # 0 is ok default 0
	}
	"""
	codec_format = config.get("codec_format", "raw")
	language = config.get("language", "ja")
	secs = config.get("secs", 0)

	if language not in ["en", "ja"]:
		raise ValueError(f"langauge option must be either one [en, ja], but {language}")

	if not(codec_format == "raw" or codec_format == "flac" or codec_format == "opus"):
		raise ValueError(f"codec_format must be either one [raw, flac, opus], but {codec_format}")
	
	if secs < 0:
		raise ValueError("secs must be positive")

	wp = fwp_factory.generate()

	try:
		async with asyncio.TaskGroup() as group:
			task1 = group.create_task(iq(iqueue, websocket, codec_format))
			task2 = group.create_task(oq(oqueue, websocket))
			task3 = group.create_task(whisper_streaming(iqueue, oqueue, wp, language, secs))
	except* fastapi.websockets.WebSocketDisconnect as e:
		r = []
		tmp = list(e.exceptions)
		newtmp = []
		while len(tmp) > 0:
			for i in tmp:
				if isinstance(i, BaseExceptionGroup):
					for j in i.exceptions:
						newtmp.append(j)
				else:
					r.append(i)
			
			tmp = newtmp
			newtmp = []
		
		for i in r:
			if not(i.code == 1000 or i.code == 1001):
				raise
		traceback.print_exception(e, limit=0)

@app.get("/offer")
@app.post("/offer")
async def offer_wapper(request: fastapi.Request):
	return await offer(request, fwp_factory.generate())

if __name__ == "__main__":
	multiprocessing.set_start_method("spawn")
	parse = argparse.ArgumentParser()
	parse.add_argument("--model", default="large-v1", choices=["tiny", "base", "small", "medium", "large", "large-v1", "large-v2", "large-v3", "turbo"])
	parse.add_argument("--port", default=9000, type=int)
	args = parse.parse_args()

	#debug setting
	#args.keepprompt = False
	#args.vad = True
	#args.model = "large-v1"

	if args.model == "large":
		args.model = "large-v1"
	print(f"load model {args.model}")
	#wp_factory = SingleTon(partial(WhisperProcesser, args.model))
	wp_factory = SingleTon(partial(WhisperSubProcesser, args.model))
	fwp_factory = wp_factory # same as ws_factory
	# fwp_factory = SingleTon(partial(FasterWhisperProcesser, args.model))

	#model = whisper.load_model(args.model, "cuda")
	# uvicorn.run(app, host="0.0.0.0", port=args.port, ssl_certfile=Path("./cert.pem"))
	uvicorn.run(app, host="0.0.0.0", port=args.port)
