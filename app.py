"""
Сайт для проверки SMS на мошенничество (Корея + Казахстан).
Интерфейс: 한국어 / English (новые языки добавляются в словарь TEXTS).

Запуск:  python3 -m streamlit run app.py
"""

import csv
import html
import json
import os
import re
from datetime import datetime

import joblib
import streamlit as st

# ====================== Признаки мошенничества (можно дополнять) ======================
URGENCY_WORDS = [
    "urgent", "immediately", "act now", "expire", "suspended", "blocked", "verify", "today",
    "긴급", "즉시", "정지", "차단", "만료", "확인 바랍니다", "오늘까지", "미납",
    "срочно", "заблокирован", "немедленно", "последнее предупреждение", "в течение 24",
    "шұғыл", "бұғатталды", "дереу", "тез арада",
]
MONEY_WORDS = [
    "prize", "winner", "cash", "free", "claim", "reward", "loan", "bank", "card", "parcel",
    "당첨", "무료", "대출", "환급", "지원금", "계좌", "카드", "택배", "결제", "송금",
    "выигрыш", "приз", "бесплатно", "карт", "перевод", "кредит", "выплат", "пособи", "компенсац",
    "ұтыс", "сыйлық", "тегін", "аударым", "несие", "төлем",
]
IMPERSONATION_WORDS = [
    "검찰", "경찰", "금융감독원", "국세청", "건강보험", "우체국", "cj대한통운", "청첩장", "부고", "엄마", "아빠",
    "kaspi", "каспи", "halyk", "халык", "egov", "налоговая", "полиция", "кнб", "служба безопасности банка",
    "police", "tax office", "delivery",
]
SHORT_LINK_DOMAINS = ["bit.ly", "tinyurl", "goo.gl", "t.co", "han.gl", "me2.do", "vo.la", "url.kr", "clck.ru", "cutt.ly"]

URL_RE = r"(https?://\S+|www\.\S+|\b[\w-]+(?:\.[\w-]+)*\.(?:com|net|kr|kz|ru|ly|io|xyz|top|site|info|gl|do|la|co)\b(?:/\S*)?)"
PHONE_RE = r"(\+?\d[\d\-\s()]{8,}\d)"

# Какой «маркер» у какого признака: go — куда тебя уводят (жёлтый), push — чем давят (розовый)
REASON_KIND = {"link": "go", "short": "go", "phone": "go",
               "urgency": "push", "money": "push", "imperson": "push", "caps": "push"}

