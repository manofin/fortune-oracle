"""Platform-neutral Tarot and I Ching draws, with replayable evidence.

Deck: Rider–Waite–Smith numbering (Strength VIII, Justice XI), 78 cards.
Hexagrams: King Wen order; three fair coins, 2/3 per coin, bottom line first.
Sources describe the structure, not these original modern reflection prompts:
https://sacred-texts.com/tarot/pkt/index.htm
https://sacred-texts.com/ich/ictoc.htm
https://uaya.org/learn/iching/using-the-oracle/casting-techniques/three-coins/casting-and-building/
No network, LLM, profile access, question storage or event logging.
"""
from __future__ import annotations

from random import SystemRandom
from typing import Sequence

class ReadingInputError(ValueError):
    """Safe, user-facing validation errors (never backend exception messages)."""


DISCLAIMER = '오락과 자기성찰용 해석입니다. 결과가 미래를 확정하지 않습니다.'
TAROT_SOURCE = 'https://sacred-texts.com/tarot/pkt/index.htm'
ICHING_SOURCE = 'https://sacred-texts.com/ich/ictoc.htm'

# Name, constructive focus, tension to reflect on. Original Korean commentary.
_MAJOR = (
    ('바보', '작게 시작하며 경험을 모으기', '준비 없이 뛰어들려는 충동'),
    ('마법사', '이미 가진 기술과 자원을 활용하기', '계획만 세우고 실행을 미루는 습관'),
    ('여사제', '조용히 관찰하고 내 기준을 듣기', '확인하지 않은 추측을 사실로 믿는 태도'),
    ('여황제', '자신과 주변을 돌보며 성장시키기', '돌봄을 혼자 떠맡는 부담'),
    ('황제', '역할과 경계를 분명히 정하기', '지나치게 통제하려는 태도'),
    ('교황', '배운 원칙과 조언을 점검하기', '관례를 무조건 따르는 태도'),
    ('연인', '중요한 가치와 선택을 맞추기', '타인의 기대 때문에 선택을 미루는 마음'),
    ('전차', '하나의 목표에 노력을 모으기', '속도를 내느라 놓치는 신호'),
    ('힘', '침착함과 인내로 상황을 다루기', '감정을 억누르거나 힘으로 밀어붙이는 태도'),
    ('은둔자', '혼자 생각할 시간과 기준 마련하기', '도움이 필요한데도 고립되는 습관'),
    ('운명의 수레바퀴', '변화에 맞춰 계획을 조정하기', '통제 밖의 일을 모두 책임지려는 마음'),
    ('정의', '근거와 책임을 공정하게 살피기', '자신에게 유리한 정보만 고르는 태도'),
    ('매달린 사람', '잠시 멈춰 다른 관점을 보기', '희생을 당연하게 받아들이는 습관'),
    ('죽음', '끝난 역할을 정리하고 새 여지를 만들기', '이미 끝난 방식에 매달리는 마음'),
    ('절제', '서로 다른 필요 사이의 균형 찾기', '회복 없이 계속 무리하는 습관'),
    ('악마', '습관과 의존을 알아차리고 선택권 찾기', '불편함을 피하려 반복하는 의존'),
    ('탑', '흔들린 전제를 점검하고 다시 세우기', '변화를 피하려 경고 신호를 무시하는 태도'),
    ('별', '회복 가능한 작은 희망을 지키기', '희망만으로 행동을 대신하는 습관'),
    ('달', '불확실한 정보와 감정을 구분하기', '불안을 사실처럼 받아들이는 마음'),
    ('태양', '명확한 목표와 성과를 나누기', '밝은 면만 보며 문제를 놓치는 태도'),
    ('심판', '경험을 돌아보고 다음 선택을 정하기', '과거의 잘못으로 자신을 규정하는 마음'),
    ('세계', '마무리한 경험을 연결하고 인정하기', '완벽한 끝을 기다리며 마무리를 미루는 습관'),
)
_SUITS = (('완드', '의욕과 실행'), ('컵', '감정과 관계'), ('소드', '생각과 소통'), ('펜타클', '생활과 자원'))
_RANKS = (
    ('에이스', '새 시도를 하나 정하기', '시작을 미루기'),
    ('2', '두 선택의 차이를 살피기', '결정을 피하기'),
    ('3', '협력하고 피드백을 받기', '의견을 혼자 짐작하기'),
    ('4', '기반을 안정시키고 쉬기', '익숙함에 갇히기'),
    ('5', '갈등과 부족한 부분을 인정하기', '비교 때문에 소진되기'),
    ('6', '도움을 주고받으며 회복하기', '받거나 주는 역할에만 머무르기'),
    ('7', '내 기준을 지키며 점검하기', '확인 없이 방어하기'),
    ('8', '반복과 집중으로 조정하기', '속도만으로 문제를 해결하려 하기'),
    ('9', '쌓인 경험과 한계를 살피기', '혼자 버텨야 한다고 믿기'),
    ('10', '완료와 다음 단계의 부담 나누기', '모든 책임을 떠맡기'),
    ('페이지', '배우고 질문하는 자세 갖기', '아직 모르는 것을 숨기기'),
    ('나이트', '방향을 정해 움직이기', '성급하게 추진하기'),
    ('퀸', '세심하게 돌보고 조율하기', '내 필요를 뒤로 미루기'),
    ('킹', '경험을 책임 있게 활용하기', '내 방식만 옳다고 고집하기'),
)
TAROT_DECK = tuple(_MAJOR) + tuple(
    (f'{suit} {rank}', f'{area}: {focus}', f'{area}: {tension}')
    for suit, area in _SUITS for rank, focus, tension in _RANKS
)
POSITIONS = ('현재 상황', '살펴볼 과제', '다음 작은 행동')


