"""Seeded Vietnamese noise; preserve action/negation tokens during deletion."""
import random
import re
import unicodedata


def no_diacritic(text, rng=None):
    return ''.join(c for c in unicodedata.normalize('NFD', text) if not unicodedata.combining(c)).replace('đ', 'd').replace('Đ', 'D')


def partial_diacritic(text, rng):
    return ' '.join(no_diacritic(w) if rng.random() < .5 else w for w in text.split())


TEENCODE = {
    'không': ['ko','k','hông'], 'được': ['đc','dc'], 'gì': ['j'], 'rồi': ['r'], 'vậy': ['v'],
    'sản phẩm': ['sp'], 'đơn hàng': ['đh'], 'tôi': ['t','mình','em'], 'bạn': ['b'], 'với': ['vs'],
    'biết': ['bít'], 'thế nào': ['sao'], 'bao nhiêu': ['bn'], 'bây giờ': ['bh'], 'bao giờ': ['bg'],
    'cũng': ['cx'], 'đang': ['đg'], 'chưa': ['ch'], 'nhưng': ['nhg'], 'những': ['nhg'], 'người': ['ng'],
    'nhiều': ['nhìu'], 'mình': ['mk'], 'em': ['e'], 'anh': ['a'], 'chị': ['c'], 'cảm ơn': ['cám ơn','tks'],
    'xin lỗi': ['sr'], 'điện thoại': ['đt'], 'tài khoản': ['tk'], 'chuyển khoản': ['ck'], 'thanh toán': ['tt'],
    'địa chỉ': ['đc'], 'số điện thoại': ['sđt'], 'kiểm tra': ['check'], 'nhắn tin': ['ib'], 'hôm nay': ['hnay'],
}
CODESWITCH = {'hoàn tiền':['refund'], 'giao hàng':['ship'], 'phí ship':['phí ship'], 'đơn hàng':['order'], 'hủy':['cancel'], 'đổi trả':['return'], 'mã giảm giá':['voucher'], 'thanh toán':['payment'], 'tài khoản':['account']}


def substitute(text, mapping, rng, probability):
    for key in sorted(mapping, key=len, reverse=True):
        text = re.sub(r'(?<!\w)' + re.escape(key) + r'(?!\w)', lambda match: rng.choice(mapping[key]) if rng.random() < probability else match.group(), text, flags=re.I)
    return text


def teencode(text, rng):
    return substitute(text, TEENCODE, rng, .7)


def codeswitch(text, rng):
    return substitute(text, CODESWITCH, rng, .5)


def telex(word):
    tones = {'\u0300':'f','\u0301':'s','\u0309':'r','\u0303':'x','\u0323':'j'}
    shapes = {'\u0302': None, '\u0306':'w', '\u031b':'w'}
    output, tone = '', ''
    for char in unicodedata.normalize('NFD', word.lower()):
        if char in tones:
            tone = tones[char]
        elif char in shapes:
            output += (output[-1] if shapes[char] is None and output else shapes[char] or '')
        else:
            output += 'dd' if char == 'đ' else char
    return output + tone


def typo(text, rng):
    words = text.split()
    if len(words) < 3:
        return text
    candidates = [i for i,w in enumerate(words) if w.isalpha() and len(w) >= 3]
    for i in rng.sample(candidates, min(len(candidates), rng.randint(1,2))):
        w = words[i]
        if no_diacritic(w) != w and rng.random() < .5:
            words[i] = telex(w); continue
        j = rng.randrange(len(w)-1)
        op = rng.choice(['delete','repeat','swap'])
        words[i] = w[:j]+w[j+1:] if op == 'delete' else w[:j]+w[j]+w[j:] if op == 'repeat' else w[:j]+w[j+1]+w[j]+w[j+2:]
    return ' '.join(words)


def polite(text, rng):
    return rng.choice(['shop ơi ', 'ad ơi cho em hỏi ', 'cho mình hỏi ', 'dạ ']) + text + rng.choice([' giúp mình với',' ạ',' nhé',' được không ạ'])


PROTECTED = {'không','chưa','chẳng','đừng','ko','k','hủy','huỷ','đổi','trả','hoàn','giao','theo','dõi','khong','chua','chang','dung','huy','doi','tra','hoan','theo','doi'}


def eda_delete(text, rng):
    return ' '.join(w for w in text.split() if w.lower().strip('.,?!') in PROTECTED or not w.isalpha() or rng.random() >= .1)


AUGMENTERS = {f.__name__: f for f in (no_diacritic, partial_diacritic, teencode, typo, codeswitch, polite, eda_delete)}
WEIGHTS = [.25,.10,.15,.10,.10,.15,.15]


def augment(text, rng: random.Random):
    names = list(AUGMENTERS)
    selected = [rng.choices(names, weights=WEIGHTS)[0]]
    if rng.random() < .3:
        others = [n for n in names if n != selected[0]]
        selected.append(rng.choices(others, weights=[WEIGHTS[names.index(n)] for n in others])[0])
    for name in selected:
        text = AUGMENTERS[name](text, rng)
    return text, '+'.join(selected)
