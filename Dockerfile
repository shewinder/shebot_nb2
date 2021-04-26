FROM python:3.8.0-slim

# 工作目录
WORKDIR /app

# 复制文件
COPY . /app

# 安装依赖
RUN apt update -y
RUN apt upgrade -y
RUN apt install libgl1-mesa-glx -y
RUN apt install libglib2.0-dev -y
RUN  pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 运行
CMD [ "python", 'run.py' ]