"""Built-in LED animations for the One RFID feeder's 26 x 7 display.

A frame is 7 ints (one per row, top to bottom); in each int bit 25 is the
leftmost pixel and bit 0 the rightmost, same as display_matrix.py. Sprites are
drawn here as ASCII ('#' = lit) and composed into frames, so the art can be
read and changed without touching bit math.

Timing: authored at one frame per 100 ms, which is screenDisplayInterval 4 (the
Reddit reporter's figure is about 25 ms per interval step, unverified here).
At most MAX_FRAMES frames: more corrupts the feeder's idle-screen buffer.
"""
import math

WIDTH = 26
HEIGHT = 7
MAX_FRAMES = 140
DEFAULT_INTERVAL = 4


# ── canvas helpers ─────────────────────────────────────────────────────────

def _blank():
    return [[0] * WIDTH for _ in range(HEIGHT)]


def _blit(canvas, sprite, x, y):
    """Draw an ASCII sprite with its top-left at (x, y); clipped to the display."""
    for r, line in enumerate(sprite):
        for c, ch in enumerate(line):
            if ch == "#":
                px, py = x + c, y + r
                if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                    canvas[py][px] = 1


def _erase(canvas, x, y, w, h):
    for py in range(y, y + h):
        for px in range(x, x + w):
            if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                canvas[py][px] = 0


def _to_frame(canvas):
    out = []
    for row in canvas:
        v = 0
        for c, bit in enumerate(row):
            if bit:
                v |= 1 << (WIDTH - 1 - c)
        out.append(v)
    return out


# ── sprites ────────────────────────────────────────────────────────────────
# Kitten facing right, 10 wide x 6 tall. Two walk poses, a crouch and a sit.

KITTEN_WALK_A = [
    "......#.#.",
    "#.....###.",
    "#########.",
    ".########.",
    "..#.#..#.#",
    "..#.#..#.#",
]
KITTEN_WALK_B = [
    "......#.#.",
    "......###.",
    "#########.",
    "#########.",
    "...##..##.",
    "...##..##.",
]
# Pounce wind-up: body low, legs tucked away, tail wagging between two heights.
KITTEN_CROUCH_A = [
    "..........",
    "......#.#.",
    "#.....###.",
    "##########",
    ".#########",
    "..........",
]
KITTEN_CROUCH_B = [
    "#.........",
    "#.....#.#.",
    "#.....###.",
    "##########",
    ".#########",
    "..........",
]
KITTEN_SIT = [
    "..#.#.",
    "..###.",
    "..###.",
    ".####.",
    "#####.",
    "#####.",
]
KITTEN_SIT_LOOK_UP = [
    "..#.#.",
    "..###.",
    "...##.",
    ".####.",
    "#####.",
    "#####.",
]
KITTEN_SLEEP_A = [
    "..........",
    "..#.#.....",
    ".#######..",
    "#########.",
    "#########.",
]
KITTEN_SLEEP_B = [
    "..#.#.....",
    ".#######..",
    "#########.",
    "#########.",
    "..........",
]

BALL = ["##", "##"]
BIRD_UP = [".#.#.", "#####", "..#.."]
BIRD_DOWN = ["..#..", "#####", ".#.#."]
Z_SMALL = ["###", ".#.", "###"]
Z_TINY = ["##", "#."]
HEART_SMALL = [".#.#.", "#####", ".###.", "..#.."]
HEART_BIG = ["..##.##..", ".#######.", ".#######.", "..#####..", "...###...", "....#...."]
HEART_TINY = [".#.#", "####", ".##.", "..#."]
EXCLAIM = ["#", "#", "#", ".", "#"]
QUESTION = ["##.", "..#", ".#.", "...", ".#."]


# ── animations ─────────────────────────────────────────────────────────────

