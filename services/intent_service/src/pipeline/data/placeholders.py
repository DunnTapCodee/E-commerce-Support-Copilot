"""Protect translation slots, restore them strictly, and fill typed values."""
import re
import random
from services.intent_service.src.preprocessing import normalize_text

SLOT = re.compile(r'\{\{[^}]+\}\}')
TOKEN = re.compile(r'\[\[SLOT\d+\]\]')


def protect(text):
    mapping = {}
    def replace(match):
        token = f'[[SLOT{len(mapping)}]]'
        mapping[token] = match.group()
        return token
    return SLOT.sub(replace, text), mapping


def restore(text, mapping):
    """Return (restored_text, qc_slot_lost); reject missing/extra/repeated slots."""
    lost = set(TOKEN.findall(text)) != set(mapping) or any(text.count(t) != 1 for t in mapping)
    for token, original in mapping.items():
        text = text.replace(token, original)
    return text, lost


def slot_kind(name):
    """Match discovered Bitext slot names; unknown slots require explicit mapping."""
    key = name.strip('{} ').lower()
    for needles, kind in [
        (('order', 'tracking', 'invoice'), 'order'),
        (('email', 'e-mail'), 'email'), (('phone', 'telephone'), 'phone'),
        (('amount', 'money', 'price', 'cost'), 'money'),
        (('person', 'customer name', 'first name', 'last name', 'full name', 'agent name'), 'person'),
        (('date', 'day', 'month', 'year'), 'date'), (('time', 'hour'), 'time'),
        (('address', 'street', 'city', 'location', 'country', 'zip', 'postal'), 'address'),
        (('product', 'item', 'brand', 'model'), 'product'),
        (('store', 'shop', 'company', 'business'), 'store'),
        (('website', 'url', 'link'), 'url'),
        (('number', 'code', ' id'), 'code'),
        (('account', 'username'), 'account'),
    ]:
        if any(n in key for n in needles):
            return kind
    raise ValueError(f'Unmapped placeholder {name!r}; extend slot_kind from reports/module1/placeholders.json')


def fill_slots(text, rng: random.Random, lang='vi'):
    def replace(match):
        kind = slot_kind(match.group())
        values = {
            'order': lambda: f'ORD-{rng.randint(1000, 999999)}',
            'email': lambda: f'customer{rng.randint(1,9999)}@example.com',
            'phone': lambda: f'09{rng.randint(10000000,99999999)}',
            'money': lambda: f'{rng.randint(1,100)*10000} VND' if lang == 'vi' else f'{rng.randint(1,500)} USD',
            'person': lambda: rng.choice(['Nguyễn An', 'Trần Minh', 'Lê Hà'] if lang == 'vi' else ['Alex Smith', 'Jamie Brown', 'Sam Lee']),
            'date': lambda: f'2026-{rng.randint(1,12):02}-{rng.randint(1,28):02}',
            'time': lambda: f'{rng.randint(8,20):02}:00',
            'address': lambda: rng.choice(['12 Nguyễn Huệ, TP HCM', '25 Tràng Tiền, Hà Nội'] if lang == 'vi' else ['12 Main Street', '25 Park Avenue']),
            'product': lambda: rng.choice(['áo thun', 'tai nghe', 'giày'] if lang == 'vi' else ['shirt', 'headphones', 'shoes']),
            'store': lambda: 'Demo Store', 'url': lambda: 'https://example.com/support',
            'code': lambda: str(rng.randint(10000,999999)),
            'account': lambda: f'customer{rng.randint(1,9999)}',
        }
        return values[kind]()
    return normalize_slots_for_inference(SLOT.sub(replace, text))


def normalize_slots_for_inference(text):
    """Order numbers are intentionally preserved in both train and serving."""
    return normalize_text(text)
