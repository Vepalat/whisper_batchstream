# docker build -t whisperserver .
# docker run -d -p 9000:9000 whisper_server:latest
# FROM nvidia/cuda:11.8.0-cudnn8-devel-ubuntu22.04
FROM python:3.11

EXPOSE 9000

RUN apt update && \
DEBIAN_FRONTEND=noninteractive apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

RUN ["useradd", "-m", "user", "-s", "/bin/bash"]
USER user
WORKDIR /home/user

RUN echo export PATH="/home/user/.local/bin:$PATH" >> /home/user/.bashrc

COPY --chown=user:user download.py requirements_lock.txt ./

RUN pip install -U pip && pip install -r requirements_lock.txt && pip cache purge
RUN python download.py --model turbo --whisper-only

#COPY --chown=user:user webrtc.py processer.py server.py model.py whisper_online.py whisper_streaming_shim.py .
COPY --chown=user:user encodec.py faster_whisper_vad.py model.py NOTICE processer.py server.py subproc.py subproc_inner.py webrtc.py whisper_online.py whisper_streaming_shim.py ./
COPY --chown=user:user faster_whisper_vad_assets/ faster_whisper_vad_assets/
COPY --chown=user:user start_docker.sh .

CMD bash start_docker.sh
