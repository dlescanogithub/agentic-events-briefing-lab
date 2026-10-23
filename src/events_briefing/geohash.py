"""Geohash encoder. Precision 6 is about 1.2 km by 0.6 km."""

from __future__ import annotations

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def encode(lat: float, lon: float, precision: int = 6) -> str:
    if precision < 1:
        raise ValueError("precision must be >= 1")
    lat_interval = [-90.0, 90.0]
    lon_interval = [-180.0, 180.0]
    bits = (16, 8, 4, 2, 1)
    hash_chars: list[str] = []
    bit_index = 0
    ch = 0
    even = True
    while len(hash_chars) < precision:
        if even:
            mid = (lon_interval[0] + lon_interval[1]) / 2
            if lon >= mid:
                ch |= bits[bit_index]
                lon_interval[0] = mid
            else:
                lon_interval[1] = mid
        else:
            mid = (lat_interval[0] + lat_interval[1]) / 2
            if lat >= mid:
                ch |= bits[bit_index]
                lat_interval[0] = mid
            else:
                lat_interval[1] = mid
        even = not even
        if bit_index < 4:
            bit_index += 1
        else:
            hash_chars.append(_BASE32[ch])
            bit_index = 0
            ch = 0
    return "".join(hash_chars)
