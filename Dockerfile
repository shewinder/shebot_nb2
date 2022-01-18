FROM python:3.8.0-slim

WORKDIR /app

RUN  sed -i s/deb.debian.org/mirrors.aliyun.com/g /etc/apt/sources.list \
    && apt update -y \
    && apt install libgl1-mesa-glx -y \
    && apt install libglib2.0-dev -y

COPY requirements.txt /app
RUN pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

EXPOSE 9000

COPY ./res /app/res

# 复制文件
COPY run.py /app
COPY ./hoshino /app/hoshino

# 运行
CMD [ "python", "run.py" ]