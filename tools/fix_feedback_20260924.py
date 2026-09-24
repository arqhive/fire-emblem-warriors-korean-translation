# -*- coding: utf-8 -*-
"""2026-09-24 피드백 반영(UI·안내문). 캐릭터 대사는 건드리지 않는다.

  python tools/fix_feedback_20260924.py            # 대조표만 (reports/feedback_20260924_table.md)
  python tools/fix_feedback_20260924.py --apply    # 반영

1. 변수 뒤 받침 조사: 이름이 들어가는 자리 뒤에 받침에 따라 바뀌는 조사를 두지 않는다.
   를 → 뺀다 / 와 → 및·측과·병력과 / 로 → 방면으로·클래스로·모습으로 / 이·가·는 → 명사를 끼우거나 문장을 고친다.
2. 「강1」(強１) → 「강공격1」. 스킬 이름 「강１강화」 → 「강공격１ 강화」.
3. 줄 끝이 종결어미인데 문장부호가 없으면 마침표를 찍는다(중간 줄 포함). 「초대한 사람을 찾는다」는 버튼이라 「초대한 사람 찾기」.
4. 「캐릭터소개」 → 「캐릭터 소개」, 「캐릭터 소개：린다.」의 마침표를 뺀다.
5. 띄어쓰기: 「의」로 붙은 명사(평화의붕괴 등), 괄호 앞 붙음, 곳마다 달랐던 게임 용어(SPACING).
"""
import collections
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctrl
import tl

VARX = r"(%[0-9]*[a-zA-Z](?:\{[A-Za-z][0-9A-Za-z]?\})*['’」』\"]?)"
C = r"(?:\{[A-Za-z][0-9A-Za-z]?\})*"

RULES = [  # (이름, 정규식, 바꿀 것) — 위에서부터 차례로
    ('의상 추가', re.compile(VARX + r"이 추가되었습니다"), r"\1 의상이 추가되었습니다"),
    ('의상 추가', re.compile(r"(%2s" + C + r")\n가 추가되었습니다"), "\\1\n의상이 추가되었습니다"),
    ('항목 추가', re.compile(VARX + r"\n가 추가되었습니다"), "\\1\n항목이 추가되었습니다"),
    ('부활', re.compile(VARX + r"\n가 부활했습니다"), "\\1\n부활했습니다"),
    ('증원', re.compile(VARX + r"가 증원을 부르기 전에 격파하라!"), r"증원을 부르기 전에 \1 격파하라!"),
    ('훔친 골드', re.compile(VARX + r"가 훔친 "), r"\1에게서 "),
    ('약해짐', re.compile(VARX + r"가 약해질"), r"\1의 힘이 약해질"),
    ('정체', re.compile(r"격파한 (" + C + r"%[0-9]*[a-zA-Z]" + C + r")는 (진짜 )?(" + C + r"%[0-9]*[a-zA-Z]" + C + r")였던 것으로"),
     r"격파한 \1, 정체는 \2\3인 것으로"),
    ('진군', re.compile(VARX + r"로(\s)진군"), r"\1 방면으로\2진군"),
    ('클래스 체인지', re.compile(VARX + r"로 클래스 체인지"), r"\1 클래스로 체인지"),
    ('변신', re.compile(VARX + r"로 변신한"), r"\1의 모습으로 변신한"),
    ('병력과', re.compile(r"((?:모든|많은) " + C + VARX + r")와(\s)"), r"\1 병력과\3"),
    ('측과', re.compile(VARX + r"와(\s)(합류|교전|곧 합류)"), r"\1 측과\2\3"),
    ('및', re.compile(VARX + r"와 "), r"\1 및 "),
    ('를 빼기', re.compile(VARX + r"를 "), r"\1 "),
    ('를 빼기', re.compile(VARX + r"를(\n)"), r"\1\2"),
    ('를 빼기', re.compile(VARX + r"\n를 "), "\\1\n"),
]
# 5. 띄어쓰기 (캐릭터 대사 제외). 「의」로 붙은 명사, 괄호 앞, 곳마다 붙였다 띄었다 한 게임 용어.
#    용어집에 띄어 쓴 표기가 있으면 따르고, 없으면 표준 띄어쓰기로 맞춘다. 긴 것부터 바꾼다.
SPACING = [
    ('사룡의보석', '사룡의 보석'), ('평화의붕괴', '평화의 붕괴'), ('무쌍오의공격', '무쌍 오의 공격'),
    ('각성오의공격', '각성 오의 공격'), ('절망의어둠', '절망의 어둠'), ('승리의기쁨', '승리의 기쁨'),
    ('칠흑의검은암흑', '칠흑의 검은 암흑'), ('최후의싸움', '최후의 싸움'), ('이계의문지기', '이계의 문지기'),
    ('용의제단', '용의 제단'), ('백의혈족', '백의 혈족'),
    ('제한시간경과', '제한 시간 경과'), ('승리조건변경', '승리 조건 변경'), ('패배조건변경', '패배 조건 변경'),
    ('제한시간', '제한 시간'), ('승리조건', '승리 조건'), ('패배조건', '패배 조건'),
    ('퇴각지점', '퇴각 지점'), ('무쌍게이지', '무쌍 게이지'), ('각성게이지', '각성 게이지'),
    ('무쌍회복', '무쌍 회복'), ('각성회복', '각성 회복'), ('지시불가', '지시 불가'), ('메인메뉴', '메인 메뉴'),
    ('포박병장', '포박 병장'), ('거점병장', '거점 병장'), ('황금수송병', '황금 수송병'), ('이탈지원병', '이탈 지원병'),
    ('아군지휘관', '아군 지휘관'), ('지휘관출현', '지휘관 출현'), ('함락직전', '함락 직전'), ('함락위기', '함락 위기'),
    ('비행특효', '비행 특효'), ('중장특효', '중장 특효'), ('기마특효', '기마 특효'), ('진군개시', '진군 개시'),
    ('통행가능', '통행 가능'), ('일시이탈', '일시 이탈'), ('잠자리잡기', '잠자리 잡기'), ('서브미션', '서브 미션'),
    ('유리불리', '유리 불리'), ('백야왕국', '백야 왕국'), ('표시전환', '표시 전환'), ('유대대화', '유대 대화'),
    ('무기변경', '무기 변경'), ('조작설정', '조작 설정'), ('플레이스타일', '플레이 스타일'),
    ('클래스체인지', '클래스 체인지'), ('레이디소드', '레이디 소드'),
    ('액스파이터', '액스 파이터'), ('아머나이트', '아머 나이트'), ('드래곤나이트', '드래곤 나이트'), ('소셜나이트', '소셜 나이트'),
]
SPACING_RX = [(re.compile(r'(?<![가-힣])' + a), b) for a, b in SPACING]
BRACKET_RX = re.compile(r'([가-힣」』])(의|에)([「『])')


