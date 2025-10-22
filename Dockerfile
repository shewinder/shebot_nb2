FROM python:3.9-slim

WORKDIR /app


COPY requirements.txt /app
RUN pip install -r requirements.txt -i https://mirrors.aliyun.com/pypi/simple/

COPY ./res /app/res

# 复制文件
COPY run.py /app
COPY ./hoshino /app/hoshino

# 软链接.env.prod
RUN ln -s /app/conf/.env.prod /app/.env.prod


# 运行
CMD [ "python", "run.py" ]