FROM harbor.fsk.ru/docker/python:3.12-bullseye

WORKDIR /app

RUN apt-get update

COPY requirements.txt ./
RUN pip install --upgrade pip \
    && pip install -r requirements.txt --no-cache-dir

COPY . .

RUN chmod +x ./scripts/entrypoint_api.sh

EXPOSE 8090

CMD ["./scripts/entrypoint_api.sh"]
