# 파이어 엠블렘 무쌍 (3DS) 한글 패치

*Fire Emblem Warriors* (닌텐도 3DS, 일본판 `KTR-P-CFMJ` / `000400000F70C100`) 비공식 한국어 팬 패치입니다.
대사는 일본어판 원문을 기준으로 번역했습니다.

**제작: arqhive** · **최신 버전: [v0.2](../../releases/tag/v0.2)**

- 메뉴, 무기·특성 설명, 전투 로그, 미션 조건, 히스토리 모드, 용어·인명 등 캐시 원문 13,328개를 번역했습니다.
- 본편과 업데이트의 순차 대사 9,950참조, 추가 콘텐츠(DLC)의 순차 대사 3,014참조를 번역했습니다.
- 훈장 이름과 조건 88종(176참조)을 번역했습니다. UTF-16으로 따로 저장되는 자료입니다.
- 본문 폰트에 한글을 넣되 일본어 글리프는 그대로 두었습니다. 작은 ARM 훅으로 비어 있는 아틀라스 칸을 쓰며, 한글 최대 1,880자가 들어갑니다(Pretendard 기반).
- 제작사 로고, 주의 안내문, 타이틀 로고, 크레딧 저작권 등 그림 글씨 7종과 HOME 메뉴 배너·게임 이름을 한글화했습니다.
- 텍스트 블록의 참조 구조를 해독해 문자열 영역을 통째로 다시 깝니다. 번역문 길이가 원문 바이트에 묶이지 않습니다.
- 본인이 가진 일본판 CIA로 한글판 CIA를 만드는 패처를 배포합니다.

> 이 저장소에는 **게임 데이터(롬·디스크 이미지, 추출한 원문 대사, 그래픽, 스크린샷)가 들어 있지 않습니다.**
> 패치를 만들거나 적용하려면 본인이 소유한 게임에서 직접 덤프한 원본이 필요합니다.

## 사용자용: 패치 적용

이 게임은 **LayeredFS(Luma3DS 게임 패치)로 적용할 수 없습니다.** 업데이트를 설치한 상태에서 romfs를
덮으면 타이틀 화면에서 반드시 멈춥니다. 본편과 업데이트가 같은 이름(`LINKDATA.bin`)의 서로 다른
파일을 쓰는데, LayeredFS는 본편 폴더의 파일을 두 곳에 모두 덮어씌우기 때문입니다. 원본 파일을
그대로 얹어도 같은 증상이며, 확인 과정은 [`docs/TECHNICAL.md`](docs/TECHNICAL.md)에 적어 두었습니다.
그래서 CIA를 다시 만들어 설치합니다.

### 준비물

- 일본판 CIA. 본편(`000400000F70C100`), 업데이트 v6.9.0(`0004000E0F70C100`), 추가 콘텐츠(`0004008C0F70C100`) 중 가진 것.
  북미판·유럽판(Fire Emblem Warriors)에는 적용할 수 없습니다. New 3DS 계열 전용 소프트입니다.
- CIA를 설치할 수 있는 CFW 3DS(FBI 등).
- 복호화용 `boot9.bin`, `seeddb.bin`. 본편이 seed 암호화라 둘 다 필요합니다.
  패치 폴더나 Azahar·Citra의 `sysdata` 폴더에 있으면 자동으로 찾습니다. 이미 복호화된 CIA에는 필요 없습니다.
- 임시 디스크 공간 약 10GB(본편 기준). 작업 폴더는 패치 폴더 안의 `work`이고 끝나면 지웁니다.

### 적용 방법

1. [배포 페이지](../../releases/latest)에서 `FEWarriors_KO_v0.2_Patcher.zip`을 받아 폴더째 풉니다.
2. 일본판 CIA를 `패치하기.bat`에 끌어다 놓습니다. 여러 개를 한 번에 놓아도 되고,
   타이틀 ID를 보고 본편·업데이트·DLC를 알아서 구분합니다.
3. 원본과 같은 폴더에 `<원래 이름>_KO.cia`가 생깁니다. 원본 파일은 바뀌지 않습니다.
4. 만들어진 CIA를 3DS에 설치합니다. 한글 패치를 다시 설치할 때는 먼저 지우는 쪽이 안전합니다.
   세이브 데이터는 타이틀과 별도라 남습니다.

업데이트와 DLC를 쓰지 않는다면 본편만 만들어 설치해도 됩니다. 다만 업데이트를 설치한 상태라면
**업데이트도 반드시 한글판으로 바꿔야 합니다.** 실제로 실행되는 프로그램이 업데이트 쪽이기 때문입니다.

