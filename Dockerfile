# 3.12 vastgepind: plants.py gebruikt de cgi-module, die in Python 3.13 verwijderd is.
FROM python:3.12-slim

# tzdata nodig zodat TZ=Europe/Amsterdam echt werkt (de 09:00-digest hangt ervan af)
RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata \
 && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    AQUARIUM_DATA=/data

WORKDIR /app
COPY plants.py icon.png manifest.json ./

RUN mkdir -p /data
VOLUME /data
EXPOSE 8377

HEALTHCHECK --interval=60s --timeout=5s --start-period=15s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8377/', timeout=3)"

CMD ["python", "plants.py"]