def _question(question: str) -> None:
    if not isinstance(question, str) or not question.strip() or len(question) > 500:
        raise ReadingInputError('질문을 1~500자로 입력해 주세요.')


def build_tarot_reading(question: str, *, draws=None, rng=None) -> dict:
    """Draw three distinct cards; explicit (deck index, reversed) pairs replay a reading."""
    _question(question)
    if draws is None:
        random = rng if rng is not None else SystemRandom()
        draws = [(i, bool(random.getrandbits(1))) for i in random.sample(range(78), 3)]
        method = '78장 비복원 추첨, 정·역방향 각각 1/2'
    else:
        method = '사용자가 지정한 카드·방향 재현'
    if (not isinstance(draws, (list, tuple)) or len(draws) != 3
            or any(not isinstance(d, (list, tuple)) or len(d) != 2 for d in draws)):
        raise ReadingInputError('서로 다른 카드 3장과 정·역방향을 지정해 주세요.')
    if any(type(i) is not int or not 0 <= i < 78 or type(rev) is not bool for i, rev in draws):
        raise ReadingInputError('카드 번호는 0~77, 역방향 값은 bool이어야 합니다.')
    if len({i for i, _ in draws}) != 3:
        raise ReadingInputError('같은 카드를 중복 선택할 수 없습니다.')
    cards, lines = [], ['타로 · 3장 펼치기']
    for position, (index, reverse) in zip(POSITIONS, draws):
        name, focus, tension = TAROT_DECK[index]
        meaning = f'주의할 패턴: {tension}. 다시 시도할 방향: {focus}.' if reverse else f'{focus}. 점검할 부분: {tension}.'
        cards.append({'id': index, 'name': name, 'reversed': reverse, 'position': position, 'interpretation': meaning})
        lines.extend([f'{position} — {name} ({"역방향" if reverse else "정방향"})', meaning])
    lines.extend(['질문에 비추어 오늘 직접 확인할 수 있는 행동 하나를 골라 보세요.',
                  '근거: ' + method + '. 카드별 현대적 성찰 해석이며 고전 원문 번역이 아닙니다.', DISCLAIMER])
    return {'ok': True, 'kind': 'tarot', 'cards': cards,
            'evidence': {'method': method, 'deck': 'Rider–Waite–Smith 78', 'source': TAROT_SOURCE},
            'text': '\n'.join(lines)}


