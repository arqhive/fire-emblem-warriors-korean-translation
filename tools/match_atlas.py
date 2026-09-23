"""아틀라스 셀 <-> SJIS 문자 대응을 단조성 제약 DP 로 확정"""
import numpy as np, sys
from PIL import Image, ImageDraw, ImageFont

def sjis_codes():
    out=[]
    for lead in list(range(0x81,0xA0))+list(range(0xE0,0xF0)):
        for trail in range(0x40,0xFD):
            if trail==0x7F: continue
            b=bytes([lead,trail])
            try: c=b.decode('cp932')
            except Exception: continue
            out.append((b,c))
    return out

def render(chars, size=16, font='C:/Windows/Fonts/msgothic.ttc'):
    f=ImageFont.truetype(font, size)
    arr=np.zeros((len(chars),size,size),np.float32)
    for i,c in enumerate(chars):
        im=Image.new('L',(size,size),0)
        ImageDraw.Draw(im).text((size//2,size//2), c, font=f, fill=255, anchor='mm')
        arr[i]=np.asarray(im,np.float32)
    return arr

def norm(a):
    v=a.reshape(len(a),-1)
    v=v-v.mean(1,keepdims=True)
    n=np.linalg.norm(v,axis=1,keepdims=True); n[n==0]=1
    return v/n

def align(score):
    """score[i,j] = 셀 i <-> 코드 j 유사도. j 가 강증가하도록 최대합 정렬 (벡터화 DP)"""
    C,K=score.shape
    idx=np.arange(K)
    prev=score[0].astype(np.float32)
    bk=np.zeros((C,K),np.int16)
    for i in range(1,C):
        m=np.maximum.accumulate(prev)
        arg=np.maximum.accumulate(np.where(prev>=m, idx, -1)).astype(np.int16)
        cur=np.full(K,-1e9,np.float32)
        cur[1:]=m[:-1]+score[i,1:]
        bk[i,1:]=arg[:-1]
        prev=cur
    path=np.zeros(C,np.int32); path[-1]=int(np.argmax(prev))
    for i in range(C-1,0,-1): path[i-1]=bk[i,path[i]]
    return path
