import math

s = 1000
m = s * 60
h = m * 60
d = h * 24


def ms(ms, *, accuracy=2, progress_bar=0):
    if ms < 1000 and not progress_bar:
        return '0s'

    ret = []

    def add(val, suffix, index):
        if progress_bar and index <= progress_bar:
            zeroes = '00' if not val else "0" * (2 - len(str(val)))
            add_str = f'{zeroes}{val if val else ""}{suffix}'
            return ret.append(add_str)

        if (not ret and val == 0) or len(ret) >= accuracy:
            return

        ret.append(f'{val}{suffix}')

    round_toward_zero = math.floor if ms > 0 else math.ceil
    parsed = {
        'd': round_toward_zero(ms / d),
        'h': round_toward_zero(ms / h) % 24,
        'm': round_toward_zero(ms / m) % 60,
        's': round_toward_zero(ms / s) % 60,
    }
    add(parsed['d'] % 365, "d", 4)
    add(parsed['h'], "h", 3)
    add(parsed['m'], "m", 2)
    add(parsed['s'], "s", 1)
    return ' '.join(ret)


def to_ms(timestamp):
    sections = timestamp.split(' ')

    total_time = 0
    for section in sections:
        total_time += int(section[:-1]) * globals()[section[-1]]

    return total_time