# ====================== Тексты интерфейса ======================
TEXTS = {
    "한국어": {
        "title": "이 문자,<br>믿어도 될까요?",
        "subtitle": "받은 문자를 붙여넣으면 위험한 부분에 형광펜을 칠해 드려요.",
        "demo": "[국제발신] 택배 주소 불일치로 보관중입니다. 오늘까지 확인 바랍니다 han.gl/x8Kd",
        "demo_from": "+82 10-****-2291",
        "nav": ["문자 검사", "스미싱 구별법", "프로젝트 소개"],
        "country": "어느 나라에서 받은 문자인가요?",
        "countries": ["대한민국", "카자흐스탄"],
        "try": "예시 문자로 해보기",
        "examples": [
            ("택배 사칭", "[국제발신] 택배 주소 불일치로 보관중입니다. 확인 바랍니다 han.gl/xxxx"),
            ("Kaspi 사칭", "[Kaspi] Ваша карта заблокирована. Срочно подтвердите данные: bit.ly/kaspi-help"),
            ("친구 문자", "내일 수업 10시에 시작해요. 늦지 마!"),
        ],
        "label": "받은 문자",
        "placeholder": "받은 문자를 여기에 붙여넣으세요",
        "button": "문자 검사하기",
        "empty": "검사할 문자를 붙여넣어 주세요.",
        "incoming": "받은 문자",
        "stamp": {"high": "사기 의심", "medium": "주의", "low": "안전"},
        "verdict": {
            "high": "전형적인 스미싱 문자와 매우 비슷합니다.",
            "medium": "의심스러운 부분이 있어요. 보낸 사람을 직접 확인하세요.",
            "low": "특별한 사기 징후는 보이지 않아요.",
        },
        "risk": "위험도",
        "model": "AI 모델",
        "rules": "규칙 분석",
        "legend_go": "어딘가로 유도하는 부분",
        "legend_push": "압박하거나 사칭하는 부분",
        "reasons_title": "형광펜으로 표시한 이유",
        "no_reasons": "표시할 위험 요소가 없어요.",
        "reasons": {
            "link": "링크가 들어 있어요",
            "short": "단축 URL이라 실제 주소가 보이지 않아요",
            "phone": "전화를 걸도록 번호를 넣었어요",
            "urgency": "급하게 행동하도록 재촉해요",
            "money": "돈, 당첨, 대출, 카드, 택배를 언급해요",
            "imperson": "기관, 은행, 택배사나 가족인 척해요",
            "caps": "느낌표나 대문자가 지나치게 많아요",
        },
        "advice_title": "지금 해야 할 일",
        "advice": [
            ["링크를 누르거나 앱을 설치하지 마세요.",
             "<b>118</b>(KISA) 또는 <b>112</b>(경찰)에 신고하세요.",
             "이미 송금했다면 바로 거래 은행에 지급정지를 요청하세요."],
            ["링크를 누르거나 문자 속 인증번호를 알려주지 마세요.",
             "은행과 eGov는 전화로 인증번호를 묻지 않아요.",
             "<b>102</b>(카자흐스탄 경찰)에 신고하고, 송금했다면 바로 은행에 연락하세요."],
        ],
        "feedback_q": "결과가 맞았나요? 답변은 다음 AI 학습에 쓰여요.",
        "fb_yes": "맞아요",
        "fb_no": "틀렸어요",
        "fb_thanks": "고마워요. 다음 학습에 반영할게요.",
        "tips_title": "스미싱을 구별하는 방법",
        "tips": [
            ("🔗", "모르는 링크는 누르지 않기", "택배, 청첩장, 부고 문자 속 링크는 대표적인 스미싱 수법이에요."),
            ("🏛️", "기관은 문자로 돈을 요구하지 않아요", "검찰, 경찰, 금융감독원은 문자나 전화로 송금을 요구하지 않아요."),
            ("👨‍👩‍👧", "가족이라고 하면 직접 전화하기", "\"폰이 고장났어\"라는 문자를 받으면 원래 번호로 전화해서 확인하세요."),
            ("⏰", "급하게 만드는 문자는 의심하기", "\"오늘까지\", \"즉시\" 같은 말은 생각할 시간을 빼앗으려는 거예요."),
            ("🔐", "인증번호는 누구에게도 알려주지 않기", "인증번호와 카드 정보는 은행 직원에게도 알려주면 안 돼요."),
        ],
        "about_title": "프로젝트 소개",
        "about": "이 사이트는 두 가지 방법으로 문자를 검사해요. AI 모델(TF-IDF + 로지스틱 회귀)이 수천 개의 문자에서 배운 패턴으로 점수를 내고, "
                 "규칙 분석이 링크, 전화번호, 재촉하는 말 같은 위험 신호를 찾아요. 최종 위험도는 두 점수 중 높은 값이에요.",
        "metrics_title": "테스트 데이터 정확도",
        "lang_names": {"en": "영어", "ko": "한국어", "ru": "러시아어", "kk": "카자흐어"},
        "no_metrics": "아직 정확도 정보가 없어요. train.py를 실행하면 여기에 표시돼요.",
        "train_size": "학습에 쓴 문자: {n}개",
        "footer": "참고용 서비스예요. 의심되면 해당 기관에 직접 확인하세요.",
    },
    "English": {
        "title": "Can you trust<br>this text?",
        "subtitle": "Paste a text you got. We'll highlight the parts that look like a scam.",
        "demo": "Your parcel is on hold. Confirm your address today: bit.ly/x8Kd",
        "demo_from": "+1 415-***-0192",
        "nav": ["Check a message", "How to spot scams", "About"],
        "country": "Where did you get this message?",
        "countries": ["South Korea", "Kazakhstan"],
        "try": "Try an example",
        "examples": [
            ("Fake prize", "URGENT! You have won a $1000 prize. Claim now at bit.ly/win123"),
            ("Fake delivery", "[국제발신] 택배 주소 불일치로 보관중입니다. 확인 바랍니다 han.gl/xxxx"),
            ("Friend's text", "Hi, are we still meeting for lunch tomorrow?"),
        ],
        "label": "Message",
        "placeholder": "Paste the message here",
        "button": "Check message",
        "empty": "Paste a message to check.",
        "incoming": "Message you got",
        "stamp": {"high": "Likely scam", "medium": "Careful", "low": "Looks safe"},
        "verdict": {
            "high": "This looks very much like a typical scam text.",
            "medium": "Some parts look suspicious. Check with the sender directly.",
            "low": "No clear signs of a scam.",
        },
        "risk": "Risk",
        "model": "AI model",
        "rules": "Rule check",
        "legend_go": "Tries to send you somewhere",
        "legend_push": "Pressures you or pretends to be someone",
        "reasons_title": "Why these parts are highlighted",
        "no_reasons": "Nothing risky to highlight.",
        "reasons": {
            "link": "It contains a link",
            "short": "The link is shortened, so you can't see where it goes",
            "phone": "It gives a number for you to call",
            "urgency": "It rushes you to act now",
            "money": "It mentions money, prizes, loans, cards or parcels",
            "imperson": "It pretends to be an agency, bank, courier or relative",
            "caps": "Too many exclamation marks or capital letters",
        },
        "advice_title": "What to do now",
        "advice": [
            ["Don't tap the link or install any app.",
             "Report it to <b>118</b> (KISA) or <b>112</b> (police).",
             "If you already sent money, ask your bank to freeze the transfer right away."],
            ["Don't tap the link or share any SMS code.",
             "Banks and eGov never ask for codes by phone.",
             "Report it to <b>102</b> (police). If you sent money, call your bank right away."],
        ],
        "feedback_q": "Was this right? Your answer helps train the next version.",
        "fb_yes": "Yes, right",
        "fb_no": "No, wrong",
        "fb_thanks": "Thanks. We'll use it in the next training.",
        "tips_title": "How to spot a scam text",
        "tips": [
            ("🔗", "Don't open unknown links", "Links in delivery, wedding or funeral texts are a classic trick."),
            ("🏛️", "Agencies don't ask for money by text", "Police, prosecutors and regulators never ask you to transfer money by SMS."),
            ("👨‍👩‍👧", "If it's \"family\", call them", "Got \"my phone broke, send money\"? Call their usual number first."),
            ("⏰", "Rushing you is a red flag", "\"Today only\" and \"immediately\" are there to stop you from thinking."),
            ("🔐", "Never share codes", "Don't give SMS codes or card details to anyone, even a \"bank employee\"."),
        ],
        "about_title": "About this project",
        "about": "This site checks a message in two ways. An AI model (TF-IDF + logistic regression) scores it using patterns "
                 "learned from thousands of texts, and a rule check looks for warning signs like links, phone numbers and pressure words. "
                 "The final risk is the higher of the two scores.",
        "metrics_title": "Accuracy on test data",
        "lang_names": {"en": "English", "ko": "Korean", "ru": "Russian", "kk": "Kazakh"},
        "no_metrics": "No accuracy data yet. Run train.py and it will show up here.",
        "train_size": "Messages used for training: {n}",
        "footer": "For reference only. If in doubt, contact the organization directly.",
    },
}