# Lower trigram rows, upper trigram columns; bits run bottom to top.
_TRIGRAM_BITS = (7, 3, 5, 1, 6, 2, 4, 0)  # 乾兌離震巽坎艮坤
_KING_WEN = (
    (1,43,14,34,9,5,26,11), (10,58,38,54,61,60,41,19),
    (13,49,30,55,37,63,22,36), (25,17,21,51,42,3,27,24),
    (44,28,50,32,57,48,18,46), (6,47,64,40,59,29,4,7),
    (33,31,56,62,53,39,52,15), (12,45,35,16,20,8,23,2),
)
# Traditional names, original modern reflection themes (not oracle probability).
_HEXAGRAMS = (
    ('乾 건','주도적으로 시작하되 힘을 꾸준히 쓰기'), ('坤 곤','받아들이고 협력할 기반 만들기'),
    ('屯 둔','시작의 혼란 속에서 작은 순서 정하기'), ('蒙 몽','모르는 것을 인정하고 배우기'),
    ('需 수','준비를 갖추며 때를 기다리기'), ('訟 송','갈등을 키우기 전에 주장과 근거 나누기'),
    ('師 사','공동 목표와 책임을 분명히 하기'), ('比 비','누구와 어떤 기준으로 함께할지 살피기'),
    ('小畜 소축','작게 모으며 성급한 확장을 늦추기'), ('履 리','상대의 경계와 절차를 존중하기'),
    ('泰 태','열린 소통을 유지하며 균형 지키기'), ('否 비','막힌 흐름에서 지킬 기준 정하기'),
    ('同人 동인','공통 목적을 찾아 협력하기'), ('大有 대유','가진 자원을 책임 있게 나누기'),
    ('謙 겸','성과를 과시하기보다 배울 여지 남기기'), ('豫 예','준비와 동기를 구체적 행동으로 바꾸기'),
    ('隨 수','상황을 따르되 내 기준 잃지 않기'), ('蠱 고','쌓인 문제의 원인을 정리하기'),
    ('臨 림','가까이 다가가되 상대의 속도 존중하기'), ('觀 관','즉시 판단하기보다 관찰하기'),
    ('噬嗑 서합','걸림돌을 분명한 절차로 다루기'), ('賁 비','겉모습과 실제 내용을 함께 살피기'),
    ('剝 박','약해진 기반을 더 소진시키지 않기'), ('復 복','기본으로 돌아가 작은 회복 시작하기'),
    ('無妄 무망','억지 기대 대신 확인 가능한 행동 고르기'), ('大畜 대축','쌓인 힘을 배우고 다듬기'),
    ('頤 이','무엇을 받아들이고 내보내는지 살피기'), ('大過 대과','과한 부담을 줄이고 역할 나누기'),
    ('坎 감','반복되는 어려움에서 안전한 순서 찾기'), ('離 리','명확한 기준과 필요한 연결 지키기'),
    ('咸 함','상대에게 미치는 영향을 세심하게 듣기'), ('恆 항','지속 가능한 습관 유지하기'),
    ('遯 둔','불필요한 경쟁에서 한 걸음 물러서기'), ('大壯 대장','힘이 있을 때 절제와 책임 더하기'),
    ('晉 진','진전을 확인하며 협력 넓히기'), ('明夷 명이','여건이 어려울 때 내 기준 보호하기'),
    ('家人 가인','가까운 관계의 역할과 약속 정하기'), ('睽 규','다른 관점을 인정하고 공통점 찾기'),
    ('蹇 건','막힌 길에서 도움과 우회로 찾기'), ('解 해','긴장을 풀고 남은 문제 정리하기'),
    ('損 손','덜어낼 것을 골라 중요한 것 지키기'), ('益 익','도움이 되는 자원을 함께 늘리기'),
    ('夬 쾌','결정할 일을 분명히 하되 과격함 피하기'), ('姤 구','새 만남을 반기되 경계 살피기'),
    ('萃 췌','모인 사람들의 목적과 역할 맞추기'), ('升 승','작은 진전을 꾸준히 쌓기'),
    ('困 곤','제약 속에서 남은 힘 아끼기'), ('井 정','모두에게 필요한 기반 돌보기'),
    ('革 혁','변화의 이유와 동의를 확인하기'), ('鼎 정','새 방식에 맞게 자원 재구성하기'),
    ('震 진','놀란 뒤 중심과 순서 되찾기'), ('艮 간','멈출 지점을 알아차리고 쉬기'),
    ('漸 점','속도보다 단계와 안정성 살피기'), ('歸妹 귀매','관계의 순서와 기대 조율하기'),
    ('豐 풍','풍요로운 때에도 과부하 점검하기'), ('旅 려','낯선 환경에서 작고 유연하게 움직이기'),
    ('巽 손','부드럽고 꾸준하게 의견 전달하기'), ('兌 태','즐거움과 솔직한 소통 나누기'),
    ('渙 환','흩어진 관심을 공동 목적에 모으기'), ('節 절','지킬 수 있는 한계와 규칙 정하기'),
    ('中孚 중부','말과 행동의 일치로 신뢰 쌓기'), ('小過 소과','큰 도약보다 작은 조정에 집중하기'),
    ('既濟 기제','완료 뒤에도 유지와 점검 이어가기'), ('未濟 미제','미완료를 인정하고 다음 순서 정하기'),
)


