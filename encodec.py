# FORMAT
# FIN 1byte 1=not fin, 2=fin, others=not used
# OP 1byte 0=text, 1=binary, others=not used
# Payload length 2bytes (max 65535) big endian
# Payload n bytes (0<n<=65535 bytes) not empty

def _encode(fin: bool, op: int, b: bytes):
	assert len(b) <= 65535, "payload length must be less than 65536"
	assert op==0 or op==1, "op is only 0 or 1, not others"
	fin: int = 2 if fin else 1

	res = bytearray()
	res += bytes.fromhex(f"0{fin}")
	res += bytes.fromhex(f"0{op}")
	res += len(b).to_bytes(2, "big")
	res += b
	return res


def encode_str(text: str) -> bytes:
	b = bytearray(text.encode())
	res = bytearray()
	while len(b) > 65535:
		res += _encode(False, 0, b[:65535])
		b = b[65535:]
	res += _encode(True, 0, b[:65535])
	return bytes(res)

def encode_bin(data: bytes) -> bytes:
	b = bytearray(data)
	res = bytearray()
	while len(b) > 65535:
		res += _encode(False, 1, b[:65535])
		b = b[65535:]
	res += _encode(True, 1, b[:65535])
	return bytes(res)

def decode(data: bytes):
	fin = data[0]
	op = data[1]
	length = int.from_bytes(data[2:4], "big")
	if len(data[4:]) < length:
		return None, data
	payload = data[4:4+length]

	return (fin, op, payload), data[4+length:]
	
if __name__ == "__main__":
	print("test1")
	b = encode_str("asdasd")
	(fin, op, data), bb = decode(b)
	print(f"{fin=}, {op=}, {data.decode()}, {len(bb)=}")

	print("test2")
	b = encode_bin(b"123456")
	(fin, op, data), bb = decode(b)
	print(f"{fin=}, {op=}, {data}, {len(bb)=}")

	print("test3")
	s = ""
	for i in range(70000):
		s += "a"
	b = encode_str(s)
	(fin, op, data), bb = decode(b)
	print(f"{fin=}, {op=}, {len(data.decode())=}, {len(bb)=}")
	(fin, op, data), bb = decode(bb)
	print(f"{fin=}, {op=}, {len(data.decode())=}, {len(bb)=}")