LEVEL_COLOR = {"high": "#E2392F", "medium": "#D9822B", "low": "#1F9D63"}

# ====================== Стиль ======================
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Black+Han+Sans&family=IBM+Plex+Sans+KR:wght@400;500;700&display=swap');

:root {
    --ink: #0F3D3E;        /* глубокий бирюзовый: шапка, навигация, текст заголовков */
    --ice: #E9F1EE;        /* фон страницы */
    --paper: #FFFFFF;      /* пузыри сообщений */
    --marker: #FFE14D;     /* жёлтый маркер: ссылки и номера */
    --push: #FFC9C2;       /* розовый маркер: давление и сокрытие */
    --text: #183334;
    --muted: #5C7372;
    --line: #CFDDD8;
}

html, body, .stApp, .stMarkdown, button, input, textarea, label, p, li {
    font-family: 'IBM Plex Sans KR', -apple-system, 'Apple SD Gothic Neo', sans-serif !important;
}
.stApp {background: var(--ice); color: var(--text);}
#MainMenu, footer, header[data-testid="stHeader"] {visibility: hidden; height: 0;}
.block-container {padding-top: 1.2rem; max-width: 860px;}

/* ---------- Шапка: тёмный «пузырь» с демонстрацией маркера ---------- */
.hero {
    background: var(--ink); color: #fff;
    border-radius: 34px 34px 34px 8px;
    padding: 40px 38px 38px; margin: 8px 0 22px;
    display: grid; grid-template-columns: 1.05fr 1fr; gap: 28px; align-items: center;
}
.hero h1 {
    font-family: 'Black Han Sans', 'IBM Plex Sans KR', sans-serif !important;
    font-weight: 400; color: #fff; font-size: 52px; line-height: 1.08; margin: 0 0 14px;
    letter-spacing: -0.01em;
}
.hero p {color: #C9DEDA; font-size: 16.5px; line-height: 1.6; margin: 0; max-width: 34ch;}
.demo-from {font-size: 12px; color: #9FC0BA; margin: 0 0 6px 6px;}
.demo {transform: rotate(1.5deg);}

/* ---------- SMS-пузырь и маркеры ---------- */
.bubble {
    background: var(--paper); color: #1B2B2B;
    border-radius: 22px 22px 22px 6px;
    padding: 16px 18px; font-size: 16.5px; line-height: 1.75;
    word-break: break-word;
}
.hero .bubble {box-shadow: 0 18px 40px rgba(0, 0, 0, .28);}
mark {
    color: inherit; padding: 1px 3px; border-radius: 4px;
    -webkit-box-decoration-break: clone; box-decoration-break: clone;
}
mark.go   {background: linear-gradient(transparent 12%, var(--marker) 12%, var(--marker) 92%, transparent 92%);}
mark.push {background: linear-gradient(transparent 12%, var(--push) 12%, var(--push) 92%, transparent 92%);}
.swatch {display: inline-block; width: 22px; height: 12px; border-radius: 3px; margin-right: 8px; vertical-align: -1px;}
.swatch.go {background: var(--marker);} .swatch.push {background: var(--push);}

/* ---------- Результат ---------- */
.result {position: relative; margin: 26px 0 8px; animation: rise .35s ease-out;}
.result .label {font-size: 13px; color: var(--muted); margin: 0 0 6px 6px;}
.result .bubble {border: 1.5px solid var(--line); padding: 20px 22px; font-size: 17px; max-width: 92%;}
.stamp {
    position: absolute; top: 4px; right: 0;
    font-family: 'Black Han Sans', 'IBM Plex Sans KR', sans-serif !important;
    font-size: 26px; padding: 6px 16px 4px; border: 4px solid currentColor; border-radius: 10px;
    background: rgba(255, 255, 255, .9); transform: rotate(-9deg);
    animation: stamp .32s cubic-bezier(.2, 1.6, .4, 1) both .12s;
}
@keyframes stamp {from {opacity: 0; transform: rotate(-9deg) scale(1.9);} to {opacity: 1; transform: rotate(-9deg) scale(1);}}
@keyframes rise {from {opacity: 0; transform: translateY(8px);} to {opacity: 1; transform: none;}}

.verdict {display: flex; flex-wrap: wrap; align-items: center; gap: 10px 22px; margin: 22px 0 6px;}
.verdict .big {font-family: 'Black Han Sans', sans-serif !important; font-size: 44px; line-height: 1;}
.verdict .big small {font-family: 'IBM Plex Sans KR', sans-serif !important; font-size: 14px; color: var(--muted); margin-left: 6px;}
.verdict .what {font-size: 16px; flex: 1 1 260px;}
.meter {display: grid; grid-template-columns: repeat(10, 1fr); gap: 5px; margin: 10px 0 6px;}
.meter i {height: 10px; border-radius: 3px; background: #D5E2DE;}
.split {font-size: 13.5px; color: var(--muted);}
.split b {color: var(--text);}

.why {margin: 26px 0 0;}
.why h4, .todo h4 {font-size: 16px; font-weight: 700; margin: 0 0 10px; color: var(--ink);}
.why ul, .todo ol {margin: 0; padding-left: 0; list-style: none;}
.why li {padding: 7px 0; border-bottom: 1px dashed var(--line); font-size: 15.5px;}
.why li:last-child {border-bottom: none;}
.legend {font-size: 13.5px; color: var(--muted); margin: 0 0 10px; display: flex; flex-wrap: wrap; gap: 6px 18px;}

.todo {margin: 22px 0 6px; background: var(--ink); color: #E6F2EF; border-radius: 22px 22px 22px 6px; padding: 20px 22px;}
.todo h4 {color: #fff;}
.todo ol {counter-reset: step;}
.todo li {counter-increment: step; padding: 6px 0 6px 34px; position: relative; font-size: 15.5px; line-height: 1.55;}
.todo li::before {
    content: counter(step); position: absolute; left: 0; top: 6px; width: 22px; height: 22px; border-radius: 50%;
    background: var(--marker); color: var(--ink); font-weight: 700; font-size: 13px;
    display: flex; align-items: center; justify-content: center;
}
.todo b {color: var(--marker);}

/* ---------- Советы и «о проекте» ---------- */
.tip {display: grid; grid-template-columns: 52px 1fr; gap: 14px; padding: 16px 0; border-bottom: 1px solid var(--line);}
.tip:last-child {border-bottom: none;}
.tip .ico {font-size: 26px; width: 52px; height: 52px; background: var(--paper); border-radius: 16px 16px 16px 4px;
           display: flex; align-items: center; justify-content: center;}
.tip b {display: block; font-size: 17px; color: var(--ink); margin: 3px 0 3px;}
.tip span {color: var(--muted); font-size: 15px; line-height: 1.55;}
.page-title {font-family: 'Black Han Sans', sans-serif !important; font-size: 32px; color: var(--ink); margin: 10px 0 8px;}
.about {font-size: 16px; line-height: 1.75; max-width: 64ch;}
.scores {display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-top: 8px;}
.score {background: var(--paper); border-radius: 18px 18px 18px 4px; padding: 16px 18px;}
.score .lang {font-size: 14px; color: var(--muted);}
.score .acc {font-family: 'Black Han Sans', sans-serif !important; font-size: 38px; color: var(--ink); line-height: 1.2;}
.score .sub {font-size: 12.5px; color: var(--muted);}
.footer {text-align: center; color: var(--muted); font-size: 13px; margin: 40px 0 12px;}

/* ---------- Элементы Streamlit ---------- */
[data-testid="stTextArea"] textarea {
    background: var(--paper); border-radius: 18px; font-size: 16.5px; line-height: 1.6; padding: 14px 16px;
}
[data-testid="stTextArea"] [data-baseweb="textarea"] {border: 2px solid var(--line) !important; border-radius: 20px; background: var(--paper);}
[data-testid="stTextArea"] [data-baseweb="textarea"]:focus-within {border-color: var(--ink) !important;}

[data-testid="stBaseButton-primary"] {
    background: var(--marker) !important; color: var(--ink) !important; border: none !important;
    border-radius: 16px !important; padding: 14px !important; min-height: 56px;
    box-shadow: 0 4px 0 #D9B92C; transition: transform .08s, box-shadow .08s;
}
[data-testid="stBaseButton-primary"] p {font-size: 18px !important; font-weight: 700 !important;}
[data-testid="stBaseButton-primary"]:hover {background: #FFD92B !important;}
[data-testid="stBaseButton-primary"]:active {transform: translateY(3px); box-shadow: 0 1px 0 #D9B92C;}

[data-testid="stBaseButton-secondary"] {
    background: var(--paper) !important; border: 1.5px solid var(--line) !important; color: var(--text) !important;
    border-radius: 999px !important;
}
[data-testid="stBaseButton-secondary"]:hover {border-color: var(--ink) !important; color: var(--ink) !important;}

[data-testid="stButtonGroup"] button {border-color: var(--line) !important; background: transparent; min-height: 44px;}
[data-testid="stButtonGroup"] button p {font-weight: 700; font-size: 15px; color: inherit;}
[data-testid="stButtonGroup"] button[aria-checked="true"] * {color: #fff !important;}
[data-testid="stButtonGroup"] button[aria-checked="true"] {
    background: var(--ink) !important; color: #fff !important; border-color: var(--ink) !important;
}
button:focus-visible, textarea:focus-visible {outline: 3px solid var(--marker) !important; outline-offset: 2px;}

@media (max-width: 680px) {
    .hero {grid-template-columns: 1fr; padding: 30px 22px 26px; border-radius: 26px 26px 26px 6px;}
    .hero h1 {font-size: 38px;}
    .result .bubble {max-width: 100%; margin-top: 30px;}
    .stamp {font-size: 21px; top: 0;}
    .verdict .big {font-size: 38px;}
}
@media (prefers-reduced-motion: reduce) {
    .result, .stamp {animation: none !important;}
}
</style>
"""


# ====================== Логика ======================
def contains(text, words):
    """Латинские слова ищем целиком (чтобы 'now' не находилось в 'know'), остальные — как часть слова."""
    return any(True for _ in find_words(text, words))


def find_words(text, words):
    """Позиции всех найденных слов-признаков в тексте (без учёта регистра)."""
    lower = text.lower()
    for w in words:
        if re.fullmatch(r"[a-z .]+", w):
            for m in re.finditer(r"\b" + re.escape(w) + r"\b", lower):
                yield m.start(), m.end()
        else:
            start = lower.find(w)
            while start != -1:
                yield start, start + len(w)
                start = lower.find(w, start + 1)


def explain(text):
    """Возвращает (ключи подозрительных признаков, оценка риска по правилам 0..1)."""
    reasons, score = [], 0.0
    lower = text.lower()

    def add(key, weight):
        nonlocal score
        reasons.append(key)
        score += weight

    if re.search(URL_RE, lower):
        add("link", 0.15)
    if any(d in lower for d in SHORT_LINK_DOMAINS):
        add("short", 0.25)
    if re.search(PHONE_RE, text):
        add("phone", 0.1)
    if contains(text, URGENCY_WORDS):
        add("urgency", 0.2)
    if contains(text, MONEY_WORDS):
        add("money", 0.15)
    if contains(text, IMPERSONATION_WORDS):
        add("imperson", 0.25)
    letters = [c for c in text if c.isalpha()]
    if text.count("!") >= 3 or (letters and sum(c.isupper() for c in letters) > 0.5 * len(letters)):
        add("caps", 0.1)
    return reasons, min(score, 0.95)


def highlight(text):
    """Возвращает HTML текста, где подозрительные куски обведены «маркером»."""
    spans = []
    for m in re.finditer(URL_RE, text, flags=re.I):
        spans.append((m.start(), m.end(), "go"))
    for m in re.finditer(PHONE_RE, text):
        spans.append((m.start(), m.end(), "go"))
    for words in (URGENCY_WORDS, MONEY_WORDS, IMPERSONATION_WORDS):
        for a, b in find_words(text, words):
            spans.append((a, b, "push"))

    # Оставляем непересекающиеся куски: сначала ссылки/номера, потом более длинные слова
    spans.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    chosen, last_end = [], -1
    for a, b, kind in spans:
        if a >= last_end:
            chosen.append((a, b, kind))
            last_end = b

    out, pos = [], 0
    for a, b, kind in chosen:
        out.append(html.escape(text[pos:a]))
        out.append(f'<mark class="{kind}">{html.escape(text[a:b])}</mark>')
        pos = b
    out.append(html.escape(text[pos:]))
    return "".join(out).replace("\n", "<br>")


@st.cache_resource
def load_model():
    # Если модели ещё нет (например, на сервере), обучаем её автоматически
    if not os.path.exists("model.joblib"):
        import train
        train.main()
    return joblib.load("model.joblib")


def load_metrics():
    if os.path.exists("metrics.json"):
        with open("metrics.json", encoding="utf-8") as f:
            return json.load(f)
    return None


def save_feedback(text, label):
    """Сохраняет исправление пользователя — потом train.py использует его для обучения."""
    new = not os.path.exists("feedback.csv")
    with open("feedback.csv", "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["label", "text", "time"])
        w.writerow(["spam" if label == 1 else "ham", text, datetime.now().isoformat(timespec="seconds")])


def set_example(text):
    st.session_state.msg = text
    st.session_state.result = None


# ====================== Интерфейс ======================
st.set_page_config(page_title="Smishing Checker", page_icon="🛡️", layout="centered")
st.markdown(CSS, unsafe_allow_html=True)

if "result" not in st.session_state:
    st.session_state.result = None

_, lang_col = st.columns([3, 1])
lang = lang_col.selectbox("🌐", list(TEXTS.keys()), key="lang", label_visibility="collapsed")
T = TEXTS[lang]

st.markdown(f"""
<div class="hero">
  <div><h1>{T["title"]}</h1><p>{T["subtitle"]}</p></div>
  <div class="demo" aria-hidden="true">
    <div class="demo-from">{T["demo_from"]}</div>
    <div class="bubble">{highlight(T["demo"])}</div>
  </div>
</div>
""", unsafe_allow_html=True)

# Навигация: храним НОМЕР страницы, а не её название — поэтому при смене языка страница не сбрасывается
if "page" not in st.session_state:
    st.session_state.page = 0
    st.session_state.page_last = 0


def keep_page():
    if st.session_state.page is None:          # повторный клик по выбранной кнопке — не даём «снять» выбор
        st.session_state.page = st.session_state.page_last
    st.session_state.page_last = st.session_state.page


st.segmented_control("nav", options=[0, 1, 2], format_func=lambda i: T["nav"][i], key="page",
                     on_change=keep_page, label_visibility="collapsed", width="stretch")
page = st.session_state.page

# ---------- Страница 1: проверка ----------
if page == 0:
    country_idx = st.radio(T["country"], [0, 1], format_func=lambda i: T["countries"][i],
                           key="country", horizontal=True)

    st.caption(T["try"])
    ex_cols = st.columns(len(T["examples"]))
    for col, (name, ex_text) in zip(ex_cols, T["examples"]):
        col.button(name, on_click=set_example, args=(ex_text,), width="stretch")

    text = st.text_area(T["label"], key="msg", height=150, placeholder=T["placeholder"],
                        label_visibility="collapsed")

    if st.button(T["button"], type="primary", width="stretch"):
        if not text.strip():
            st.warning(T["empty"])
            st.session_state.result = None
        else:
            model = load_model()
            model_prob = float(model.predict_proba([text])[0][1])
            reasons, rules_prob = explain(text)
            prob = max(model_prob, rules_prob)  # гибридный подход
            st.session_state.result = {
                "text": text, "prob": prob, "model": model_prob, "rules": rules_prob,
                "reasons": reasons, "feedback": False,
            }

    r = st.session_state.result
    if r:
        level = "high" if r["prob"] >= 0.7 else "medium" if r["prob"] >= 0.4 else "low"
        color = LEVEL_COLOR[level]
        pct = round(r["prob"] * 100)
        filled = max(1, round(pct / 10)) if pct > 0 else 0
        cells = "".join(f'<i style="background:{color}"></i>' if i < filled else "<i></i>" for i in range(10))

        if r["reasons"]:
            kinds = {REASON_KIND[k] for k in r["reasons"]}
            legend = "".join(
                f'<span><span class="swatch {k}"></span>{T["legend_" + k]}</span>' for k in ("go", "push") if k in kinds
            )
            items = "".join(
                f'<li><span class="swatch {REASON_KIND[k]}"></span>{T["reasons"][k]}</li>' for k in r["reasons"]
            )
            why = f'<div class="why"><h4>{T["reasons_title"]}</h4><div class="legend">{legend}</div><ul>{items}</ul></div>'
        else:
            why = f'<div class="why"><h4>{T["reasons_title"]}</h4><p style="color:var(--muted)">{T["no_reasons"]}</p></div>'

        st.markdown(f"""
<div class="result">
  <p class="label">{T["incoming"]}</p>
  <div class="bubble">{highlight(r["text"])}</div>
  <div class="stamp" style="color:{color}">{T["stamp"][level]}</div>
</div>
<div class="verdict">
  <div class="big" style="color:{color}">{pct}%<small>{T["risk"]}</small></div>
  <div class="what">{T["verdict"][level]}</div>
</div>
<div class="meter" role="img" aria-label="{T["risk"]} {pct}%">{cells}</div>
<div class="split">{T["model"]} <b>{r["model"]:.0%}</b> &nbsp;/&nbsp; {T["rules"]} <b>{r["rules"]:.0%}</b></div>
{why}
""", unsafe_allow_html=True)

        if level != "low":
            steps = "".join(f"<li>{s}</li>" for s in T["advice"][country_idx])
            st.markdown(f'<div class="todo"><h4>{T["advice_title"]}</h4><ol>{steps}</ol></div>',
                        unsafe_allow_html=True)

        st.write("")
        if not r["feedback"]:
            st.caption(T["feedback_q"])
            predicted = 1 if r["prob"] >= 0.5 else 0
            c1, c2, _ = st.columns([1, 1, 2])
            if c1.button("👍 " + T["fb_yes"], width="stretch"):
                save_feedback(r["text"], predicted)
                r["feedback"] = True
                st.rerun()
            if c2.button("👎 " + T["fb_no"], width="stretch"):
                save_feedback(r["text"], 1 - predicted)
                r["feedback"] = True
                st.rerun()
        else:
            st.success(T["fb_thanks"])

# ---------- Страница 2: советы ----------
if page == 1:
    tips_html = "".join(
        f'<div class="tip"><div class="ico">{ico}</div><div><b>{title}</b><span>{desc}</span></div></div>'
        for ico, title, desc in T["tips"]
    )
    st.markdown(f'<div class="page-title">{T["tips_title"]}</div>{tips_html}', unsafe_allow_html=True)

# ---------- Страница 3: о проекте ----------
if page == 2:
    st.markdown(f'<div class="page-title">{T["about_title"]}</div><p class="about">{T["about"]}</p>',
                unsafe_allow_html=True)
    metrics = load_metrics()
    st.markdown(f'<div class="why"><h4>{T["metrics_title"]}</h4></div>', unsafe_allow_html=True)
    if metrics:
        boxes = "".join(
            f'<div class="score"><div class="lang">{T["lang_names"].get(code, code)}</div>'
            f'<div class="acc">{s["accuracy"]:.0%}</div>'
            f'<div class="sub">precision {s["precision"]:.0%}, recall {s["recall"]:.0%}, n={s["n"]}</div></div>'
            for code, s in metrics["by_language"].items()
        )
        st.markdown(f'<div class="scores">{boxes}</div>', unsafe_allow_html=True)
        st.caption(T["train_size"].format(n=metrics["train_size"]))
    else:
        st.info(T["no_metrics"])

st.markdown(f'<div class="footer">{T["footer"]}</div>', unsafe_allow_html=True)