def hexagram_number(lines: Sequence[int]) -> int:
    """Lines are bottom first: 6/8 yin, 7/9 yang."""
    if (not isinstance(lines, (tuple, list)) or len(lines) != 6
            or any(type(v) is not int or v not in (6,7,8,9) for v in lines)):
        raise ReadingInputError('아래에서 위 순서로 6·7·8·9 중 여섯 값을 입력해 주세요.')
    lower = sum((v % 2) << i for i,v in enumerate(lines[:3]))
    upper = sum((v % 2) << i for i,v in enumerate(lines[3:]))
    return _KING_WEN[_TRIGRAM_BITS.index(lower)][_TRIGRAM_BITS.index(upper)]


def build_iching_reading(question: str, *, lines=None, rng=None) -> dict:
    """Three independent fair coins per line (totals 6/7/8/9), or replay user lines."""
    _question(question)
    coins = None
    if lines is None:
        random = rng if rng is not None else SystemRandom()
        coins = [[random.choice((2,3)) for _ in range(3)] for _ in range(6)]
        lines = [sum(row) for row in coins]
        method = '3동전법 · 각 동전 2/3 동일 확률 · 초효부터 상효까지 6회'
    else:
        method = '사용자 효값 재현 · 아래에서 위 순서'
    number = hexagram_number(lines)
    changed = [i+1 for i,v in enumerate(lines) if v in (6,9)]
    transformed = [7 if v == 6 else 8 if v == 9 else v for v in lines]
    next_number = hexagram_number(transformed)
    name, theme = _HEXAGRAMS[number-1]
    next_name, next_theme = _HEXAGRAMS[next_number-1]
    text = [f'주역 · 본괘 {number} {name}', f'성찰 주제: {theme}.']
    for i in range(5,-1,-1):
        text.append(f'{i+1}효  {"━━━━━━" if lines[i] % 2 else "━━  ━━"}  {lines[i]}'
                    + (' · 변화' if i+1 in changed else ''))
    if changed:
        text.extend([f'변효: {", ".join(map(str,changed))}효 · 지괘 {next_number} {next_name}',
                     f'변화를 생각할 관점: {next_theme}.',
                     '변효 위치를 표시한 현대적 성찰 해석입니다. 고전 효사를 계산하거나 인용한 결과는 아닙니다.'])
    else:
        text.append('변효 없음 · 현재 주제를 유지하며 점검해 보세요.')
    text.extend(['근거: ' + method + '. 문왕 64괘 순서.', DISCLAIMER])
    reading = {'ok': True, 'kind': 'iching', 'lines': list(lines), 'coins': coins,
            'hexagram': {'number': number, 'name': name, 'theme': theme},
            'changing_lines': changed,
            'transformed': {'number': next_number, 'name': next_name, 'lines': transformed},
            'evidence': {'method': method, 'source': ICHING_SOURCE, 'line_order': 'bottom_to_top'},
            'text': '\n'.join(text)}
    from .spoken_reading import iching_speech_text
    reading['speech_text'] = iching_speech_text(reading)
    return reading
