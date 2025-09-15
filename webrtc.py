import asyncio
import datetime
import json
import logging
from asyncio import Queue

import aiortc
import aiortc.contrib.media
import av
import fastapi
import faster_whisper_vad
import numpy as np

from model import WhisperProcesser
from processer import japan_standard_time, pr

pcs = set()
logger = logging.getLogger('uvicorn')

async def iq(iqueue: Queue, track: aiortc.MediaStreamTrack):
	resampler = av.AudioResampler(format="s16", layout=1, rate=16000)
	while True:
		task1_recived_data: av.AudioFrame = await track.recv() #recive audio frame
		newframes = resampler.resample(task1_recived_data)[0]

		arr = newframes.to_ndarray()[0, :] / (2**15)
		arr = arr.astype(np.float32)

		# 16khz 1ch f32 part arr
		await iqueue.put((arr, datetime.datetime.now(japan_standard_time)))

async def oq(oqueue: Queue, datachannel: aiortc.RTCDataChannel):
	while True:
		item = await oqueue.get()
		datachannel.send(item)

class SpeakToText:
	def __init__(self, wp: WhisperProcesser) -> None:
		self.track = None
		self.dc = None
		self.options = None
		self.wp = wp
	
	def addTrack(self, track: aiortc.MediaStreamTrack):
		self.track = track
	
	def addDatachannel(self, dc: aiortc.RTCDataChannel):
		self.dc = dc
		@self.dc.on("message")
		def onmessage(message: str):
			self.options = json.loads(message)
			self.options["vadconfig"] = faster_whisper_vad.VadOptions(**self.options["vadconfig"]) if self.options["vadconfig"] is True else None
			self.options["min_silence_duration_s"] = float(self.options.get("min_silence_duration_s", 5.0))
	
	async def start(self):
		self.task = asyncio.create_task(self._task())
		self.task.add_done_callback(lambda future: self.stop())
		logger.info("recorder started")
	
	async def _task(self):
		while True:
			if self.track is None:
				await asyncio.sleep(1)
			else:
				break
		while True:
			if self.dc is None:
				await asyncio.sleep(1)
			else:
				break
		while True:
			if self.options is None:
				await asyncio.sleep(1)
			else:
				break
		self.dc.send(json.dumps(["connected", "", ""]))

		iqueue = Queue()
		oqueue = Queue()
		try:
			async with asyncio.TaskGroup() as group:
				task1 = group.create_task(iq(iqueue, self.track))
				task2 = group.create_task(oq(oqueue, self.dc))
				task3 = group.create_task(pr(iqueue, oqueue, self.wp, self.options["vad"], self.options["keepprompt"], buffer_length=self.options["secs"], vad_parameters=self.options["vadconfig"], min_silence_duration_s=self.options["min_silence_duration_s"]))
		except* Exception:
			logger.exception("error on webrtc task")

	def stop(self):
		if self.track is not None:
			self.track.stop()
			self.track = None
		if self.dc is not None:
			self.dc.close()
			self.dc = None
		if self.task is not None:
			self.task.cancel()
			self.task = None
			logger.info("recorder stoped")

async def offer(request: fastapi.Request, wp: WhisperProcesser):
	params = await request.json()
	offer = aiortc.RTCSessionDescription(sdp=params["sdp"], type=params["type"])

	pc = aiortc.RTCPeerConnection()
	pcs.add(pc)
	client = f"{request.client.host}:{request.client.port}"

	recorder = SpeakToText(wp)

	@pc.on("datachannel")
	def on_datachannel(channel: aiortc.RTCDataChannel):
		logger.info("%s: Datachannel %s received", str(client), channel.label)
		recorder.addDatachannel(channel)
		@channel.on("close")
		async def datachannel_on_close():
			recorder.stop()
			await pc.close()
	
	@pc.on("connectionstatechange")
	async def on_connectionstatechange():
		logger.info("%s: Connection state is %s", str(client), pc.connectionState)
		if pc.connectionState == "failed":
			recorder.stop()
			await pc.close()
		if pc.connectionState == "closed":
			pcs.discard(pc)
	
	@pc.on("track")
	def on_track(track: aiortc.MediaStreamTrack):
		logger.info("%s: Track %s received", str(client), track.kind)
		if track.kind == "audio":
			recorder.addTrack(track)

		@track.on("ended")
		async def on_ended():
			logger.info("%s: Track %s ended", str(client), track.kind)
			recorder.stop()
			await pc.close()

	await pc.setRemoteDescription(offer)
	await recorder.start()

	answer = await pc.createAnswer()
	await pc.setLocalDescription(answer)

	return fastapi.responses.JSONResponse(
		{"sdp": pc.localDescription.sdp, "type": pc.localDescription.type},
	)