자세한 방법은 [`README_한국어.txt`](release/README_한국어.txt)를 참고하세요.

### 파일 확인값

패처가 만드는 CIA는 설치 티켓에 무작위 키가 들어가 파일 전체 해시가 매번 달라집니다.
그래서 패치가 바꾸는 아카이브의 값을 적습니다. 패처는 원본과 결과를 이 값으로 스스로 검사합니다.

| 항목 | 원본 본편 | 한글 본편 (v0.2) | 원본 업데이트 | 한글 업데이트 (v0.2) |
|---|---|---|---|---|
| 크기 | 1,392,747,100 바이트 | 1,397,029,264 바이트 | 111,236,698 바이트 | 115,879,796 바이트 |
| CRC32 | `D7F0AD48` | `42BF6F7B` | `D1479A11` | `03F42CE3` |
| MD5 | `fab421456583c8243a012ed62522e681` | `fa5f9bf6159b791cfea2bcb7efd4f43a` | `bdf1b153bc42f28e4d253fbadd8e9bcf` | `d1c5dcfb06810a2643866d3c9fac0c9e` |
| SHA-1 | `7797fa6d5f08aa2d0f21e8e622f0ba2b4af492bd` | `0e60bf97ff2e9a83c07f9d1eff3946ea2a0984fe` | `2401688fd150d550409aace9be6110b94f12fa57` | `25747b7d6b2ceebec3ed253c736e3817f166f485` |

원본 파일 위치: 각 타이틀 romfs의 `LINKDATA.bin`.

### 실행 환경

- **확인함**: New 3DS(Luma3DS) 실기에 한글판 CIA를 설치.

### 알려진 문제

- LayeredFS로는 적용할 수 없습니다. 위에 적은 대로 CIA를 다시 만들어야 합니다.
- 전투 알림(GAME OVER, STAGE CLEAR 등)과 일본어 DLC 배너 일부는 원본을 그대로 둡니다.
- 반각·혼합 인코딩 문자열 224종은 어느 언어 분기인지 판단이 남아 있습니다.

## 개발자용: 직접 빌드

### 요구 사항

