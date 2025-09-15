import argparse
import gc

import faster_whisper
import torch
import whisper


parser = argparse.ArgumentParser()
parser.add_argument("--model", choices=["tiny", "base", "small", "medium", "large", "large-v1", "large-v2", "large-v3"])
parser.add_argument("--faster-whisper-only", action="store_true")
parser.add_argument("--whisper-only", action="store_true")
args = parser.parse_args()
assert not(args.faster_whisper_only and args.whisper_only), "Must specify exactly one of --faster-whisper-only or --whisper-only"
if args.model == "large":
	args.model = "large-v1"

if args.faster_whisper_only:
	faster_whisper.download_model(args.model)
elif args.whisper_only:
	whisper.load_model(args.model)
else:
	whisper.load_model(args.model)
	gc.collect()
	torch.cuda.empty_cache()
	faster_whisper.load_model(args.model)

#gc.collect()
#torch.cuda.empty_cache()
#
#faster_whisper.WhisperModel(args.model)