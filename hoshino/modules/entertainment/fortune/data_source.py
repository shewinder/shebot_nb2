from os import path

from PIL import Image, ImageDraw, ImageFont

from hoshino.util.sutil import add_text_to_img

def vertical(str_):
    l = [s for s in str_]
    return '\n'.join(l)

def decrement(text):
    length = len(text)
    result = []
    cardinality = 9
    if length > 4*cardinality:
        return False
    numbers_of_slice = length//cardinality + 1
    # Optimize for two columns
    space = ' '
    if numbers_of_slice == 2:
        if length % 2 == 0:
            # even number
            fill = space * int(cardinality - length / 2)
            return [text[:int(length / 2)] + fill, fill + text[int(length / 2):]]
        else:
            # odd number
            fill = space * int(cardinality - (length + 1) / 2)
            return [text[:int((length + 1) / 2)] + fill, fill + space + text[int((length + 1) / 2):]]
    for i in range(0, numbers_of_slice):
        if i == numbers_of_slice - 1 or numbers_of_slice == 1: # 最后一行
            result.append(text[i * cardinality:])
        else:
            result.append(text[i * cardinality:(i + 1) * cardinality])
    return result

def drawing(img: Image.Image, title: str, text: str, title_font: str, text_font: str) -> Image.Image:
    # Draw title
    font_size = 45
    color = '#F5F5F5'
    center = (140, 99)
    font = ImageFont.truetype(str(title_font), font_size)
    font_length = font.getsize(title)
    pos = (center[0]-font_length[0]/2, center[1]-font_length[1]/2)
    add_text_to_img(img, title, font_size, font=title_font, textfill=color, position=pos)

    # Text rendering
    font_size = 25
    color = '#323232'
    center = [140, 297]
    font = ImageFont.truetype(text_font, font_size)

    texts = decrement(text)
    columns = len(texts)
    for i, text in enumerate(texts):
        font_height = len(text) * (font_size + 4)
        text = vertical(text) #将文字改成竖排
        x = int(center[0] + (columns - 2)*font_size/2 +
            (columns - 1)*4 - i*(font_size + 4))
        y = int(center[1] - font_height / 2)
        add_text_to_img(img, text, textsize=font_size, font=text_font, textfill=color, position=(x, y))
    return img