def _chase_ball():
    frames = []
    for t in range(0, 70):
        cv = _blank()
        walking = t < 28
        kx = -9 + int(t * 0.7) if walking else -9 + int(28 * 0.7)
        ball_x = 14 + int(min(t, 28) * 0.25)
        bounce = abs(math.sin(math.pi * t / 7.0))
        ball_y = 5 - int(round(bounce * 4))
        if t < 28:
            sprite = KITTEN_WALK_A if (t // 3) % 2 == 0 else KITTEN_WALK_B
            _blit(cv, sprite, kx, 1)
            _blit(cv, BALL, ball_x, ball_y)
        elif t < 42:
            # Crouch with a wagging tail while the ball keeps bouncing; "!" appears.
            sprite = KITTEN_CROUCH_A if (t // 2) % 2 == 0 else KITTEN_CROUCH_B
            _blit(cv, sprite, kx, 1)
            _blit(cv, BALL, ball_x, ball_y)
            if t >= 32:
                _blit(cv, EXCLAIM, kx + 8, 0)
        elif t < 50:
            # Pounce: kitten leaps forward onto the ball.
            _blit(cv, KITTEN_WALK_A, kx + (t - 41), 1)
        else:
            # Caught it: kitten sits, a heart floats up.
            _blit(cv, KITTEN_SIT, ball_x - 4, 1)
            hy = max(0, 3 - (t - 50) // 3)
            _blit(cv, HEART_TINY, ball_x - 10, hy)
        frames.append(_to_frame(cv))
    return frames


def _chase_bird():
    frames = []
    for t in range(0, 72):
        cv = _blank()
        flap = BIRD_UP if (t // 2) % 2 == 0 else BIRD_DOWN
        if t < 40:
            kx = -9 + int(t * 0.45)
            bx = 8 + int(t * 0.35)
            by = 1 + int(round(1.0 * math.sin(t / 3.0)))
            _blit(cv, KITTEN_WALK_A if (t // 3) % 2 == 0 else KITTEN_WALK_B, kx, 1)
            _blit(cv, flap, bx, by)
        elif t < 56:
            # Bird speeds off the right edge, kitten stops and watches it go.
            kx = -9 + int(40 * 0.45)
            bx = 8 + int(40 * 0.35) + (t - 40) * 2
            _blit(cv, KITTEN_SIT, kx + 2, 1)
            _blit(cv, flap, bx, max(0, 2 - (t - 40) // 4))
        else:
            # Kitten looks up at the empty sky, "?" appears, then a small shrug.
            kx = -9 + int(40 * 0.45)
            _blit(cv, KITTEN_SIT_LOOK_UP if (t // 4) % 2 == 0 else KITTEN_SIT, kx + 2, 1)
            if t >= 60:
                _blit(cv, QUESTION, kx + 9, 0)
        frames.append(_to_frame(cv))
    return frames


def _catnap():
    frames = []
    for t in range(0, 60):
        cv = _blank()
        breathe = (t // 6) % 2
        _blit(cv, KITTEN_SLEEP_A if breathe == 0 else KITTEN_SLEEP_B, 3, 2 if breathe == 0 else 1)
        # Three z's drift up and to the right, staggered, growing as they rise.
        for k in range(3):
            phase = (t + k * 8) % 24
            zy = 4 - phase // 5
            zx = 14 + phase // 3 + k
            if zy < 0 or zx > WIDTH - 1:
                continue
            _blit(cv, Z_SMALL if phase > 8 else Z_TINY, zx, zy)
        frames.append(_to_frame(cv))
    return frames


def _fish():
    frames = []
    fish_a = [
        "..##....",
        ".#####.#",
        "########",
        ".#####.#",
        "..##....",
    ]
    fish_b = [
        "..##....",
        ".#####..",
        "########",
        ".#####..",
        "..##..#.",
    ]
    for t in range(0, 60):
        cv = _blank()
        x = -9 + int(t * 0.6)
        y = 1 + int(round(0.9 * math.sin(t / 4.0)))
        spr = fish_a if (t // 3) % 2 == 0 else fish_b
        _blit(cv, [line[::-1] for line in spr], x, y)   # flipped: head on the right, tail trailing
        # A bubble rises from the fish's mouth now and then.
        for k in range(2):
            phase = (t + k * 10) % 20
            by = 5 - phase // 4
            if by >= 0 and x + 9 < WIDTH:
                _blit(cv, ["#"], x + 9 + (phase // 8), by)
        frames.append(_to_frame(cv))
    return frames


def _heartbeat():
    frames = []
    seq = [HEART_TINY, HEART_SMALL, HEART_BIG, HEART_SMALL, HEART_TINY, HEART_TINY]
    for beat in range(4):
        for spr in seq:
            for _ in range(2):
                cv = _blank()
                w = max(len(line) for line in spr)
                _blit(cv, spr, (WIDTH - w) // 2, (HEIGHT - len(spr)) // 2)
                frames.append(_to_frame(cv))
    return frames


def _display_test():
    """Border plus an X. A first check that all 7 rows and 26 columns light."""
    a = _blank()
    for c in range(WIDTH):
        a[0][c] = a[HEIGHT - 1][c] = 1
    for r in range(HEIGHT):
        a[r][0] = a[r][WIDTH - 1] = 1
    b = _blank()
    for r in range(HEIGHT):
        b[r][r * 3] = 1
        b[r][WIDTH - 1 - r * 3] = 1
    return [_to_frame(a)] * 6 + [_to_frame(b)] * 6


PRESETS = [
    {"id": "chase_ball", "name": "Kitten chases a ball", "build": _chase_ball},
    {"id": "chase_bird", "name": "Kitten watches a bird", "build": _chase_bird},
    {"id": "catnap", "name": "Catnap", "build": _catnap},
    {"id": "fish", "name": "Fish swimming", "build": _fish},
    {"id": "heartbeat", "name": "Heartbeat", "build": _heartbeat},
    {"id": "display_test", "name": "Display test (border and X)", "build": _display_test},
]


def list_presets():
    out = []
    for p in PRESETS:
        frames = p["build"]()
        out.append({"id": p["id"], "name": p["name"], "frames": frames,
                    "interval": DEFAULT_INTERVAL, "count": len(frames)})
    return out


def validate_frames(frames):
    """Frames must be 1..MAX_FRAMES lists of exactly 7 ints in 0..2^26-1."""
    if not isinstance(frames, list) or not (1 <= len(frames) <= MAX_FRAMES):
        return False
    for f in frames:
        if not (isinstance(f, list) and len(f) == HEIGHT):
            return False
        for v in f:
            if not isinstance(v, int) or isinstance(v, bool) or not (0 <= v < (1 << WIDTH)):
                return False
    return True


def render_ascii(frame):
    return ["".join("#" if (row >> (WIDTH - 1 - c)) & 1 else "." for c in range(WIDTH)) for row in frame]
