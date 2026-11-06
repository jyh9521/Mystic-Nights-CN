"""Read-only cutscene audio discovery and strict Sony VAG/MIH layout helpers.

The module does not infer dialogue from sound-effect names, does not execute
scripts, and does not turn decoder/ASR output into approved subtitles.  MIH
field interpretation is independently checked against the pinned vgmstream
parser cited in docs/CUTSCENE_AUDIO.md; no upstream code is copied.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
import struct


class AudioFormatError(ValueError):
    """Unknown or malformed audio layout; never guess a decoding profile."""


@dataclass(frozen=True)
class VagInfo:
    sample_rate: int
    data_size: int
    name: str | None
    name_bytes_hex: str

    @property
    def samples(self) -> int:
        return self.data_size // 16 * 28


@dataclass(frozen=True)
class MihInfo:
    channels: int
    sample_rate: int
    interleave: int
    block_count: int
    last_block: int

    @property
    def channel_bytes(self) -> int:
        return (self.block_count - 1) * self.interleave + (self.last_block or self.interleave)

    @property
    def samples(self) -> int:
        return self.channel_bytes // 16 * 28


def parse_vag(data: bytes) -> VagInfo:
    if len(data) < 48 or data[:4] != b'VAGp':
        raise AudioFormatError('Expected a 48-byte VAGp header')
    version, reserved, length, rate = struct.unpack_from('>4I', data, 4)
    if version != 0x20 or reserved or not 8000 <= rate <= 96000:
        raise AudioFormatError('Unsupported VAG version/reserved/sample-rate fields')
    if length == 0 or length % 16 or len(data) != 48 + length:
        raise AudioFormatError('VAG payload length must match complete 16-byte frames')
    if any(data[20:32]):
        raise AudioFormatError('Unsupported non-zero VAG channel/reserved fields')
    raw_name = data[32:48].split(b'\0', 1)[0]
    # This debug label is not a codec field.  Some real bank names contain
    # non-ASCII bytes; retain them exactly without guessing their encoding.
    name = raw_name.decode('ascii') if raw_name.isascii() else None
    return VagInfo(rate, length, name, raw_name.hex())


def make_vag(payload: bytes, sample_rate: int, name: str = '') -> bytes:
    if not payload or len(payload) % 16 or not 8000 <= sample_rate <= 96000:
        raise AudioFormatError('A complete PS-ADPCM payload and valid rate are required')
    try:
        encoded_name = name.encode('ascii')
    except UnicodeEncodeError as exc:
        raise AudioFormatError('VAG channel name must be ASCII') from exc
    if len(encoded_name) > 16 or b'\0' in encoded_name:
        raise AudioFormatError('VAG channel name exceeds its 16-byte field')
    return (b'VAGp' + struct.pack('>4I', 0x20, 0, len(payload), sample_rate)
            + bytes(12) + encoded_name.ljust(16, b'\0') + payload)


def parse_mih(data: bytes) -> MihInfo:
    if len(data) != 64:
        raise AudioFormatError('Expected exactly 64 MIH header bytes')
    size, packed_last, channels, rate, interleave, blocks = struct.unpack_from('<6I', data)
    last = packed_last >> 8
    if size != 64 or packed_last & 255 != 32 or any(data[24:]):
        raise AudioFormatError('Unsupported MIH header/reserved fields')
    if not 1 <= channels <= 8 or not 8000 <= rate <= 96000:
        raise AudioFormatError('Unsupported MIH channels/sample rate')
    if not interleave or interleave % 16 or not blocks or blocks > 1000000:
        raise AudioFormatError('MIH interleave/block count must be explicit and complete')
    if last > interleave or last % 16:
        raise AudioFormatError('MIH last block is not within a complete channel block')
    return MihInfo(channels, rate, interleave, blocks, last)


def split_mib(info: MihInfo, data: bytes) -> tuple[bytes, ...]:
    expected = info.block_count * info.interleave * info.channels
    if len(data) != expected:
        raise AudioFormatError(f'MIB size mismatch: expected {expected}, got {len(data)}')
    channels = [bytearray() for _ in range(info.channels)]
    for block in range(info.block_count):
        length = info.last_block if block == info.block_count - 1 and info.last_block else info.interleave
        for ch in range(info.channels):
            start = (block * info.channels + ch) * info.interleave
            channels[ch].extend(data[start:start + length])
    result = tuple(bytes(c) for c in channels)
    assert all(len(c) == info.channel_bytes for c in result)
    return result


def _active_lines(data: bytes) -> bytes:
    result = []
    for line in data.splitlines(keepends=True):
        quoted = False
        stop = len(line)
        for index, value in enumerate(line):
            if value == 34:
                quoted = not quoted
            elif value == 59 and not quoted:
                stop = index
                break
        # Keep original byte offsets, including comments and CR CR LF endings.
        result.append(line[:stop] + bytes(32 if b not in (10, 13) else b for b in line[stop:]))
    return b''.join(result)


def cutscene_sound_commands(data: bytes) -> list[dict]:
    active = _active_lines(data)
    if not re.match(rb'SCR_TYPE\s+CUTSCENE(?:\s|$)', active):
        raise AudioFormatError('Expected CUTSCENE SCR')
    result = []
    for block in re.finditer(rb'\bSOUND\s*\{([^{}]*)\}', active):
        body = block[1]
        frames = re.findall(rb'\bFRAME\s+(\d+)(?=\s|$)', body)
        names = re.findall(rb'\bNAME\s+([^\s{}]+)', body)
        types = re.findall(rb'\bSOUND_TYPE\s+(BGM|VOICE|EFFECT)\s+(\d+)(?=\s|$)', body)
        if len(frames) != 1 or len(names) != 1 or len(types) != 1:
            raise AudioFormatError('SOUND requires one FRAME, NAME and supported SOUND_TYPE')
        raw = data[block.start():block.end()]
        result.append({'offset': block.start(), 'length': len(raw),
                       'source_sha256': hashlib.sha256(raw).hexdigest(),
                       'frame': int(frames[0]), 'name': names[0].decode('ascii'),
                       'sound_type': types[0][0].decode('ascii'),
                       'sound_argument': int(types[0][1])})
    if len(re.findall(rb'\bSOUND\s*\{', active)) != len(result):
        raise AudioFormatError('Malformed or nested SOUND block')
    return result
