"""3DS ETC1A4 알파 추출 (폰트/마스크용). Y축은 아래에서 위로 저장됨."""
import numpy as np
_cache={}

def morton8_abgr32_rgba(data, W, H, flip=True):
    """Decode the 3DS G1T format-9 level-0 ABGR bytes for source inspection.

    Platform-5 format 9 is swizzled 32-bit colour (gust_g1t.c). 3DS stores
    pixels in 8x8 Morton tiles, with rows displayed bottom to top.
    """
    if W < 8 or H < 8 or W % 8 or H % 8 or len(data) < W*H*4:
        raise ValueError('Requires complete 8x8 tiles and level-0 ABGR data')
    y, x = np.indices((H, W))
    addresses = (y//8*(W//8)+x//8)*64
    for bit in range(3):
        addresses += ((x >> bit) & 1) << (2*bit)
        addresses += ((y >> bit) & 1) << (2*bit+1)
    pixels = np.frombuffer(data[:W*H*4], dtype=np.uint8).reshape(-1, 4)
    out = pixels[addresses, ::-1]
    return out[::-1] if flip else out

def _idx(W,H):
    k=(W,H)
    if k in _cache: return _cache[k]
    tw,th=W//8,H//8
    ty,tx=np.divmod(np.arange(tw*th),tw)
    sub=np.array([(0,0),(4,0),(0,4),(4,4)])
    kk=np.arange(16); sx=kk//4; sy=kk%4
    X=(tx[:,None,None]*8 + sub[None,:,0,None] + sx[None,None,:])
    Y=(ty[:,None,None]*8 + sub[None,:,1,None] + sy[None,None,:])
    _cache[k]=(Y.ravel(),X.ravel())
    return _cache[k]

def etc1a4_alpha(data, W, H, flip=True):
    n=(W*H)//16
    b=np.frombuffer(data[:n*16],dtype=np.uint8).reshape(n,16)[:,:8]
    lo=(b&0xF); hi=(b>>4)
    nib=np.empty((n,16),np.uint8); nib[:,0::2]=lo; nib[:,1::2]=hi
    Y,X=_idx(W,H)
    img=np.zeros((H,W),np.uint8)
    img[Y,X]=nib.ravel()*17
    return img[::-1] if flip else img

def etc1a4_rgba(data, W, H, flip=True):
    """Decode level 0 for source inspection; never modifies compressed data.

    ETC1 bit layout reference: azahar-emu/azahar,
    src/video_core/texture/etc1.cpp. Existing _idx supplies 3DS tile order.
    """
    if W < 8 or H < 8 or W % 8 or H % 8 or len(data) < W * H:
        raise ValueError('ETC1A4 requires complete 8x8 tiles and level-0 data')
    blocks = np.frombuffer(data[:W*H], dtype='<u8').reshape(-1, 2)
    bits = blocks[:, 1]
    flipbit = ((bits >> 32) & 1).astype(bool)
    diff = ((bits >> 33) & 1).astype(bool)
    tables = np.array([[2,8],[5,17],[9,29],[13,42],
                       [18,60],[24,80],[33,106],[47,183]], dtype=np.int16)
    rgb = np.empty((len(bits), 16, 3), dtype=np.uint8)
    for k in range(16):
        x, y = divmod(k, 4)
        second = np.where(flipbit, y >= 2, x >= 2)
        table = np.where(second, (bits >> 34) & 7, (bits >> 37) & 7).astype(int)
        selector = ((bits >> k) & 1).astype(int)
        sign = np.where(((bits >> (k+16)) & 1) != 0, -1, 1)
        modifier = tables[table, selector] * sign
        for channel, shift in enumerate((56, 48, 40)):
            base5 = ((bits >> (shift+3)) & 31).astype(np.int16)
            delta = ((bits >> shift) & 7).astype(np.int16)
            delta = np.where(delta >= 4, delta-8, delta)
            val5 = base5 + np.where(second, delta, 0)
            val5 = (val5 << 3) | (val5 >> 2)
            val4 = np.where(second, (bits >> shift) & 15,
                            (bits >> (shift+4)) & 15).astype(np.int16) * 17
            rgb[:, k, channel] = np.clip(np.where(diff, val5, val4)+modifier, 0, 255)
    Y, X = _idx(W, H)
    out = np.zeros((H, W, 4), dtype=np.uint8)
    out[Y, X, :3] = rgb.reshape(-1, 3)
    out[:, :, 3] = etc1a4_alpha(data, W, H, flip=False)
    return out[::-1] if flip else out

def etc1a4_write(data, W, H, img, flip=True):
    """img(표시 방향, uint8 0~255)의 알파를 ETC1A4 데이터에 써넣는다. ETC1 색부분은 유지."""
    src = img[::-1] if flip else img
    n=(W*H)//16
    out=bytearray(data[:n*16])
    Y,X=_idx(W,H)
    vals=(src[Y,X].astype(np.uint16)*15+127)//255       # 0~15
    v=vals.reshape(n,16)
    lo=v[:,0::2].astype(np.uint8); hi=v[:,1::2].astype(np.uint8)
    packed=(lo|(hi<<4)).astype(np.uint8)
    buf=np.frombuffer(bytes(out),dtype=np.uint8).reshape(n,16).copy()
    buf[:,:8]=packed
    return buf.tobytes()