def fix_spacing(t):
    new = t
    for rx, b in SPACING_RX:
        new = rx.sub(b, new)
    new = BRACKET_RX.sub(r'\1\2 \3', new)
    new = new.replace('러플레?등장', '러플레? 등장')
    return new


PARTICLE = re.compile(VARX + r"(\s*)(이|가|을|를|은|는|과|와|으로|로)(?![가-힣])")

END = re.compile(r'(니다|[습입합됩갑봅]니까|세요|에요|예요|어요|아요|워요|해요|네요|군요|죠|지요|까요|나요|'
                 r'[았었였겠했한된진난온간린킨든른는있없같이]다)$')
CLOSE = '.!?…~」』"\')）】]〉》。！？．'
EXCLUDE_CAT = {'전투 음성', '맵 대사'}      # 캐릭터 대사 성격


def add_periods(t):
    parts = t.split('\n')
    for i, line in enumerate(parts):
        plain = ctrl.PH.sub('', line).rstrip()
        if len(plain) < 3 or plain[-1] in CLOSE or not END.search(plain):
            continue
        stripped = line.rstrip()
        parts[i] = stripped + '.' + line[len(stripped):]
    return '\n'.join(parts)


def convert(t):
    notes = []
    new = t
    for name, rx, rep in RULES:
        n2 = rx.sub(rep, new)
        if n2 != new:
            notes.append(name)
            new = n2
    if re.search(r'강\s?[0-9１-９]', new):
        n2 = re.sub(r'강([１-９])강화', r'강공격\1 강화', new)
        n2 = re.sub(r'강([0-9])(?=[은는이가을를의로에과와 ])', r'강공격\1', n2)
        if n2 != new:
            notes.append('강공격')
            new = n2
    if new.strip() == '초대한 사람을 찾는다':
        new = new.replace('초대한 사람을 찾는다', '초대한 사람 찾기')
        notes.append('버튼 이름')
    n2 = add_periods(new)
    if n2 != new:
        notes.append('마침표')
        new = n2
    n2 = fix_spacing(new)
    if n2 != new:
        notes.append('띄어쓰기')
        new = n2
    if new.startswith('캐릭터소개'):
        new = '캐릭터 소개' + new[len('캐릭터소개'):]
        notes.append('띄어쓰기')
    if new.startswith('캐릭터 소개') and new.endswith('.') and '\n' not in new:
        new = new[:-1]
        notes.append('마침표 삭제')
    return new, notes


def main():
    apply = '--apply' in sys.argv
    import pickle
    meta = pickle.load(open('extract/meta.pkl', 'rb'))
    ko = tl.load_ko()
    table = []
    for h, t in ko.items():
        m = meta.get(bytes.fromhex(h), {})
        if m.get('cat') in EXCLUDE_CAT:
            continue
        new, notes = convert(t)
        if new != t:
            table.append((notes, m.get('cat', '?'), ctrl.to_text(bytes.fromhex(h)), t, new))
            ko[h] = new
    left = [(ctrl.to_text(bytes.fromhex(h)), t) for h, t in ko.items()
            if meta.get(bytes.fromhex(h), {}).get('cat') not in EXCLUDE_CAT and PARTICLE.search(t)]
    if apply:
        tl.save_ko(ko)
    g = lambda s: s.replace('\n', ' ⏎ ').replace('|', '\\|')
    out = Path('reports/feedback_20260924_table.md')
    out.parent.mkdir(exist_ok=True)
    with out.open('w', encoding='utf-8') as f:
        f.write('# 2026-09-24 피드백 반영 대조표\n\n%d건. 캐릭터 대사(순차·DLC 대사, 전투 음성, 맵 대사)는 제외.\n\n' % len(table))
        f.write('| 구분 | 분류 | 원문 | 전 | 후 |\n|---|---|---|---|---|\n')
        for notes, cat, src, a, b in sorted(table, key=lambda r: (r[0][0], r[2])):
            f.write('| %s | %s | %s | %s | %s |\n' % ('·'.join(notes), cat, g(src), g(a), g(b)))
    print('%d건%s  (대조표 %s)' % (len(table), ' 반영' if apply else ' 미반영', out))
    print('구분별', dict(collections.Counter(n for notes, *_ in table for n in notes).most_common()))
    print('변수 뒤 받침 조사가 남은 것 %d건' % len(left))
    for s, t in left:
        print('   ', g(t))


if __name__ == '__main__':
    main()
