import asyncio
import datetime
import json
import tempfile
from asyncio import Queue, QueueEmpty
from functools import partial
from itertools import pairwise

import fastapi
import faster_whisper_vad
# import faster_whisper.audio
# import faster_whisper.transcribe
import numpy as np
from fastapi.responses import Response

from model import WhisperProcesserAbstruct

japan_standard_time = datetime.timezone(datetime.timedelta(hours=+9), "JST")

# async def process(wp: WhisperProcesserAbstruct, file: bytes = fastapi.File()):
# 	with tempfile.NamedTemporaryFile(mode="wb") as f:
# 		await asyncio.get_event_loop().run_in_executor(None, f.write, file)
# 		audio = await asyncio.get_event_loop().run_in_executor(None, partial(faster_whisper.audio.decode_audio, f.name))
# 	result = await wp.transcribe_async(audio, language="ja")
# 	response = Response(result["text"])
# 	return response

async def iq(iqueue: Queue, websocket: fastapi.WebSocket, codec_format: str):
	match codec_format:
		case "raw":
			while True:
				task1_recived_data = await websocket.receive_bytes() #recive 1ch f32 16khz audio
				recived_data_numpy = np.frombuffer(task1_recived_data, np.float32)
				await iqueue.put((recived_data_numpy, datetime.datetime.now(japan_standard_time)))
				await asyncio.sleep(0)
		case "flac":
			p = await asyncio.create_subprocess_exec(
				"ffmpeg",
				*["-f", "flac", "-i", "pipe:", "-f", "f32le", "-ar", "16000", "-ac", "1", "pipe:"],
				stdin=asyncio.subprocess.PIPE,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.DEVNULL
			)
			async def send_data():
				while True:
					task1_recived_data = await websocket.receive_bytes() #recive flac audio
					p.stdin.write(task1_recived_data)
					await p.stdin.drain()
			async def recv_data():
				size = 4 * 16000 * 1 //2 # f32 * samplerate * ch * ratio
				while True:
					data = await p.stdout.read(size)
					if len(data) == 0:
						raise EOFError
					recived_data_numpy = np.frombuffer(data, np.float32)
					await iqueue.put((recived_data_numpy, datetime.datetime.now(japan_standard_time)))
					await asyncio.sleep(0)
			try:
				async with asyncio.TaskGroup() as group:
					task1 = group.create_task(send_data())
					task2 = group.create_task(recv_data())
			finally:
				p.kill()
		case "opus":
			p = await asyncio.create_subprocess_exec(
				"ffmpeg",
				*["-acodec", "libopus", "-i", "pipe:", "-filter:a", "loudnorm", "-f", "f32le", "-ar", "16000", "-ac", "1", "pipe:"],
				stdin=asyncio.subprocess.PIPE,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.DEVNULL
			)
			async def send_data():
				while True:
					task1_recived_data = await websocket.receive_bytes() #recive flac audio
					p.stdin.write(task1_recived_data)
					await p.stdin.drain()
			async def recv_data():
				size = 4 * 16000 * 1 //2 # f32 * samplerate * ch * ratio
				while True:
					data = await p.stdout.read(size)
					if len(data) == 0:
						raise EOFError
					recived_data_numpy = np.frombuffer(data, np.float32)
					await iqueue.put((recived_data_numpy, datetime.datetime.now(japan_standard_time)))
					await asyncio.sleep(0)
			try:
				async with asyncio.TaskGroup() as group:
					task1 = group.create_task(send_data())
					task2 = group.create_task(recv_data())
			finally:
				p.kill()
		case _:
			raise ValueError(f"not support codec_format: {codec_format}")

async def oq(oqueue: Queue, websocket: fastapi.WebSocket):
	while True:
		item = await oqueue.get()
		await websocket.send_text(item)

async def get_data(queue: Queue) -> tuple[list, datetime.datetime]:
	data_parts = []
	recived_data, last_add_timestamp = await queue.get()
	data_parts.append(recived_data)
	try:
		while True:
			recived_data, last_add_timestamp = queue.get_nowait()
			data_parts.append(recived_data)
	except QueueEmpty:
		pass
	return data_parts, last_add_timestamp

