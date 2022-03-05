from enum import Enum
import random
from PIL import Image, ImageDraw, ImageFont

if __name__ == '__main__':
    from pathlib import Path
    font_dir = Path('/mnt/shebot_nb2/res/fonts')
    res_dir = Path('/mnt/shebot_nb2/res/wordle')
    FONT = ImageFont.truetype('/mnt/shebot_nb2/res/fonts/font-bold.ttf', size=50)
    wordle_dir = Path('/mnt/shebot_nb2/res/wordle')
    possible_words_path = wordle_dir.joinpath('possible_words.txt')
    allowed_words_path = wordle_dir.joinpath('allowed_words.txt')
else:
    from hoshino import font_dir, res_dir
    FONT = ImageFont.truetype(font_dir.joinpath('font-bold.ttf').as_posix(), size=50)
    wordle_dir = res_dir.joinpath('wordle')
    possible_words_path = wordle_dir.joinpath('possible_words.txt')
    allowed_words_path = wordle_dir.joinpath('allowed_words.txt')


Color = {
    "green": (106, 170, 100),
    "yellow": (201, 180, 88),
    "grey": (120, 124, 126),
    "side": (211, 214, 218),
    "font": (255, 255, 255),
}
class ColorEnum(Enum):
    green = (106, 170, 100)
    yellow = (201, 180, 88)
    grey = (120, 124, 126)
    side = (211, 214, 218)
    font = (255, 255, 255)
    white = (255, 255, 255)

try:
    with open(
        possible_words_path,
        "r",
        encoding="utf-8",
    ) as f:
        possible_words = f.read().split("\n")
        f.close()
    with open(
        allowed_words_path,
        "r",
        encoding="utf-8",
    ) as f:
        allowed_words = f.read().split("\n")
        f.close()
except FileNotFoundError:
    possible_words = []
    allowed_words = []

class Game:
    def __init__(self):
        self.answer: str = self.get_word()
        self.image: Image.Image = self.init_image()
        self.cnt: int = 0
        self.message: str = ""
        self.used: set = set()
        self.draw_keyboard()

    def check_word(self, word: str) -> bool:
        if word not in allowed_words:
            self.message = "您确定这是一个单词？"
            return False
        elif word == self.answer:
            self.draw_word(word)
            self.cnt += 1
            return True
        else:
            for ch in word:
                self.used.add(ch.upper())
            self.draw_word(word)
            self.draw_keyboard()
            self.cnt += 1
            self.message = ""
            return False

    @staticmethod
    def get_word() -> str:
        return random.choice(possible_words)

    @staticmethod
    def get_margin(width: int, n: int, card_size: int, sep: int) -> int:
        return int((width - sep * (n-1) - card_size * n) / 2)

    @staticmethod
    def draw_card(a: str, size: int, bg_color, font_color) -> Image.Image:
        f = ImageFont.truetype(font_dir.joinpath('font-bold.ttf').as_posix(), size=int(size/7*5))
        w, h = f.getsize(a)
        card = Image.new("RGB", (size, size), bg_color)
        draw = ImageDraw.Draw(card)
        draw.text(((size-w)/2, (size-h)/2), a, fill=font_color, font=f)
        return card

    def draw_word(self, word: str):
        image = self.image
        width = image.width
        n = len(word)
        card_size = 70
        sep = 10
        margin = int((width - sep * (n-1) - card_size * n) / 2)
        y = 20 + self.cnt * (sep + card_size)
        for i in range(n):
            if word[i] == self.answer[i]:
                color = ColorEnum.green.value
            elif word[i] in self.answer:
                color = ColorEnum.yellow.value
            else:
                color = ColorEnum.grey.value
            card = self.draw_card(word[i].upper(), card_size, color, ColorEnum.white.value)
            image.paste(card, (margin + sep*i + card_size*i, y))
        self.image = image

    def draw_keyboard(self):
        image = self.image
        width = image.width
        def draw_line(s: str, y: int, card_size: int):
            sep = 8
            margin = int((width - sep * (len(s)-1) - card_size * len(s)) / 2)
            for i, ch in enumerate(s):
                if ch not in self.used:
                    color = ColorEnum.side.value
                else:
                    if ch in self.answer.upper():
                        color = ColorEnum.yellow.value
                    else:
                        color = ColorEnum.grey.value

                card = self.draw_card(ch, card_size, color, ColorEnum.white.value)
                image.paste(card, (margin + sep*i + card_size*i, y))
        ys = [520 + i*45 for i in range(3)]
        draw_line('ABCDEFGHIJ', ys[0], 35)
        draw_line('KLMNOPQRST', ys[1], 35)
        draw_line('UVWXYZ', ys[2], 35)
        
        self.image = image


    @staticmethod
    def init_image() -> Image.Image:
        image = Image.new("RGB", (430, 670), "white")
        width = image.width
        sep, card_size = 10, 70
        margin = Game.get_margin(width, 5, card_size, sep)
        draw = ImageDraw.Draw(image)
        def draw_row(y: int):
            for i in range(5):
                draw.rectangle(
                    (margin + sep*i + card_size*i, y, margin + sep*i + card_size*i + card_size, y + card_size), 
                    fill=ColorEnum.side.value,
                    outline=ColorEnum.font.value)
        y = 20
        for i in range(6):
            draw_row(y + i*80)
        return image

if __name__ == "__main__":
    import time
    gm = Game()
    t1 = time.time()
    gm.check_word('hello')
    gm.draw_keyboard()
    gm.check_word('world')
    gm.draw_keyboard()
    gm.check_word('apple')
    gm.draw_keyboard()
    print(gm.used)
    gm.draw_keyboard()
    print("用时:", time.time() - t1)
    gm.image.save(Path(__file__).parent.joinpath("test.png"))