- Python 3.10 이상과 [`requirements.txt`](requirements.txt)의 패키지(pyctr, Pillow, NumPy, keystone-engine, unicorn).
- 일본판 CIA 세 개와 복호화용 `boot9.bin`, `seeddb.bin`.
- `3dstool`, `makerom`, `xdelta3`를 `tools/bin`에 둡니다.
- 폰트: [Pretendard](https://github.com/orioncactus/pretendard) → `tools/fonts/PretendardVariable.ttf`.
- 본인 게임에서 뽑은 `extract/`. 원본 아카이브(`base`, `update`, `dlc`), 복호화한 `.code`(`exefs/`),
  문자열 위치 캐시(`meta.pkl`, `locs.pkl`), 순차 대사 목록(`dialogue_v2/blocks.json`),
  글리프 아틀라스 대응표(`font/atlas_map_true.json`)가 들어갑니다. 위치 캐시와 대사 목록은
  `audit_extraction_v2.py` → `restore_extraction_locations.py`, `extract_dialogue_records.py`로,
  대응표는 `match_atlas.py`로 만들었습니다.
- 그림 글씨와 HOME 배너·아이콘의 승인본(`translation/graphics/`, `translation/home_menu/`,
  `reports/graphics_review/home_menu/`)은 게임 그래픽을 바탕으로 그린 것이라 저장소에 넣지 않았습니다.

### 빌드

```bash
python tools/build_all.py                                            # 번역 → 한글판 CIA 세 개 → 배포 차분
python tools/make_patcher.py --python <임베디드 파이썬 zip 또는 폴더>   # release/patcher 의 lib·bin, release/python
python tools/make_release.py v0.2                                    # release/FEWarriors_KO_v0.2_Patcher.zip
```

`build_all.py`는 아래 순서를 한 번에 돌립니다.

```bash
python tools/build_verified.py work/builds/out                       # 텍스트·대사·폰트·코드 훅
python tools/apply_graphics.py work/builds/out                       # 승인된 그림 글씨
python tools/apply_medals.py  work/builds/out                        # UTF-16 훈장
python tools/verify_patch.py  work/builds/out                        # 되읽어 대조
python tools/patch_dlc.py     work/builds/out work/builds/out_dlc    # DLC 대사
python tools/build_cia.py --tag base --cia "본편.cia" --out "1차.cia" --romfs-from work/builds/out/base/romfs
python tools/build_cia.py --tag base --cia "1차.cia"  --out "한글본편.cia" --code --no-home
python tools/build_dlc_cia.py --cia "DLC.cia" --out "한글DLC.cia"
python tools/make_payload.py                                         # 원본·한글 CIA 차분 → release/patcher/payload
```

빌드는 쓴 문자열을 모두 다시 파싱해 대조하고, 제어코드와 포맷 지정자가 보존됐는지 검사하며,
반영하지 못한 항목을 `build_report.json`에 남깁니다. 같은 입력이면 `LINKDATA`가 바이트 단위로 같게 나옵니다.
패처로 원본 CIA를 패치한 결과는 빌드 도구로 만든 한글판과 콘텐츠 단위로 같습니다(티켓의 무작위 키만 다름).

### 번역 수정

- 번역 파일에는 일본어 원문을 넣지 않았습니다. 도구는 [`tools/tl.py`](tools/tl.py)로 읽으며, 원문은 `extract/`에서 채웁니다.
  - [`translation/ko.json`](translation/ko.json): 캐시 원문. 키는 원문 CP932 바이트의 SHA-1 앞 12자리, 값은 번역문입니다.
  - [`translation/dialogue_ko.json`](translation/dialogue_ko.json): 본편·업데이트 순차 대사. `tag`·`path`·`index`로 위치를 가리킵니다.
  - `translation/dlc_dialogue_ko.json`은 DLC 순차 대사, `utf16_medals_ko.json`은 훈장입니다. 형식이 달라 서로 합산하지 않습니다.
- `python tools/tl.py find <문구>`로 원문과 번역문을 함께 찾습니다. 고친 뒤 `tl.save_*()`로 저장하면 원문은 다시 걷힙니다.
- 인명·고유명사는 [`translation/glossary.json`](translation/glossary.json)의 확정 표기를 우선합니다. 이미 확정한 이름은 임의로 바꾸지 않습니다.
- 문체 규칙은 [`docs/STYLE_GUIDE.md`](docs/STYLE_GUIDE.md)에 있고, `audit_periods.py`·`audit_style.py`로 마침표 누락과 문체 위반 후보를 훑습니다.
- 제어코드는 `{A6}`, `{PY}`, `{R}` 같은 플레이스홀더로 다룹니다. 지우면 화면에서 버튼 아이콘이나 색 강조가 사라집니다.
- 글리프 아틀라스는 본편 폰트 한 벌뿐입니다. DLC와 훈장에만 나오는 음절도 함께 배정해야 그쪽 화면에서 빈칸이 되지 않습니다.

### 폴더 구조

```
release/       배포 폴더: 패치하기.bat, 설명서, patcher/patch.py (lib·bin·payload·python 은 빌드 때 채움)
translation/   번역문(원문 없음)과 용어집
tools/         추출, LINKDATA·XL·G1T 읽기·쓰기, 폰트·그래픽 빌드, CIA 재빌드, 패처, 검증 도구
docs/          기술 문서, 문체 규칙, QA 체크리스트, 릴리즈 노트 사본(docs/releases/)
extract/, work/, reports/   원본 추출물, 빌드 산출물, 검수 기록 (원문이 들어 있어 저장소에는 없음)
```

### 기술 문서

LINKDATA·XL 텍스트 블록·순차 대사·G1T 텍스처·폰트 아틀라스·HOME 배너(CBMD) 형식, LayeredFS가
안 되는 이유와 CIA 재빌드·패처 절차는 [`docs/TECHNICAL.md`](docs/TECHNICAL.md)에 정리했습니다.
설치 후 확인할 항목은 [`docs/QA_CHECKLIST.md`](docs/QA_CHECKLIST.md)에 있습니다.

## 변경 내역

전체 내역은 [`CHANGELOG.md`](CHANGELOG.md)에 있습니다.

## 크레딧·라이선스

- 이 저장소의 도구 코드, 한국어 번역문, 문서: [MIT License](LICENSE) (© 2026 arqhive).
- 한글 글리프는 [Pretendard](https://github.com/orioncactus/pretendard)(SIL Open Font License 1.1)로 그렸습니다.

## 면책

비공식 팬 번역이며 Nintendo와 관련이 없습니다. 「파이어 엠블렘 무쌍」 관련 상표·저작권은 Nintendo에 있습니다.
패치를 적용한 게임 파일의 배포를 금지합니다.