def make_skipped_chunks(speech_chunks: list, skipped_chunks: list):
	speech_chunks = speech_chunks[:]
	skipped_chunks = skipped_chunks[:]

	duration = speech_chunks[0]["start"]
	skipped_chunks = [{"start": i["start"]-duration, "duration": i["duration"]} for i in skipped_chunks]
	speech_chunks = [{"start": i["start"]-duration, "end": i["end"]-duration} for i in speech_chunks]
	for chunk0, chunk1 in pairwise(speech_chunks):
		concat_frames = 0
		for c,i in enumerate(skipped_chunks):
			if chunk0["end"] <= i["start"] <= chunk1["start"]:
				concat_frames += i["duration"]
				del skipped_chunks[c]
		duration = chunk1["start"] - chunk0["end"] + concat_frames
		skipped_chunks.append({
			"start": chunk0["end"],
			"duration": duration
		})
		for c,i in enumerate(skipped_chunks):
			if chunk0["end"] < i["start"]:
				skipped_chunks[c]["start"] -= duration
		for c,i in enumerate(speech_chunks):
			if chunk0["end"] < i["start"]:
				speech_chunks[c]["start"] -= duration
				speech_chunks[c]["end"] -= duration
	return skipped_chunks

def make_response(text: str, segmentsize: int, speech_relative_start_sec: int, speech_relative_end_sec: int, skipped_chunks: list, last_add_timestamp: datetime.datetime):
	start_sum_of_skipped_duration = sum([i["duration"]/16000 for i in skipped_chunks if speech_relative_start_sec<=i["start"]/16000])
	end_sum_of_skipped_duration = sum([i["duration"]/16000 for i in skipped_chunks if speech_relative_end_sec<=i["start"]/16000])
	start_timestamp = (
		last_add_timestamp
		-datetime.timedelta(seconds=segmentsize/16000)
		-datetime.timedelta(seconds=start_sum_of_skipped_duration)
		+datetime.timedelta(seconds=speech_relative_start_sec))
	end_timestamp = (
		last_add_timestamp
		-datetime.timedelta(seconds=segmentsize/16000)
		-datetime.timedelta(seconds=end_sum_of_skipped_duration)
		+datetime.timedelta(seconds=speech_relative_end_sec))
	s = json.dumps([text, f"{start_timestamp.strftime('%H:%M:%S')}", f"{end_timestamp.strftime('%H:%M:%S')}"])
	return s

async def pr(input_queue: Queue, output_queue: Queue, wp: WhisperProcesserAbstruct, vad: bool, keepprompt: bool, buffer_length: int = 30, vad_parameters: faster_whisper_vad.VadOptions|None = None, min_silence_duration_s: float = 5, language: str = "ja"):
	before_frames = 0
	data = np.empty((0,), np.float32)
	from collections import deque
	prompt_history = deque(maxlen=4)
	# prompt = "" if keepprompt is True else None
	prompt = "\n".join(list(prompt_history))
	skipped_chunks = []
	while True:
		data_parts, last_add_timestamp = await get_data(input_queue)
		data = np.concatenate([data, *data_parts])

		if not data.size >= 16000*buffer_length + before_frames:
			continue

		print(f"{data.size/16000} sec ({before_frames/16000} before_frame)", end="")
		if vad is True:
			speech_chunks = faster_whisper_vad.get_speech_timestamps(data, vad_parameters)
			speech_chunks.append({"start": data.size, "end": data.size})
			data = faster_whisper_vad.collect_chunks(data, speech_chunks)
			skipped_chunks = make_skipped_chunks(speech_chunks, skipped_chunks)
			print(f" vad {data.size/16000} sec")
		else:
			print()

		result = await wp.transcribe_async(data, language=language, initial_prompt=prompt)
		is_continue_silence = any([i["start"]==data.size and i["duration"]/16000 >= min_silence_duration_s for i in skipped_chunks])

		if len(result["segments"]) >= 2:
			for segment in result["segments"][:-1]:
				if keepprompt:
					prompt_history.append(segment.text)
					# prompt += segment.text
					prompt = "\n".join(list(prompt_history))
				s = make_response(segment.text, data.size, segment.start, segment.end, skipped_chunks, last_add_timestamp)
				await output_queue.put(s)
		elif is_continue_silence:
			for segment in result["segments"]:
				if keepprompt:
					prompt_history.append(segment.text)
					# prompt += segment.text
					prompt = "\n".join(list(prompt_history))
				s = make_response(segment.text, data.size, segment.start, segment.end, skipped_chunks, last_add_timestamp)
				await output_queue.put(s)

		if len(result["segments"]) > 0 and not is_continue_silence:
			# set to last segment start
			data = data[int(result["segments"][-1].start*16000):]
			skipped_chunks = [{"start": i["start"]-int(result["segments"][-1].start*16000), "duration": i["duration"]} for i in skipped_chunks if i["start"]>int(result["segments"][-1].start*16000)]
		else: # if result["sengments"] is empty or is_continue_silence
			data = np.empty((0,), np.float32)
			skipped_chunks = []
		before_frames = data.size