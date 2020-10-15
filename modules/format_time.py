import math

s = 1000
m = s * 60
h = m * 60
d = h * 24
w = d * 7
y = d * 365.25


def ms(ms, *, accuracy=2):
    if ms < 1000:
        return f'{int(ms)}ms'

    ret = []

    def add(val, suffix):
        if val == 0 or len(ret) >= accuracy:
            return

        ret.append(f'{val}{suffix}')

    round_toward_zero = math.floor if ms > 0 else math.ceil
    parsed = {
        'days': round_toward_zero(ms / d),
        'hours': round_toward_zero(ms / h) % 24,
        'minutes': round_toward_zero(ms / m) % 60,
        'seconds': round_toward_zero(ms / s) % 60
    }
    add(math.trunc(parsed['days'] / 365), "y")
    add(parsed['days'] % 365, "d")
    add(parsed['hours'], "h")
    add(parsed['minutes'], "m")
    add(parsed['seconds'], "s")
    return ' '.join(ret)
