FROM alpine:latest

COPY . /root

WORKDIR /root
RUN apk add --no-cache python3 gcc python3-dev jpeg-dev zlib-dev musl-dev linux-headers cmd:pip3 ffmpeg
RUN pip3 install -r requirements.txt --no-cache-dir

WORKDIR /root/tapkofon

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8888"]