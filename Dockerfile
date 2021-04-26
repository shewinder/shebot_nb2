FROM python:3.8.0-slim

# 工作目录
WORKDIR /app

# 复制文件
COPY . /app

# 安装依赖
RUN sed -i s/deb.debian.org/mirrors.aliyun.com/g /etc/apt/sources.list
RUN apt update -y
#RUN apt upgrade -y
RUN apt install libgl1-mesa-glx -y
RUN apt install libglib2.0-dev -y
RUN pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

# 端口
EXPOSE 9000

# 数据卷
VOLUME [ "/data" ]

# 运行
CMD [ "python", "run.py" ]