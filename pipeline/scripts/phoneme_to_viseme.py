phoneme_to_viseme = {
    "sil": 0, "sp": 0, "": 0,

    "æ": 1, "ə": 1, "ʌ": 1,
    "ɑ": 2,
    "ɔ": 3,
    "ɛ": 4, "ʊ": 4,
    "ɝ": 5, "ɚ": 5,
    "j": 6, "i": 6, "ɪ": 6,
    "w": 7, "u": 7,
    "o": 8,
    "aʊ": 9,
    "ɔɪ": 10,
    "aɪ": 11,
    "h": 12,
    "ɹ": 13, "r": 13,
    "l": 14,

    "s": 15, "z": 15,
    "ʃ": 16, "tʃ": 16, "dʒ": 16, "ʒ": 16,

    "ð": 17,

    "f": 18, "v": 18,

    "d": 19, "t": 19, "n": 19, "θ": 19,

    "k": 20, "g": 20, "ŋ": 20,

    "p": 21, "b": 21, "m": 21,
}

normalize = {
    "ER": "ɝ", "AXR": "ɚ", "ER0": "ɚ",
    "AA": "ɑ", "AO": "ɔ", "AE": "æ", "AH": "ʌ", "AX": "ə",
    "EH": "ɛ", "IH": "ɪ", "IY": "i", "UH": "ʊ", "UW": "u",
    "R": "ɹ",
    "CH": "tʃ", "JH": "dʒ", "ZH": "ʒ", "SH": "ʃ",
    "TH": "θ", "DH": "ð",
    "NG": "ŋ",
    "W": "w", "Y": "j", "HH": "h", "L": "l", "S": "s", "Z": "z",
    "D": "d", "T": "t", "N": "n", "K": "k", "G": "g",
    "P": "p", "B": "b", "M": "m",
    "AY": "aɪ", "AW": "aʊ", "OY": "ɔɪ",
}

def to_viseme(ph):
    """Map a single phoneme (IPA or ARPAbet-like) to a viseme id."""
    p = ph.strip()
    if p in phoneme_to_viseme:
        return phoneme_to_viseme[p]
    if p in normalize:
        p2 = normalize[p]
        return phoneme_to_viseme.get(p2, 0)
    p3 = ''.join([c for c in p if not c.isdigit()])
    if p3 in normalize:
        p4 = normalize[p3]
        return phoneme_to_viseme.get(p4, 0)
    return 0
