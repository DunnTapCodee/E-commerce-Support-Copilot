"""Light augmentation only; Bitext already includes English linguistic noise."""
from services.intent_service.src.pipeline.data.augment_vi import typo


def augment(text, rng):
    if rng.random() < .3:
        return text.lower(), 'lowercase'
    if rng.random() < (2 / 7):
        return typo(text, rng), 'typo'
    return text, 'orig'
