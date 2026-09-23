"""Native texture encoding for approved graphics; no archive writes.

ETC1 individual-mode bit fields mirror ctrtex's existing decoder. Both
partition directions and all modifier tables are searched. Alpha weights
the RGB error so invisible texels do not distort visible lettering.
"""
import numpy as np
from ctrtex import _idx


def abgr32_encode(rgba, flip=True):
    """G1T 텍스처는 Y축을 뒤집어 저장한다(flip=True).
    HOME 배너의 CGFX 텍스처는 뒤집지 않으므로 flip=False 로 쓴다."""
    src = np.asarray(rgba, dtype=np.uint8)
    src = src[::-1] if flip else src
    h, w, c = src.shape
    if c != 4 or w % 8 or h % 8:
        raise ValueError('RGBA image with complete 8x8 tiles required')
    y, x = np.indices((h, w))
    addr = (y // 8 * (w // 8) + x // 8) * 64
    for bit in range(3):
        addr += ((x >> bit) & 1) << (2 * bit)
        addr += ((y >> bit) & 1) << (2 * bit + 1)
    out = np.empty((w*h, 4), np.uint8)
    out[addr] = src[..., ::-1]
    return out.tobytes()


TABLES = np.array([[2, 8], [5, 17], [9, 29], [13, 42],
                   [18, 60], [24, 80], [33, 106], [47, 183]])


def _half(pixels, weights):
    n = len(pixels)
    mean = ((pixels * weights[..., None]).sum(1) /
            np.maximum(weights.sum(1, keepdims=True), 1))
    mean4 = np.rint(mean / 17)
    grays = np.broadcast_to(np.arange(16)[None, :, None], (n, 16, 3))
    candidates = np.concatenate([grays, np.rint(pixels / 17),
                                mean4[:, None] - 1, mean4[:, None],
                                mean4[:, None] + 1], axis=1)
    candidates = np.clip(candidates, 0, 15).astype(np.uint8)
    best_err = np.full(n, np.inf)
    best_base = np.zeros((n, 3), np.uint8)
    best_table = np.zeros(n, np.uint8)
    best_sel = np.zeros((n, 8), np.uint8)
    for table, (small, large) in enumerate(TABLES):
        mods = np.array([small, large, -small, -large])
        colours = np.clip(candidates[:, :, None, :] * 17.0 +
                          mods[None, None, :, None], 0, 255)
        errors = ((pixels[:, None, :, None, :] -
                   colours[:, :, None, :, :]) ** 2).sum(-1)
        sels = errors.argmin(-1)
        err = (errors.min(-1) * weights[:, None, :]).sum(-1)
        ci = err.argmin(-1)
        pick = err[np.arange(n), ci]
        improved = pick < best_err
        best_err[improved] = pick[improved]
        best_base[improved] = candidates[np.arange(n), ci][improved]
        best_table[improved] = table
        best_sel[improved] = sels[np.arange(n), ci][improved]
    return best_err, best_base, best_table, best_sel


def _colour_blocks(rgba):
    # Exact black individual-mode block: negative modifier clips to zero.
    words = np.full(len(rgba), np.uint64(0xffff0000), dtype=np.uint64)
    active = np.flatnonzero(((rgba[:, :, :3] != 0) &
                            (rgba[:, :, 3:4] != 0)).any(axis=(1, 2)))
    for start in range(0, len(active), 64):
        ids = active[start:start+64]
        px = rgba[ids, :, :3].astype(np.float64)
        weights = rgba[ids, :, 3].astype(np.float64) / 255
        best_err = np.full(len(ids), np.inf)
        best_bits = np.zeros(len(ids), np.uint64)
        for flip in (0, 1):
            bits = np.full(len(ids), np.uint64(flip << 32), np.uint64)
            total = np.zeros(len(ids))
            for second in (0, 1):
                kk = np.array([k for k in range(16)
                               if int((k % 4 if flip else k // 4) >= 2) == second])
                err, base, table, selectors = _half(px[:, kk], weights[:, kk])
                total += err
                for channel, shift in enumerate((56, 48, 40)):
                    bits |= base[:, channel].astype(np.uint64) << np.uint64(shift + (0 if second else 4))
                bits |= table.astype(np.uint64) << np.uint64(34 if second else 37)
                for pos, k in enumerate(kk):
                    sel = selectors[:, pos].astype(np.uint64)
                    bits |= (sel & 1) << np.uint64(k)
                    bits |= (sel >> 1) << np.uint64(k + 16)
            improved = total < best_err
            best_err[improved] = total[improved]
            best_bits[improved] = bits[improved]
        words[ids] = best_bits
    return words


def etc1a4_encode(rgba, original=None, region=None):
    """Encode full texture or only 4x4 blocks intersecting display-space ROI.

    For a region edit, all other compressed bytes remain exactly original.
    Input outside the ROI should already be original decoded pixels.
    """
    src = np.asarray(rgba, dtype=np.uint8)
    h, w, c = src.shape
    if c != 4 or w % 8 or h % 8:
        raise ValueError('RGBA image with complete 8x8 tiles required')
    y, x = _idx(w, h)
    blocks = src[::-1][y, x].reshape(-1, 16, 4)
    if region is None:
        ids = np.arange(len(blocks))
        out = np.zeros((len(blocks), 16), np.uint8)
    else:
        if original is None or len(original) != w*h:
            raise ValueError('Original full payload required for region edit')
        rx, ry, rw, rh = region
        display_y = h - 1 - y
        mask = ((x >= rx) & (x < rx+rw) & (display_y >= ry) &
                (display_y < ry+rh)).reshape(-1, 16).any(1)
        ids = np.flatnonzero(mask)
        out = np.frombuffer(original, np.uint8).reshape(-1, 16).copy()
    selected = blocks[ids]
    alpha4 = (selected[:, :, 3].astype(np.uint16) * 15 + 127) // 255
    out[ids, :8] = (alpha4[:, 0::2] | (alpha4[:, 1::2] << 4)).astype(np.uint8)
    words = _colour_blocks(selected)
    out[ids, 8:] = words.astype('<u8').view(np.uint8).reshape(-1, 8)
    return out.tobytes(), ids
