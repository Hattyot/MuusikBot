FROM ubuntu:18.04

ENV LANG='en_US.UTF-8' LANGUAGE='en_US:en' LC_ALL='en_US.UTF-8'

RUN apt-get update \
    && apt-get install -y --no-install-recommends tzdata curl ca-certificates fontconfig locales \
    && echo "en_US.UTF-8 UTF-8" >> /etc/locale.gen \
    && locale-gen en_US.UTF-8 \
    && apt-get install software-properties-common -y \
    && add-apt-repository -y ppa:deadsnakes \
    && apt-get install python3.8 -y \
    && apt-get install python3-pip -y \
    && apt-get install python3.8-dev -y \
    && curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py \
    && python3.8 get-pip.py

RUN pip3.8 install --upgrade pip requests

WORKDIR /muusikbot

COPY requirements.txt .

RUN python3.8 -m pip install -r requirements.txt

COPY /cogs ./cogs
COPY /modules ./modules
COPY bot.py .
COPY config.py .

ENV IN_DOCKER Yes